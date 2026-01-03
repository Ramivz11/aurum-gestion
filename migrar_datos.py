import streamlit as st
import pandas as pd
import mysql.connector
from datetime import datetime
import time

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Aurum Suplementos", page_icon="logo.png", layout="wide")

# --- CONEXIÓN MYSQL ---
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="aurum_db"
    )

# --- FUNCIONES DE LECTURA ---
def obtener_datos():
    conn = get_db_connection()
    try:
        # 1. Sucursales
        df_suc = pd.read_sql("SELECT nombre FROM sucursales", conn)
        lista_sucursales = df_suc['nombre'].tolist() if not df_suc.empty else []
        
        # 2. Productos y Stock (Pivot)
        df_prod_base = pd.read_sql("SELECT nombre as Nombre, costo as Costo, precio as Precio FROM productos", conn)
        df_stock = pd.read_sql("SELECT producto_nombre, sucursal_nombre, cantidad FROM inventario", conn)
        
        if not df_stock.empty:
            pivot_stock = df_stock.pivot(index='producto_nombre', columns='sucursal_nombre', values='cantidad').fillna(0)
            pivot_stock.columns = [f"Stock_{col}" for col in pivot_stock.columns]
            df_prod = pd.merge(df_prod_base, pivot_stock, left_on='Nombre', right_index=True, how='left').fillna(0)
        else:
            df_prod = df_prod_base
            
        # 3. Ventas
        df_ventas = pd.read_sql("SELECT * FROM ventas ORDER BY fecha DESC", conn)
        df_ventas = df_ventas.rename(columns={
            'id': 'ID', 'fecha': 'FECHA', 'producto': 'PRODUCTO', 
            'cantidad': 'CANTIDAD', 'precio_unitario': 'PRECIO UNITARIO', 
            'total': 'TOTAL', 'metodo_pago': 'METODO PAGO', 
            'ubicacion': 'UBICACION', 'notas': 'NOTAS'
        })
        
        return df_prod, lista_sucursales, df_ventas
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return pd.DataFrame(), [], pd.DataFrame()
    finally:
        conn.close()

# --- FUNCIONES DE ESCRITURA (SQL) ---

