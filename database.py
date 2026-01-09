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

# ==========================================
#      NUEVA LÓGICA DE STOCK (MATRIZ)
# ==========================================

def obtener_datos_matrix():
    """Obtiene un DataFrame formateado para edición tipo Excel"""
    conn = get_db_connection()
    try:
        # 1. Productos Base (Solo activos)
        # IMPORTANTE: Aquí se usa la columna 'activo' que acabamos de crear
        sql_prod = "SELECT nombre, costo, precio FROM productos WHERE activo = 1 ORDER BY nombre"
        df_base = pd.read_sql(sql_prod, conn)
        
        # 2. Stock (Inventario)
        sql_stock = "SELECT producto_nombre, variante, sucursal_nombre, cantidad FROM inventario"
        df_stock = pd.read_sql(sql_stock, conn)
        
        # 3. Sucursales
        df_suc = pd.read_sql("SELECT nombre FROM sucursales ORDER BY nombre", conn)
        sucursales = df_suc['nombre'].tolist() if not df_suc.empty else []

        if df_base.empty:
            return pd.DataFrame(), sucursales

        # --- CONSTRUCCIÓN DE LA MATRIZ ---
        df_vars = pd.read_sql("SELECT producto_nombre, nombre_variante FROM variantes", conn)
        
        lista_skus = []
        for _, prod in df_base.iterrows():
            nombre = prod['nombre']
            variantes_prod = df_vars[df_vars['producto_nombre'] == nombre]['nombre_variante'].tolist()
            
            if not variantes_prod:
                lista_skus.append({'Producto': nombre, 'Variante': '', 'Costo': prod['costo'], 'Precio': prod['precio']})
            else:
                for v in variantes_prod:
                    lista_skus.append({'Producto': nombre, 'Variante': v, 'Costo': prod['costo'], 'Precio': prod['precio']})
        
        df_matrix = pd.DataFrame(lista_skus)
        
        # Pegar Stock
        if not df_stock.empty and not df_matrix.empty:
            df_stock['variante'] = df_stock['variante'].fillna('')
            for suc in sucursales:
                col_name = f"{suc}"
                df_matrix[col_name] = 0
                stock_suc = df_stock[df_stock['sucursal_nombre'] == suc]
                # Crear diccionario para mapeo rápido
                stock_map = stock_suc.set_index(['producto_nombre', 'variante'])['cantidad'].to_dict()
                
                def get_qty(row):
                    return stock_map.get((row['Producto'], row['Variante']), 0)
                
                df_matrix[col_name] = df_matrix.apply(get_qty, axis=1)

        return df_matrix, sucursales
    except Exception as e:
        # Si falla, devolvemos vacío para no romper la app
        print(f"Error matrix: {e}")
        return pd.DataFrame(), []
    finally:
        if conn.is_connected(): conn.close()

def guardar_cambios_masivos(df_nuevo, sucursales):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for index, row in df_nuevo.iterrows():
            prod = row['Producto']
            var = row['Variante'] if row['Variante'] else ""
            nuevo_costo = row['Costo']
            nuevo_precio = row['Precio']
            
            cursor.execute("UPDATE productos SET costo = %s, precio = %s WHERE nombre = %s", (nuevo_costo, nuevo_precio, prod))
            
            for suc in sucursales:
                cantidad = int(row[suc])
                sql_stock = """
                    INSERT INTO inventario (producto_nombre, sucursal_nombre, variante, cantidad)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE cantidad = %s
                """
                cursor.execute(sql_stock, (prod, suc, var, cantidad, cantidad))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error al guardar: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def obtener_listas_auxiliares():
    conn = get_db_connection()
    try:
        sucursales = pd.read_sql("SELECT nombre FROM sucursales", conn)['nombre'].tolist()
        productos = pd.read_sql("SELECT nombre FROM productos WHERE activo = 1", conn)['nombre'].tolist()
        return sucursales, productos
    finally:
        conn.close()

def obtener_variantes_de_producto(producto):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT nombre_variante FROM variantes WHERE producto_nombre = %s", (producto,))
        res = cursor.fetchall()
        return [r[0] for r in res] if res else []
    finally:
        conn.close()

def renombrar_variante(prod, old_var, new_var):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM variantes WHERE producto_nombre=%s AND nombre_variante=%s", (prod, new_var))
        if cursor.fetchone(): return False, "El nombre ya existe."
        
        cursor.execute("UPDATE variantes SET nombre_variante=%s WHERE producto_nombre=%s AND nombre_variante=%s", (new_var, prod, old_var))
        
        tablas = ['inventario', 'ventas', 'compras']
        for t in tablas:
            try:
                col_prod = 'producto_nombre' if t == 'inventario' else 'producto'
                sql = f"UPDATE {t} SET variante=%s WHERE {col_prod}=%s AND variante=%s"
                cursor.execute(sql, (new_var, prod, old_var))
            except: pass
            
        conn.commit()
        return True, "Renombrado exitoso."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def mover_stock_entre_variantes(prod, suc, var_origen, var_destino, cantidad):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre=%s AND sucursal_nombre=%s AND variante=%s", (cantidad, prod, suc, var_origen))
        cursor.execute("""
            INSERT INTO inventario (producto_nombre, sucursal_nombre, variante, cantidad)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE cantidad = cantidad + %s
        """, (prod, suc, var_destino, cantidad, cantidad))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        return False
    finally:
        conn.close()

