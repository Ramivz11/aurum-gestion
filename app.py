import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
import time

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Aurum Suplementos", page_icon="💪", layout="wide")

# --- CONEXIÓN HÍBRIDA (ROBUSTA) ---
@st.cache_resource
def conectar_google_sheets():
    # 👇 Cambia esto por tu ID real si es diferente
    sheet_id = "10VhKuyPQVvqxux4_tQ_ZeoXrqED0VWSEXEytPVMBuW8"
    
    gc = None
    
    # 1. PRIMER INTENTO: Buscar archivo local (Tu PC)
    try:
        gc = gspread.service_account(filename='credenciales.json')
    except FileNotFoundError:
        pass

    # 2. SEGUNDO INTENTO: Buscar en la Nube (Secrets)
    if gc is None:
        try:
            if "gcp_service_account" in st.secrets:
                creds_dict = dict(st.secrets["gcp_service_account"])
                if "private_key" in creds_dict:
                    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                gc = gspread.service_account_from_dict(creds_dict)
        except Exception:
            pass

    # 3. VERIFICACIÓN FINAL
    if gc is None:
        st.error("⚠️ ERROR CRÍTICO: No se encontraron credenciales.")
        st.info("PC: Verifica que 'credenciales.json' esté en la carpeta.")
        st.info("Nube: Verifica que hayas cargado los 'Secrets'.")
        st.stop()
    
    sh = gc.open_by_key(sheet_id)
    return sh

# --- FUNCIÓN: LIMPIAR DATOS MONETARIOS ---
def limpiar_columna_dinero(serie):
    """Convierte strings con $ y comas a números"""
    if serie.dtype == 'object':
        serie = serie.astype(str)
        serie = serie.str.replace('$', '', regex=False)
        serie = serie.str.replace(',', '', regex=False)
        serie = serie.str.strip()
    return pd.to_numeric(serie, errors='coerce').fillna(0)

# --- LECTURA DE DATOS ---
def obtener_datos():
    sh = conectar_google_sheets()
    
    try:
        ws_prod = sh.worksheet("Productos")
        ws_suc = sh.worksheet("Sucursales")
        ws_ventas = sh.worksheet("Ventas")
        ws_caja = sh.worksheet("Caja")
    except gspread.WorksheetNotFound as e:
        st.error(f"❌ Falta la hoja: {e}")
        st.info("Asegúrate de tener: 'Productos', 'Sucursales', 'Ventas', 'Caja'")
        st.stop()
    
    # Lectura de Productos
    df_prod = pd.DataFrame(ws_prod.get_all_records())
    
    # Lectura de Sucursales (desde columna A, saltando el encabezado)
    col_sucursales = ws_suc.col_values(1)
    lista_sucursales = col_sucursales[1:] if len(col_sucursales) > 1 else []
    
    # Lectura de Ventas
    df_ventas = pd.DataFrame(ws_ventas.get_all_records())
    
    # Lectura de Caja
    df_caja = pd.DataFrame(ws_caja.get_all_records())
    
    return df_prod, lista_sucursales, df_ventas, df_caja

