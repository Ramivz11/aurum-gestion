import streamlit as st
import pandas as pd
import time
import database as db
from datetime import datetime
from fpdf import FPDF

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Aurum Suplementos", page_icon="logo.png", layout="wide")
try:
    st.sidebar.image("logo.png", width=200)
except:
    pass # Si no hay logo, no falla
st.sidebar.title("Aurum Gestión")

# Menú Principal (Incluye Clientes)
menu = st.sidebar.radio("MENÚ", ["Registrar Venta", "Registrar Compra", "Movimientos", "Stock", "Clientes", "Finanzas"])

# Carga inicial de datos
df_prod, sucursales, df_ventas, df_compras = db.obtener_datos_globales()

# --- 1. REGISTRAR VENTA ---
if menu == "Registrar Venta":
    st.title("💸 Nueva Venta")
    
    if not sucursales:
        st.warning("⚠️ Carga sucursales en la base de datos primero.")
    else:
        # ---------------------------------------------------------
        # A) LÓGICA DE CLIENTES
        # ---------------------------------------------------------
        lista_tuples = db.obtener_lista_clientes_simple()
        dict_clientes = {nombre: id_c for id_c, nombre in lista_tuples}
        nombres_ordenados = sorted(list(dict_clientes.keys()))
        
        # Ordenar lista: Nuevo Cliente -> Consumidor Final -> Resto A-Z
        if "Consumidor Final" in nombres_ordenados:
            nombres_ordenados.remove("Consumidor Final")
            opciones_clientes = ["➕ Nuevo Cliente", "Consumidor Final"] + nombres_ordenados
        else:
            opciones_clientes = ["➕ Nuevo Cliente"] + nombres_ordenados

        # Auto-selección inteligente tras crear
        idx_defecto = 0
        if "nuevo_cliente_creado" in st.session_state:
            nombre_creado = st.session_state["nuevo_cliente_creado"]
            if nombre_creado in opciones_clientes:
                idx_defecto = opciones_clientes.index(nombre_creado)
            del st.session_state["nuevo_cliente_creado"]
        elif "Consumidor Final" in opciones_clientes:
            idx_defecto = opciones_clientes.index("Consumidor Final")
        elif len(opciones_clientes) > 1:
            idx_defecto = 1 

        c1, c2 = st.columns(2)
        cliente_sel = c1.selectbox("👤 Cliente", opciones_clientes, index=idx_defecto)
        suc_sel = c2.selectbox("Sucursal", sucursales)

        # Crear cliente rápido
        if cliente_sel == "➕ Nuevo Cliente":
            st.info("🆕 Creando cliente nuevo...")
            with st.form("form_rapido_cliente"):
                nc1, nc2 = st.columns(2)
                new_nombre = nc1.text_input("Nombre y Apellido")
                new_ubicacion = nc2.text_input("Ubicación")
                if st.form_submit_button("💾 Guardar y Usar"):
                    if new_nombre:
                        if db.crear_cliente(new_nombre, new_ubicacion):
                            st.session_state["nuevo_cliente_creado"] = new_nombre
                            st.rerun()
                        else:
                            st.error("Error: Cliente ya existe.")
                    else:
                        st.error("Nombre obligatorio.")
            st.stop()

        cliente_id_final = dict_clientes.get(cliente_sel)

        # ---------------------------------------------------------
        # B) LÓGICA DE PRODUCTOS CON VARIANTE
        # ---------------------------------------------------------
        
        # Traemos el catálogo "expandido" (Producto + Variante)
        df_catalogo = db.obtener_catalogo_venta()
        
        opciones_venta = []
        mapa_datos = {} 
        
        if not df_catalogo.empty:
            for _, row in df_catalogo.iterrows():
                # Si tiene variante, mostramos "Producto | Sabor"
                if row['nombre_variante']:
                    etiqueta = f"{row['nombre']} | {row['nombre_variante']}"
                    var_real = row['nombre_variante']
                else:
                    etiqueta = row['nombre']
                    var_real = ""
                
                opciones_venta.append(etiqueta)
                
                # Guardamos la info real para usarla luego
                mapa_datos[etiqueta] = {
                    "base": row['nombre'],
                    "variante": var_real,
                    "precio": float(row['precio'])
                }
        
        # Selectbox Buscador
        prod_sel_txt = st.selectbox("Producto / Sabor", opciones_venta, index=None, placeholder="Escribe para buscar (ej: Star Choco)")
        
        if prod_sel_txt:
            datos_prod = mapa_datos[prod_sel_txt]
            
            nombre_real = datos_prod['base']
            variante_real = datos_prod['variante']
            precio_lista = datos_prod['precio']
            
            # Consultar Stock (Ahora buscamos en df_prod que tiene claves combinadas "Nombre | Sabor")
            row_stock = df_prod[df_prod['Nombre'] == prod_sel_txt]
            
            if not row_stock.empty:
                stock_disp = int(row_stock.iloc[0].get(f"Stock_{suc_sel}", 0))
            else:
                stock_disp = 0
                
            # --- C) PRECIO DINÁMICO ---
            
            # Resetear si cambia el producto
            if "last_prod_v" not in st.session_state or st.session_state.last_prod_v != prod_sel_txt:
                st.session_state.last_prod_v = prod_sel_txt
                st.session_state.v_cant = 1
                st.session_state.v_precio_total = precio_lista
                st.rerun()

            def actualizar_precio_total():
                st.session_state.v_precio_total = st.session_state.v_cant * precio_lista

            m1, m2 = st.columns(2)
            m1.metric("Precio Unitario", f"${precio_lista:,.0f}")
            
            if stock_disp > 0:
                m2.metric(f"Stock {suc_sel}", f"{stock_disp} u.", delta="Disponible")
            else:
                m2.metric(f"Stock {suc_sel}", "❌ AGOTADO", delta="- Sin Stock", delta_color="inverse")
            
            st.divider()
            
            col_f1, col_f2 = st.columns(2)
            cant = col_f1.number_input("Cantidad", min_value=1, key="v_cant", on_change=actualizar_precio_total)
            precio_total_final = col_f2.number_input("Precio Final Total ($)", min_value=0.0, key="v_precio_total")
            
            metodo = st.radio("Pago", ["Efectivo", "Transferencia"], horizontal=True)
            notas = st.text_input("Notas")
            
            if st.button("✅ REGISTRAR VENTA", type="primary", use_container_width=True):
                if stock_disp < cant:
                    st.error("❌ Stock insuficiente.")
                else:
                    precio_unitario_calc = precio_total_final / cant
                    
                    # Llamamos a registrar_venta con TODOS los argumentos nuevos
                    exito = db.registrar_venta(
                        producto=nombre_real, 
                        variante=variante_real, 
                        cantidad=cant, 
                        precio=precio_unitario_calc, 
                        metodo=metodo, 
                        ubicacion=suc_sel, 
                        notas=notas, 
                        cliente_id=cliente_id_final
                    )
                    
                    if exito:
                        st.success(f"¡Venta de {prod_sel_txt} registrada!")
                        time.sleep(1)
                        if "last_prod_v" in st.session_state: del st.session_state.last_prod_v
                        st.rerun()

