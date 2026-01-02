import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
import time

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Aurum Suplementos", page_icon="💪", layout="wide")

# --- FUNCIONES AUXILIARES ---

def limpiar_moneda(serie):
    """Convierte strings con $ y comas a números flotantes."""
    if serie.dtype == 'object':
        serie = serie.astype(str)
        serie = serie.str.replace('$', '', regex=False)
        serie = serie.str.replace(',', '', regex=False)
        serie = serie.str.strip()
    return pd.to_numeric(serie, errors='coerce').fillna(0)

def buscar_columna_stock(worksheet, nombre_ubicacion):
    """
    Busca el índice de la columna de stock correspondiente a una ubicación.
    Retorna el índice de la columna (1-based) o None si falla.
    """
    try:
        encabezados = worksheet.row_values(1)
        col_nombre = None
        
        # Normalizar ubicación buscada (minúsculas, sin guiones bajos)
        ubicacion_target = nombre_ubicacion.replace('_', ' ').strip().lower()

        for encabezado in encabezados:
            if encabezado.startswith('Stock_'):
                sucursal_header = encabezado.replace('Stock_', '').replace('_', ' ').strip().lower()
                if sucursal_header == ubicacion_target:
                    col_nombre = encabezado
                    break
        
        if col_nombre:
            return encabezados.index(col_nombre) + 1
        return None
    except Exception:
        return None

# --- CONEXIÓN GOOGLE SHEETS ---
@st.cache_resource
def conectar_google_sheets():
    sheet_id = "10VhKuyPQVvqxux4_tQ_ZeoXrqED0VWSEXEytPVMBuW8"  # ID de tu hoja
    gc = None
    
    # 1. Intento Local
    try:
        gc = gspread.service_account(filename='credenciales.json')
    except FileNotFoundError:
        pass

    # 2. Intento Nube (Streamlit Secrets)
    if gc is None:
        try:
            if "gcp_service_account" in st.secrets:
                creds_dict = dict(st.secrets["gcp_service_account"])
                if "private_key" in creds_dict:
                    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                gc = gspread.service_account_from_dict(creds_dict)
        except Exception:
            pass

    if gc is None:
        st.error("⚠️ ERROR CRÍTICO: No se encontraron credenciales (ni locales ni en Secrets).")
        st.stop()
    
    try:
        sh = gc.open_by_key(sheet_id)
        return sh
    except Exception as e:
        st.error(f"❌ Error al abrir la hoja de cálculo: {e}")
        st.stop()

# --- LECTURA DE DATOS ---
def obtener_datos():
    sh = conectar_google_sheets()
    try:
        ws_prod = sh.worksheet("Productos")
        ws_suc = sh.worksheet("Sucursales")
        ws_ventas = sh.worksheet("Ventas")
        ws_caja = sh.worksheet("Caja")
        
        # Dataframes
        df_prod = pd.DataFrame(ws_prod.get_all_records())
        
        col_sucursales = ws_suc.col_values(1)
        lista_sucursales = col_sucursales[1:] if len(col_sucursales) > 1 else []
        
        df_ventas = pd.DataFrame(ws_ventas.get_all_records())
        df_caja = pd.DataFrame(ws_caja.get_all_records())
        
        return df_prod, lista_sucursales, df_ventas, df_caja
        
    except gspread.WorksheetNotFound as e:
        st.error(f"❌ Falta la hoja: {e}. Asegúrate de tener: 'Productos', 'Sucursales', 'Ventas', 'Caja'")
        st.stop()
    except Exception as e:
        st.error(f"❌ Error leyendo datos: {e}")
        st.stop()

# --- LÓGICA DE NEGOCIO ---

def registrar_venta_db(producto_nombre, cantidad, precio, metodo, ubicacion, notas):
    sh = conectar_google_sheets()
    ws_ventas = sh.worksheet("Ventas")
    ws_prod = sh.worksheet("Productos")
    
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = precio * cantidad
    
    # 1. Verificar Stock
    try:
        cell = ws_prod.find(producto_nombre, in_column=2) # Busca en columna B
        fila_prod = cell.row
        
        col_idx = buscar_columna_stock(ws_prod, ubicacion)
        
        if not col_idx:
            st.error(f"❌ No se encontró columna de stock para '{ubicacion}'")
            return False

        val_celda = ws_prod.cell(fila_prod, col_idx).value
        stock_actual = int(float(val_celda)) if val_celda else 0
        
        if stock_actual < cantidad:
            st.error(f"⚠️ Stock insuficiente en {ubicacion}. Disponible: {stock_actual}")
            return False
            
        # 2. Descontar Stock
        ws_prod.update_cell(fila_prod, col_idx, stock_actual - cantidad)
        
        # 3. Registrar Venta
        nueva_fila = [fecha, producto_nombre, cantidad, precio, total, metodo, ubicacion, notas]
        ws_ventas.append_row(nueva_fila)
        return True
        
    except gspread.CellNotFound:
        st.error(f"❌ Producto '{producto_nombre}' no encontrado.")
        return False
    except Exception as e:
        st.error(f"❌ Error al procesar venta: {e}")
        return False

