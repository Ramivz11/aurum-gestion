import mysql.connector
import streamlit as st
from database import get_db_connection

def migrar_v2():
    print("🚀 Iniciando migración V2 (Stock Flexible)...")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Agregar campo ACTIVO a productos (Para borrado lógico)
        print("--- Agregando columna 'activo'...")
        try:
            cursor.execute("ALTER TABLE productos ADD COLUMN activo TINYINT(1) DEFAULT 1")
            print("✅ Columna 'activo' agregada.")
        except mysql.connector.Error as err:
            if err.errno == 1060:
                print("ℹ️ La columna 'activo' ya existe.")
            else:
                raise err

        # 2. Asegurarnos que existan índices para búsquedas rápidas
        try:
            cursor.execute("CREATE INDEX idx_prod_nombre ON productos(nombre)")
        except: pass

        conn.commit()
        print("🎉 Migración completada con éxito.")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    migrar_v2()