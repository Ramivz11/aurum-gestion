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
        # Crear columna visual combinada
        df_show['PRODUCTO_FULL'] = df_show.apply(lambda x: f"{x['PRODUCTO']} {('| ' + x['VARIANTE']) if x['VARIANTE'] else ''}", axis=1)
        # Reordenar para ver mejor
        cols = ['ID', 'FECHA', 'PRODUCTO_FULL', 'CANTIDAD', 'UBICACION']
        if tipo_mov == "Ventas": cols += ['TOTAL', 'METODO PAGO', 'CLIENTE_ID']
        else: cols += ['COSTO', 'PROVEEDOR']
        st.dataframe(df_show[cols], use_container_width=True, hide_index=True)
    else:
        st.dataframe(df_show, use_container_width=True, hide_index=True)

    st.divider()
    
    # Eliminación
    st.subheader("🗑️ Eliminar Registro")
    opciones = []
    if not df_show.empty:
        opciones = df_show.apply(lambda x: f"ID {x['ID']} | {x['PRODUCTO']} {x.get('VARIANTE','')} | {x['FECHA']}", axis=1).tolist()
    
    sel_del = st.selectbox(f"Seleccionar {tipo_mov}:", options=opciones)
    if sel_del:
        id_del = int(sel_del.split(" | ")[0].replace("ID ", ""))
        if st.button("ELIMINAR DEFINITIVAMENTE", type="primary"):
            row_del = df_show[df_show['ID'] == id_del].iloc[0]
            if tipo_mov == "Ventas":
                if db.eliminar_venta(id_del, row_del): st.success("Eliminado"); time.sleep(1); st.rerun()
            else:
                if db.eliminar_compra(id_del, row_del): st.success("Eliminado"); time.sleep(1); st.rerun()