def editar_venta(fila_idx, datos_antiguos, datos_nuevos):
    """Edita una venta y ajusta el stock. fila_idx es el índice en Sheets (1-based)."""
    sh = conectar_google_sheets()
    ws_ventas = sh.worksheet("Ventas")
    ws_prod = sh.worksheet("Productos")
    
    try:
        # 1. Devolver Stock (Revertir venta antigua)
        cell_ant = ws_prod.find(datos_antiguos['producto'], in_column=2)
        if cell_ant:
            col_ant = buscar_columna_stock(ws_prod, datos_antiguos['ubicacion'])
            if col_ant:
                val = ws_prod.cell(cell_ant.row, col_ant).value
                stock_curr = int(float(val)) if val else 0
                ws_prod.update_cell(cell_ant.row, col_ant, stock_curr + datos_antiguos['cantidad'])

        # 2. Descontar Nuevo Stock
        cell_new = ws_prod.find(datos_nuevos['producto'], in_column=2)
        if not cell_new:
            st.error("❌ Producto nuevo no encontrado")
            return False
            
        col_new = buscar_columna_stock(ws_prod, datos_nuevos['ubicacion'])
        if not col_new:
            st.error(f"❌ Ubicación '{datos_nuevos['ubicacion']}' no encontrada en Productos")
            return False
            
        val_new = ws_prod.cell(cell_new.row, col_new).value
        stock_disp = int(float(val_new)) if val_new else 0
        
        if stock_disp < datos_nuevos['cantidad']:
            st.error(f"⚠️ Stock insuficiente para el cambio. Disponible: {stock_disp}")
            return False
            
        ws_prod.update_cell(cell_new.row, col_new, stock_disp - datos_nuevos['cantidad'])
        
        # 3. Actualizar Fila de Venta (Batch update para velocidad)
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total = datos_nuevos['precio'] * datos_nuevos['cantidad']
        
        row_values = [
            fecha,
            datos_nuevos['producto'],
            datos_nuevos['cantidad'],
            datos_nuevos['precio'],
            total,
            datos_nuevos['metodo'],
            datos_nuevos['ubicacion'],
            datos_nuevos['notas']
        ]
        
        # Rango A{fila}:H{fila}
        rango = f"A{fila_idx}:H{fila_idx}"
        ws_ventas.update(range_name=rango, values=[row_values])
        
        return True

    except Exception as e:
        st.error(f"❌ Error editando venta: {e}")
        return False

def eliminar_venta(fila_idx, producto, cantidad, ubicacion):
    """Elimina venta y devuelve stock."""
    sh = conectar_google_sheets()
    ws_ventas = sh.worksheet("Ventas")
    ws_prod = sh.worksheet("Productos")
    
    try:
        # 1. Devolver Stock
        cell = ws_prod.find(producto, in_column=2)
        if cell:
            col_idx = buscar_columna_stock(ws_prod, ubicacion)
            if col_idx:
                val = ws_prod.cell(cell.row, col_idx).value
                stock = int(float(val)) if val else 0
                ws_prod.update_cell(cell.row, col_idx, stock + cantidad)
        
        # 2. Eliminar fila
        ws_ventas.delete_rows(fila_idx)
        return True
        
    except Exception as e:
        st.error(f"❌ Error eliminando venta: {e}")
        return False

# --- INTERFAZ DE USUARIO ---

st.sidebar.image("logo.png", width=150) # Asegúrate de tener logo.png o comenta esta línea
st.sidebar.title("Aurum Gestión")
menu = st.sidebar.radio("Navegación", ["Tablero Principal", "Registrar Venta", "Historial Ventas"])

# Cargar datos globales
df_prod, sucursales, df_ventas, df_caja = obtener_datos()

