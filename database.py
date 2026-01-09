import mysql.connector
import pandas as pd
import streamlit as st
from datetime import datetime

# --- 1. CONEXIÓN Y AUTO-REPARACIÓN ---
def get_db_connection():
    # Detectar si estamos en la nube o local
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

def asegurar_estructura_db(conn):
    """
    Función de AUTO-CURACIÓN:
    Verifica que las tablas tengan las columnas nuevas (activo, cliente_id, etc).
    Si no están, las crea automáticamente para evitar errores.
    """
    cursor = conn.cursor()
    try:
        # 1. Verificar columna 'activo' en productos
        cursor.execute("SHOW COLUMNS FROM productos LIKE 'activo'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE productos ADD COLUMN activo TINYINT(1) DEFAULT 1")
            cursor.execute("UPDATE productos SET activo = 1") # Activar todos los existentes
            conn.commit()
            print("✅ DB Reparada: Columna 'activo' creada.")

        # 2. Verificar columna 'cliente_id' en ventas
        cursor.execute("SHOW COLUMNS FROM ventas LIKE 'cliente_id'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE ventas ADD COLUMN cliente_id INT DEFAULT NULL")
            conn.commit()
            print("✅ DB Reparada: Columna 'cliente_id' creada.")

    except Exception as e:
        print(f"⚠️ Advertencia de esquema: {e}")
    finally:
        cursor.close()

# --- 2. LECTURA DE DATOS GLOBAL ---
def obtener_datos_globales():
    conn = get_db_connection()
    
    # ¡PASO CRÍTICO! Reparar DB antes de leer
    asegurar_estructura_db(conn)
    
    try:
        # Sucursales
        df_suc = pd.read_sql("SELECT nombre FROM sucursales", conn)
        lista_sucursales = df_suc['nombre'].tolist() if not df_suc.empty else []
        
        # Productos (Ahora seguro existe 'activo')
        try:
            df_prod = pd.read_sql("SELECT nombre as Nombre, costo as Costo, precio as Precio FROM productos WHERE activo=1", conn)
        except:
            # Fallback por si acaso
            df_prod = pd.read_sql("SELECT nombre as Nombre, costo as Costo, precio as Precio FROM productos", conn)
        
        # Ventas (Renombrar SIEMPRE para evitar KeyError: 'ID')
        df_ventas = pd.read_sql("SELECT * FROM ventas ORDER BY fecha DESC", conn)
        columnas_ventas = {
            'id': 'ID', 'fecha': 'FECHA', 'producto': 'PRODUCTO', 
            'cantidad': 'CANTIDAD', 'precio_unitario': 'PRECIO UNITARIO', 
            'total': 'TOTAL', 'metodo_pago': 'METODO PAGO', 
            'ubicacion': 'UBICACION', 'notas': 'NOTAS', 'cliente_id': 'CLIENTE_ID',
            'variante': 'VARIANTE'
        }
        df_ventas = df_ventas.rename(columns=columnas_ventas)
        
        # Compras
        df_compras = pd.read_sql("SELECT * FROM compras ORDER BY fecha DESC", conn)
        columnas_compras = {
            'id': 'ID', 'fecha': 'FECHA', 'producto': 'PRODUCTO', 
            'cantidad': 'CANTIDAD', 'costo_total': 'COSTO', 
            'proveedor': 'PROVEEDOR', 'metodo_pago': 'METODO PAGO', 
            'ubicacion': 'UBICACION', 'notas': 'NOTAS',
            'variante': 'VARIANTE'
        }
        df_compras = df_compras.rename(columns=columnas_compras)

        return df_prod, lista_sucursales, df_ventas, df_compras
    except Exception as e:
        st.error(f"Error crítico leyendo datos: {e}")
        return pd.DataFrame(), [], pd.DataFrame(), pd.DataFrame()
    finally:
        conn.close()

# --- 3. LÓGICA DE STOCK TIPO EXCEL (MATRIZ) ---
def obtener_datos_matrix():
    conn = get_db_connection()
    try:
        sql_prod = "SELECT nombre, costo, precio FROM productos WHERE activo = 1 ORDER BY nombre"
        df_base = pd.read_sql(sql_prod, conn)
        
        sql_stock = "SELECT producto_nombre, variante, sucursal_nombre, cantidad FROM inventario"
        df_stock = pd.read_sql(sql_stock, conn)
        
        df_suc = pd.read_sql("SELECT nombre FROM sucursales ORDER BY nombre", conn)
        sucursales = df_suc['nombre'].tolist() if not df_suc.empty else []

        if df_base.empty: return pd.DataFrame(), sucursales

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
        
        if not df_stock.empty and not df_matrix.empty:
            df_stock['variante'] = df_stock['variante'].fillna('')
            for suc in sucursales:
                col_name = f"{suc}"
                df_matrix[col_name] = 0
                stock_suc = df_stock[df_stock['sucursal_nombre'] == suc]
                stock_map = stock_suc.set_index(['producto_nombre', 'variante'])['cantidad'].to_dict()
                df_matrix[col_name] = df_matrix.apply(lambda row: stock_map.get((row['Producto'], row['Variante']), 0), axis=1)

        return df_matrix, sucursales
    except Exception as e:
        return pd.DataFrame(), []
    finally:
        conn.close()