# --- 2. REGISTRAR COMPRA ---
elif menu == "Registrar Compra":
    st.title("📦 Ingreso de Mercadería")
    if not sucursales:
        st.warning("Carga sucursales primero.")
    else:
        # CATALOGO COMPRAS: También necesita variantes
        # Reutilizamos la lógica de catalogo pero para ingreso
        # (Para simplificar, usamos el DF global df_prod que ya tiene "Nombre | Sabor")
        lista_prods = sorted(df_prod['Nombre'].unique()) if not df_prod.empty else []
        
        c1, c2 = st.columns(2)
        prod_compra_full = c1.selectbox("Producto / Sabor", lista_prods)
        suc_compra = c2.selectbox("Destino", sucursales)

        # Separar Nombre y Variante
        if prod_compra_full:
            if " | " in prod_compra_full:
                parts = prod_compra_full.split(" | ")
                prod_real_c = parts[0]
                var_real_c = parts[1]
            else:
                prod_real_c = prod_compra_full
                var_real_c = ""
            
            # Buscar costo base
            costo_ini = 0.0
            row = df_prod[df_prod['Nombre'] == prod_compra_full]
            if not row.empty: costo_ini = float(row.iloc[0]['Costo'])
            
            with st.form("form_compra"):
                cc1, cc2 = st.columns(2)
                cant_c = cc1.number_input("Cantidad", min_value=1, value=1)
                costo_c = cc2.number_input("Costo Total ($)", min_value=0.0, value=costo_ini)
                
                cc3, cc4 = st.columns(2)
                prov = cc3.text_input("Proveedor")
                metodo_c = cc4.selectbox("Método Pago", ["Efectivo", "Transferencia"])
                notas_c = st.text_input("Notas / Factura")
                
                if st.form_submit_button("📥 REGISTRAR INGRESO"):
                    if db.registrar_compra(prod_real_c, var_real_c, cant_c, costo_c, prov, metodo_c, suc_compra, notas_c):
                        st.success(f"Ingreso registrado en {suc_compra}!")
                        time.sleep(1.5)
                        st.rerun()