# Preparación de datos de Productos
cols_stock = []
if not df_prod.empty:
    # Limpiar monedas
    for col in ['Costo', 'Precio']:
        if col in df_prod.columns:
            df_prod[col] = limpiar_moneda(df_prod[col])
    
    # Identificar stocks
    cols_stock = [col for col in df_prod.columns if col.startswith('Stock_')]
    for col in cols_stock:
        df_prod[col] = pd.to_numeric(df_prod[col], errors='coerce').fillna(0)
    
    # Cálculos globales
    if cols_stock:
        df_prod['Stock_Total'] = df_prod[cols_stock].sum(axis=1)
        df_prod['Inversion_Total'] = df_prod['Stock_Total'] * df_prod['Costo']
        df_prod['Venta_Estimada'] = df_prod['Stock_Total'] * df_prod['Precio']
    else:
        for c in ['Stock_Total', 'Inversion_Total', 'Venta_Estimada']:
            df_prod[c] = 0

# --- PANTALLA 1: TABLERO ---
if menu == "Tablero Principal":
    st.title("Aurum Suplementos 💪")
    
    # Cálculo Caja
    efectivo_ventas = 0
    banco_ventas = 0
    
    if not df_ventas.empty and 'TOTAL' in df_ventas.columns:
        df_ventas['TOTAL'] = limpiar_moneda(df_ventas['TOTAL'])
        if 'METODO PAGO' in df_ventas.columns:
            efectivo_ventas = df_ventas[df_ventas['METODO PAGO'] == 'Efectivo']['TOTAL'].sum()
            banco_ventas = df_ventas[df_ventas['METODO PAGO'] == 'Transferencia']['TOTAL'].sum()
            
    inicio_efectivo = 0
    inicio_banco = 0
    
    if not df_caja.empty and 'Monto' in df_caja.columns:
        df_caja['Monto'] = limpiar_moneda(df_caja['Monto'])
        if 'Concepto' in df_caja.columns:
            inicio_efectivo = df_caja[df_caja['Concepto'] == 'Inicio Efectivo']['Monto'].sum()
            inicio_banco = df_caja[df_caja['Concepto'] == 'Inicio Banco']['Monto'].sum()
            
    total_efectivo = efectivo_ventas + inicio_efectivo
    total_banco = banco_ventas + inicio_banco
    valor_mercaderia = df_prod['Venta_Estimada'].sum() if not df_prod.empty else 0
    
    # Métricas
    c1, c2, c3 = st.columns(3)
    c1.metric("💵 Caja Efectivo", f"${total_efectivo:,.0f}")
    c2.metric("🏦 Mercado Pago", f"${total_banco:,.0f}")
    c3.metric("💰 Patrimonio Total", f"${(total_efectivo + total_banco + valor_mercaderia):,.0f}", delta="Caja + Stock")
    
    st.divider()
    
    m1, m2, m3 = st.columns(3)
    stk_tot = df_prod['Stock_Total'].sum() if not df_prod.empty else 0
    inv_tot = df_prod['Inversion_Total'].sum() if not df_prod.empty else 0
    ven_est = df_prod['Venta_Estimada'].sum() if not df_prod.empty else 0
    
    m1.metric("📦 Unidades Stock", f"{stk_tot:,.0f}")
    m2.metric("💸 Inversión Costo", f"${inv_tot:,.0f}")
    m3.metric("💵 Valor Venta", f"${ven_est:,.0f}")
    
    st.subheader("🔎 Detalle de Stock")
    if not df_prod.empty:
        cols_base = ['Nombre', 'Precio']
        cols_ver = cols_base + cols_stock + ['Stock_Total']
        cols_final = [c for c in cols_ver if c in df_prod.columns]
        
        # Limpiar nombres de columnas para mostrar
        df_show = df_prod[cols_final].copy()
        rename_map = {c: c.replace('Stock_', '').replace('_', ' ') for c in cols_stock}
        df_show.rename(columns=rename_map, inplace=True)
        
        st.dataframe(df_show, hide_index=True, use_container_width=True)
    else:
        st.info("Sin datos de productos.")