def guardar_cambios_masivos(df_nuevo, sucursales):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        for index, row in df_nuevo.iterrows():
            prod = row['Producto']
            var = row['Variante'] if row['Variante'] else ""
            nuevo_costo = row['Costo']
            nuevo_precio = row['Precio']
            
            cursor.execute("UPDATE productos SET costo = %s, precio = %s WHERE nombre = %s", (nuevo_costo, nuevo_precio, prod))
            
            for suc in sucursales:
                cantidad = int(row[suc])
                sql_stock = "INSERT INTO inventario (producto_nombre, sucursal_nombre, variante, cantidad) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE cantidad = %s"
                cursor.execute(sql_stock, (prod, suc, var, cantidad, cantidad))
        conn.commit(); return True
    except: return False
    finally: conn.close()

# --- 4. FUNCIONES AUXILIARES FALTANTES (Error AttributeError) ---
def obtener_listas_auxiliares():
    conn = get_db_connection()
    try:
        s = pd.read_sql("SELECT nombre FROM sucursales", conn)['nombre'].tolist()
        p = pd.read_sql("SELECT nombre FROM productos WHERE activo = 1", conn)['nombre'].tolist()
        return s, p
    except: return [], []
    finally: conn.close()

def obtener_variantes_de_producto(producto):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        cursor.execute("SELECT nombre_variante FROM variantes WHERE producto_nombre = %s", (producto,))
        res = cursor.fetchall()
        return [r[0] for r in res] if res else []
    finally: conn.close()

def renombrar_variante(prod, old_var, new_var):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        cursor.execute("UPDATE variantes SET nombre_variante=%s WHERE producto_nombre=%s AND nombre_variante=%s", (new_var, prod, old_var))
        cursor.execute("UPDATE inventario SET variante=%s WHERE producto_nombre=%s AND variante=%s", (new_var, prod, old_var))
        cursor.execute("UPDATE ventas SET variante=%s WHERE producto=%s AND variante=%s", (new_var, prod, old_var))
        cursor.execute("UPDATE compras SET variante=%s WHERE producto=%s AND variante=%s", (new_var, prod, old_var))
        conn.commit(); return True, "Ok"
    except Exception as e: return False, str(e)
    finally: conn.close()

def mover_stock_entre_variantes(prod, suc, var_origen, var_destino, cantidad):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre=%s AND sucursal_nombre=%s AND variante=%s", (cantidad, prod, suc, var_origen))
        cursor.execute("INSERT INTO inventario (producto_nombre, sucursal_nombre, variante, cantidad) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE cantidad = cantidad + %s", (prod, suc, var_destino, cantidad, cantidad))
        conn.commit(); return True
    except: return False
    finally: conn.close()

def borrado_logico_producto(nombre_producto):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        cursor.execute("UPDATE productos SET activo = 0 WHERE nombre = %s", (nombre_producto,))
        conn.commit(); return True
    except: return False
    finally: conn.close()

def crear_producto(nombre, costo, precio):
    conn = get_db_connection(); cursor=conn.cursor()
    try: 
        cursor.execute("INSERT INTO productos (nombre, costo, precio, activo) VALUES (%s, %s, %s, 1)", (nombre, costo, precio))
        conn.commit(); return True
    except: return False
    finally: conn.close()

def crear_variante(prod, var):
    conn = get_db_connection(); cursor=conn.cursor()
    try: 
        cursor.execute("INSERT INTO variantes (producto_nombre, nombre_variante) VALUES (%s, %s)", (prod, var))
        conn.commit(); return True, "Ok"
    except: return False, "Error"
    finally: conn.close()

def obtener_catalogo_venta():
    conn = get_db_connection()
    try:
        return pd.read_sql("SELECT p.nombre, p.precio, v.nombre_variante FROM productos p LEFT JOIN variantes v ON p.nombre = v.producto_nombre WHERE p.activo = 1 ORDER BY p.nombre, v.nombre_variante", conn)
    except: return pd.DataFrame()
    finally: conn.close()

