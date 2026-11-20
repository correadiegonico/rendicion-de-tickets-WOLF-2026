import streamlit as st
import pandas as pd
from datetime import date
import gspread
from google.oauth2.service_account import Credentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import streamlit.components.v1 as components

st.set_page_config(page_title="Rendición de Gastos - Wolf Internacional", page_icon="🐺", layout="wide")

st.title("🐺 Wolf Internacional - Carga Múltiple de Rendiciones")
st.markdown("Herramienta móvil para registrar comprobantes de viaje.")

# Script ligero para que al presionar Enter en los campos de texto pase automáticamente al siguiente cuadro
components.html(
    """
    <script>
    const doc = window.parent.document;
    doc.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && e.target.tagName === 'INPUT') {
            const inputs = Array.from(doc.querySelectorAll('input[type="text"]'));
            const idx = inputs.indexOf(e.target);
            if (idx > -1 && idx < inputs.length - 1) {
                e.preventDefault();
                inputs[idx + 1].focus();
            }
        }
    });
    </script>
    """,
    height=0,
)

# ID de tu Google Sheet
SPREADSHEET_ID = "1TqAAUw9K_Arn6aDTAZJ4sXciSe9FpO99cMXKenY_AcU"

MONEDAS = [
    "Pesos ARS",
    "USD",
    "Reales"
]

OPCIONES_DINERO_DISPONIBLE = [
    "Viático",
    "Seguro de hotel",
    "No recibe"
]

TIPOS_GASTO = [
    "🎢 Actividades",
    "🍽️ Alimentos",
    "🏷️ Alimentos de Excursión",
    "⛽ Combustibles",
    "🏷️ Costo de excursión (telesilla, entradas, excursiones)",
    "🏦 Financiaciones",
    "🏨 Hotelería",
    "🏷️ Luz y agua",
    "🏷️ Merchandising",
    "🛡️ Seguros",
    "🚌 Transporte",
    "🧳 Viáticos",
    "📦 Otros"
]

def recalcular_tabla(df):
    df = df.copy()
    for idx, row in df.iterrows():
        moneda = row.get("Moneda") or "Pesos ARS"
        monto_ticket = float(row.get("Monto") or 0.0)
        cotizacion = float(row.get("Conversión") or 1.0)

        if moneda == "Pesos ARS":
            cotizacion = 1.0
            df.at[idx, "Conversión"] = 1.0

        df.at[idx, "Monto en pesos ARS"] = round(monto_ticket * cotizacion, 2)
    return df

def formatear_observacion_con_moneda(row, dinero_disp):
    moneda = row.get("Moneda") or "Pesos ARS"
    monto_ticket = float(row.get("Monto") or 0.0)
    cotizacion = float(row.get("Conversión") or 1.0)
    obs_usuario = str(row.get("Observaciones") or "").strip()

    partes = []
    if dinero_disp["tipo"] == "Seguro de hotel" and dinero_disp.get("pasajero"):
        partes.append(f"[Seguro Hotel - Pax: {dinero_disp['pasajero']}]")
    if moneda != "Pesos ARS":
        partes.append(f"[{moneda} {monto_ticket:,.2f} x Cotiz. {cotizacion:,.2f}]")
    if obs_usuario:
        partes.append(obs_usuario)

    return " ".join(partes).strip()

def obtener_cliente_gspread():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def buscar_hoja_por_nombre(spreadsheet, nombre_buscado):
    for ws in spreadsheet.worksheets():
        if ws.title.strip().lower() == nombre_buscado.strip().lower():
            return ws
    return None

def guardar_en_sheets(coordinador, coche, destino, dinero_disp, df_gastos, archivos_tickets):
    try:
        client = obtener_cliente_gspread()
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        
        sheet_rendiciones = buscar_hoja_por_nombre(spreadsheet, "rendiciones") or spreadsheet.sheet1

        enlace_comprobante = (
            f"Enviado por mail ({', '.join([f.name for f in archivos_tickets])})"
            if archivos_tickets else "Sin adjunto"
        )

        for idx, row in df_gastos.iterrows():
            numero_orden = str(idx + 1)
            monto_final_ars = float(row["Monto en pesos ARS"])
            observaciones_final = formatear_observacion_con_moneda(row, dinero_disp)
            viatico_columna_c = float(dinero_disp["total_ars"]) if idx == 0 else 0.0

            # Mapeo de columnas A hasta L en "rendiciones":
            # A: Destino | B: Coordinador | C: Viático (Total ARS) | D: Fecha | E: Orden TK | F: Factura/TK
            # G: Monto en pesos ARS | H: Enlace | I: (Vacío) | J: Abona con viático | K: Observaciones | L: Tipo de gasto
            sheet_rendiciones.append_row([
                destino,
                f"{coordinador} (Coche: {coche})" if coche else coordinador,
                viatico_columna_c,
                str(row["Fecha de compra"]),
                numero_orden,
                str(row["N° Factura / TK"]),
                monto_final_ars,
                enlace_comprobante,
                "",
                str(row["Abona con viático"]),
                observaciones_final,
                str(row.get("Tipo de gasto", ""))
            ])

        return True
    except Exception as e:
        st.error("Error al guardar en Google Sheets:")
        st.exception(e)
        return False