# --- PANTALLA 2: REGISTRAR VENTA (MODIFICADO TIEMPO REAL) ---
elif menu == "Registrar Venta":
    st.title("💸 Registrar Venta")
    
    if df_prod.empty or not sucursales:
        st.warning("⚠️ Faltan datos de Productos o Sucursales.")
    else:
        # 1. SELECCIÓN FUERA DEL FORMULARIO (Para actualización en tiempo real)
        st.info("👇 Selecciona Producto y Sucursal para ver disponibilidad")
        
        c_sel1, c_sel2 = st.columns(2)
        prods_lista = df_prod['Nombre'].dropna().unique()
        
        # Selectores interactivos (al cambiar, recargan la página y actualizan las métricas abajo)
        prod_sel = c_sel1.selectbox("🏷️ Producto", prods_lista)
        suc_sel = c_sel2.selectbox("📍 Sucursal", sucursales)
        
        # 2. CÁLCULO DE DATOS EN TIEMPO REAL
        precio_sug = 0.0
        stock_actual = 0
        
        # Buscar datos del producto seleccionado
        row_prod = df_prod[df_prod['Nombre'] == prod_sel]
        
        if not row_prod.empty:
            precio_sug = float(row_prod.iloc[0]['Precio'])
            
            # Buscar columna stock correspondiente a la sucursal seleccionada
            col_stk = next((c for c in cols_stock if c.replace('Stock_', '').replace('_', ' ').lower() == suc_sel.lower().replace('_', ' ')), None)
            
            if col_stk:
                stock_actual = int(row_prod.iloc[0][col_stk])
        
        # 3. VISUALIZACIÓN DE MÉTRICAS (PRECIO Y STOCK)
        m_col1, m_col2 = st.columns(2)
        m_col1.metric("💵 Precio Lista", f"${precio_sug:,.0f}")
        m_col2.metric(f"📦 Stock en {suc_sel}", f"{stock_actual} u.", delta_color="normal" if stock_actual > 0 else "inverse")
        
        if stock_actual == 0:
            st.error(f"⚠️ ¡Atención! No hay stock de este producto en {suc_sel}.")

        st.divider()

        # 4. FORMULARIO DE CONFIRMACIÓN (Solo datos de transacción)
        with st.form("form_venta"):
            cc1, cc2 = st.columns(2)
            cantidad = cc1.number_input("📦 Cantidad a vender", min_value=1, value=1)
            # El precio se pre-carga con el valor calculado arriba
            precio_final = cc2.number_input("💵 Precio Por Unidad", value=precio_sug, step=100.0)
            
            metodo = st.radio("Pago", ["Efectivo", "Transferencia"], horizontal=True)
            notas = st.text_input("Notas (Opcional)")
            
            # Cálculo del total dinámico dentro del form(visual solamente tras enviar, o estimado mentalmente)
            st.markdown("---")
            
            if st.form_submit_button("✅ CONFIRMAR VENTA", type="primary", use_container_width=True):
                # Validaciones finales
                if stock_actual < cantidad:
                    st.error(f"❌ No puedes vender {cantidad}. Solo hay {stock_actual} en stock.")
                else:
                    with st.spinner("Registrando venta..."):
                        if registrar_venta_db(prod_sel, cantidad, precio_final, metodo, suc_sel, notas):
                            st.cache_resource.clear()
                            st.success("✅ ¡Venta registrada exitosamente!")
                            time.sleep(1.5)
                            st.rerun()