def borrado_logico_producto(nombre_producto):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE productos SET activo = 0 WHERE nombre = %s", (nombre_producto,))
        conn.commit()
        return True
    except: return False
    finally: conn.close()

# ==========================================
#      COMPATIBILIDAD (Renombrado de Columnas)
# ==========================================

def obtener_datos_globales():
    """Esta función es CRÍTICA para evitar el KeyError: 'ID'"""
    conn = get_db_connection()
    try:
        # Sucursales
        df_suc = pd.read_sql("SELECT nombre FROM sucursales", conn)
        lista_sucursales = df_suc['nombre'].tolist() if not df_suc.empty else []
        
        # Productos Base (Para precios)
        # Nota: Usamos activo=1, si falla es porque no corriste la migración del PASO 1
        df_prod = pd.read_sql("SELECT nombre as Nombre, costo as Costo, precio as Precio FROM productos WHERE activo=1", conn)
        
        # Ventas (¡RENOMBRAMOS A MAYÚSCULAS!)
        df_ventas = pd.read_sql("SELECT * FROM ventas ORDER BY fecha DESC", conn)
        df_ventas = df_ventas.rename(columns={
            'id': 'ID', 'fecha': 'FECHA', 'producto': 'PRODUCTO', 
            'cantidad': 'CANTIDAD', 'precio_unitario': 'PRECIO UNITARIO', 
            'total': 'TOTAL', 'metodo_pago': 'METODO PAGO', 
            'ubicacion': 'UBICACION', 'notas': 'NOTAS', 'cliente_id': 'CLIENTE_ID',
            'variante': 'VARIANTE'
        })
        
        # Compras (¡RENOMBRAMOS A MAYÚSCULAS!)
        df_compras = pd.read_sql("SELECT * FROM compras ORDER BY fecha DESC", conn)
        df_compras = df_compras.rename(columns={
            'id': 'ID', 'fecha': 'FECHA', 'producto': 'PRODUCTO', 
            'cantidad': 'CANTIDAD', 'costo_total': 'COSTO', 
            'proveedor': 'PROVEEDOR', 'metodo_pago': 'METODO PAGO', 
            'ubicacion': 'UBICACION', 'notas': 'NOTAS',
            'variante': 'VARIANTE'
        })

        return df_prod, lista_sucursales, df_ventas, df_compras
    except Exception as e:
        st.error(f"Error datos globales: {e}")
        return pd.DataFrame(), [], pd.DataFrame(), pd.DataFrame()
    finally:
        conn.close()

def obtener_catalogo_venta():
    conn = get_db_connection()
    try:
        sql = """
        SELECT p.nombre, p.precio, v.nombre_variante 
        FROM productos p
        LEFT JOIN variantes v ON p.nombre = v.producto_nombre
        WHERE p.activo = 1
        ORDER BY p.nombre, v.nombre_variante
        """
        return pd.read_sql(sql, conn)
    except: return pd.DataFrame()
    finally: conn.close()

# ==========================================
#      CLIENTES (Recuperado)
# ==========================================

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
    except: return pd.DataFrame()
    finally: conn.close()

def crear_cliente(nombre, ubicacion):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO clientes (nombre, ubicacion) VALUES (%s, %s)", (nombre, ubicacion))
        conn.commit(); return True
    except: return False
    finally: conn.close()

def obtener_lista_clientes_simple():
    conn = get_db_connection(); cursor = conn.cursor()
    try: cursor.execute("SELECT id, nombre FROM clientes ORDER BY nombre"); return cursor.fetchall()
    except: return []
    finally: conn.close()

def actualizar_cliente(id_c, nom, loc):
    conn = get_db_connection(); cursor = conn.cursor()
    try: cursor.execute("UPDATE clientes SET nombre=%s, ubicacion=%s WHERE id=%s", (nom, loc, id_c)); conn.commit(); return True
    except: return False
    finally: conn.close()

def eliminar_cliente(id_c):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        cursor.execute("UPDATE ventas SET cliente_id = NULL WHERE cliente_id = %s", (id_c,))
        cursor.execute("DELETE FROM clientes WHERE id = %s", (id_c,))
        conn.commit(); return True
    except: return False
    finally: conn.close()

# ==========================================
#      FINANZAS (Recuperado)
# ==========================================

def obtener_resumen_finanzas():
    conn = get_db_connection()
    try:
        df_v = pd.read_sql("SELECT metodo_pago, SUM(total) as total FROM ventas GROUP BY metodo_pago", conn)
        df_c = pd.read_sql("SELECT metodo_pago, SUM(costo_total) as total FROM compras GROUP BY metodo_pago", conn)
        df_s = pd.read_sql("SELECT cuenta, monto FROM saldos_iniciales", conn)
        return df_v, df_c, df_s
    except: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    finally: conn.close()