# --- 5. CLIENTES Y FINANZAS (Recuperados) ---
def obtener_clientes_metricas():
    conn = get_db_connection()
    try:
        return pd.read_sql("SELECT c.id, c.nombre, c.ubicacion, COALESCE(SUM(v.total), 0) as total_gastado FROM clientes c LEFT JOIN ventas v ON c.id = v.cliente_id GROUP BY c.id, c.nombre, c.ubicacion ORDER BY total_gastado DESC", conn)
    except: return pd.DataFrame()
    finally: conn.close()

def crear_cliente(n, u):
    conn = get_db_connection(); cursor = conn.cursor()
    try: cursor.execute("INSERT INTO clientes (nombre, ubicacion) VALUES (%s, %s)", (n, u)); conn.commit(); return True
    except: return False
    finally: conn.close()

def obtener_lista_clientes_simple():
    conn = get_db_connection(); cursor = conn.cursor()
    try: cursor.execute("SELECT id, nombre FROM clientes ORDER BY nombre"); return cursor.fetchall()
    except: return []
    finally: conn.close()

def actualizar_cliente(id_c, n, u):
    conn = get_db_connection(); cursor = conn.cursor()
    try: cursor.execute("UPDATE clientes SET nombre=%s, ubicacion=%s WHERE id=%s", (n, u, id_c)); conn.commit(); return True
    except: return False
    finally: conn.close()

def eliminar_cliente(id_c):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        cursor.execute("UPDATE ventas SET cliente_id=NULL WHERE cliente_id=%s", (id_c,))
        cursor.execute("DELETE FROM clientes WHERE id=%s", (id_c,))
        conn.commit(); return True
    except: return False
    finally: conn.close()

def obtener_resumen_finanzas():
    conn = get_db_connection()
    try:
        df_v = pd.read_sql("SELECT metodo_pago, SUM(total) as total FROM ventas GROUP BY metodo_pago", conn)
        df_c = pd.read_sql("SELECT metodo_pago, SUM(costo_total) as total FROM compras GROUP BY metodo_pago", conn)
        df_s = pd.read_sql("SELECT cuenta, monto FROM saldos_iniciales", conn)
        return df_v, df_c, df_s
    except: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    finally: conn.close()

def actualizar_saldo_inicial(c, m):
    conn = get_db_connection(); cursor = conn.cursor()
    try: cursor.execute("UPDATE saldos_iniciales SET monto=%s WHERE cuenta=%s", (m, c)); conn.commit(); return True
    except: return False
    finally: conn.close()

# --- 6. TRANSACCIONES ---
def registrar_venta(producto, variante, cantidad, precio, metodo, ubicacion, notas, cliente_id):
    conn = get_db_connection(); cursor=conn.cursor()
    try:
        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre=%s AND variante=%s AND sucursal_nombre=%s", (cantidad, producto, variante, ubicacion))
        cursor.execute("INSERT INTO ventas (fecha, producto, variante, cantidad, precio_unitario, total, metodo_pago, ubicacion, notas, cliente_id) VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s)", (producto, variante, cantidad, precio, precio*cantidad, metodo, ubicacion, notas, cliente_id))
        conn.commit(); return True
    except: return False
    finally: conn.close()

def registrar_compra(producto, variante, cantidad, costo, proveedor, metodo, ubicacion, notas):
    conn = get_db_connection(); cursor=conn.cursor()
    try:
        cursor.execute("INSERT INTO inventario (producto_nombre, sucursal_nombre, variante, cantidad) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE cantidad = cantidad + %s", (producto, ubicacion, variante, cantidad, cantidad))
        cursor.execute("INSERT INTO compras (fecha, producto, variante, cantidad, costo_total, proveedor, metodo_pago, ubicacion, notas) VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s)", (producto, variante, cantidad, costo, proveedor, metodo, ubicacion, notas))
        conn.commit(); return True
    except: return False
    finally: conn.close()

def eliminar_venta(id_v, d):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        cursor.execute("UPDATE inventario SET cantidad = cantidad + %s WHERE producto_nombre=%s AND variante=%s AND sucursal_nombre=%s", (int(d['CANTIDAD']), str(d['PRODUCTO']), str(d.get('VARIANTE','')), str(d['UBICACION'])))
        cursor.execute("DELETE FROM ventas WHERE id=%s", (id_v,))
        conn.commit(); return True
    except: return False
    finally: conn.close()

def eliminar_compra(id_c, d):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre=%s AND variante=%s AND sucursal_nombre=%s", (int(d['CANTIDAD']), str(d['PRODUCTO']), str(d.get('VARIANTE','')), str(d['UBICACION'])))
        cursor.execute("DELETE FROM compras WHERE id=%s", (id_c,))
        conn.commit(); return True
    except: return False
    finally: conn.close()

