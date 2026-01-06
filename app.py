import streamlit as st
import pandas as pd
import time
import database as db
from datetime import datetime
from fpdf import FPDF

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Aurum Suplementos", page_icon="logo.png", layout="wide")
st.sidebar.image("logo.png", width=200)
st.sidebar.title("Aurum Gestión")

menu = st.sidebar.radio("MENÚ", ["Registrar Venta", "Registrar Compra", "Movimientos", "Stock", "Finanzas"])

# Carga inicial de datos (ahora recuperamos 4 variables)
df_prod, sucursales, df_ventas, df_compras = db.obtener_datos_globales()

# --- 1. REGISTRAR VENTA ---
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
            
            if stock_disp > 0:
                m2.metric(f"Stock {suc_sel}", f"{stock_disp} u.", delta="Disponible")
            else:
                m2.metric(f"Stock {suc_sel}", "❌ AGOTADO", delta="- Sin Stock", delta_color="inverse")
            
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
                        if db.registrar_venta(prod_sel, cant, precio, metodo, suc_sel, notas):
                            st.success("Venta registrada!")
                            time.sleep(1)
                            st.rerun()

# --- 2. REGISTRAR COMPRA ---
elif menu == "Registrar Compra":
    st.title("📦 Ingreso de Mercadería")
    if not sucursales:
        st.warning("Carga sucursales primero.")
    else:
        # --- FUNCIÓN DE ACTUALIZACIÓN AUTOMÁTICA ---
        def actualizar_total():
            # 1. Obtener valores desde el estado
            p_sel = st.session_state.k_prod_compra
            c_sel = st.session_state.k_cant_compra
            
            # 2. Buscar costo unitario
            c_unitario = 0.0
            if not df_prod.empty:
                row = df_prod[df_prod['Nombre'] == p_sel]
                if not row.empty:
                    c_unitario = float(row.iloc[0]['Costo'])
            
            # 3. Calcular y escribir en el estado de "Costo Total"
            st.session_state.k_costo_total = c_unitario * c_sel

        # --- INTERFAZ ---
        c1, c2 = st.columns(2)
        
        lista_prods = sorted(df_prod['Nombre'].unique()) if not df_prod.empty else []
        
        # Selectbox: Producto
        prod_compra = c1.selectbox(
            "Producto", 
            lista_prods, 
            key="k_prod_compra", 
            on_change=actualizar_total
        )
        
        suc_compra = c2.selectbox("Destino", sucursales)

        # --- PREPARACIÓN DE VALORES INICIALES ---
        # Si el usuario entra por primera vez y no existe 'k_costo_total' en memoria, lo calculamos.
        if "k_costo_total" not in st.session_state:
            costo_ini_unitario = 0.0
            if prod_compra and not df_prod.empty:
                row_ini = df_prod[df_prod['Nombre'] == prod_compra]
                if not row_ini.empty:
                    costo_ini_unitario = float(row_ini.iloc[0]['Costo'])
            # Inicializamos en memoria (Cantidad 1 por defecto * Costo)
            st.session_state.k_costo_total = costo_ini_unitario * 1.0

        with st.container(): # Usamos container visual en lugar de form para orden
            cc1, cc2 = st.columns(2)
            
            # Input: Cantidad
            cant_c = cc1.number_input(
                "Cantidad", 
                min_value=1, 
                value=1, 
                key="k_cant_compra", 
                on_change=actualizar_total
            )
            
            # Input: Costo Total
            # IMPORTANTE: No usamos 'value=' aquí para evitar el error.
            # Streamlit tomará el valor directamente de st.session_state.k_costo_total
            costo_c = cc2.number_input(
                "Costo Total ($)", 
                min_value=0.0, 
                step=100.0, 
                key="k_costo_total" 
            )
            
            cc3, cc4 = st.columns(2)
            prov = cc3.text_input("Proveedor")
            metodo_c = cc4.selectbox("Método Pago", ["Efectivo", "Transferencia"])
            
            notas_c = st.text_input("Notas / Factura")
            
            st.divider()
            
            if st.button("📥 REGISTRAR INGRESO", type="primary", use_container_width=True):
                if db.registrar_compra(prod_compra, cant_c, costo_c, prov, metodo_c, suc_compra, notas_c):
                    st.success(f"Ingreso registrado en {suc_compra}!")
                    time.sleep(1.5)
                    st.rerun()