def registrar_venta_db(producto, cantidad, precio, metodo, ubicacion, notas):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True) # Buffered ayuda a evitar errores de lectura pendiente
    try:
        # Desactivar modo seguro temporalmente para permitir updates por nombre
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        
        # Verificar Stock
        cursor.execute("SELECT cantidad FROM inventario WHERE producto_nombre = %s AND sucursal_nombre = %s", (producto, ubicacion))
        res = cursor.fetchone()
        stock_actual = res[0] if res else 0
        
        if stock_actual < cantidad:
            st.error(f"⚠️ Stock insuficiente en {ubicacion}. Hay {stock_actual}.")
            return False

        # Actualizar Stock y Registrar Venta
        cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre = %s AND sucursal_nombre = %s", (cantidad, producto, ubicacion))
        
        total = precio * cantidad
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sql = "INSERT INTO ventas (fecha, producto, cantidad, precio_unitario, total, metodo_pago, ubicacion, notas) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        cursor.execute(sql, (fecha, producto, cantidad, precio, total, metodo, ubicacion, notas))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"❌ Error SQL al registrar: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def editar_venta_db(id_venta, datos_old, datos_new):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        
        # 1. Devolver Stock de la venta original
        cursor.execute("UPDATE inventario SET cantidad = cantidad + %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                       (datos_old['CANTIDAD'], datos_old['PRODUCTO'], datos_old['UBICACION']))
        
        # 2. Verificar Stock para la nueva modificación
        cursor.execute("SELECT cantidad FROM inventario WHERE producto_nombre = %s AND sucursal_nombre = %s", (datos_new['producto'], datos_new['ubicacion']))
        res = cursor.fetchone()
        stock_disp = res[0] if res else 0
        
        if stock_disp < datos_new['cantidad']:
            # Rollback manual si falla la validación
            cursor.execute("UPDATE inventario SET cantidad = cantidad - %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                           (datos_old['CANTIDAD'], datos_old['PRODUCTO'], datos_old['UBICACION']))
            conn.commit()
            st.error(f"⚠️ Stock insuficiente para el cambio. Disponible real: {stock_disp}")
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
        st.error(f"❌ Error al editar: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def eliminar_venta_db(id_venta, datos_venta):
    conn = get_db_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        
        # 1. Devolver Stock
        cursor.execute("UPDATE inventario SET cantidad = cantidad + %s WHERE producto_nombre = %s AND sucursal_nombre = %s", 
                       (datos_venta['CANTIDAD'], datos_venta['PRODUCTO'], datos_venta['UBICACION']))
        
        # 2. Eliminar registro
        cursor.execute("DELETE FROM ventas WHERE id = %s", (id_venta,))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"❌ Error al eliminar: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

# --- INTERFAZ ---
st.sidebar.image("logo.png", width=200) # Comenta si no tienes la imagen
st.sidebar.title("Aurum Gestión SQL")
menu = st.sidebar.radio("Navegación", ["Registrar Venta", "Historial y Edición", "Inventario"])

# Carga inicial de datos
df_prod, sucursales, df_ventas = obtener_datos()

if menu == "Registrar Venta":
    st.title("💸 Nueva Venta")
    if not sucursales:
        st.warning("Carga sucursales en la base de datos primero.")
    else:
        c1, c2 = st.columns(2)
        prod_sel = c1.selectbox("Producto", sorted(df_prod['Nombre'].unique()) if not df_prod.empty else [])
        suc_sel = c2.selectbox("Sucursal", sucursales)
        
        if prod_sel:
            row_prod = df_prod[df_prod['Nombre'] == prod_sel].iloc[0]
            precio_sug = float(row_prod['Precio'])
            stock_disp = int(row_prod.get(f"Stock_{suc_sel}", 0))
            
            m1, m2 = st.columns(2)
            m1.metric("Precio Lista", f"${precio_sug:,.0f}")
            m2.metric(f"Stock {suc_sel}", f"{stock_disp} u.")
            
            with st.form("venta_form"):
                col_f1, col_f2 = st.columns(2)
                cant = col_f1.number_input("Cantidad", min_value=1, value=1)
                precio = col_f2.number_input("Precio Final", value=precio_sug)
                metodo = st.radio("Pago", ["Efectivo", "Transferencia"], horizontal=True)
                notas = st.text_input("Notas")
                
                if st.form_submit_button("✅ VENDER", type="primary", use_container_width=True):
                    if stock_disp < cant:
                        st.error("❌ Stock insuficiente.")
                    else:
                        if registrar_venta_db(prod_sel, cant, precio, metodo, suc_sel, notas):
                            st.success("Venta registrada!")
                            time.sleep(1)
                            st.rerun()

elif menu == "Historial y Edición":
    st.title("📜 Historial de Ventas")
    
    # Filtros
    fc1, fc2, fc3 = st.columns(3)
    f_suc = fc1.selectbox("Filtrar Sucursal", ["Todas"] + sucursales)
    f_prod = fc2.selectbox("Filtrar Producto", ["Todos"] + (sorted(df_prod['Nombre'].unique().tolist()) if not df_prod.empty else []))
    
    df_show = df_ventas.copy()
    if f_suc != "Todas": df_show = df_show[df_show['UBICACION'] == f_suc]
    if f_prod != "Todos": df_show = df_show[df_show['PRODUCTO'] == f_prod]
    
    st.dataframe(df_show, use_container_width=True, hide_index=True)
    st.divider()
    
    # Pestañas Editar / Eliminar
    tab1, tab2 = st.tabs(["✏️ Editar Venta", "🗑️ Eliminar Venta"])
    
    # Selector de venta (común para ambas pestañas)
    opciones_venta = df_show.apply(lambda x: f"ID {x['ID']} | {x['PRODUCTO']} | {x['FECHA']}", axis=1).tolist()
    
    if not opciones_venta:
        st.info("No hay ventas visibles para modificar.")
    else:
        # --- PESTAÑA EDITAR ---
        with tab1:
            sel_edit = st.selectbox("Selecciona venta a editar", opciones_venta, key="sel_edit")
            id_edit = int(sel_edit.split(" | ")[0].replace("ID ", ""))
            
            # Recuperar datos de manera segura
            if id_edit in df_ventas['ID'].values:
                row_edit = df_ventas[df_ventas['ID'] == id_edit].iloc[0]
                
                with st.form("form_editar"):
                    st.caption(f"Editando Venta ID: {id_edit}")
                    ec1, ec2 = st.columns(2)
                    
                    # Pre-cargar valores actuales con manejo de errores si el producto cambió de nombre
                    prod_options = df_prod['Nombre'].unique()
                    curr_prod_idx = list(prod_options).index(row_edit['PRODUCTO']) if row_edit['PRODUCTO'] in prod_options else 0
                    
                    curr_suc_idx = sucursales.index(row_edit['UBICACION']) if row_edit['UBICACION'] in sucursales else 0
                    
                    new_prod = ec1.selectbox("Producto", prod_options, index=curr_prod_idx)
                    new_suc = ec2.selectbox("Sucursal", sucursales, index=curr_suc_idx)
                    
                    ec3, ec4 = st.columns(2)
                    new_cant = ec3.number_input("Cantidad", value=int(row_edit['CANTIDAD']), min_value=1)
                    new_precio = ec4.number_input("Precio Unitario", value=float(row_edit['PRECIO UNITARIO']))
                    
                    pagos = ["Efectivo", "Transferencia"]
                    idx_pago = pagos.index(row_edit['METODO PAGO']) if row_edit['METODO PAGO'] in pagos else 0
                    new_pago = st.selectbox("Pago", pagos, index=idx_pago)
                    
                    new_notas = st.text_input("Notas", value=str(row_edit['NOTAS']) if row_edit['NOTAS'] else "")
                    
                    if st.form_submit_button("💾 GUARDAR CAMBIOS"):
                        datos_new = {
                            'producto': new_prod, 'cantidad': new_cant, 'precio': new_precio,
                            'ubicacion': new_suc, 'metodo': new_pago, 'notas': new_notas
                        }
                        if editar_venta_db(id_edit, row_edit, datos_new):
                            st.success("¡Venta actualizada correctamente!")
                            time.sleep(1)
                            st.rerun()
            else:
                st.warning("La venta seleccionada no se encuentra en la base de datos actual.")

        # --- PESTAÑA ELIMINAR ---
        with tab2:
            sel_del = st.selectbox("Selecciona venta a eliminar", opciones_venta, key="sel_del")
            id_del = int(sel_del.split(" | ")[0].replace("ID ", ""))
            
            if id_del in df_ventas['ID'].values:
                row_del = df_ventas[df_ventas['ID'] == id_del].iloc[0]
                
                st.error(f"¿Estás seguro de eliminar la venta de **{row_del['PRODUCTO']}** ({row_del['CANTIDAD']} u.)?")
                st.caption("⚠️ Esta acción devolverá el stock a la sucursal automáticamente.")
                
                if st.button("🗑️ SÍ, ELIMINAR VENTA", type="primary"):
                    if eliminar_venta_db(id_del, row_del):
                        st.success("Venta eliminada y stock restaurado.")
                        time.sleep(1)
                        st.rerun()

elif menu == "Inventario":
    st.title("📦 Inventario Global")
    st.dataframe(df_prod, use_container_width=True, hide_index=True)