# --- PANTALLA 3: HISTORIAL ---
elif menu == "Historial Ventas":
    st.title("📜 Historial y Edición")
    
    if df_ventas.empty:
        st.info("No hay ventas registradas.")
    else:
        # Preprocesamiento para IDs
        df_ventas['ID_SHEET'] = range(2, len(df_ventas) + 2)
        if 'TOTAL' in df_ventas.columns:
            df_ventas['TOTAL_NUM'] = limpiar_moneda(df_ventas['TOTAL'])
            
        # --- FILTROS ---
        st.subheader("Filtros")
        fc1, fc2, fc3, fc4 = st.columns(4)
        
        f_prod = fc1.selectbox("Producto", ['Todos'] + sorted(df_ventas['PRODUCTO'].unique().tolist()))
        f_suc = fc2.selectbox("Sucursal", ['Todas'] + sorted(df_ventas['UBICACION'].unique().tolist()))
        f_pago = fc3.selectbox("Pago", ['Todos'] + sorted(df_ventas['METODO PAGO'].unique().tolist()))
        f_cant = fc4.selectbox("Ver", ["Últimas 20", "Todas"])
        
        df_filter = df_ventas.copy()
        if f_prod != 'Todos': df_filter = df_filter[df_filter['PRODUCTO'] == f_prod]
        if f_suc != 'Todas': df_filter = df_filter[df_filter['UBICACION'] == f_suc]
        if f_pago != 'Todos': df_filter = df_filter[df_filter['METODO PAGO'] == f_pago]
        
        if f_cant == "Últimas 20":
            df_filter = df_filter.tail(20)
            
        df_filter = df_filter.iloc[::-1] # Invertir orden
        
        # Mostrar Tabla
        cols_ver = ['ID_SHEET', 'FECHA', 'PRODUCTO', 'CANTIDAD', 'PRECIO UNITARIO', 'TOTAL', 'METODO PAGO', 'UBICACION', 'NOTAS']
        cols_ok = [c for c in cols_ver if c in df_filter.columns]
        st.dataframe(df_filter[cols_ok], hide_index=True, use_container_width=True)
        
        st.divider()
        
        # --- EDICIÓN / ELIMINACIÓN ---
        tab1, tab2 = st.tabs(["✏️ Editar", "🗑️ Eliminar"])
        
        # Opciones para selectbox
        opciones = df_filter.apply(lambda x: f"ID {x['ID_SHEET']} | {x['PRODUCTO']} | ${x.get('TOTAL_NUM', 0):,.0f}", axis=1).tolist()
        
        with tab1:
            if not opciones:
                st.warning("No hay ventas visibles para editar.")
            else:
                sel_edit = st.selectbox("Selecciona venta a editar", opciones, key="sel_edit")
                id_sheet_edit = int(sel_edit.split('|')[0].replace('ID', '').strip())
                
                row_edit = df_ventas[df_ventas['ID_SHEET'] == id_sheet_edit].iloc[0]
                
                with st.form("edit_form"):
                    st.caption(f"Editando Venta ID: {id_sheet_edit} - {row_edit['FECHA']}")
                    ec1, ec2 = st.columns(2)
                    
                    prod_list = df_prod['Nombre'].unique().tolist() if not df_prod.empty else []
                    idx_prod = prod_list.index(row_edit['PRODUCTO']) if row_edit['PRODUCTO'] in prod_list else 0
                    
                    new_prod = ec1.selectbox("Producto", prod_list, index=idx_prod)
                    
                    idx_suc = sucursales.index(row_edit['UBICACION']) if row_edit['UBICACION'] in sucursales else 0
                    new_suc = ec2.selectbox("Sucursal", sucursales, index=idx_suc)
                    
                    ec3, ec4 = st.columns(2)
                    new_cant = ec3.number_input("Cantidad", value=int(row_edit['CANTIDAD']), min_value=1)
                    new_precio = ec4.number_input("Precio Unitario", value=float(row_edit['PRECIO UNITARIO']))
                    
                    pay_opts = ["Efectivo", "Transferencia"]
                    idx_pay = 0 if row_edit['METODO PAGO'] == "Efectivo" else 1
                    new_pay = st.selectbox("Método Pago", pay_opts, index=idx_pay)
                    
                    new_note = st.text_input("Notas", value=str(row_edit['NOTAS']))
                    
                    if st.form_submit_button("💾 Guardar Cambios", type="primary"):
                        datos_old = {
                            'producto': row_edit['PRODUCTO'],
                            'cantidad': int(row_edit['CANTIDAD']),
                            'ubicacion': row_edit['UBICACION']
                        }
                        datos_new = {
                            'producto': new_prod,
                            'cantidad': new_cant,
                            'precio': new_precio,
                            'ubicacion': new_suc,
                            'metodo': new_pay,
                            'notas': new_note
                        }
                        
                        if editar_venta(id_sheet_edit, datos_old, datos_new):
                            st.cache_resource.clear()
                            st.success("Actualizado correctamente")
                            time.sleep(1)
                            st.rerun()

        with tab2:
            if not opciones:
                st.warning("No hay ventas visibles para eliminar.")
            else:
                sel_del = st.selectbox("Selecciona venta a eliminar", opciones, key="sel_del")
                id_sheet_del = int(sel_del.split('|')[0].replace('ID', '').strip())
                row_del = df_ventas[df_ventas['ID_SHEET'] == id_sheet_del].iloc[0]
                
                st.error(f"¿Estás seguro de eliminar la venta de **{row_del['PRODUCTO']}** ({row_del['CANTIDAD']} u.)?")
                if st.button("🗑️ SÍ, ELIMINAR VENTA", type="primary"):
                    if eliminar_venta(id_sheet_del, row_del['PRODUCTO'], int(row_del['CANTIDAD']), row_del['UBICACION']):
                        st.cache_resource.clear()
                        st.success("Eliminado correctamente")
                        time.sleep(1)
                        st.rerun()