def actualizar_saldo_inicial(cuenta, monto):
    conn = get_db_connection(); cursor = conn.cursor()
    try: cursor.execute("UPDATE saldos_iniciales SET monto=%s WHERE cuenta=%s", (monto, cuenta)); conn.commit(); return True
    except: return False
    finally: conn.close()

# ==========================================
#      TRANSACCIONES (Restauradas y Mejoradas)
# ==========================================

def crear_producto(nombre, costo, precio):
    conn = get_db_connection(); cursor=conn.cursor()
    try: cursor.execute("INSERT INTO productos (nombre, costo, precio, activo) VALUES (%s, %s, %s, 1)", (nombre, costo, precio)); conn.commit(); return True
    except: return False
    finally: conn.close()

def crear_variante(prod, var):
    conn = get_db_connection(); cursor=conn.cursor()
    try: cursor.execute("INSERT INTO variantes (producto_nombre, nombre_variante) VALUES (%s, %s)", (prod, var)); conn.commit(); return True, "Ok"
    except Exception as e: return False, str(e)
    finally: conn.close()

def registrar_venta(producto, variante, cantidad, precio, metodo, ubicacion, notas, cliente_id):
    conn = get_db_connection(); cursor=conn.cursor()
    try:
        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre=%s AND variante=%s AND sucursal_nombre=%s", (cantidad, producto, variante, ubicacion))
        sql = "INSERT INTO ventas (fecha, producto, variante, cantidad, precio_unitario, total, metodo_pago, ubicacion, notas, cliente_id) VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        cursor.execute(sql, (producto, variante, cantidad, precio, precio*cantidad, metodo, ubicacion, notas, cliente_id))
        conn.commit(); return True
    except Exception as e: print(e); return False
    finally: conn.close()

def registrar_compra(producto, variante, cantidad, costo, proveedor, metodo, ubicacion, notas):
    conn = get_db_connection(); cursor=conn.cursor()
    try:
        sql_st = "INSERT INTO inventario (producto_nombre, sucursal_nombre, variante, cantidad) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE cantidad = cantidad + %s"
        cursor.execute(sql_st, (producto, ubicacion, variante, cantidad, cantidad))
        sql = "INSERT INTO compras (fecha, producto, variante, cantidad, costo_total, proveedor, metodo_pago, ubicacion, notas) VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s)"
        cursor.execute(sql, (producto, variante, cantidad, costo, proveedor, metodo, ubicacion, notas))
        conn.commit(); return True
    except: return False
    finally: conn.close()

def eliminar_venta(id_venta, datos):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        cant = int(datos['CANTIDAD']); prod = str(datos['PRODUCTO']); ubic = str(datos['UBICACION']); var = str(datos.get('VARIANTE', '')) 
        cursor.execute("UPDATE inventario SET cantidad = cantidad + %s WHERE producto_nombre = %s AND variante = %s AND sucursal_nombre = %s", (cant, prod, var, ubic))
        cursor.execute("DELETE FROM ventas WHERE id = %s", (id_venta,))
        conn.commit(); return True
    except: return False
    finally: conn.close()

def eliminar_compra(id_c, datos):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        cant = int(datos['CANTIDAD']); prod = str(datos['PRODUCTO']); ubic = str(datos['UBICACION']); var = str(datos.get('VARIANTE', ''))
        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre = %s AND variante = %s AND sucursal_nombre = %s", (cant, prod, var, ubic))
        cursor.execute("DELETE FROM compras WHERE id = %s", (id_c,))
        conn.commit(); return True
    except: return False
    finally: conn.close()

# --- EDICIÓN DE VENTAS (NECESARIO PARA TU BOTÓN DE EDITAR) ---
def obtener_venta_por_id(id_venta):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM ventas WHERE id = %s", (id_venta,))
        return cursor.fetchone()
    finally: conn.close()

def actualizar_venta(id_venta, nueva_cant, nuevo_precio, nuevo_metodo, nuevas_notas):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        cursor.execute("SELECT producto, variante, sucursal_nombre, cantidad, ubicacion FROM ventas WHERE id = %s", (id_venta,))
        row = cursor.fetchone()
        if not row: return False, "Venta no encontrada"
        
        prod, var, _, old_cant, suc = row
        var = var if var else ""
        diferencia = nueva_cant - old_cant
        
        if diferencia > 0:
            cursor.execute("SELECT cantidad FROM inventario WHERE producto_nombre=%s AND variante=%s AND sucursal_nombre=%s", (prod, var, suc))
            stock_res = cursor.fetchone()
            stock_actual = stock_res[0] if stock_res else 0
            if stock_actual < diferencia: return False, f"Sin stock suficiente."

        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre=%s AND variante=%s AND sucursal_nombre=%s", (diferencia, prod, var, suc))
        nuevo_total = nueva_cant * nuevo_precio
        sql_update = "UPDATE ventas SET cantidad=%s, precio_unitario=%s, total=%s, metodo_pago=%s, notas=%s WHERE id=%s"
        cursor.execute(sql_update, (nueva_cant, nuevo_precio, nuevo_total, nuevo_metodo, nuevas_notas, id_venta))
        
        conn.commit()
        return True, "Venta actualizada."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally: conn.close()