# --- 3. MOVIMIENTOS ---
elif menu == "Movimientos":
    st.title("📜 Historial de Transacciones")
    tipo_mov = st.radio("Ver:", ["Ventas", "Compras"], horizontal=True)
    
    fc1, fc2 = st.columns(2)
    f_suc = fc1.selectbox("Filtrar Sucursal", ["Todas"] + sucursales)
    
    # Filtro producto simple
    f_prod = fc2.text_input("Filtrar Producto (Texto)")
    
    df_show = df_ventas.copy() if tipo_mov == "Ventas" else df_compras.copy()

    if f_suc != "Todas" and not df_show.empty: df_show = df_show[df_show['UBICACION'] == f_suc]
    if f_prod and not df_show.empty: df_show = df_show[df_show['PRODUCTO'].str.contains(f_prod, case=False, na=False)]
    
    # Mostrar tabla con variante si existe
    if 'VARIANTE' in df_show.columns:
        df_show['PRODUCTO_FULL'] = df_show.apply(lambda x: f"{x['PRODUCTO']} {('| ' + x['VARIANTE']) if x['VARIANTE'] else ''}", axis=1)
        cols = ['ID', 'FECHA', 'PRODUCTO_FULL', 'CANTIDAD', 'UBICACION']
        if tipo_mov == "Ventas": cols += ['TOTAL', 'METODO PAGO', 'CLIENTE_ID']
        else: cols += ['COSTO', 'PROVEEDOR']
        st.dataframe(df_show[cols], use_container_width=True, hide_index=True)
    else:
        st.dataframe(df_show, use_container_width=True, hide_index=True)

    st.divider()
    
    # --- ZONA DE ACCIONES (EDITAR / ELIMINAR) ---
    st.subheader("🛠️ Gestionar Registros")
    
    col_sel, col_act = st.columns([2, 1])
    
    # Selector de Registro
    opciones = []
    if not df_show.empty:
        # Creamos una lista legible para el selectbox
        opciones = df_show.apply(lambda x: f"ID {x['ID']} | {x['PRODUCTO']} ({x['CANTIDAD']} u.) | {str(x['FECHA'])}", axis=1).tolist()
    
    sel_registro = col_sel.selectbox(f"Seleccionar {tipo_mov}:", options=opciones)
    
    if sel_registro:
        # Extraer ID del string seleccionado
        id_sel = int(sel_registro.split(" | ")[0].replace("ID ", ""))
        
        tab_edit, tab_del = col_act.tabs(["✏️ Editar", "🗑️ Eliminar"])
        
        # A) EDITAR (Solo implementado para Ventas en este ejemplo)
        with tab_edit:
            if tipo_mov == "Ventas":
                datos_old = db.obtener_venta_por_id(id_sel)
                if datos_old:
                    with st.form("form_edit_venta"):
                        st.caption(f"Editando: {datos_old['producto']}")
                        e_cant = st.number_input("Cantidad", value=int(datos_old['cantidad']), min_value=1)
                        e_precio = st.number_input("Precio Unit.", value=float(datos_old['precio_unitario']), min_value=0.0)
                        e_metodo = st.selectbox("Pago", ["Efectivo", "Transferencia"], index=0 if datos_old['metodo_pago']=="Efectivo" else 1)
                        e_notas = st.text_input("Notas", value=datos_old['notas'] if datos_old['notas'] else "")
                        
                        if st.form_submit_button("Guardar Cambios"):
                            ok, msg = db.actualizar_venta(id_sel, e_cant, e_precio, e_metodo, e_notas)
                            if ok:
                                st.success(msg)
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(msg)
            else:
                st.info("La edición de Compras se puede agregar si la necesitas.")

        # B) ELIMINAR
        with tab_del:
            st.write("¿Borrar permanentemente?")
            if st.button("CONFIRMAR ELIMINACIÓN", type="primary"):
                # Obtenemos la fila del dataframe original para pasar los datos a la función eliminar
                row_del = df_show[df_show['ID'] == id_sel].iloc[0]
                
                if tipo_mov == "Ventas":
                    if db.eliminar_venta(id_sel, row_del): 
                        st.success("Venta eliminada y stock devuelto.")
                        time.sleep(1); st.rerun()
                else:
                    if db.eliminar_compra(id_sel, row_del): 
                        st.success("Compra eliminada y stock descontado.")
                        time.sleep(1); st.rerun()

