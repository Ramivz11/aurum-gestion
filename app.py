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
    # 👇👇 TU ID DEL EXCEL 👇👇
    sheet_id = "10VhKuyPQVvqxux4_tQ_ZeoXrqED0VWSEXEytPVMBuW8"
    
    gc = None
    
    # 1. PRIMER INTENTO: Buscar archivo local (Tu PC)
    try:
        gc = gspread.service_account(filename='credenciales.json')
    except FileNotFoundError:
        # Si no encuentra el archivo, no pasa nada, seguimos al paso 2
        pass

    # 2. SEGUNDO INTENTO: Buscar en la Nube (Secrets)
    if gc is None:
        try:
            # Solo intentamos acceder a secrets si no encontramos el archivo local
            # Así evitamos el error en tu PC
            if "gcp_service_account" in st.secrets:
                creds_dict = dict(st.secrets["gcp_service_account"])
                
                # Arreglo de saltos de línea para la clave privada
                if "private_key" in creds_dict:
                    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
                
                gc = gspread.service_account_from_dict(creds_dict)
        except Exception as e:
            # Si falla esto también, capturamos el error pero no rompemos todo inmediatamente
            pass

    # 3. VERIFICACIÓN FINAL
    if gc is None:
        st.error("⚠️ ERROR CRÍTICO: No se encontraron credenciales.")
        st.info("PC: Verifica que 'credenciales.json' esté en la carpeta.")
        st.info("Nube: Verifica que hayas cargado los 'Secrets'.")
        st.stop()
    
    # Si todo salió bien, abrimos la hoja
    sh = gc.open_by_key(sheet_id)
    return sh

# --- LECTURA DE DATOS ---
def obtener_datos():
    sh = conectar_google_sheets()
    
    try:
        ws_prod = sh.worksheet("Productos")
        ws_suc = sh.worksheet("Sucursales")
        ws_ventas = sh.worksheet("Ventas")
        # Intentamos leer la hoja Caja, si no existe no falla crítico
        try:
            ws_caja = sh.worksheet("Caja")
            df_caja = pd.DataFrame(ws_caja.get_all_records())
            df_caja = df_caja.astype(str) # Convertimos a texto para limpiar
        except:
            df_caja = pd.DataFrame() 
            
    except gspread.WorksheetNotFound:
        st.error("❌ Faltan hojas en el Excel. Asegúrate de tener: 'Productos', 'Sucursales', 'Ventas' y 'Caja'.")
        st.stop()
    
    # Lectura de Productos
    df_prod = pd.DataFrame(ws_prod.get_all_records())
    df_prod = df_prod.astype(str) 
    
    # Lectura de Sucursales
    col_sucursales = ws_suc.col_values(1)
    if len(col_sucursales) > 1:
        lista_sucursales = col_sucursales[1:] 
    else:
        lista_sucursales = []
        
    # Lectura de Ventas
    df_ventas = pd.DataFrame(ws_ventas.get_all_records())
    
    return df_prod, lista_sucursales, df_ventas, df_caja

# --- FUNCIÓN: REGISTRAR VENTA ---
def registrar_venta_db(producto_nombre, cantidad, precio, metodo, ubicacion, notas):
    sh = conectar_google_sheets()
    ws_ventas = sh.worksheet("Ventas")
    ws_prod = sh.worksheet("Productos")
    
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = precio * cantidad
    nueva_fila = [fecha, producto_nombre, cantidad, precio, total, metodo, ubicacion, notas]
    ws_ventas.append_row(nueva_fila)
    
    try:
        cell = ws_prod.find(producto_nombre)
        fila_idx = cell.row
        col_nombre = f"Stock_{ubicacion}"
        
        encabezados = ws_prod.row_values(1)
        if col_nombre in encabezados:
            col_idx = encabezados.index(col_nombre) + 1
            val_celda = ws_prod.cell(fila_idx, col_idx).value
            try:
                stock_actual = int(float(val_celda)) if val_celda else 0
            except:
                stock_actual = 0
                
            ws_prod.update_cell(fila_idx, col_idx, stock_actual - cantidad)
            return True
        else:
            st.error(f"Error: No existe la columna '{col_nombre}' en la hoja Productos.")
            return False
    except Exception as e:
        st.error(f"Error al actualizar stock: {e}")
        return False

# --- INTERFAZ GRÁFICA ---
# En lugar de una dirección web, pones el nombre de tu archivo entre comillas
st.sidebar.image("logo.png", width=150)
st.sidebar.title("Aurum Gestión")
menu = st.sidebar.radio("Navegación", ["Tablero Principal", "Registrar Venta", "Historial Ventas"])

