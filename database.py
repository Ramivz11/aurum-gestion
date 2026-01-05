import mysql.connector
import pandas as pd
import streamlit as st
from datetime import datetime

# --- 1. CONEXIÓN ---
def get_db_connection():
    if "mysql" in st.secrets:
        return mysql.connector.connect(
            host=st.secrets["mysql"]["host"],
            user=st.secrets["mysql"]["user"],
            password=st.secrets["mysql"]["password"],
            database=st.secrets["mysql"]["database"],
            port=st.secrets["mysql"]["port"]
        )
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
        
        # Productos base
        df_prod_base = pd.read_sql("SELECT nombre as Nombre, costo as Costo, precio as Precio FROM productos", conn)
        
        # Stock
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

        # Compras
        df_compras = pd.read_sql("SELECT * FROM compras ORDER BY fecha DESC", conn)
        df_compras = df_compras.rename(columns={
            'id': 'ID', 'fecha': 'FECHA', 'producto': 'PRODUCTO', 
            'cantidad': 'CANTIDAD', 'costo_total': 'COSTO', 
            'proveedor': 'PROVEEDOR', 'metodo_pago': 'METODO PAGO', 
            'ubicacion': 'UBICACION', 'notas': 'NOTAS'
        })
        
        return df_prod, lista_sucursales, df_ventas, df_compras
    except Exception as e:
        st.error(f"Error al leer datos: {e}")
        return pd.DataFrame(), [], pd.DataFrame(), pd.DataFrame()
    finally:
        if conn.is_connected():
            conn.close()

# --- 3. CREAR PRODUCTO ---
def crear_producto(nombre, costo, precio):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SELECT id FROM productos WHERE nombre = %s", (nombre,))
        if cursor.fetchone():
            st.warning(f"⚠️ El producto '{nombre}' ya existe.")
            return False
        sql = "INSERT INTO productos (nombre, costo, precio) VALUES (%s, %s, %s)"
        cursor.execute(sql, (nombre, costo, precio))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False
    finally:
        cursor.close()
        conn.close()
        # --- EN database.py ---

def actualizar_producto(nombre_anterior, nuevo_nombre, nuevo_costo, nuevo_precio):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        
        # 1. Validar si el nuevo nombre ya existe (si es que estamos cambiándolo)
        if nuevo_nombre != nombre_anterior:
            cursor.execute("SELECT id FROM productos WHERE nombre = %s", (nuevo_nombre,))
            if cursor.fetchone():
                st.warning(f"⚠️ El nombre '{nuevo_nombre}' ya está en uso por otro producto.")
                return False

        # 2. Actualizar tabla maestra de productos
        sql_prod = "UPDATE productos SET nombre=%s, costo=%s, precio=%s WHERE nombre=%s"
        cursor.execute(sql_prod, (nuevo_nombre, nuevo_costo, nuevo_precio, nombre_anterior))

        # 3. Si el nombre cambió, actualizar referencias en las otras tablas
        if nuevo_nombre != nombre_anterior:
            # Actualizar inventario
            cursor.execute("UPDATE inventario SET producto_nombre=%s WHERE producto_nombre=%s", (nuevo_nombre, nombre_anterior))
            # Actualizar ventas históricas
            cursor.execute("UPDATE ventas SET producto=%s WHERE producto=%s", (nuevo_nombre, nombre_anterior))
            # Actualizar compras históricas
            cursor.execute("UPDATE compras SET producto=%s WHERE producto=%s", (nuevo_nombre, nombre_anterior))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error al actualizar producto: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