# --- 4. STOCK (RENOVADO) ---
elif menu == "Stock":
    st.title("📦 Gestión de Inventario Flexible")
    
    # Obtenemos los datos en formato "Matriz" para editar
    df_matrix, lista_sucursales = db.obtener_datos_matrix()
    
    tab_editor, tab_avanzado, tab_nuevo = st.tabs(["📦 Stock", "🛠️ Gestión Variantes / Bajas", "➕ Nuevo Producto"])

    # --- TAB 1: EDITOR TIPO EXCEL ---
    with tab_editor:
        st.caption("Modifica precios, costos y stock directamente en las celdas. Los cambios se guardan al pulsar el botón.")
        
        if not df_matrix.empty:
            # Configuración de columnas para el editor
            column_config = {
                "Producto": st.column_config.TextColumn("Producto", disabled=True), # Bloqueamos nombre para no romper integridad
                "Variante": st.column_config.TextColumn("Variante", disabled=True), # Bloqueamos variante aquí
                "Costo": st.column_config.NumberColumn("Costo ($)", min_value=0, format="$%d"),
                "Precio": st.column_config.NumberColumn("Precio ($)", min_value=0, format="$%d"),
            }
            # Configurar columnas dinámicas de sucursales
            for suc in lista_sucursales:
                column_config[suc] = st.column_config.NumberColumn(f"Stock {suc}", min_value=0, step=1, format="%d u.")

            # EDITOR DE DATOS
            df_editado = st.data_editor(
                df_matrix,
                column_config=column_config,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed", # No permitir agregar filas aquí, usar pestaña "Nuevo"
                key="editor_stock"
            )

            # Botón de guardado
            st.write("")
            col_save, col_info = st.columns([1, 4])
            if col_save.button("💾 GUARDAR CAMBIOS", type="primary"):
                if db.guardar_cambios_masivos(df_editado, lista_sucursales):
                    st.success("✅ ¡Base de datos actualizada!")
                    time.sleep(1)
                    st.rerun()
        else:
            st.info("No hay productos activos. Ve a 'Nuevo Producto'.")

