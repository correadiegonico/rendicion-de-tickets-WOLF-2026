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

# Script ligero para que al presionar Enter en los campos de texto superiores pase automáticamente al siguiente cuadro
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

def guardar_en_sheets(coordinador, coche, destino, df_gastos, archivos):
    try:
        client = obtener_cliente_gspread()
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1

        enlace_comprobante = (
            f"Enviado por mail ({', '.join([f.name for f in archivos])})"
            if archivos else "Sin adjunto"
        )

        for idx, row in df_gastos.iterrows():
            numero_orden = str(idx + 1)
            
            # Mapeo de columnas A hasta K (Columna H queda vacía para no desfasar las siguientes):
            # A: Destino | B: Coordinador | C: Fecha | D: Orden TK | E: Factura/TK | F: Monto
            # G: Enlace | H: (Vacío) | I: Viático | J: Observaciones | K: Tipo de gasto
            sheet.append_row([
                destino,
                f"{coordinador} (Coche: {coche})" if coche else coordinador,
                str(row["Fecha de compra"]),
                numero_orden,
                str(row["N° Factura / TK"]),
                float(row["Monto ($)"]),
                enlace_comprobante,
                "",
                str(row["Abona con viático"]),
                str(row.get("Observaciones", "")),
                str(row.get("Tipo de gasto", ""))
            ])
        return True
    except Exception as e:
        st.error("Error al guardar en Google Sheets:")
        st.exception(e)
        return False

def enviar_notificacion_email(coordinador, coche, destino, df_gastos, archivos):
    try:
        sender_email = st.secrets["email"]["sender_email"]
        sender_password = st.secrets["email"]["sender_password"]
        receiver_email = st.secrets["email"]["receiver_email"]

        total = df_gastos["Monto ($)"].sum()
        
        filas_html = ""
        for idx, r in df_gastos.iterrows():
            num_tk = idx + 1
            tipo_gasto = r.get("Tipo de gasto", "-")
            obs = r.get("Observaciones", "-")
            filas_html += (
                f"<tr>"
                f"<td>{num_tk}</td>"
                f"<td>{r['Fecha de compra']}</td>"
                f"<td>{r['N° Factura / TK']}</td>"
                f"<td>{r['Abona con viático']}</td>"
                f"<td>{tipo_gasto}</td>"
                f"<td>{obs}</td>"
                f"<td style='text-align:right'>${r['Monto ($)']:,.2f}</td>"
                f"</tr>"
            )

        nombres_archivos = ", ".join([f.name for f in archivos]) if archivos else "Ninguno"

        html_body = f"""
        <h2>Nueva Rendición Recibida - Wolf Internacional</h2>
        <p><b>Coordinador:</b> {coordinador}</p>
        <p><b>Coche:</b> {coche} | <b>Destino:</b> {destino}</p>
        <p><b>Archivos adjuntos:</b> {nombres_archivos}</p>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
            <tr style="background:#1a3c6e;color:white;">
                <th>N° TK</th><th>Fecha</th><th>Factura/TK</th><th>Viático</th><th>Tipo de Gasto</th><th>Observaciones</th><th>Monto</th>
            </tr>
            {filas_html}
            <tr style="font-weight:bold;background:#f0f0f0;">
                <td colspan="6" style="text-align:right">TOTAL</td>
                <td style="text-align:right">${total:,.2f}</td>
            </tr>
        </table>
        """

        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"[Rendición] {coordinador} | {destino} | ${total:,.2f}"
        msg["From"] = sender_email
        
        # Destinatarios principales
        segundo_receptor = "fbocchi@lantier.com.ar"
        msg["To"] = f"{receiver_email}, {segundo_receptor}"
        destinatarios = [receiver_email, segundo_receptor]

        cuerpo_html = MIMEMultipart("alternative")
        cuerpo_html.attach(MIMEText(html_body, "html"))
        msg.attach(cuerpo_html)

        if archivos:
            for archivo in archivos:
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

st.subheader("1. Datos Generales del Viaje")
col1, col2, col3 = st.columns(3)
with col1:
    coordinador = st.text_input("Nombre y Apellido del Coordinador")
with col2:
    coche = st.text_input("N° de Coche / Unidad")
with col3:
    destino = st.text_input("Destino principal del viaje")

st.markdown("---")
st.subheader("2. Detalle de Comprobantes (Múltiples Gastos)")

df_default = pd.DataFrame([{
    "Fecha de compra": date.today(),
    "N° Factura / TK": "",
    "Monto ($)": 0.0,
    "Abona con viático": "Sí",
    "Tipo de gasto": "🍽️ Alimentos",
    "Observaciones": ""
}])

df_gastos = st.data_editor(
    df_default,
    num_rows="dynamic",
    column_config={
        "Fecha de compra": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY", required=True),
        "N° Factura / TK": st.column_config.TextColumn("N° Factura / Proveedor", required=True),
        "Monto ($)": st.column_config.NumberColumn("Monto ($)", min_value=0.0, format="$ %.2f", required=True),
        "Abona con viático": st.column_config.SelectboxColumn("¿Abona con viático?", options=["Sí", "No"], required=True),
        "Tipo de gasto": st.column_config.SelectboxColumn("🏷️ ¿Qué tipo de gasto es?", options=TIPOS_GASTO, required=True),
        "Observaciones": st.column_config.TextColumn("Observaciones", required=False)
    },
    hide_index=True,
    use_container_width=True
)

st.markdown("---")
st.subheader("3. Adjuntar Comprobantes (Obligatorio)")
archivos_adjuntos = st.file_uploader(
    "Sube fotos o PDFs de los tickets",
    type=["png", "jpg", "jpeg", "pdf"],
    accept_multiple_files=True
)

enviado = st.button("🚀 Enviar Rendición Completa", type="primary")

if enviado:
    if not coordinador or not archivos_adjuntos or df_gastos.empty:
        st.error("⚠️ Por favor completa el nombre del coordinador y asegúrate de adjuntar al menos un comprobante.")
    else:
        if guardar_en_sheets(coordinador, coche, destino, df_gastos, archivos_adjuntos):
            enviar_notificacion_email(coordinador, coche, destino, df_gastos, archivos_adjuntos)
            st.success(f"¡Rendición procesada con éxito para **{coordinador}**!")
            st.dataframe(df_gastos, use_container_width=True)