# --- 4. VENTAS ---
def registrar_venta(producto, cantidad, precio, metodo, ubicacion, notas):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        cursor.execute("SELECT cantidad FROM inventario WHERE producto_nombre = %s AND sucursal_nombre = %s", (producto, ubicacion))
        res = cursor.fetchone()
        stock_actual = res[0] if res else 0
        
        if stock_actual < cantidad:
            st.error(f"⚠️ Stock insuficiente. Hay {stock_actual}.")
            return False

        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre = %s AND sucursal_nombre = %s", (cantidad, producto, ubicacion))
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
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        
        # Conversión de tipos (Pandas -> Python nativo)
        cant_old = int(datos_old['CANTIDAD'])
        prod_old = str(datos_old['PRODUCTO'])
        ubic_old = str(datos_old['UBICACION'])
        
        # 1. Devolver stock anterior
        cursor.execute("UPDATE inventario SET cantidad = cantidad + %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                       (cant_old, prod_old, ubic_old))
        
        # 2. Chequear stock nuevo disponible
        cursor.execute("SELECT cantidad FROM inventario WHERE producto_nombre = %s AND sucursal_nombre = %s", (datos_new['producto'], datos_new['ubicacion']))
        res = cursor.fetchone()
        stock_disp = res[0] if res else 0
        
        if stock_disp < datos_new['cantidad']:
            # Revertir la devolución si falla
            cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                           (cant_old, prod_old, ubic_old))
            st.error(f"⚠️ Stock insuficiente para el cambio.")
            return False
            
        # 3. Restar stock nuevo
        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                       (datos_new['cantidad'], datos_new['producto'], datos_new['ubicacion']))
        
        total = datos_new['precio'] * datos_new['cantidad']
        sql = "UPDATE ventas SET producto=%s, cantidad=%s, precio_unitario=%s, total=%s, metodo_pago=%s, ubicacion=%s, notas=%s WHERE id=%s"
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
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        
        # Conversión de tipos
        cant_revertir = int(datos_venta['CANTIDAD'])
        prod = str(datos_venta['PRODUCTO'])
        ubic = str(datos_venta['UBICACION'])

        cursor.execute("UPDATE inventario SET cantidad = cantidad + %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                       (cant_revertir, prod, ubic))
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

# --- 5. COMPRAS ---
def registrar_compra(producto, cantidad, costo, proveedor, metodo, ubicacion, notas):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("UPDATE inventario SET cantidad = cantidad + %s WHERE producto_nombre = %s AND sucursal_nombre = %s", (cantidad, producto, ubicacion))
        if cursor.rowcount == 0: 
            cursor.execute("INSERT INTO inventario (producto_nombre, sucursal_nombre, cantidad) VALUES (%s, %s, %s)", (producto, ubicacion, cantidad))

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

def editar_compra(id_compra, datos_old, datos_new):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        
        # Conversión de tipos explícita (Solución al error numpy.int64)
        cant_old = int(datos_old['CANTIDAD'])
        prod_old = str(datos_old['PRODUCTO'])
        ubic_old = str(datos_old['UBICACION'])
        
        # 1. Revertir el stock que se agregó (Restamos la cantidad vieja)
        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                       (cant_old, prod_old, ubic_old))
        
        # 2. Agregar el nuevo stock (Sumamos la cantidad nueva)
        cursor.execute("SELECT id FROM inventario WHERE producto_nombre = %s AND sucursal_nombre = %s", (datos_new['producto'], datos_new['ubicacion']))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO inventario (producto_nombre, sucursal_nombre, cantidad) VALUES (%s, %s, 0)", (datos_new['producto'], datos_new['ubicacion']))

        cursor.execute("UPDATE inventario SET cantidad = cantidad + %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                       (datos_new['cantidad'], datos_new['producto'], datos_new['ubicacion']))

        # 3. Actualizar la compra
        sql = """UPDATE compras SET producto=%s, cantidad=%s, costo_total=%s, proveedor=%s, metodo_pago=%s, ubicacion=%s, notas=%s WHERE id=%s"""
        cursor.execute(sql, (datos_new['producto'], datos_new['cantidad'], datos_new['costo'], datos_new['proveedor'], 
                             datos_new['metodo'], datos_new['ubicacion'], datos_new['notas'], id_compra))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error al editar compra: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def eliminar_compra(id_compra, datos_compra):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        
        # Conversión de tipos explícita
        cant_revertir = int(datos_compra['CANTIDAD'])
        prod = str(datos_compra['PRODUCTO'])
        ubic = str(datos_compra['UBICACION'])
        
        # 1. Revertir stock (Restamos lo que se compró)
        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                       (cant_revertir, prod, ubic))
        
        # 2. Eliminar registro
        cursor.execute("DELETE FROM compras WHERE id = %s", (id_compra,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error al eliminar compra: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

# --- 6. FINANZAS ---
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
        if conn.is_connected():
            conn.close()

def actualizar_saldo_inicial(cuenta, monto):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
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