# --- TAB 2: GESTIÓN AVANZADA (Variantes y Bajas) ---
    with tab_avanzado:
        # 1. RECUPERAR DATOS: Obtenemos AMBAS listas (Sucursales y Productos)
        sucs_list, all_prods = db.obtener_listas_auxiliares()
        
        # --- SECCIÓN A: CREAR NUEVA VARIANTE ---
        st.subheader("🎨 Agregar Variantes")
        with st.form("form_add_variante_new"):
            c_add1, c_add2 = st.columns([2, 2])
            prod_add = c_add1.selectbox("Seleccionar Producto", all_prods, key="sel_prod_add_var")
            nombre_var = c_add2.text_input("Nombre de la Variante (Ej: Chocolate)")
            
            if st.form_submit_button("➕ Crear Variante"):
                if prod_add and nombre_var:
                    ok, msg = db.crear_variante(prod_add, nombre_var)
                    if ok:
                        st.success(f"Variante '{nombre_var}' agregada.")
                        time.sleep(1); st.rerun()
                    else: st.error(msg)
                else: st.warning("Completa los campos.")
        
        st.divider()

        # --- SECCIÓN B: HERRAMIENTAS DE CORRECCIÓN ---
        st.subheader("🛠️ Herramientas de Corrección")
        c1, c2 = st.columns(2)
        
        # B.1 RENOMBRAR VARIANTE
        with c1:
            st.markdown("**🏷️ Renombrar Variante**")
            p_renom = st.selectbox("Producto", all_prods, key="sel_prod_renom")
            
            if p_renom:
                vars_exist = db.obtener_variantes_de_producto(p_renom)
                if vars_exist:
                    v_old = st.selectbox("Variante actual", vars_exist, key="sel_var_old")
                    v_new_name = st.text_input("Nuevo nombre", key="inp_var_new")
                    
                    if st.button("Renombrar"):
                        ok, msg = db.renombrar_variante(p_renom, v_old, v_new_name)
                        if ok: 
                            st.success("¡Renombrado exitoso!")
                            time.sleep(1); st.rerun()
                        else: st.error(msg)
                else:
                    st.info("Este producto no tiene variantes.")

        st.divider()
        
        # --- SECCIÓN C: ELIMINAR PRODUCTO ---
        with st.expander("🗑️ Zona de Peligro: Eliminar Producto"):
            st.warning("El producto dejará de aparecer en las listas.")
            prod_del = st.selectbox("Producto a Eliminar", all_prods, key="del_prod_unique")
            
            if st.button("Confirmar Eliminación", type="primary"):
                if db.borrado_logico_producto(prod_del):
                    st.success(f"'{prod_del}' eliminado.")
                    time.sleep(1); st.rerun()

    # --- TAB 3: NUEVO PRODUCTO ---
    with tab_nuevo:
        st.subheader("Alta de Producto")
        with st.form("alta_prod_v2"):
            np_nombre = st.text_input("Nombre del Producto (Ej: PROTEINA STAR)").upper()
            c_np1, c_np2 = st.columns(2)
            np_costo = c_np1.number_input("Costo", min_value=0.0)
            np_precio = c_np2.number_input("Precio", min_value=0.0)
            
            st.markdown("**Variantes Iniciales (Opcional)**")
            np_vars = st.text_input("Separa por comas (Ej: Chocolate, Vainilla, Frutilla)")
            
            if st.form_submit_button("Guardar Nuevo Producto"):
                if db.crear_producto(np_nombre, np_costo, np_precio):
                    # Si puso variantes, las creamos
                    if np_vars:
                        lista_v = [v.strip() for v in np_vars.split(',') if v.strip()]
                        for v in lista_v:
                            db.crear_variante(np_nombre, v)
                    st.success("¡Producto Creado!"); time.sleep(1); st.rerun()
                else:
                    st.error("Error: Probablemente el nombre ya existe.")