# --- FUNCIÓN: REGISTRAR VENTA ---
def registrar_venta_db(producto_nombre, cantidad, precio, metodo, ubicacion, notas):
    sh = conectar_google_sheets()
    ws_ventas = sh.worksheet("Ventas")
    ws_prod = sh.worksheet("Productos")
    
    # Formato de fecha con hora
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = precio * cantidad
    
    # ✅ CAMBIO 1: Registrar venta con el orden correcto de columnas
    # FECHA | PRODUCTO | CANTIDAD | PRECIO UNITARIO | TOTAL | METODO PAGO | UBICACION | NOTAS
    nueva_fila = [fecha, producto_nombre, cantidad, precio, total, metodo, ubicacion, notas]
    ws_ventas.append_row(nueva_fila)
    
    # ✅ CAMBIO 2: Actualizar stock en la hoja Productos
    try:
        # Buscar el producto por nombre en la columna B (Nombre)
        cell = ws_prod.find(producto_nombre, in_column=2)  # Columna B = índice 2
        fila_idx = cell.row
        
        # ✅ CAMBIO 3: Buscar la columna de stock que corresponde a la ubicación
        # Las columnas pueden ser: Stock_Cordoba, Stock_Rio Tercero, etc.
        col_nombre = None
        encabezados = ws_prod.row_values(1)
        
        # Buscar coincidencia exacta o parcial
        for encabezado in encabezados:
            if encabezado.startswith('Stock_'):
                # Extraer el nombre de la sucursal de la columna
                nombre_sucursal = encabezado.replace('Stock_', '')
                # Comparar sin importar espacios o guiones bajos
                if nombre_sucursal.replace('_', ' ').lower() == ubicacion.replace('_', ' ').lower():
                    col_nombre = encabezado
                    break
        
        if col_nombre is None:
            st.error(f"❌ No se encontró columna de stock para '{ubicacion}'")
            st.info(f"Columnas disponibles: {', '.join([c for c in encabezados if c.startswith('Stock_')])}")
            return False
        
        if col_nombre in encabezados:
            col_idx = encabezados.index(col_nombre) + 1
            val_celda = ws_prod.cell(fila_idx, col_idx).value
            
            # Convertir a número
            try:
                stock_actual = int(float(val_celda)) if val_celda else 0
            except:
                stock_actual = 0
            
            # ✅ CAMBIO 4: Validar stock suficiente
            if stock_actual < cantidad:
                st.error(f"⚠️ Stock insuficiente en {ubicacion}!")
                st.warning(f"Disponible: {stock_actual} | Solicitado: {cantidad}")
                return False
            
            # Descontar stock
            nuevo_stock = stock_actual - cantidad
            ws_prod.update_cell(fila_idx, col_idx, nuevo_stock)
            
            return True
        else:
            # Este else ya no debería ejecutarse porque buscamos la columna arriba
            st.error(f"❌ Error inesperado: columna '{col_nombre}' no encontrada.")
            return False
            
    except gspread.CellNotFound:
        st.error(f"❌ Producto '{producto_nombre}' no encontrado en la hoja Productos.")
        return False
    except Exception as e:
        st.error(f"❌ Error al actualizar stock: {e}")
        return False

# --- INTERFAZ GRÁFICA ---
st.sidebar.image("logo.png", width=150)
st.sidebar.title("Aurum Gestión")
menu = st.sidebar.radio("Navegación", ["Tablero Principal", "Registrar Venta", "Historial Ventas"])

