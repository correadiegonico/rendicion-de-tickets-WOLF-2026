import streamlit as st
import pandas as pd
from datetime import date
import gspread
from google.oauth2.service_account import Credentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

st.set_page_config(page_title="Rendición de Gastos - Wolf Internacional", page_icon="🚗", layout="wide")

st.title("🚗 Wolf Internacional - Carga Múltiple de Rendiciones")
st.markdown("Herramienta móvil para registrar comprobantes de viaje.")

# ID de tu Google Sheet
SPREADSHEET_ID = "1TqAAUw9K_Arn6aDTAZJ4sXciSe9FpO99cMXKenY_AcU"

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

def guardar_en_sheets(coordinador, email, coche, destino, df_gastos, archivos):
    try:
        client = obtener_cliente_gspread()
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1

        enlace_comprobante = (
            f"Enviado por mail ({', '.join([f.name for f in archivos])})"
            if archivos else "Sin adjunto"
        )

        for idx, row in df_gastos.iterrows():
            numero_orden = str(idx + 1)
            
            # Mapeo exacto de columnas A hasta J:
            # A: Destino | B: Coordinador | C: Fecha | D: Orden TK | E: Factura/TK | F: Monto | G: Enlace | H: Mail | I: Viático | J: Observaciones
            sheet.append_row([
                destino,
                f"{coordinador} (Coche: {coche})" if coche else coordinador,
                str(row["Fecha de compra"]),
                numero_orden,
                str(row["N° Factura / TK"]),
                float(row["Monto ($)"]),
                enlace_comprobante,
                email,
                str(row["Abona con viático"]),
                str(row.get("Observaciones", ""))
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
            obs = r.get("Observaciones", "-")
            filas_html += f"<tr><td>{num_tk}</td><td>{r['Fecha de compra']}</td><td>{r['N° Factura / TK']}</td><td>{r['Abona con viático']}</td><td>{obs}</td><td style='text-align:right'>${r['Monto ($)']:,.2f}</td></tr>"

        nombres_archivos = ", ".join([f.name for f in archivos]) if archivos else "Ninguno"

        html_body = f"""
        <h2>Nueva Rendición Recibida - Wolf Internacional</h2>
        <p><b>Coordinador:</b> {coordinador}</p>
        <p><b>Coche:</b> {coche} | <b>Destino:</b> {destino}</p>
        <p><b>Archivos adjuntos:</b> {nombres_archivos}</p>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
            <tr style="background:#1a3c6e;color:white;">
                <th>N° TK</th><th>Fecha</th><th>Factura/TK</th><th>Viático</th><th>Observaciones</th><th>Monto</th>
            </tr>
            {filas_html}
            <tr style="font-weight:bold;background:#f0f0f0;">
                <td colspan="5" style="text-align:right">TOTAL</td>
                <td style="text-align:right">${total:,.2f}</td>
            </tr>
        </table>
        """

        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"[Rendición] {coordinador} | {destino} | ${total:,.2f}"
        msg["From"] = sender_email
        msg["To"] = receiver_email

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
            server.sendmail(sender_email, receiver_email, msg.as_string())
        return True
    except Exception as e:
        st.warning(f"No se pudo enviar la notificación por correo: {e}")
        return False

with st.form("form_multi_rendicion"):
    st.subheader("1. Datos Generales del Viaje")
    col1, col2, col3 = st.columns(3)
    with col1:
        coordinador = st.text_input("Nombre y Apellido del Coordinador")
    with col2:
        email = st.text_input("Correo electrónico coordinador")
    with col3:
        coche = st.text_input("N° de Coche / Unidad")
        
    destino = st.text_input("Destino principal del viaje")

    st.markdown("---")
    st.subheader("2. Detalle de Comprobantes (Múltiples Gastos)")

    df_default = pd.DataFrame([{
        "Fecha de compra": date.today(),
        "N° Factura / TK": "",
        "Monto ($)": 0.0,
        "Abona con viático": "Sí",
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
            "Observaciones": st.column_config.TextColumn("Observaciones", required=False)
        },
        hide_index=True,
        use_container_width=True
    )

    st.markdown("---")
    st.subheader("3. Adjuntar Comprobantes (Opcional)")
    archivos_adjuntos = st.file_uploader(
        "Sube fotos o PDFs de los tickets",
        type=["png", "jpg", "jpeg", "pdf"],
        accept_multiple_files=True
    )

    enviado = st.form_submit_button("🚀 Enviar Rendición Completa")

if enviado:
    if not coordinador or not email or df_gastos.empty:
        st.error("⚠️ Por favor completa los datos obligatorios.")
    else:
        if guardar_en_sheets(coordinador, email, coche, destino, df_gastos, archivos_adjuntos):
            enviar_notificacion_email(coordinador, coche, destino, df_gastos, archivos_adjuntos)
            st.success(f"¡Rendición procesada con éxito para **{coordinador}**!")
            st.dataframe(df_gastos, use_container_width=True)