# ... (resto de las secciones igual) ...
# --- 5. CLIENTES ---
elif menu == "Clientes":
    st.title("👥 Gestión de Clientes")
    tab1, tab2, tab3 = st.tabs(["📊 Directorio", "➕ Nuevo", "⚙️ Administrar"])
    
    with tab1:
        df_c = db.obtener_clientes_metricas()
        if not df_c.empty:
            df_c['total_gastado'] = df_c['total_gastado'].apply(lambda x: f"${x:,.0f}")
            bsq = st.text_input("Buscar Cliente")
            if bsq: df_c = df_c[df_c['nombre'].str.contains(bsq, case=False, na=False)]
            st.dataframe(df_c, use_container_width=True, hide_index=True)
        else: st.info("Sin clientes.")
        
    with tab2:
        with st.form("new_cl"):
            cn = st.text_input("Nombre")
            cl = st.text_input("Ubicación")
            if st.form_submit_button("Crear"):
                if cn and db.crear_cliente(cn, cl): st.success("Creado"); time.sleep(1); st.rerun()
                
    with tab3:
        lst = db.obtener_lista_clientes_simple()
        if lst:
            n_map = {n: i for i, n in lst}
            c_edit = st.selectbox("Cliente a editar", sorted(n_map.keys()))
            id_e = n_map[c_edit]
            
            c_col1, c_col2 = st.columns([2,1])
            with c_col1:
                with st.form("ed_cl"):
                    ncn = st.text_input("Nuevo Nombre", value=c_edit)
                    if st.form_submit_button("Renombrar"):
                        if db.actualizar_cliente(id_e, ncn, ""): st.success("Listo"); time.sleep(1); st.rerun()
            with c_col2:
                st.write("Zona de peligro")
                if st.button("❌ Eliminar Cliente"):
                    if db.eliminar_cliente(id_e): st.success("Eliminado"); time.sleep(1); st.rerun()