def obtener_venta_por_id(id_v):
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try: cursor.execute("SELECT * FROM ventas WHERE id=%s", (id_v,)); return cursor.fetchone()
    finally: conn.close()

def actualizar_venta(id_v, nc, np, nm, nn):
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        # CORRECCIÓN: Cambiamos 'sucursal_nombre' por 'ubicacion' que es el nombre real en la tabla ventas
        cursor.execute("SELECT producto, variante, ubicacion, cantidad FROM ventas WHERE id=%s", (id_v,))
        row = cursor.fetchone()
        
        if not row: return False, "No existe la venta"
        
        # Datos actuales en la base de datos
        prod_db = row[0]
        var_db = row[1] if row[1] else ''
        suc_db = row[2] # Aquí recibimos la ubicación correctamente
        cant_old = row[3]
        
        # Calculamos la diferencia para ajustar el stock
        # Si vendí 1 y ahora pongo 3, la diferencia es +2 (tengo que restar 2 más al stock)
        # Si vendí 3 y ahora pongo 1, la diferencia es -2 (tengo que devolver 2 al stock)
        diff = nc - cant_old
        
        # Actualizamos el inventario (Aquí sí se llama 'sucursal_nombre')
        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre=%s AND variante=%s AND sucursal_nombre=%s", 
                       (diff, prod_db, var_db, suc_db))
        
        # Actualizamos la venta con los nuevos datos
        cursor.execute("UPDATE ventas SET cantidad=%s, precio_unitario=%s, total=%s, metodo_pago=%s, notas=%s WHERE id=%s", 
                       (nc, np, nc*np, nm, nn, id_v))
        
        conn.commit()
        return True, "Ok"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()
# --- AGREGAR AL FINAL DE database.py (PARA COMPRAS) ---

def obtener_compra_por_id(id_c):
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM compras WHERE id = %s", (id_c,))
        return cursor.fetchone()
    finally:
        if conn.is_connected(): conn.close()

def actualizar_compra(id_compra, nueva_cant, nuevo_costo, nuevo_prov, nuevo_metodo, nuevas_notas):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Obtener datos viejos (CORREGIDO: Usamos 'ubicacion' y quitamos 'sucursal_nombre' que no existe)
        cursor.execute("SELECT producto, variante, ubicacion, cantidad FROM compras WHERE id = %s", (id_compra,))
        row = cursor.fetchone()
        
        if not row: return False, "Compra no encontrada"
        
        # Desempaquetamos los 4 valores correctos
        prod, var, suc, old_cant = row
        var = var if var else ""
        
        # 2. Calcular diferencia de Stock (Nuevo - Viejo)
        diferencia = nueva_cant - old_cant
        
        # 3. Validación de Seguridad
        # Si estamos reduciendo la compra (ej: corregir de 10 a 5), verificar que tengamos ese stock para "devolver"
        if diferencia < 0:
            cursor.execute("SELECT cantidad FROM inventario WHERE producto_nombre=%s AND variante=%s AND sucursal_nombre=%s", (prod, var, suc))
            res = cursor.fetchone()
            stock_actual = res[0] if res else 0
            
            if stock_actual < abs(diferencia):
                return False, f"No puedes reducir {abs(diferencia)} u. porque solo quedan {stock_actual} en stock (ya se vendieron)."

        # 4. Actualizar Inventario (Usamos 'sucursal_nombre' porque así se llama en la tabla inventario)
        cursor.execute("""
            UPDATE inventario SET cantidad = cantidad + %s 
            WHERE producto_nombre=%s AND variante=%s AND sucursal_nombre=%s
        """, (diferencia, prod, var, suc))
        
        # 5. Actualizar Registro Compra
        sql_upd = """
            UPDATE compras 
            SET cantidad=%s, costo_total=%s, proveedor=%s, metodo_pago=%s, notas=%s
            WHERE id=%s
        """
        cursor.execute(sql_upd, (nueva_cant, nuevo_costo, nuevo_prov, nuevo_metodo, nuevas_notas, id_compra))
        
        conn.commit()
        return True, "Compra corregida exitosamente."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cursor.close()
        conn.close()
        
# --- EN database.py ---

def obtener_stock_actual(producto, sucursal, variante=""):
    """
    Obtiene la cantidad disponible de un producto/variante en una sucursal específica.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Aseguramos que variante no sea None para la consulta
        variante = variante if variante else ""
        
        sql = """
        SELECT cantidad FROM inventario 
        WHERE producto_nombre = %s AND sucursal_nombre = %s AND variante = %s
        """
        cursor.execute(sql, (producto, sucursal, variante))
        result = cursor.fetchone()
        
        return result[0] if result else 0
    except Exception as e:
        print(f"Error consultando stock: {e}")
        return 0
    finally:
        conn.close()