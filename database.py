import mysql.connector
import pandas as pd
import streamlit as st
from datetime import datetime

# --- 1. CONEXIÓN (INTELIGENTE: NUBE O LOCAL) ---
def get_db_connection():
    # Intenta usar la configuración de la Nube (Streamlit Cloud)
    if "mysql" in st.secrets:
        return mysql.connector.connect(
            host=st.secrets["mysql"]["host"],
            user=st.secrets["mysql"]["user"],
            password=st.secrets["mysql"]["password"],
            database=st.secrets["mysql"]["database"],
            port=st.secrets["mysql"]["port"]
        )
    # Si no, usa la configuración Local (Tu PC)
    else:
        return mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="aurum_db"
        )

# --- 2. LECTURA DE DATOS ---
def obtener_datos_globales():
    conn = get_db_connection()
    try:
        # Sucursales
        df_suc = pd.read_sql("SELECT nombre FROM sucursales", conn)
        lista_sucursales = df_suc['nombre'].tolist() if not df_suc.empty else []
        
        # Productos y Stock (Pivot)
        df_prod_base = pd.read_sql("SELECT nombre as Nombre, costo as Costo, precio as Precio FROM productos", conn)
        df_stock = pd.read_sql("SELECT producto_nombre, sucursal_nombre, cantidad FROM inventario", conn)
        
        if not df_stock.empty:
            pivot_stock = df_stock.pivot(index='producto_nombre', columns='sucursal_nombre', values='cantidad').fillna(0)
            pivot_stock.columns = [f"Stock_{col}" for col in pivot_stock.columns]
            df_prod = pd.merge(df_prod_base, pivot_stock, left_on='Nombre', right_index=True, how='left').fillna(0)
        else:
            df_prod = df_prod_base
            
        # Ventas
        df_ventas = pd.read_sql("SELECT * FROM ventas ORDER BY fecha DESC", conn)
        df_ventas = df_ventas.rename(columns={
            'id': 'ID', 'fecha': 'FECHA', 'producto': 'PRODUCTO', 
            'cantidad': 'CANTIDAD', 'precio_unitario': 'PRECIO UNITARIO', 
            'total': 'TOTAL', 'metodo_pago': 'METODO PAGO', 
            'ubicacion': 'UBICACION', 'notas': 'NOTAS'
        })
        
        return df_prod, lista_sucursales, df_ventas
    except Exception as e:
        st.error(f"Error al leer datos: {e}")
        return pd.DataFrame(), [], pd.DataFrame()
    finally:
        conn.close()

# --- 3. VENTAS (REGISTRAR / EDITAR / ELIMINAR) ---
def registrar_venta(producto, cantidad, precio, metodo, ubicacion, notas):
    conn = get_db_connection()
    # buffered=True evita errores de "Unread result found"
    cursor = conn.cursor(buffered=True) 
    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        
        # Verificar Stock
        cursor.execute("SELECT cantidad FROM inventario WHERE producto_nombre = %s AND sucursal_nombre = %s", (producto, ubicacion))
        res = cursor.fetchone()
        stock_actual = res[0] if res else 0
        
        if stock_actual < cantidad:
            st.error(f"⚠️ Stock insuficiente. Hay {stock_actual}.")
            return False

        # Restar Stock
        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre = %s AND sucursal_nombre = %s", (cantidad, producto, ubicacion))
        
        # Registrar Venta
        total = precio * cantidad
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sql = "INSERT INTO ventas (fecha, producto, cantidad, precio_unitario, total, metodo_pago, ubicacion, notas) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        cursor.execute(sql, (fecha, producto, cantidad, precio, total, metodo, ubicacion, notas))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error SQL: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def editar_venta(id_venta, datos_old, datos_new):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True) # buffered=True agregado
    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        
        # 1. Devolver Stock original
        cursor.execute("UPDATE inventario SET cantidad = cantidad + %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                       (datos_old['CANTIDAD'], datos_old['PRODUCTO'], datos_old['UBICACION']))
        
        # 2. Verificar Stock nuevo
        cursor.execute("SELECT cantidad FROM inventario WHERE producto_nombre = %s AND sucursal_nombre = %s", (datos_new['producto'], datos_new['ubicacion']))
        res = cursor.fetchone()
        stock_disp = res[0] if res else 0
        
        if stock_disp < datos_new['cantidad']:
            # Rollback manual (volver a restar lo que devolvimos porque falló la validación)
            cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                           (datos_old['CANTIDAD'], datos_old['PRODUCTO'], datos_old['UBICACION']))
            conn.commit()
            st.error(f"⚠️ Stock insuficiente para el cambio.")
            return False
            
        # 3. Restar el nuevo Stock
        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                       (datos_new['cantidad'], datos_new['producto'], datos_new['ubicacion']))
        
        # 4. Actualizar la Venta
        total = datos_new['precio'] * datos_new['cantidad']
        sql = """UPDATE ventas SET producto=%s, cantidad=%s, precio_unitario=%s, total=%s, metodo_pago=%s, ubicacion=%s, notas=%s WHERE id=%s"""
        cursor.execute(sql, (datos_new['producto'], datos_new['cantidad'], datos_new['precio'], total, datos_new['metodo'], datos_new['ubicacion'], datos_new['notas'], id_venta))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error al editar: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def eliminar_venta(id_venta, datos_venta):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True) # buffered=True agregado
    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        
        # Devolver Stock
        cursor.execute("UPDATE inventario SET cantidad = cantidad + %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                       (datos_venta['CANTIDAD'], datos_venta['PRODUCTO'], datos_venta['UBICACION']))
        
        # Eliminar registro
        cursor.execute("DELETE FROM ventas WHERE id = %s", (id_venta,))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error al eliminar: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

# --- 4. COMPRAS ---
def registrar_compra(producto, cantidad, costo, proveedor, metodo, ubicacion, notas):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True) # buffered=True agregado
    try:
        # Aumentar Stock
        cursor.execute("""
            UPDATE inventario SET cantidad = cantidad + %s 
            WHERE producto_nombre = %s AND sucursal_nombre = %s
        """, (cantidad, producto, ubicacion))
        
        if cursor.rowcount == 0: # Si no existe, insertar
            cursor.execute("INSERT INTO inventario (producto_nombre, sucursal_nombre, cantidad) VALUES (%s, %s, %s)", (producto, ubicacion, cantidad))

        # Registrar Compra
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sql = "INSERT INTO compras (fecha, producto, cantidad, costo_total, proveedor, metodo_pago, ubicacion, notas) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        cursor.execute(sql, (fecha, producto, cantidad, costo, proveedor, metodo, ubicacion, notas))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error en compra: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

# --- 5. FINANZAS ---
def obtener_resumen_finanzas():
    conn = get_db_connection()
    try:
        df_v = pd.read_sql("SELECT metodo_pago, SUM(total) as total FROM ventas GROUP BY metodo_pago", conn)
        df_c = pd.read_sql("SELECT metodo_pago, SUM(costo_total) as total FROM compras GROUP BY metodo_pago", conn)
        df_saldos = pd.read_sql("SELECT cuenta, monto FROM saldos_iniciales", conn)
        return df_v, df_c, df_saldos
    except:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    finally:
        conn.close()

def actualizar_saldo_inicial(cuenta, monto):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True) # buffered=True agregado
    try:
        cursor.execute("UPDATE saldos_iniciales SET monto=%s WHERE cuenta=%s", (monto, cuenta))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error saldos: {e}")
        return False
    finally:
        cursor.close()
        conn.close()