# --- 6. FINANZAS (MEJORADO) ---
elif menu == "Finanzas":
    st.title("💰 Tablero Financiero")
    
    tab1, tab2 = st.tabs(["💵 Flujo de Caja (Caja/Banco)", "📦 Valorización de Stock"])
    
    # --- TAB 1: CAJA Y BANCO (Lo que ya tenías restaurado) ---
    with tab1:
        st.subheader("Disponibilidad Actual")
        df_v, df_c, df_s = db.obtener_resumen_finanzas()
        
        def get_tot(df, met): 
            val = df.loc[df['metodo_pago'] == met, 'total'] if not df.empty else pd.Series([0])
            return float(val.iloc[0]) if not val.empty else 0.0

        # Totales Históricos
        ve, vt = get_tot(df_v, 'Efectivo'), get_tot(df_v, 'Transferencia')
        ce, ct = get_tot(df_c, 'Efectivo'), get_tot(df_c, 'Transferencia')
        
        # Saldos Iniciales
        be, bt = 0.0, 0.0
        if not df_s.empty:
            re = df_s[df_s['cuenta']=='Efectivo']
            rt = df_s[df_s['cuenta']=='Transferencia']
            if not re.empty: be = float(re.iloc[0]['monto'])
            if not rt.empty: bt = float(rt.iloc[0]['monto'])
            
        fin_e = (be + ve - ce)
        fin_t = (bt + vt - ct)
        
        # Tarjetas Métricas
        k1, k2, k3 = st.columns(3)
        k1.metric("💵 EFECTIVO", f"${fin_e:,.0f}", delta=f"Ingresos: ${ve:,.0f}")
        k2.metric("🏦 MERCADO PAGO", f"${fin_t:,.0f}", delta=f"Ingresos: ${vt:,.0f}")
        k3.metric("💰 Total Líquido", f"${(fin_e + fin_t):,.0f}")
        
        st.divider()
        
        with st.expander("⚙️ Ajustar Saldos Iniciales"):
            st.caption("Usa esto si el monto real no coincide con el sistema.")
            with st.form("calib"):
                n_e = st.number_input("Efectivo Real en Mano", value=fin_e)
                n_t = st.number_input("Saldo Real en Banco", value=fin_t)
                if st.form_submit_button("Guardar Ajuste"):
                    # Calculamos el saldo inicial necesario para llegar a ese número
                    # Formula: Saldo_Ini = Real - Ventas + Compras
                    nuevo_be = n_e - ve + ce
                    nuevo_bt = n_t - vt + ct
                    
                    db.actualizar_saldo_inicial('Efectivo', nuevo_be)
                    db.actualizar_saldo_inicial('Transferencia', nuevo_bt)
                    st.success("Saldos recalibrados.")
                    time.sleep(1)
                    st.rerun()

    # --- TAB 2: VALORIZACIÓN DE STOCK (NUEVO) ---
    with tab2:
        st.subheader("Activos en Mercadería")
        
        # Usamos la matriz para calcular todo en tiempo real
        df_matrix, sucursales = db.obtener_datos_matrix()
        
        if not df_matrix.empty and sucursales:
            # 1. Calcular Stock Total por producto (Suma de sucursales)
            df_matrix['stock_total'] = df_matrix[sucursales].sum(axis=1)
            
            # 2. Filtrar solo lo que tiene stock > 0
            df_con_stock = df_matrix[df_matrix['stock_total'] > 0].copy()
            
            if not df_con_stock.empty:
                # 3. Cálculos Financieros
                df_con_stock['val_costo'] = df_con_stock['stock_total'] * df_con_stock['Costo']
                df_con_stock['val_venta'] = df_con_stock['stock_total'] * df_con_stock['Precio']
                df_con_stock['ganancia_pot'] = df_con_stock['val_venta'] - df_con_stock['val_costo']
                
                total_costo = df_con_stock['val_costo'].sum()
                total_venta = df_con_stock['val_venta'].sum()
                total_ganancia = df_con_stock['ganancia_pot'].sum()
                margen_promedio = (total_ganancia / total_costo * 100) if total_costo > 0 else 0
                
                # Métricas Principales
                m1, m2, m3 = st.columns(3)
                m1.metric("Costo Total Stock", f"${total_costo:,.0f}", help="Dinero invertido en mercadería hoy.")
                m2.metric("Valor Precio Venta", f"${total_venta:,.0f}", help="Si vendieras todo hoy a precio de lista.")
                m3.metric("Ganancia Potencial", f"${total_ganancia:,.0f}", delta=f"{margen_promedio:.1f}% Margen")
                
                st.divider()
                st.write("🔎 **Detalle por Producto**")
                
                # Tabla bonita para ver dónde está la plata
                df_view = df_con_stock[['Producto', 'Variante', 'stock_total', 'Costo', 'Precio', 'val_costo', 'ganancia_pot']].sort_values(by='val_costo', ascending=False)
                
                # Formateo visual
                st.dataframe(
                    df_view,
                    column_config={
                        "stock_total": st.column_config.NumberColumn("Cant.", format="%d"),
                        "val_costo": st.column_config.NumberColumn("Inversión ($)", format="$%d"),
                        "ganancia_pot": st.column_config.NumberColumn("Ganancia ($)", format="$%d"),
                        "Costo": st.column_config.NumberColumn("Costo U.", format="$%d"),
                        "Precio": st.column_config.NumberColumn("Precio U.", format="$%d"),
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("No tienes mercadería en stock actualmente.")
        else:
            st.warning("No hay productos cargados o sucursales configuradas.")