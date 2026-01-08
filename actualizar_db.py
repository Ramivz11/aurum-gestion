import mysql.connector
import streamlit as st
from database import get_db_connection

def migrar_base_datos():
    print("🔄 Iniciando actualización de base de datos...")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. CREAR TABLA CLIENTES (Si no existe)
        print("--- Verificando tabla 'clientes'...")
        sql_clientes = """
        CREATE TABLE IF NOT EXISTS clientes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(255) NOT NULL UNIQUE,
            ubicacion VARCHAR(100),
            fecha_alta DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(sql_clientes)
        print("✅ Tabla clientes verificada.")

        # 2. CREAR CLIENTE POR DEFECTO
        print("--- Creando 'Consumidor Final'...")
        # Usamos INSERT IGNORE para que no falle si ya existe
        cursor.execute("INSERT IGNORE INTO clientes (nombre, ubicacion) VALUES ('Consumidor Final', 'General')")
        
        # Obtenemos el ID de este cliente para usarlo después
        cursor.execute("SELECT id FROM clientes WHERE nombre = 'Consumidor Final'")
        id_consumidor_final = cursor.fetchone()[0]
        print(f"✅ Consumidor Final listo (ID: {id_consumidor_final}).")

        # 3. ACTUALIZAR TABLA VENTAS (Agregar columna cliente_id)
        print("--- Actualizando estructura de 'ventas'...")
        try:
            cursor.execute("ALTER TABLE ventas ADD COLUMN cliente_id INT DEFAULT NULL")
            print("✅ Columna 'cliente_id' agregada a ventas.")
        except mysql.connector.Error as err:
            if err.errno == 1060: # Error 1060: Duplicate column name
                print("ℹ️ La columna 'cliente_id' ya existía en ventas. Omitiendo.")
            else:
                raise err

        # 4. VINCULAR CLAVE FORÁNEA (Opcional pero recomendado)
        try:
            cursor.execute("ALTER TABLE ventas ADD CONSTRAINT fk_venta_cliente FOREIGN KEY (cliente_id) REFERENCES clientes(id)")
            print("✅ Relación (Foreign Key) creada.")
        except mysql.connector.Error as err:
             # Ignoramos error si la constraint ya existe o si hay incompatibilidad menor
            print(f"ℹ️ Nota sobre FK: {err.msg}")

        # 5. ACTUALIZAR VENTAS VIEJAS
        # Todas las ventas que tengan cliente_id NULL, se asignan a "Consumidor Final"
        print("--- Asignando ventas antiguas a 'Consumidor Final'...")
        cursor.execute("UPDATE ventas SET cliente_id = %s WHERE cliente_id IS NULL", (id_consumidor_final,))
        print(f"✅ {cursor.rowcount} ventas antiguas actualizadas.")

        conn.commit()
        print("\n🚀 ¡MIGRACIÓN COMPLETADA CON ÉXITO! 🚀")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ ERROR CRÍTICO: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    migrar_base_datos()