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
        


def registrar_compra_db(producto, cantidad, costo, proveedor, ubicacion, notas):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Aumentar Stock (Si el producto no existe en esa sucursal, lo crea)
        # Primero intentamos actualizar
        cursor.execute("""
            UPDATE inventario 
            SET cantidad = cantidad + %s 
            WHERE producto_nombre = %s AND sucursal_nombre = %s
        """, (cantidad, producto, ubicacion))
        
        # Si no se actualizó ninguna fila (rowcount=0), es porque no existía en esa sucursal -> Insertamos
        if cursor.rowcount == 0:
            cursor.execute("""
                INSERT INTO inventario (producto_nombre, sucursal_nombre, cantidad)
                VALUES (%s, %s, %s)
            """, (producto, ubicacion, cantidad))

        # 2. Registrar la Compra (Salida de dinero / Gasto)
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO compras (fecha, producto, cantidad, costo_total, proveedor, ubicacion, notas)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (fecha, producto, cantidad, costo, proveedor, ubicacion, notas))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"❌ Error SQL al registrar compra: {e}")
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
st.sidebar.title("Aurum Gestión ")
menu = st.sidebar.radio("Navegación", ["Registrar Venta", "Registrar Compra", "Movimientos", "Stock", "Finanzas"])# Carga inicial de datos
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
            
            # --- MODIFICACIÓN PARA ALERTA VISUAL ---
            if stock_disp > 0:
                # Si hay stock, se muestra verde o normal
                m2.metric(f"Stock {suc_sel}", f"{stock_disp} u.", delta="Disponible")
            else:
                # Si NO hay stock, muestra la cruz y el texto en rojo (gracias a delta_color="inverse")
                m2.metric(f"Stock {suc_sel}", "❌ AGOTADO", delta="- Sin Stock", delta_color="inverse")
            # ---------------------------------------
            
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
elif menu == "Registrar Compra":
    st.title("📦 Ingreso de Mercadería (Compras)")

    if not sucursales:
        st.warning("Carga sucursales primero.")
    else:
        c1, c2 = st.columns(2)
        # Nota: Aquí usamos los productos ya definidos. Si es uno NUEVO de nombre, 
        # idealmente deberías agregarlo a la tabla 'productos' primero.
        prod_compra = c1.selectbox("Producto a reponer", sorted(df_prod['Nombre'].unique()) if not df_prod.empty else [])
        suc_compra = c2.selectbox("Destino (Sucursal)", sucursales)

        with st.form("compra_form"):
            col_c1, col_c2 = st.columns(2)
            cant_compra = col_c1.number_input("Cantidad Comprada", min_value=1, value=10)
            costo_total = col_c2.number_input("Costo Total de la Compra ($)", min_value=0.0, step=100.0)

            col_c3, col_c4 = st.columns(2)
            proveedor = col_c3.text_input("Proveedor (Opcional)")
            notas_compra = col_c4.text_input("Notas / Nro Factura")

            if st.form_submit_button("📥 REGISTRAR INGRESO", type="primary", use_container_width=True):
                if registrar_compra_db(prod_compra, cant_compra, costo_total, proveedor, suc_compra, notas_compra):
                    st.success(f"✅ ¡Ingreso registrado! Se sumaron {cant_compra} u. a {suc_compra}")
                    time.sleep(1.5)
                    st.rerun()

elif menu == "Movimientos":
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

elif menu == "Stock":
    st.title("📦 Inventario Global")
    st.dataframe(df_prod, use_container_width=True, hide_index=True)

