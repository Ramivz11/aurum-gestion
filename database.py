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
        
        # Productos Base
        df_prod_base = pd.read_sql("SELECT nombre as Nombre, costo as Costo, precio as Precio FROM productos", conn)
        
        # STOCK DETALLADO
        try:
            sql_stock = """
                SELECT 
                    CONCAT(producto_nombre, IF(variante != '' AND variante IS NOT NULL, CONCAT(' | ', variante), '')) as prod_full,
                    sucursal_nombre, 
                    cantidad 
                FROM inventario
            """
            df_stock = pd.read_sql(sql_stock, conn)
        except:
            df_stock = pd.read_sql("SELECT producto_nombre as prod_full, sucursal_nombre, cantidad FROM inventario", conn)
        
        if not df_stock.empty:
            pivot_stock = df_stock.pivot(index='prod_full', columns='sucursal_nombre', values='cantidad').fillna(0)
            pivot_stock.columns = [f"Stock_{col}" for col in pivot_stock.columns]
            
            df_prod = pivot_stock.reset_index().rename(columns={'prod_full': 'Nombre'})
            df_prod['Nombre_Base'] = df_prod['Nombre'].apply(lambda x: x.split(' | ')[0])
            df_prod = pd.merge(df_prod, df_prod_base[['Nombre', 'Costo', 'Precio']], left_on='Nombre_Base', right_on='Nombre', how='left')
            
            if 'Nombre_y' in df_prod.columns: del df_prod['Nombre_y']
            df_prod = df_prod.rename(columns={'Nombre_x': 'Nombre'})
            df_prod = df_prod.drop(columns=['Nombre_Base']).fillna(0)
        else:
            df_prod = df_prod_base
            
        # Ventas
        df_ventas = pd.read_sql("SELECT * FROM ventas ORDER BY fecha DESC", conn)
        df_ventas = df_ventas.rename(columns={
            'id': 'ID', 'fecha': 'FECHA', 'producto': 'PRODUCTO', 
            'cantidad': 'CANTIDAD', 'precio_unitario': 'PRECIO UNITARIO', 
            'total': 'TOTAL', 'metodo_pago': 'METODO PAGO', 
            'ubicacion': 'UBICACION', 'notas': 'NOTAS', 'cliente_id': 'CLIENTE_ID'
        })
        if 'variante' in df_ventas.columns: df_ventas.rename(columns={'variante': 'VARIANTE'}, inplace=True)

        # Compras
        df_compras = pd.read_sql("SELECT * FROM compras ORDER BY fecha DESC", conn)
        df_compras = df_compras.rename(columns={
            'id': 'ID', 'fecha': 'FECHA', 'producto': 'PRODUCTO', 
            'cantidad': 'CANTIDAD', 'costo_total': 'COSTO', 
            'proveedor': 'PROVEEDOR', 'metodo_pago': 'METODO PAGO', 
            'ubicacion': 'UBICACION', 'notas': 'NOTAS'
        })
        if 'variante' in df_compras.columns: df_compras.rename(columns={'variante': 'VARIANTE'}, inplace=True)
        
        return df_prod, lista_sucursales, df_ventas, df_compras
    except Exception as e:
        st.error(f"Error al leer datos: {e}")
        return pd.DataFrame(), [], pd.DataFrame(), pd.DataFrame()
    finally:
        if conn.is_connected(): 
            conn.close()

def obtener_catalogo_venta():
    conn = get_db_connection()
    try:
        sql = """
        SELECT p.nombre, p.precio, v.nombre_variante 
        FROM productos p
        LEFT JOIN variantes v ON p.nombre = v.producto_nombre
        ORDER BY p.nombre, v.nombre_variante
        """
        df = pd.read_sql(sql, conn)
        return df
    except Exception:
        return pd.read_sql("SELECT nombre, precio, '' as nombre_variante FROM productos", conn)
    finally:
        if conn.is_connected(): 
            conn.close()