def enviar_notificacion_email(coordinador, coche, destino, dinero_disp, df_gastos, archivos_tickets, archivos_dinero):
    try:
        sender_email = st.secrets["email"]["sender_email"]
        sender_password = st.secrets["email"]["sender_password"]
        receiver_email = st.secrets["email"]["receiver_email"]

        total_ars = float(df_gastos["Monto en pesos ARS"].sum())
        filas_html = ""

        for idx, r in df_gastos.iterrows():
            num_tk = idx + 1
            monto_ticket = float(r.get("Monto") or 0.0)
            moneda = r.get("Moneda") or "Pesos ARS"
            cotiz = float(r.get("Conversión") or 1.0)
            monto_ars = float(r.get("Monto en pesos ARS") or 0.0)

            tipo_gasto = r.get("Tipo de gasto", "-")
            obs = formatear_observacion_con_moneda(r, dinero_disp) or "-"
            info_cotiz = f"{cotiz:,.2f}" if moneda != "Pesos ARS" else "-"

            filas_html += (
                f"<tr>"
                f"<td>{num_tk}</td>"
                f"<td>{r['Fecha de compra']}</td>"
                f"<td>{r['N° Factura / TK']}</td>"
                f"<td style='text-align:right'>${monto_ticket:,.2f}</td>"
                f"<td>{moneda}</td>"
                f"<td style='text-align:right'>{info_cotiz}</td>"
                f"<td style='text-align:right'><b>${monto_ars:,.2f}</b></td>"
                f"<td>{r['Abona con viático']}</td>"
                f"<td>{tipo_gasto}</td>"
                f"<td>{obs}</td>"
                f"</tr>"
            )

        todos_los_archivos = list(archivos_tickets or []) + list(archivos_dinero or [])
        nombres_archivos = ", ".join([f.name for f in todos_los_archivos]) if todos_los_archivos else "Ninguno"

        # Construcción del cuadro superior para "Dinero disponible para gastos"
        if dinero_disp["tipo"] == "No recibe":
            pasajero_celda = "-"
            moneda_celda = "-"
            monto_celda = "$0.00"
            cotiz_celda = "-"
            total_disp_celda = "$0.00"
        else:
            pasajero_celda = (
                dinero_disp["pasajero"]
                if dinero_disp["tipo"] == "Seguro de hotel" and dinero_disp.get("pasajero")
                else "-"
            )
            moneda_celda = dinero_disp["moneda"]
            monto_celda = f"${dinero_disp['monto']:,.2f}"
            cotiz_celda = f"{dinero_disp['cotizacion']:,.2f}" if dinero_disp["moneda"] != "Pesos ARS" else "-"
            total_disp_celda = f"${dinero_disp['total_ars']:,.2f}"

        tabla_dinero_html = f"""
        <h3 style="margin-bottom:6px;color:#1a3c6e;">Dinero disponible para gastos</h3>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;margin-bottom:18px;">
            <tr style="background:#1a3c6e;color:white;">
                <th>Proviene de...</th>
                <th>Pasajero (Seguro Hotel)</th>
                <th>Tipo de Moneda</th>
                <th>Monto</th>
                <th>Cotización pesos ARS</th>
                <th>Total (ARS)</th>
            </tr>
            <tr>
                <td>{dinero_disp['tipo']}</td>
                <td>{pasajero_celda}</td>
                <td>{moneda_celda}</td>
                <td style="text-align:right">{monto_celda}</td>
                <td style="text-align:right">{cotiz_celda}</td>
                <td style="text-align:right"><b>{total_disp_celda}</b></td>
            </tr>
            <tr style="font-weight:bold;background:#f0f0f0;">
                <td colspan="5" style="text-align:right">TOTAL DINERO DISPONIBLE (ARS)</td>
                <td style="text-align:right">{total_disp_celda}</td>
            </tr>
        </table>
        """

        html_body = f"""
        <h2>Nueva Rendición Recibida - Wolf Internacional</h2>
        <p><b>Coordinador:</b> {coordinador}</p>
        <p><b>Coche:</b> {coche} | <b>Destino:</b> {destino}</p>
        <p><b>Archivos adjuntos:</b> {nombres_archivos}</p>
        
        {tabla_dinero_html}

        <h3 style="margin-bottom:6px;color:#1a3c6e;">Detalle de Comprobantes Rendidos</h3>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
            <tr style="background:#1a3c6e;color:white;">
                <th>N° TK</th>
                <th>Fecha</th>
                <th>Factura/TK</th>
                <th>Monto Ticket</th>
                <th>Moneda</th>
                <th>Conversión</th>
                <th>Monto en pesos ARS</th>
                <th>Viático</th>
                <th>Tipo de Gasto</th>
                <th>Observaciones</th>
            </tr>
            {filas_html}
            <tr style="font-weight:bold;background:#f0f0f0;">
                <td colspan="6" style="text-align:right">TOTAL GENERAL RENDIDO (ARS)</td>
                <td style="text-align:right">${total_ars:,.2f}</td>
                <td colspan="3"></td>
            </tr>
        </table>
        """

        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"[Rendición] {coordinador} | {destino} | ${total_ars:,.2f} ARS"
        msg["From"] = sender_email
        
        # Lista completa de destinatarios (incluye correadwolf@gmail.com, fbocchi@lantier.com.ar y carolapou@gmail.com)
        destinatarios = list(dict.fromkeys([
            receiver_email,
            "correadwolf@gmail.com",
            "fbocchi@lantier.com.ar",
            "carolapou@gmail.com"
        ]))
        msg["To"] = ", ".join(destinatarios)

        cuerpo_html = MIMEMultipart("alternative")
        cuerpo_html.attach(MIMEText(html_body, "html"))
        msg.attach(cuerpo_html)

        for archivo in todos_los_archivos:
            adjunto = MIMEApplication(archivo.getvalue(), Name=archivo.name)
            adjunto["Content-Disposition"] = f'attachment; filename="{archivo.name}"'
            msg.attach(adjunto)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, destinatarios, msg.as_string())
        return True
    except Exception as e:
        st.warning(f"No se pudo enviar la notificación por correo: {e}")
        return False