# --- 3. MOVIMIENTOS ---
elif menu == "Movimientos":
    st.title("📜 Historial de Transacciones")
    
    tipo_mov = st.radio("Ver:", ["Ventas", "Compras"], horizontal=True)
    
    fc1, fc2 = st.columns(2)
    f_suc = fc1.selectbox("Filtrar Sucursal", ["Todas"] + sucursales)
    f_prod = fc2.selectbox("Filtrar Producto", ["Todos"] + (sorted(df_prod['Nombre'].unique().tolist()) if not df_prod.empty else []))
    
    # Seleccionamos qué tabla usar
    if tipo_mov == "Ventas":
        df_show = df_ventas.copy()
    else:
        df_show = df_compras.copy()

    # Aplicar filtros
    if f_suc != "Todas" and not df_show.empty: 
        df_show = df_show[df_show['UBICACION'] == f_suc]
    if f_prod != "Todos" and not df_show.empty: 
        df_show = df_show[df_show['PRODUCTO'] == f_prod]
    
    st.dataframe(df_show, use_container_width=True, hide_index=True)
    st.divider()
    
    # Pestañas para editar / eliminar
    tab1, tab2 = st.tabs(["✏️ Editar Registro", "🗑️ Eliminar Registro"])
    
    # Generamos la lista de opciones para el selectbox
    opciones = []
    if not df_show.empty:
        opciones = df_show.apply(lambda x: f"ID {x['ID']} | {x['PRODUCTO']} | {x['FECHA']}", axis=1).tolist()
    
    if opciones:
        with tab1:
            sel_edit = st.selectbox(f"Editar {tipo_mov.lower()}:", opciones, key="s_edit")
            id_edit = int(sel_edit.split(" | ")[0].replace("ID ", ""))
            row = df_show[df_show['ID'] == id_edit].iloc[0]
            
            with st.form("f_edit"):
                ne1, ne2 = st.columns(2)
                # Producto y Sucursal
                idx_p = list(df_prod['Nombre'].unique()).index(row['PRODUCTO']) if row['PRODUCTO'] in df_prod['Nombre'].unique() else 0
                idx_s = sucursales.index(row['UBICACION']) if row['UBICACION'] in sucursales else 0
                
                np = ne1.selectbox("Producto", df_prod['Nombre'].unique(), index=idx_p)
                ns = ne2.selectbox("Sucursal", sucursales, index=idx_s)
                
                nc = st.number_input("Cantidad", value=int(row['CANTIDAD']))
                
                # Campos diferentes según venta o compra
                if tipo_mov == "Ventas":
                    n_money = st.number_input("Precio Unitario", value=float(row['PRECIO UNITARIO']))
                    n_prov = ""
                else:
                    n_money = st.number_input("Costo Total", value=float(row['COSTO']))
                    n_prov = st.text_input("Proveedor", value=str(row['PROVEEDOR']))
                
                nm = st.selectbox("Pago", ["Efectivo", "Transferencia"], index=["Efectivo", "Transferencia"].index(row['METODO PAGO']))
                nn = st.text_input("Notas", value=str(row['NOTAS']))
                
                if st.form_submit_button("Guardar Cambios"):
                    if tipo_mov == "Ventas":
                        d_new = {'producto': np, 'cantidad': nc, 'precio': n_money, 'ubicacion': ns, 'metodo': nm, 'notas': nn}
                        if db.editar_venta(id_edit, row, d_new):
                            st.success("Venta editada correctamente")
                            time.sleep(1)
                            st.rerun()
                    else:
                        # Para compras
                        d_new = {'producto': np, 'cantidad': nc, 'costo': n_money, 'proveedor': n_prov, 'ubicacion': ns, 'metodo': nm, 'notas': nn}
                        if db.editar_compra(id_edit, row, d_new):
                            st.success("Compra editada correctamente (Stock y Caja ajustados)")
                            time.sleep(1)
                            st.rerun()

        with tab2:
            sel_del = st.selectbox(f"Eliminar {tipo_mov.lower()}:", opciones, key="s_del")
            id_del = int(sel_del.split(" | ")[0].replace("ID ", ""))
            
            st.warning(f"⚠️ Al eliminar, se revertirá el stock y el dinero automáticamente.")
            if st.button("🗑️ ELIMINAR DEFINITIVAMENTE", type="primary"):
                row_del = df_show[df_show['ID'] == id_del].iloc[0]
                
                if tipo_mov == "Ventas":
                    if db.eliminar_venta(id_del, row_del):
                        st.success("Venta eliminada")
                        time.sleep(1)
                        st.rerun()
                else:
                    if db.eliminar_compra(id_del, row_del):
                        st.success("Compra eliminada (Stock descontado)")
                        time.sleep(1)
                        st.rerun()
    else:
        st.info("No hay registros para mostrar con los filtros actuales.")