elif menu == "Finanzas":
    st.title("Tablero de finanzas 💰")
    
    conn = get_db_connection()
    
    # --- 1. PRIMERO CALCULAMOS EL FLUJO (Ventas y Compras) ---
    # Necesitamos estos datos ANTES del formulario para poder hacer el ajuste matemático
    
    # A. Ingresos por Ventas
    df_v_totales = pd.read_sql("SELECT metodo_pago, SUM(total) as total FROM ventas GROUP BY metodo_pago", conn)
    def get_val(df, metodo):
        if df.empty: return 0.0
        val = df.loc[df['metodo_pago'] == metodo, 'total']
        return float(val.iloc[0]) if not val.empty else 0.0

    ventas_efectivo = get_val(df_v_totales, 'Efectivo')
    ventas_banco = get_val(df_v_totales, 'Transferencia')
    
    # B. Egresos por Compras
    try:
        df_c_totales = pd.read_sql("SELECT metodo_pago, SUM(costo_total) as total FROM compras GROUP BY metodo_pago", conn)
        compras_efectivo = get_val(df_c_totales, 'Efectivo')
        compras_banco = get_val(df_c_totales, 'Transferencia')
    except:
        compras_efectivo = 0.0
        compras_banco = 0.0
        
    # --- 2. GESTIÓN DE SALDOS (CALIBRACIÓN) ---
    with st.expander("⚙️ Calibrar Caja (Ajuste de Saldo Real)"):
        st.info("Ingresa el dinero que tienes **HOY REALMENTE** en tu poder. El sistema calculará el ajuste matemático automáticamente.")
        
        # Leemos el saldo inicial guardado solo para referencia interna
        df_saldos = pd.read_sql("SELECT cuenta, monto FROM saldos_iniciales", conn)
        base_efectivo = 0.0
        base_banco = 0.0
        if not df_saldos.empty:
            r_ef = df_saldos[df_saldos['cuenta'] == 'Efectivo']
            r_tr = df_saldos[df_saldos['cuenta'] == 'Transferencia']
            if not r_ef.empty: base_efectivo = float(r_ef.iloc[0]['monto'])
            if not r_tr.empty: base_banco = float(r_tr.iloc[0]['monto'])
            
        # Calculamos cuánto cree el sistema que tienes ahora, para ponerlo como valor por defecto
        sistema_efectivo = base_efectivo + ventas_efectivo - compras_efectivo
        sistema_banco = base_banco + ventas_banco - compras_banco
        
        with st.form("form_saldos_reales"):
            c_ini1, c_ini2 = st.columns(2)
            # El usuario edita lo que QUIERE ver (su realidad)
            real_efectivo = c_ini1.number_input("Efectivo", value=sistema_efectivo, step=100.0)
            real_banco = c_ini2.number_input("Transferencia", value=sistema_banco, step=100.0)
            
            if st.form_submit_button("✅ Calibrar Saldos"):
                # FÓRMULA MÁGICA:
                # Si Saldo_Real = Inicial + Ventas - Compras
                # Entonces: Inicial = Saldo_Real - Ventas + Compras
                
                nuevo_base_efectivo = real_efectivo - ventas_efectivo + compras_efectivo
                nuevo_base_banco = real_banco - ventas_banco + compras_banco
                
                cursor = conn.cursor()
                try:
                    cursor.execute("UPDATE saldos_iniciales SET monto=%s WHERE cuenta='Efectivo'", (nuevo_base_efectivo,))
                    cursor.execute("UPDATE saldos_iniciales SET monto=%s WHERE cuenta='Transferencia'", (nuevo_base_banco,))
                    conn.commit()
                    st.success(f"¡Caja calibrada! Ajustado a: ${real_efectivo:,.0f} y ${real_banco:,.0f}")
                    time.sleep(1.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
                finally:
                    cursor.close()
    
    # --- 3. CÁLCULO FINAL PARA MOSTRAR ---
    # Volvemos a leer la base (que ahora ya tiene el ajuste correcto)
    df_saldos_final = pd.read_sql("SELECT cuenta, monto FROM saldos_iniciales", conn)
    final_base_ef = 0.0
    final_base_tr = 0.0
    
    if not df_saldos_final.empty:
        r_ef = df_saldos_final[df_saldos_final['cuenta'] == 'Efectivo']
        r_tr = df_saldos_final[df_saldos_final['cuenta'] == 'Transferencia']
        if not r_ef.empty: final_base_ef = float(r_ef.iloc[0]['monto'])
        if not r_tr.empty: final_base_tr = float(r_tr.iloc[0]['monto'])

    # Ahora sí, esta cuenta dará EXACTAMENTE lo que pusiste en el formulario
    caja_efectivo_real = final_base_ef + ventas_efectivo - compras_efectivo
    caja_banco_real = final_base_tr + ventas_banco - compras_banco
    
    # 4. Valor de Mercadería
    cols_stock = [c for c in df_prod.columns if c.startswith('Stock_')]
    if cols_stock and not df_prod.empty:
        df_prod['Stock_Total_U'] = df_prod[cols_stock].sum(axis=1)
        valor_venta_total = (df_prod['Stock_Total_U'] * df_prod['Precio']).sum()
        valor_costo_total = (df_prod['Stock_Total_U'] * df_prod['Costo']).sum()
    else:
        valor_venta_total = 0
        valor_costo_total = 0

    patrimonio_total = caja_efectivo_real + caja_banco_real + valor_venta_total
    
    conn.close()

    # --- D. VISUALIZACIÓN ---
    st.markdown("### 💵 Disponibilidad Real")
    col1, col2, col3 = st.columns(3)
    
    col1.metric("Caja Efectivo", f"${caja_efectivo_real:,.0f}", delta="Disponible hoy")            
    col2.metric("Mercado Pago", f"${caja_banco_real:,.0f}", delta="Disponible hoy")
    col3.metric("Total Líquido", f"${(caja_efectivo_real + caja_banco_real):,.0f}", help="Suma de Efectivo y Banco")
    
    st.divider()
    
    st.markdown("### 📦 Valor de Stock")
    m1, m2, m3 = st.columns(3)
    m1.metric("Costo Invertido", f"${valor_costo_total:,.0f}")
    m2.metric("Valor de Venta", f"${valor_venta_total:,.0f}")
    m3.metric("Ganancia Potencial", f"${(valor_venta_total - valor_costo_total):,.0f}", delta="Margen")
    
    st.divider()
    st.subheader("💎 Patrimonio Total")
    st.info(f"Capital Total (Dinero + Mercadería): **${patrimonio_total:,.0f}**")