import streamlit as st
import gspread

st.title("🕵️‍♂️ Diagnóstico de Conexión")

try:
    st.info("1. Intentando leer credenciales...")
    # Usamos el método moderno (service_account) que es más robusto
    gc = gspread.service_account(filename='credenciales.json')
    st.success("✅ Credenciales aceptadas.")

    st.info("2. Buscando la hoja 'aurum_db'...")
    # Intentamos abrir por nombre (asegúrate que en Google se llame EXACTO así)
    sh = gc.open("aurum_db")
    st.success(f"✅ Hoja encontrada: {sh.title}")

    st.info("3. Leyendo datos de prueba...")
    # Leemos la primera pestaña para ver si trae datos
    datos = sh.sheet1.get_all_records()
    st.write(datos)
    st.balloons()

except Exception as e:
    st.error("❌ Ocurrió un error:")
    # Esta línea mágica nos mostrará el error completo en pantalla
    st.exception(e)