# --- EN app.py (Sección STOCK completa) ---

# ... (resto del código anterior) ...

# --- 4. STOCK ---
elif menu == "Stock":
    st.title("📦 Gestión de Productos e Inventario")
    
    # AHORA SON 4 PESTAÑAS
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Ver Inventario", "➕ Nuevo Producto", "✏️ Editar Producto", "📄 Reporte PDF"])
    
    # --- EN app.py --- dentro de la sección STOCK

    # ... (líneas anteriores donde defines tab1, tab2, tab3, tab4) ...

    with tab1:
        st.subheader("📋 Inventario Global")
        
        # 1. Campo de búsqueda (Filtro)
        busqueda = st.text_input("🔍 Filtrar por Producto o Marca", placeholder="Ej: Star Nutrition, Ena, Proteina...")
        
        # 2. Lógica de filtrado
        if not df_prod.empty:
            if busqueda:
                # Busca el texto dentro del Nombre (ignora mayúsculas/minúsculas)
                mask = df_prod['Nombre'].str.contains(busqueda, case=False, na=False)
                df_show = df_prod[mask]
            else:
                df_show = df_prod
            
            # 3. Mostrar tabla filtrada
            st.dataframe(df_show, use_container_width=True, hide_index=True)
            
            # (Opcional) Contador de resultados
            st.caption(f"Mostrando {len(df_show)} productos.")
        else:
            st.info("Aún no hay productos registrados.")

    # ... (resto del código de tab2, tab3, tab4) ...

    with tab2:
        st.subheader("Dar de alta nuevo producto")
        with st.form("alta_producto"):
            nombre_nuevo = st.text_input("Nombre del Producto").upper()
            c1, c2 = st.columns(2)
            costo_nuevo = c1.number_input("Costo", min_value=0.0, step=100.0)
            precio_nuevo = c2.number_input("Precio Venta", min_value=0.0, step=100.0)
            
            if st.form_submit_button("Guardar Producto"):
                if not nombre_nuevo:
                    st.error("El nombre no puede estar vacío.")
                else:
                    if db.crear_producto(nombre_nuevo, costo_nuevo, precio_nuevo):
                        st.success(f"¡Producto '{nombre_nuevo}' creado!")
                        time.sleep(1)
                        st.rerun()

    with tab3:
        st.subheader("Modificar producto existente")
        if df_prod.empty:
            st.info("No hay productos cargados.")
        else:
            lista_productos = sorted(df_prod['Nombre'].unique())
            prod_a_editar = st.selectbox("Seleccionar Producto", lista_productos)
            
            datos_actuales = df_prod[df_prod['Nombre'] == prod_a_editar].iloc[0]
            
            with st.form("editar_producto"):
                new_name = st.text_input("Nombre", value=datos_actuales['Nombre'])
                col_e1, col_e2 = st.columns(2)
                new_costo = col_e1.number_input("Costo", min_value=0.0, step=100.0, value=float(datos_actuales['Costo']))
                new_precio = col_e2.number_input("Precio Venta", min_value=0.0, step=100.0, value=float(datos_actuales['Precio']))
                
                if st.form_submit_button("💾 Guardar Cambios"):
                    if db.actualizar_producto(prod_a_editar, new_name, new_costo, new_precio):
                        st.success(f"Producto '{new_name}' actualizado correctamente.")
                        time.sleep(1)
                        st.rerun()

    # --- NUEVA PESTAÑA: REPORTE PDF ---
    # --- PESTAÑA 4: REPORTE PDF (DISEÑO PROFESIONAL) ---
    with tab4:
        st.subheader("Generar Reporte de Stock para Gimnasio")
        st.write("Selecciona una sucursal para generar un PDF con su stock actual.")
        
        suc_pdf = st.selectbox("Seleccionar Sucursal:", sucursales, key="s_pdf")
        
        if st.button("📄 Descargar Reporte PDF"):
            # 1. Preparar datos
            col_stock = f"Stock_{suc_pdf}"
            if col_stock in df_prod.columns:
                df_reporte = df_prod[df_prod[col_stock] > 0][['Nombre', col_stock]].copy()
            else:
                df_reporte = pd.DataFrame()

            if df_reporte.empty:
                st.warning(f"La sucursal {suc_pdf} no tiene stock registrado.")
            else:
                # 2. Configuración de colores y métricas
                ORANGE_RGB = (255, 153, 0) # Naranja Aurum
                GREY_TEXT = (100, 100, 100)
                GREY_LIGHT = (245, 245, 245) # Para filas alternadas

                class PDF(FPDF):
                    def header(self):
                        # --- LOGO (Izquierda) ---
                        # Ajusta la 'w' (ancho) si el logo se ve muy grande o chico
                        try:
                            self.image('logo.png', 10, 10, 35) 
                        except:
                            pass # Si no encuentra el logo, no falla
                        
                        # --- TITULOS (Derecha) ---
                        self.set_y(12)
                        self.set_font('Arial', '', 20)
                        self.set_text_color(0, 0, 0) # Negro
                        self.cell(0, 10, 'AURUM SUPLEMENTOS', 0, 1, 'R')
                        
                        self.set_font('Arial', 'B', 12)
                        self.set_text_color(*ORANGE_RGB) # Naranja
                        self.cell(0, 6, 'REPORTE DE STOCK', 0, 1, 'R')
                        
                        self.set_font('Arial', '', 10)
                        self.set_text_color(*GREY_TEXT) # Gris
                        self.cell(0, 6, f'Sucursal: {suc_pdf}', 0, 1, 'R')
                        self.cell(0, 6, f'Fecha: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'R')
                        
                        # --- LINEA SEPARADORA ---
                        self.ln(5)
                        self.set_draw_color(*ORANGE_RGB)
                        self.set_line_width(0.8)
                        self.line(10, self.get_y(), 200, self.get_y())
                        self.ln(10)

                    def footer(self):
                        # Posición a 3 cm del final
                        self.set_y(-30)
                        
                        # --- REDES Y CONTACTO (Derecha) ---
                        self.set_font('Arial', '', 10)
                        self.set_text_color(*ORANGE_RGB)
                        self.cell(0, 5, '@suplementos.aurum', 0, 1, 'R')
                        
                        self.set_text_color(*GREY_TEXT)
                        self.cell(0, 5, 'Tel: 3516753814', 0, 1, 'R')
                        
                        # --- TEXTO LEGAL CENTRADO (Muy abajo) ---
                        self.set_y(-12)
                        self.set_font('Arial', 'I', 8)
                        self.set_text_color(200, 200, 200) # Gris muy claro
                        self.cell(0, 10, 'Aurum Suplementos - Documento Interno', 0, 0, 'C')

                # Instanciar PDF
                pdf = PDF()
                pdf.set_auto_page_break(auto=True, margin=35)
                pdf.add_page()
                
                # --- TABLA DE PRODUCTOS ---
                
                # Encabezado de Tabla (Naranja)
                pdf.set_font("Arial", 'B', 10)
                pdf.set_fill_color(*ORANGE_RGB)
                pdf.set_text_color(255, 255, 255) # Blanco
                pdf.set_draw_color(255, 255, 255) # Bordes blancos para limpieza
                
                # Anchos: Producto (150mm), Cantidad (40mm) -> Total 190mm
                pdf.cell(150, 12, "Producto", 1, 0, 'C', fill=True)
                pdf.cell(40, 12, "Cantidad", 1, 1, 'C', fill=True)
                
                # Cuerpo de Tabla
                pdf.set_font("Arial", size=10)
                pdf.set_text_color(50, 50, 50) # Gris oscuro para texto
                pdf.set_draw_color(230, 230, 230) # Gris muy suave para líneas
                
                fill = False # Variable para alternar colores (Cebra)
                
                for _, row in df_reporte.iterrows():
                    # Sanitizar texto
                    nombre_txt = str(row['Nombre']).encode('latin-1', 'replace').decode('latin-1')
                    cant_txt = str(int(row[col_stock]))
                    
                    # Color de fondo alternado
                    if fill:
                        pdf.set_fill_color(*GREY_LIGHT)
                    else:
                        pdf.set_fill_color(255, 255, 255)
                    
                    # Celdas con relleno (height=10 para dar aire)
                    pdf.cell(150, 10, f"  {nombre_txt}", 'B', 0, 'L', fill=True) # 'B' es border-bottom
                    pdf.cell(40, 10, cant_txt, 'B', 1, 'C', fill=True)
                    
                    fill = not fill # Cambiar color para la siguiente vuelta
                
                # --- TOTAL ITEMS ---
                pdf.ln(5)
                pdf.set_text_color(*GREY_TEXT)
                pdf.set_font("Arial", '', 10)
                pdf.cell(0, 10, f"Total de items diferentes en stock: {len(df_reporte)}", ln=True)

                # Generar bytes
                pdf_bytes = pdf.output(dest='S').encode('latin-1')
                
                st.success("¡PDF Generado!")
                
                st.download_button(
                    label=f"⬇️ Descargar Reporte {suc_pdf}",
                    data=pdf_bytes,
                    file_name=f"Stock_{suc_pdf}_{datetime.now().strftime('%Y-%m-%d')}.pdf",
                    mime="application/pdf"
                )

# --- 5. FINANZAS ---
elif menu == "Finanzas":
    st.title("💰 Finanzas y Patrimonio")
    
    df_v, df_c, df_saldos = db.obtener_resumen_finanzas()
    
    def get_val(df, metodo):
        if df.empty: return 0.0
        val = df.loc[df['metodo_pago'] == metodo, 'total']
        return float(val.iloc[0]) if not val.empty else 0.0

    # 1. Ventas y Compras
    v_ef = get_val(df_v, 'Efectivo')
    v_tr = get_val(df_v, 'Transferencia')
    c_ef = get_val(df_c, 'Efectivo')
    c_tr = get_val(df_c, 'Transferencia')
    
    # 2. Saldos Iniciales
    base_ef = 0.0
    base_tr = 0.0
    if not df_saldos.empty:
        r_ef = df_saldos[df_saldos['cuenta'] == 'Efectivo']
        r_tr = df_saldos[df_saldos['cuenta'] == 'Transferencia']
        if not r_ef.empty: base_ef = float(r_ef.iloc[0]['monto'])
        if not r_tr.empty: base_tr = float(r_tr.iloc[0]['monto'])

    # 3. Calculos Actuales
    sis_ef = base_ef + v_ef - c_ef
    sis_tr = base_tr + v_tr - c_tr

    with st.expander("⚙️ Calibrar Caja (Saldo Real)"):
        st.info("Ingresa el dinero REAL que tienes hoy.")
        with st.form("calibrar"):
            c1, c2 = st.columns(2)
            real_ef = c1.number_input("Efectivo Real", value=sis_ef, step=100.0)
            real_tr = c2.number_input("Banco Real", value=sis_tr, step=100.0)
            
            if st.form_submit_button("Calibrar"):
                n_base_ef = real_ef - v_ef + c_ef
                n_base_tr = real_tr - v_tr + c_tr
                
                db.actualizar_saldo_inicial('Efectivo', n_base_ef)
                db.actualizar_saldo_inicial('Transferencia', n_base_tr)
                st.success("¡Calibrado!")
                time.sleep(1)
                st.rerun()

    final_ef = sis_ef 
    final_tr = sis_tr 

    # Valor Stock
    cols_s = [c for c in df_prod.columns if c.startswith('Stock_')]
    if cols_s and not df_prod.empty:
        df_prod['Total_U'] = df_prod[cols_s].sum(axis=1)
        val_venta = (df_prod['Total_U'] * df_prod['Precio']).sum()
        val_costo = (df_prod['Total_U'] * df_prod['Costo']).sum()
    else:
        val_venta = 0
        val_costo = 0

    st.markdown("### 💵 Disponibilidad")
    k1, k2, k3 = st.columns(3)
    k1.metric("Caja Efectivo", f"${final_ef:,.0f}")
    k2.metric("Banco", f"${final_tr:,.0f}")
    k3.metric("Total Líquido", f"${(final_ef + final_tr):,.0f}")
    
    st.divider()
    
    st.markdown("### 📦 Inventario")
    m1, m2, m3 = st.columns(3)
    m1.metric("Costo", f"${val_costo:,.0f}")
    m2.metric("Venta Potencial", f"${val_venta:,.0f}")
    m3.metric("Margen", f"${(val_venta - val_costo):,.0f}")
    
    st.subheader(f"💎 Patrimonio Total: ${(final_ef + final_tr + val_venta):,.0f}")