# fix_cloud.py
import mysql.connector
import streamlit as st

def fix_database():
    print("🚑 Iniciando reparación de base de datos en la nube...")
    
    # Conexión usando tus secretos de Streamlit Cloud
    if "mysql" in st.secrets:
        config = st.secrets["mysql"]
    else:
        st.error("No se encontraron secretos de conexión.")
        return

    conn = mysql.connector.connect(
        host=config["host"],
        user=config["user"],
        password=config["password"],
        database=config["database"],
        port=config["port"]
    )
    cursor = conn.cursor()

    try:
        # 1. AGREGAR COLUMNA 'ACTIVO' A PRODUCTOS
        print("--- Intentando agregar columna 'activo'...")
        try:
            cursor.execute("ALTER TABLE productos ADD COLUMN activo TINYINT(1) DEFAULT 1")
            st.success("✅ Columna 'activo' creada correctamente.")
        except mysql.connector.Error as err:
            if err.errno == 1060:
                st.info("ℹ️ La columna 'activo' ya existía.")
            else:
                st.error(f"Error SQL: {err}")

        # 2. ASEGURAR QUE LOS PRODUCTOS EXISTENTES ESTÉN ACTIVOS
        cursor.execute("UPDATE productos SET activo = 1 WHERE activo IS NULL")
        
        conn.commit()
        st.balloons()
        st.success("¡Base de datos reparada! Ahora puedes borrar este script.")

    except Exception as e:
        st.error(f"❌ Error crítico: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    fix_database()