# --- 4. STOCK ---
elif menu == "Stock":
    st.title("📦 Gestión de Productos e Inventario")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Ver Inventario", "➕ Nuevo Producto", "🎨 Agregar Variantes", "✏️ Editar Producto", "📄 Reporte PDF"])
    
    with tab1:
        st.subheader("📋 Inventario Global")
        busqueda = st.text_input("🔍 Filtrar por Producto", placeholder="Ej: Star Proteina")
        if not df_prod.empty:
            df_show = df_prod.copy()
            if busqueda:
                for palabra in busqueda.split():
                    df_show = df_show[df_show['Nombre'].str.contains(palabra, case=False, regex=False, na=False)]
            st.dataframe(df_show, use_container_width=True, hide_index=True)
            st.caption(f"Resultados: {len(df_show)}")
        else:
            st.info("No hay productos.")

    with tab2:
        st.subheader("Nuevo Producto Base")
        with st.form("alta_producto"):
            nombre_nuevo = st.text_input("Nombre (Sin sabor)").upper()
            c1, c2 = st.columns(2)
            costo_nuevo = c1.number_input("Costo", min_value=0.0)
            precio_nuevo = c2.number_input("Precio", min_value=0.0)
            if st.form_submit_button("Guardar"):
                if nombre_nuevo and db.crear_producto(nombre_nuevo, costo_nuevo, precio_nuevo):
                    st.success("Creado!"); time.sleep(1); st.rerun()

    with tab3:
        st.subheader("🎨 Crear Sabores / Variantes")
        st.info("Agrega variantes a tus productos existentes (Ej: Chocolate, Vainilla).")
        if not df_prod.empty:
            # Filtramos solo nombres base
            nombres_base = sorted(list(set([n.split(' | ')[0] for n in df_prod['Nombre'].unique()])))
            with st.form("form_variante"):
                prod_padre = st.selectbox("Seleccionar Producto Base", nombres_base)
                nombre_var = st.text_input("Nombre de la Variante (Ej: Frutilla)")
                if st.form_submit_button("➕ Agregar Variante"):
                    ok, msg = db.crear_variante(prod_padre, nombre_var.strip())
                    if ok:
                        st.success(f"¡{nombre_var} agregado!"); time.sleep(1); st.rerun()
                    else:
                        st.error(msg)
        else:
            st.warning("Carga productos primero.")

    with tab4:
        st.subheader("Editar Producto Base")
        if not df_prod.empty:
            prod_edit = st.selectbox("Seleccionar", sorted(df_prod['Nombre'].unique()))
            datos = df_prod[df_prod['Nombre'] == prod_edit].iloc[0]
            with st.form("edit_prod"):
                nn = st.text_input("Nombre", value=datos['Nombre'])
                ce1, ce2 = st.columns(2)
                nc = ce1.number_input("Costo", value=float(datos['Costo']))
                np = ce2.number_input("Precio", value=float(datos['Precio']))
                if st.form_submit_button("Actualizar"):
                    if db.actualizar_producto(prod_edit, nn, nc, np):
                        st.success("Actualizado!"); time.sleep(1); st.rerun()

    with tab5:
        st.subheader("Reporte PDF")
        if sucursales:
            suc_pdf = st.selectbox("Sucursal:", sucursales, key="s_pdf")
            if st.button("Descargar PDF"):
                col_s = f"Stock_{suc_pdf}"
                if col_s in df_prod.columns:
                    df_r = df_prod[df_prod[col_s] > 0][['Nombre', col_s]].copy()
                    if not df_r.empty:
                        pdf = FPDF()
                        pdf.add_page(); pdf.set_font('Arial', 'B', 16); pdf.cell(0,10,f"Stock: {suc_pdf}",0,1,'C')
                        pdf.ln(5); pdf.set_font('Arial', '', 12)
                        for _, r in df_r.iterrows():
                            pdf.cell(140, 10, str(r['Nombre']).encode('latin-1','replace').decode('latin-1'), 1)
                            pdf.cell(40, 10, str(int(r[col_s])), 1, 1, 'C')
                        st.download_button("⬇️ PDF", pdf.output(dest='S').encode('latin-1'), f"Stock_{suc_pdf}.pdf", "application/pdf")
                    else: st.warning("Sin stock.")

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

# --- 6. FINANZAS ---
elif menu == "Finanzas":
    st.title("💰 Finanzas")
    df_v, df_c, df_s = db.obtener_resumen_finanzas()
    
    def get_tot(df, met): 
        val = df.loc[df['metodo_pago'] == met, 'total'] if not df.empty else pd.Series([0])
        return float(val.iloc[0]) if not val.empty else 0.0

    ve, vt = get_tot(df_v, 'Efectivo'), get_tot(df_v, 'Transferencia')
    ce, ct = get_tot(df_c, 'Efectivo'), get_tot(df_c, 'Transferencia')
    
    be, bt = 0.0, 0.0
    if not df_s.empty:
        re = df_s[df_s['cuenta']=='Efectivo']
        rt = df_s[df_s['cuenta']=='Transferencia']
        if not re.empty: be = float(re.iloc[0]['monto'])
        if not rt.empty: bt = float(rt.iloc[0]['monto'])
        
    fin_e, fin_t = (be + ve - ce), (bt + vt - ct)
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Caja Efectivo", f"${fin_e:,.0f}")
    k2.metric("Banco", f"${fin_t:,.0f}")
    k3.metric("Total Líquido", f"${(fin_e + fin_t):,.0f}")
    
    st.divider()
    with st.expander("Calibrar Saldos"):
        with st.form("calib"):
            n_e = st.number_input("Efectivo Real", value=fin_e)
            n_t = st.number_input("Banco Real", value=fin_t)
            if st.form_submit_button("Ajustar"):
                db.actualizar_saldo_inicial('Efectivo', n_e - ve + ce)
                db.actualizar_saldo_inicial('Transferencia', n_t - vt + ct)
                st.rerun()