# --- 3. PRODUCTOS Y VARIANTES ---
def crear_producto(nombre, costo, precio):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SELECT id FROM productos WHERE nombre = %s", (nombre,))
        if cursor.fetchone():
            return False
        cursor.execute("INSERT INTO productos (nombre, costo, precio) VALUES (%s, %s, %s)", (nombre, costo, precio))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def crear_variante(producto_nombre, nombre_variante):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SELECT id FROM variantes WHERE producto_nombre = %s AND nombre_variante = %s", (producto_nombre, nombre_variante))
        if cursor.fetchone():
            return False, "Variante ya existe"
        cursor.execute("INSERT INTO variantes (producto_nombre, nombre_variante) VALUES (%s, %s)", (producto_nombre, nombre_variante))
        conn.commit()
        return True, "Creada"
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

def actualizar_producto(nombre_anterior, nuevo_nombre, nuevo_costo, nuevo_precio):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        if nuevo_nombre != nombre_anterior:
            cursor.execute("SELECT id FROM productos WHERE nombre = %s", (nuevo_nombre,))
            if cursor.fetchone():
                return False
        
        cursor.execute("UPDATE productos SET nombre=%s, costo=%s, precio=%s WHERE nombre=%s", (nuevo_nombre, nuevo_costo, nuevo_precio, nombre_anterior))
        
        if nuevo_nombre != nombre_anterior:
            cursor.execute("UPDATE inventario SET producto_nombre=%s WHERE producto_nombre=%s", (nuevo_nombre, nombre_anterior))
            cursor.execute("UPDATE ventas SET producto=%s WHERE producto=%s", (nuevo_nombre, nombre_anterior))
            cursor.execute("UPDATE compras SET producto=%s WHERE producto=%s", (nuevo_nombre, nombre_anterior))
            try:
                cursor.execute("UPDATE variantes SET producto_nombre=%s WHERE producto_nombre=%s", (nuevo_nombre, nombre_anterior))
            except: pass

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# --- 4. GESTIÓN DE CLIENTES ---
def obtener_clientes_metricas():
    conn = get_db_connection()
    try:
        sql = """
        SELECT c.id, c.nombre, c.ubicacion, COALESCE(SUM(v.total), 0) as total_gastado,
        (SELECT v2.producto FROM ventas v2 WHERE v2.cliente_id = c.id GROUP BY v2.producto ORDER BY SUM(v2.cantidad) DESC LIMIT 1) as producto_favorito
        FROM clientes c LEFT JOIN ventas v ON c.id = v.cliente_id
        GROUP BY c.id, c.nombre, c.ubicacion ORDER BY total_gastado DESC
        """
        return pd.read_sql(sql, conn)
    except:
        return pd.DataFrame()
    finally:
        if conn.is_connected(): 
            conn.close()

def crear_cliente(nombre, ubicacion):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SELECT id FROM clientes WHERE nombre = %s", (nombre,))
        if cursor.fetchone(): return False
        cursor.execute("INSERT INTO clientes (nombre, ubicacion) VALUES (%s, %s)", (nombre, ubicacion))
        conn.commit()
        return True
    except: return False
    finally: 
        cursor.close()
        conn.close()

def obtener_lista_clientes_simple():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre FROM clientes ORDER BY nombre ASC")
        return cursor.fetchall()
    except: 
        return []
    finally: 
        if conn.is_connected(): 
            conn.close()

def actualizar_cliente(id_c, nom, loc):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE clientes SET nombre=%s, ubicacion=%s WHERE id=%s", (nom, loc, id_c))
        conn.commit()
        return True
    except: return False
    finally: 
        cursor.close()
        conn.close()

def eliminar_cliente(id_c):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE ventas SET cliente_id = NULL WHERE cliente_id = %s", (id_c,))
        cursor.execute("DELETE FROM clientes WHERE id = %s", (id_c,))
        conn.commit()
        return True
    except: return False
    finally: 
        cursor.close()
        conn.close()

