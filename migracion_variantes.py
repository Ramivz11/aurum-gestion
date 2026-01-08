import mysql.connector
import streamlit as st
from database import get_db_connection

def migrar_variantes():
    print("🍦 Iniciando migración de Variantes...")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Crear tabla de Variantes (Vinculada al nombre del producto)
        print("--- Creando tabla 'variantes'...")
        sql_var = """
        CREATE TABLE IF NOT EXISTS variantes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            producto_nombre VARCHAR(255),
            nombre_variante VARCHAR(100),
            FOREIGN KEY (producto_nombre) REFERENCES productos(nombre) ON DELETE CASCADE,
            UNIQUE KEY unique_var (producto_nombre, nombre_variante)
        );
        """
        cursor.execute(sql_var)

        # 2. Agregar columna 'variante' a INVENTARIO
        print("--- Actualizando Inventario...")
        try:
            cursor.execute("ALTER TABLE inventario ADD COLUMN variante VARCHAR(100) DEFAULT ''")
        except:
            print("ℹ️ Columna variante ya existe en inventario.")
            
        # Re-hacer la clave única del inventario para incluir la variante
        try:
            cursor.execute("ALTER TABLE inventario DROP INDEX unique_stock")
        except:
            pass # Si no existe el indice viejo, seguimos
            
        try:
            cursor.execute("ALTER TABLE inventario ADD UNIQUE KEY unique_stock_var (producto_nombre, sucursal_nombre, variante)")
        except:
            pass

        # 3. Agregar columna 'variante' a VENTAS y COMPRAS
        print("--- Actualizando Historiales...")
        try:
            cursor.execute("ALTER TABLE ventas ADD COLUMN variante VARCHAR(100) DEFAULT ''")
            cursor.execute("ALTER TABLE compras ADD COLUMN variante VARCHAR(100) DEFAULT ''")
        except:
            pass

        conn.commit()
        print("✅ ¡MIGRACIÓN DE VARIANTES COMPLETADA!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    migrar_variantes()