# --- BLOQUE 1 ---
st.subheader("1. Datos Generales del Viaje")
col1, col2, col3 = st.columns(3)
with col1:
    coordinador = st.text_input("Nombre y Apellido del Coordinador")
with col2:
    coche = st.text_input("N° de Coche / Unidad")
with col3:
    destino = st.text_input("Destino principal del viaje")

st.markdown("---")

# --- BLOQUE 2 ---
st.subheader("2. Dinero disponible para gastos")
d_col1, d_col2, d_col3, d_col4, d_col5 = st.columns([1.4, 1.2, 1.2, 1.2, 1.2])

with d_col1:
    tipo_dinero = st.selectbox("Proviene de...", OPCIONES_DINERO_DISPONIBLE)

deshabilitar_montos = (tipo_dinero == "No recibe")

with d_col2:
    moneda_dinero = st.selectbox("Tipo de moneda", MONEDAS, disabled=deshabilitar_montos)

with d_col3:
    monto_dinero = st.number_input(
        "Monto",
        min_value=0.0,
        step=100.0,
        format="%.2f",
        disabled=deshabilitar_montos
    )

with d_col4:
    cotizacion_dinero = st.number_input(
        "Cotización pesos ARS",
        min_value=0.0,
        value=1.0,
        step=10.0,
        format="%.2f",
        disabled=deshabilitar_montos or (moneda_dinero == "Pesos ARS")
    )

if deshabilitar_montos:
    total_dinero_ars = 0.0
    cotizacion_efectiva = 1.0
elif moneda_dinero == "Pesos ARS":
    cotizacion_efectiva = 1.0
    total_dinero_ars = round(monto_dinero, 2)
else:
    cotizacion_efectiva = cotizacion_dinero
    total_dinero_ars = round(monto_dinero * cotizacion_dinero, 2)

with d_col5:
    st.number_input(
        "Total (ARS)",
        value=total_dinero_ars,
        format="%.2f",
        disabled=True
    )