try:
    df, sucursales, df_ventas, df_caja = obtener_datos()
    
    # --- 🧹 LIMPIEZA DE DATOS 🧹 ---
    
    if not df.empty:
        # 1. Limpiamos Costo y Precio
        for col in ['Costo', 'Precio']:
            if col in df.columns:
                df[col] = df[col].str.replace('$', '', regex=False).str.replace(',', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # 2. Identificamos y limpiamos columnas de Stock
        cols_stock = [f"Stock_{s}" for s in sucursales if f"Stock_{s}" in df.columns]
        for col in cols_stock:
             df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # 3. Cálculos Stock
        if cols_stock:
            df['Stock Total'] = df[cols_stock].sum(axis=1)
            df['Inversion Total'] = df['Stock Total'] * df['Costo']
            df['Venta Estimada'] = df['Stock Total'] * df['Precio']
        else:
            df['Stock Total'] = 0
            df['Inversion Total'] = 0
            df['Venta Estimada'] = 0
    else:
        cols_stock = []
        df['Stock Total'] = 0
        df['Inversion Total'] = 0
        df['Venta Estimada'] = 0

    # --- PANTALLAS ---
    if menu == "Tablero Principal":
        st.title("Aurum Suplementos 💪")
        
        # --- CÁLCULO DE CAJA (VENTAS + INICIO) ---
        liq_efvo_ventas, liq_banco_ventas = 0, 0
        
        # 1. Sumar Ventas
        if not df_ventas.empty:
            if 'Total' in df_ventas.columns:
                df_ventas['Total'] = df_ventas['Total'].astype(str)
                df_ventas['Total'] = df_ventas['Total'].str.replace('$', '', regex=False).str.replace(',', '', regex=False)
                df_ventas['Total'] = pd.to_numeric(df_ventas['Total'], errors='coerce').fillna(0)
                
                liq_efvo_ventas = df_ventas[df_ventas['Metodo Pago'] == 'Efectivo']['Total'].sum()
                liq_banco_ventas = df_ventas[df_ventas['Metodo Pago'] == 'Transferencia']['Total'].sum()
        
        # 2. Sumar Caja Inicial (Excel)
        inicio_efvo, inicio_banco = 0, 0
        if not df_caja.empty and 'Monto' in df_caja.columns:
            # Limpiamos columna Monto
            df_caja['Monto'] = df_caja['Monto'].str.replace('$', '', regex=False).str.replace(',', '', regex=False)
            df_caja['Monto'] = pd.to_numeric(df_caja['Monto'], errors='coerce').fillna(0)
            
            # Buscamos los valores
            if not df_caja[df_caja['Concepto'] == 'Inicio Efectivo'].empty:
                inicio_efvo = df_caja[df_caja['Concepto'] == 'Inicio Efectivo']['Monto'].sum()
            
            if not df_caja[df_caja['Concepto'] == 'Inicio Banco'].empty:
                inicio_banco = df_caja[df_caja['Concepto'] == 'Inicio Banco']['Monto'].sum()

        # 3. Totales Finales
        valor_mercaderia_venta = df['Venta Estimada'].sum() # Valor de la mercadería a precio de venta
        total_efvo = liq_efvo_ventas + inicio_efvo
        total_banco = liq_banco_ventas + inicio_banco
        
        # 👇👇 AQUI ESTA EL CAMBIO QUE PEDISTE 👇👇
        # Sumamos: Efectivo + Banco + Valor de Venta de la Mercadería
        gran_total = total_efvo + total_banco + valor_mercaderia_venta

        # MOSTRAR MÉTRICAS
        col1, col2, col3 = st.columns(3)
        col1.metric("💵 Caja Efectivo", f"${total_efvo:,.0f}")
        col2.metric("🏦 Banco/App", f"${total_banco:,.0f}")
        col3.metric("💰 Patrimonio Total", f"${gran_total:,.0f}", delta="Dinero + Mercadería (Precio Venta)")
        
        st.divider()
        
        # Métricas Stock
        c1, c2, c3 = st.columns(3)
        c1.metric("📦 Unidades en Stock", f"{df['Stock Total'].sum():,.0f}")
        c2.metric("Inversión (Costo)", f"${df['Inversion Total'].sum():,.0f}")
        c3.metric("Valor Venta Potencial", f"${df['Venta Estimada'].sum():,.0f}")

        st.subheader("🔎 Detalle de Stock")
        if not df.empty:
            cols_mostrar = ['Nombre', 'Precio', 'Stock Total'] + cols_stock
            cols_reales = [c for c in cols_mostrar if c in df.columns]
            st.dataframe(df[cols_reales], hide_index=True, use_container_width=True)
        else:
            st.info("Carga productos en el Excel.")

    elif menu == "Registrar Venta":
        st.title("💸 Registrar Venta")
        
        if df.empty:
            st.warning("No hay productos cargados en el Excel.")
        elif not sucursales:
            st.warning("No hay sucursales cargadas en el Excel.")
        else:
            with st.form("form_venta"):
                col_a, col_b = st.columns(2)
                prod = col_a.selectbox("Producto", df['Nombre'].unique())
                origen = col_b.selectbox("Sucursal de salida", sucursales)
                
                precio_sug = 0.0
                if not df[df['Nombre'] == prod].empty:
                    val = df[df['Nombre'] == prod]['Precio'].values[0]
                    precio_sug = float(val) if val else 0.0
                
                c1, c2 = st.columns(2)
                cant = c1.number_input("Cantidad", min_value=1, value=1)
                precio = c2.number_input("Precio Cobrado", value=precio_sug)
                
                pago = st.radio("Pago", ["Efectivo", "Transferencia"], horizontal=True)
                nota = st.text_input("Nota")
                
                if st.form_submit_button("CONFIRMAR VENTA"):
                    if registrar_venta_db(prod, cant, precio, pago, origen, nota):
                        st.success(f"Venta registrada!")
                        time.sleep(1)
                        st.rerun()

    elif menu == "Historial Ventas":
        st.title("📜 Historial")
        st.dataframe(df_ventas, use_container_width=True, hide_index=True)

except Exception as e:
    st.error("Ocurrió un error:")
    st.exception(e)