# --- 5. VENTAS ---
def registrar_venta(producto, variante, cantidad, precio, metodo, ubicacion, notas, cliente_id):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("""SELECT cantidad FROM inventario 
                          WHERE producto_nombre = %s AND variante = %s AND sucursal_nombre = %s""", 
                       (producto, variante, ubicacion))
        res = cursor.fetchone()
        stock_actual = res[0] if res else 0
        
        if stock_actual < cantidad:
            st.error(f"⚠️ Stock insuficiente. Hay {stock_actual}.")
            return False

        cursor.execute("""UPDATE inventario SET cantidad = cantidad - %s 
                          WHERE producto_nombre = %s AND variante = %s AND sucursal_nombre = %s""", 
                       (cantidad, producto, variante, ubicacion))
        
        total = precio * cantidad
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        sql = """INSERT INTO ventas (fecha, producto, variante, cantidad, precio_unitario, total, metodo_pago, ubicacion, notas, cliente_id) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        cursor.execute(sql, (fecha, producto, variante, cantidad, precio, total, metodo, ubicacion, notas, cliente_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error SQL: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def editar_venta(id_v, old, new):
    return False 

def eliminar_venta(id_venta, datos):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cant = int(datos['CANTIDAD'])
        prod = str(datos['PRODUCTO'])
        ubic = str(datos['UBICACION'])
        var = str(datos.get('VARIANTE', '')) 
        
        cursor.execute("""UPDATE inventario SET cantidad = cantidad + %s 
                          WHERE producto_nombre = %s AND variante = %s AND sucursal_nombre = %s""", 
                       (cant, prod, var, ubic))
        cursor.execute("DELETE FROM ventas WHERE id = %s", (id_venta,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error eliminar: {e}")
        return False
    finally: 
        cursor.close()
        conn.close()

# --- 6. COMPRAS ---
def registrar_compra(producto, variante, cantidad, costo, proveedor, metodo, ubicacion, notas):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("""UPDATE inventario SET cantidad = cantidad + %s 
                          WHERE producto_nombre = %s AND variante = %s AND sucursal_nombre = %s""", 
                       (cantidad, producto, variante, ubicacion))
        if cursor.rowcount == 0:
            cursor.execute("""INSERT INTO inventario (producto_nombre, sucursal_nombre, cantidad, variante) 
                              VALUES (%s, %s, %s, %s)""", (producto, ubicacion, cantidad, variante))
            
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sql = """INSERT INTO compras (fecha, producto, variante, cantidad, costo_total, proveedor, metodo_pago, ubicacion, notas) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        cursor.execute(sql, (fecha, producto, variante, cantidad, costo, proveedor, metodo, ubicacion, notas))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error compra: {e}")
        return False
    finally: 
        cursor.close()
        conn.close()

def eliminar_compra(id_c, datos):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cant = int(datos['CANTIDAD'])
        prod = str(datos['PRODUCTO'])
        ubic = str(datos['UBICACION'])
        var = str(datos.get('VARIANTE', ''))
        
        cursor.execute("""UPDATE inventario SET cantidad = cantidad - %s 
                          WHERE producto_nombre = %s AND variante = %s AND sucursal_nombre = %s""", 
                       (cant, prod, var, ubic))
        cursor.execute("DELETE FROM compras WHERE id = %s", (id_c,))
        conn.commit()
        return True
    except: return False
    finally: 
        cursor.close()
        conn.close()

# --- 7. FINANZAS ---
def obtener_resumen_finanzas():
    conn = get_db_connection()
    try:
        df_v = pd.read_sql("SELECT metodo_pago, SUM(total) as total FROM ventas GROUP BY metodo_pago", conn)
        df_c = pd.read_sql("SELECT metodo_pago, SUM(costo_total) as total FROM compras GROUP BY metodo_pago", conn)
        df_s = pd.read_sql("SELECT cuenta, monto FROM saldos_iniciales", conn)
        return df_v, df_c, df_s
    except: 
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    finally: 
        if conn.is_connected(): 
            conn.close()

def actualizar_saldo_inicial(cuenta, monto):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE saldos_iniciales SET monto=%s WHERE cuenta=%s", (monto, cuenta))
        conn.commit()
        return True
    except: return False
    finally: 
        cursor.close()
        conn.close()