pasajero_seguro = ""
if tipo_dinero == "Seguro de hotel":
    pasajero_seguro = st.text_input(
        "Nombre y Apellido del Pasajero (correspondiente al seguro de hotel)",
        placeholder="Ej: Juan Pérez"
    )

archivos_dinero_disp = st.file_uploader(
    "Adjuntar comprobante de recepción de viático o transferencia de cambio (USD a ARS)",
    type=["png", "jpg", "jpeg", "pdf"],
    accept_multiple_files=True,
    key="uploader_dinero_disponible",
    disabled=deshabilitar_montos
)

dinero_disponible_data = {
    "tipo": tipo_dinero,
    "pasajero": pasajero_seguro.strip(),
    "moneda": moneda_dinero,
    "monto": monto_dinero,
    "cotizacion": cotizacion_efectiva,
    "total_ars": total_dinero_ars
}

st.markdown("---")

# --- BLOQUE 3 ---
st.subheader("3. Detalle de Comprobantes (Múltiples Gastos)")

if "df_gastos" not in st.session_state:
    st.session_state.df_gastos = pd.DataFrame([{
        "Fecha de compra": date.today(),
        "N° Factura / TK": "",
        "Monto": 0.0,
        "Moneda": "Pesos ARS",
        "Conversión": 1.0,
        "Monto en pesos ARS": 0.0,
        "Abona con viático": "Sí",
        "Tipo de gasto": "🍽️ Alimentos",
        "Observaciones": ""
    }])

df_editado = st.data_editor(
    st.session_state.df_gastos,
    num_rows="dynamic",
    column_config={
        "Fecha de compra": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY", default=date.today(), required=True),
        "N° Factura / TK": st.column_config.TextColumn("N° Factura / Proveedor", default="", required=True),
        "Monto": st.column_config.NumberColumn("Monto", min_value=0.0, format="$ %.2f", default=0.0, required=True),
        "Moneda": st.column_config.SelectboxColumn("Moneda", options=MONEDAS, default="Pesos ARS", required=True),
        "Conversión": st.column_config.NumberColumn("Conversión", min_value=0.0, format="%.2f", default=1.0, required=False),
        "Monto en pesos ARS": st.column_config.NumberColumn("Monto en pesos ARS", min_value=0.0, format="$ %.2f", default=0.0),
        "Abona con viático": st.column_config.SelectboxColumn("¿Abona con viático?", options=["Sí", "No"], default="Sí", required=True),
        "Tipo de gasto": st.column_config.SelectboxColumn("🏷️ ¿Qué tipo de gasto es?", options=TIPOS_GASTO, default="🍽️ Alimentos", required=True),
        "Observaciones": st.column_config.TextColumn("Observaciones", default="", required=False)
    },
    disabled=["Monto en pesos ARS"],
    hide_index=True,
    use_container_width=True
)

df_recalculado = recalcular_tabla(df_editado)
if not df_recalculado.equals(st.session_state.df_gastos):
    st.session_state.df_gastos = df_recalculado
    st.rerun()

st.markdown("---")

# --- BLOQUE 4 ---
st.subheader("4. Adjuntar Comprobantes de Gastos (Obligatorio)")
archivos_adjuntos = st.file_uploader(
    "Sube fotos o PDFs de los tickets",
    type=["png", "jpg", "jpeg", "pdf"],
    accept_multiple_files=True,
    key="uploader_tickets_gastos"
)

enviado = st.button("🚀 Enviar Rendición Completa", type="primary")

if enviado:
    df_final = st.session_state.df_gastos
    if not coordinador or not archivos_adjuntos or df_final.empty:
        st.error("⚠️ Por favor completa el nombre del coordinador y asegúrate de adjuntar al menos un comprobante de gasto.")
    elif tipo_dinero == "Seguro de hotel" and not pasajero_seguro.strip():
        st.error("⚠️ Seleccionaste 'Seguro de hotel'. Por favor ingresa el Nombre y Apellido del Pasajero.")
    else:
        if guardar_en_sheets(coordinador, coche, destino, dinero_disponible_data, df_final, archivos_adjuntos):
            enviar_notificacion_email(coordinador, coche, destino, dinero_disponible_data, df_final, archivos_adjuntos, archivos_dinero_disp)
            st.success(f"¡Rendición procesada con éxito para **{coordinador}**!")
            st.dataframe(df_final, use_container_width=True)