try:
    df_prod, sucursales, df_ventas, df_caja = obtener_datos()
    
    # --- 🧹 LIMPIEZA DE DATOS 🧹 ---
    
    if not df_prod.empty:
        # ✅ CAMBIO 5: Limpiar columnas Costo y Precio
        if 'Costo' in df_prod.columns:
            df_prod['Costo'] = limpiar_columna_dinero(df_prod['Costo'])
        if 'Precio' in df_prod.columns:
            df_prod['Precio'] = limpiar_columna_dinero(df_prod['Precio'])
        
        # ✅ CAMBIO 6: Identificar columnas de stock por sucursal
        # Buscar columnas que empiecen con "Stock_"
        cols_stock = [col for col in df_prod.columns if col.startswith('Stock_')]
        
        # Limpiar todas las columnas de stock encontradas
        for col in cols_stock:
            df_prod[col] = pd.to_numeric(df_prod[col], errors='coerce').fillna(0)
        
        # Calcular totales
        if cols_stock:
            df_prod['Stock_Total'] = df_prod[cols_stock].sum(axis=1)
            df_prod['Inversion_Total'] = df_prod['Stock_Total'] * df_prod['Costo']
            df_prod['Venta_Estimada'] = df_prod['Stock_Total'] * df_prod['Precio']
        else:
            df_prod['Stock_Total'] = 0
            df_prod['Inversion_Total'] = 0
            df_prod['Venta_Estimada'] = 0
    
    # --- PANTALLAS ---
    if menu == "Tablero Principal":
        st.title("Aurum Suplementos 💪")
        
        # 🔍 DEBUG: Mostrar columnas detectadas
        with st.expander("🔧 Debug - Columnas detectadas"):
            st.write("**Columnas en Productos:**", list(df_prod.columns))
            st.write("**Sucursales encontradas:**", sucursales)
            st.write("**Columnas de stock detectadas:**", cols_stock)
        
        # ✅ CAMBIO 7: Calcular dinero en caja
        efectivo_ventas = 0
        banco_ventas = 0
        
        if not df_ventas.empty and 'TOTAL' in df_ventas.columns:
            df_ventas['TOTAL'] = limpiar_columna_dinero(df_ventas['TOTAL'])
            
            if 'METODO PAGO' in df_ventas.columns:
                efectivo_ventas = df_ventas[df_ventas['METODO PAGO'] == 'Efectivo']['TOTAL'].sum()
                banco_ventas = df_ventas[df_ventas['METODO PAGO'] == 'Transferencia']['TOTAL'].sum()
        
        # ✅ CAMBIO 8: Sumar caja inicial
        inicio_efectivo = 0
        inicio_banco = 0
        
        if not df_caja.empty and 'Monto' in df_caja.columns:
            df_caja['Monto'] = limpiar_columna_dinero(df_caja['Monto'])
            
            if 'Concepto' in df_caja.columns:
                ef = df_caja[df_caja['Concepto'] == 'Inicio Efectivo']['Monto']
                inicio_efectivo = ef.sum() if not ef.empty else 0
                
                ba = df_caja[df_caja['Concepto'] == 'Inicio Banco']['Monto']
                inicio_banco = ba.sum() if not ba.empty else 0
        
        # Totales
        total_efectivo = efectivo_ventas + inicio_efectivo
        total_banco = banco_ventas + inicio_banco
        valor_mercaderia = df_prod['Venta_Estimada'].sum()
        patrimonio_total = total_efectivo + total_banco + valor_mercaderia
        
        # MÉTRICAS PRINCIPALES
        col1, col2, col3 = st.columns(3)
        col1.metric("💵 Caja Efectivo", f"${total_efectivo:,.0f}")
        col2.metric("🏦 Mercado Pago", f"${total_banco:,.0f}")
        col3.metric("💰 Patrimonio Total", f"${patrimonio_total:,.0f}", 
                   delta="Dinero + Mercadería")
        
        st.divider()
        
        # MÉTRICAS DE STOCK
        c1, c2, c3 = st.columns(3)
        c1.metric("📦 Unidades Stock", f"{df_prod['Stock_Total'].sum():,.0f}")
        c2.metric("💸 Inversión Costo", f"${df_prod['Inversion_Total'].sum():,.0f}")
        c3.metric("💵 Valor Venta", f"${df_prod['Venta_Estimada'].sum():,.0f}")
        
        st.subheader("🔎 Detalle de Stock por Producto")
        
        if not df_prod.empty:
            # Seleccionar columnas a mostrar
            cols_mostrar = ['Nombre', 'Precio'] + cols_stock + ['Stock_Total']
            cols_disponibles = [c for c in cols_mostrar if c in df_prod.columns]
            
            # Renombrar columnas para mejor visualización
            df_display = df_prod[cols_disponibles].copy()
            
            # Renombrar columnas de stock para quitar el prefijo
            rename_dict = {}
            for col in df_display.columns:
                if col.startswith('Stock_'):
                    rename_dict[col] = col.replace('Stock_', '').replace('_', ' ')
            
            df_display = df_display.rename(columns=rename_dict)
            
            st.dataframe(df_display, hide_index=True, use_container_width=True)
        else:
            st.info("📝 No hay productos cargados en el Excel.")

    elif menu == "Registrar Venta":
        st.title("💸 Registrar Venta")
        
        if df_prod.empty:
            st.warning("⚠️ No hay productos cargados en la hoja 'Productos'.")
        elif not sucursales:
            st.warning("⚠️ No hay sucursales cargadas en la hoja 'Sucursales'.")
        else:
            with st.form("form_venta"):
                st.subheader("Datos de la Venta")
                
                col_a, col_b = st.columns(2)
                
                # Selección de producto
                productos_disponibles = df_prod['Nombre'].dropna().unique()
                prod = col_a.selectbox("🏷️ Producto", productos_disponibles)
                
                # Selección de sucursal
                origen = col_b.selectbox("📍 Sucursal", sucursales)
                
                # Obtener precio sugerido
                precio_sug = 0.0
                if not df_prod[df_prod['Nombre'] == prod].empty:
                    precio_sug = float(df_prod[df_prod['Nombre'] == prod]['Precio'].values[0])
                
                c1, c2 = st.columns(2)
                cant = c1.number_input("📦 Cantidad", min_value=1, value=1, step=1)
                precio = c2.number_input("💵 Precio Cobrado", value=precio_sug, step=100.0)
                
                # Mostrar stock disponible
                # Buscar la columna que corresponde a esta sucursal
                col_stock_name = None
                for col in df_prod.columns:
                    if col.startswith('Stock_'):
                        nombre_suc = col.replace('Stock_', '')
                        if nombre_suc.replace('_', ' ').lower() == origen.replace('_', ' ').lower():
                            col_stock_name = col
                            break
                
                if col_stock_name and col_stock_name in df_prod.columns:
                    stock_disp = df_prod[df_prod['Nombre'] == prod][col_stock_name].values
                    if len(stock_disp) > 0:
                        stock_val = int(stock_disp[0])
                        if stock_val > 0:
                            st.info(f"✅ Stock disponible en **{origen}**: **{stock_val}** unidades")
                        else:
                            st.warning(f"⚠️ Sin stock en {origen}")
                
                pago = st.radio("💳 Método de Pago", ["Efectivo", "Transferencia"], horizontal=True)
                nota = st.text_input("📝 Notas (opcional)")
                
                total_venta = precio * cant
                st.markdown(f"### Total: **${total_venta:,.0f}**")
                
                if st.form_submit_button("✅ CONFIRMAR VENTA", type="primary", use_container_width=True):
                    with st.spinner("Procesando venta..."):
                        if registrar_venta_db(prod, cant, precio, pago, origen, nota):
                            st.cache_resource.clear()
                            st.success("✅ ¡Venta registrada exitosamente!")
                            st.balloons()
                            time.sleep(1.5)
                            st.rerun()

    elif menu == "Historial Ventas":
        st.title("📜 Historial de Ventas")
        
        if not df_ventas.empty:
            # Limpiar y preparar datos para mostrar
            df_display = df_ventas.copy()
            
            if 'TOTAL' in df_display.columns:
                df_display['TOTAL'] = limpiar_columna_dinero(df_display['TOTAL'])
                df_display['TOTAL'] = df_display['TOTAL'].apply(lambda x: f"${x:,.0f}")
            
            # Mostrar últimas 50 ventas
            st.dataframe(
                df_display.tail(50).iloc[::-1],  # Más recientes primero
                use_container_width=True,
                hide_index=True
            )
            
            # Estadísticas
            st.divider()
            st.subheader("📊 Resumen de Ventas")
            
            col1, col2, col3 = st.columns(3)
            
            total_ventas = len(df_ventas)
            col1.metric("🔢 Total Ventas", total_ventas)
            
            if 'TOTAL' in df_ventas.columns:
                df_ventas['TOTAL'] = limpiar_columna_dinero(df_ventas['TOTAL'])
                monto_total = df_ventas['TOTAL'].sum()
                col2.metric("💰 Monto Total", f"${monto_total:,.0f}")
                
                if total_ventas > 0:
                    promedio = monto_total / total_ventas
                    col3.metric("📈 Ticket Promedio", f"${promedio:,.0f}")
        else:
            st.info("📝 No hay ventas registradas aún.")

except Exception as e:
    st.error("❌ Ocurrió un error:")
    st.exception(e)
    st.info("💡 Verifica que todas las hojas del Excel existan y tengan las columnas correctas.")