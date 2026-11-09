import streamlit as st
import pandas as pd
from datetime import date
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

st.set_page_config(page_title="Rendición de Gastos - Wolf Internacional", page_icon="🚗", layout="wide")

st.title("🚗 Wolf Internacional - Carga Múltiple de Rendiciones")
st.markdown("Herramienta móvil para registrar comprobantes de viaje.")

SPREADSHEET_ID = "1-VBqXnZ0OQC5YaAiMG2-c7HPCMS1P5grtiaJlfFvBBI"

def obtener_cliente_gspread():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    return gspread.authorize(creds)

def guardar_en_sheets(coordinador, email, coche, destino, df_gastos):
    try:
        client = obtener_cliente_gspread()
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1

        for _, row in df_gastos.iterrows():
            sheet.append_row([
                coordinador,
                email,
                coche,
                destino,
                str(row["Fecha de compra"]),
                str(row["N° Orden Interno TK"]),
                str(row["N° Factura / TK"]),
                float(row["Monto ($)"]),
                str(row["Abona con viático"])
            ])
        return True
    except Exception as e:
        st.error(f"Error al guardar en Google Sheets: {e}")
        return False

def enviar_notificacion_email(coordinador, coche, destino, df_gastos):
    try:
        sender_email = st.secrets["email"]["sender_email"]
        sender_password = st.secrets["email"]["sender_password"]
        receiver_email = st.secrets["email"]["receiver_email"]

        total = df_gastos["Monto ($)"].sum()
        
        filas_html = ""
        for _, r in df_gastos.iterrows():
            filas_html += f"<tr><td>{r['Fecha de compra']}</td><td>{r['N° Orden Interno TK']}</td><td>{r['N° Factura / TK']}</td><td>{r['Abona con viático']}</td><td style='text-align:right'>${r['Monto ($)']:,.2f}</td></tr>"

        html_body = f"""
        <h2>Nueva Rendición Recibida - Wolf Internacional</h2>
        <p><b>Coordinador:</b> {coordinador}</p>
        <p><b>Coche:</b> {coche} | <b>Destino:</b> {destino}</p>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
            <tr style="background:#1a3c6e;color:white;">
                <th>Fecha</th><th>TK Interno</th><th>Factura/TK</th><th>Viático</th><th>Monto</th>
            </tr>
            {filas_html}
            <tr style="font-weight:bold;background:#f0f0f0;">
                <td colspan="4" style="text-align:right">TOTAL</td>
                <td style="text-align:right">${total:,.2f}</td>
            </tr>
        </table>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[Rendición] {coordinador} | {destino} | ${total:,.2f}"
        msg["From"] = sender_email
        msg["To"] = receiver_email
        msg.attach(MIMEText(html_body, "html"))

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
        email = st.text_input("Correo electrónico")
    with col3:
        coche = st.text_input("N° de Coche / Unidad")
        
    destino = st.text_input("Destino principal del viaje")

    st.markdown("---")
    st.subheader("2. Detalle de Comprobantes (Múltiples Gastos)")

    df_default = pd.DataFrame([{
        "Fecha de compra": date.today(),
        "N° Orden Interno TK": "",
        "N° Factura / TK": "",
        "Monto ($)": 0.0,
        "Abona con viático": "Sí"
    }])

    df_gastos = st.data_editor(
        df_default,
        num_rows="dynamic",
        column_config={
            "Fecha de compra": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY", required=True),
            "N° Orden Interno TK": st.column_config.TextColumn("N° Orden Interno TK", required=True),
            "N° Factura / TK": st.column_config.TextColumn("N° Factura / Proveedor", required=True),
            "Monto ($)": st.column_config.NumberColumn("Monto ($)", min_value=0.0, format="$ %.2f", required=True),
            "Abona con viático": st.column_config.SelectboxColumn("¿Abona con viático?", options=["Sí", "No"], required=True)
        },
        hide_index=True,
        use_container_width=True
    )

    enviado = st.form_submit_button("🚀 Enviar Rendición Completa")

if enviado:
    if not coordinador or not email or df_gastos.empty:
        st.error("⚠️ Por favor completa los datos obligatorios.")
    else:
        if guardar_en_sheets(coordinador, email, coche, destino, df_gastos):
            enviar_notificacion_email(coordinador, coche, destino, df_gastos)
            st.success(f"¡Rendición procesada con éxito para **{coordinador}**!")
            st.dataframe(df_gastos, use_container_width=True)