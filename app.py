import streamlit as st
import pandas as pd
from datetime import date
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Configuración de la página
st.set_page_config(page_title="Rendición de Gastos - Wolf Internacional", page_icon="🚗", layout="wide")

st.title("🚗 Wolf Internacional - Carga Múltiple de Rendiciones")
st.markdown("Utiliza esta herramienta para registrar varios tickets o facturas en una sola rendición.")

# ID de tu Google Sheet existente
SPREADSHEET_ID = "1-VBqXnZ0OQC5YaAiMG2-c7HPCMS1P5grtiaJlfFvBBI"

def guardar_en_sheets(coordinador, email, coche, destino, df_gastos):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1

        # Recorre cada fila del editor interactivo y la agrega a la hoja
        for index, row in df_gastos.iterrows():
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
        st.error(f"Error al conectar con Google Sheets: {e}")
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
    st.markdown("Agrega o edita los datos de cada ticket o factura que deseas rendir:")

    # Grilla interactiva para múltiples gastos
    df_default = pd.DataFrame([
        {
            "Fecha de compra": date.today(),
            "N° Orden Interno TK": "",
            "N° Factura / TK": "",
            "Monto ($)": 0.0,
            "Abona con viático": "Sí"
        }
    ])

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

    st.markdown("---")
    st.subheader("3. Comprobantes Adjuntos")
    archivos = st.file_uploader("Sube los tickets o facturas (PDF o imágenes)", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True)

    enviado = st.form_submit_button("🚀 Enviar Rendición Completa")

if enviado:
    if not coordinador or not email or df_gastos.empty:
        st.error("⚠️ Por favor completa los datos obligatorios (Coordinador, Correo y al menos un gasto en la tabla).")
    else:
        total_rendicion = df_gastos["Monto ($)"].sum()
        
        # Guardar en Google Sheets
        exito = guardar_en_sheets(coordinador, email, coche, destino, df_gastos)
        
        if exito:
            st.success(f"¡Rendición procesada y guardada con éxito para **{coordinador}**!")
            st.info(f"Total acumulado en este envío: **${total_rendicion:,.2f}** con {len(df_gastos)} comprobante(s).")
            st.dataframe(df_gastos, use_container_width=True)

