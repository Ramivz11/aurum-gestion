import streamlit as st
import pandas as pd
import time
import database as db  # <--- IMPORTAMOS NUESTRO NUEVO MÓDULO

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Aurum Suplementos", page_icon="logo.png", layout="wide")
st.sidebar.image("logo.png", width=200)
st.sidebar.title("Aurum Gestión")

menu = st.sidebar.radio("MENÚ", ["Registrar Venta", "Registrar Compra", "Movimientos", "Stock", "Finanzas"])

# Carga inicial de datos usando el módulo nuevo
df_prod, sucursales, df_ventas = db.obtener_datos_globales()

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
                        # LLAMADA A DATABASE.PY
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
        c1, c2 = st.columns(2)
        prod_compra = c1.selectbox("Producto", sorted(df_prod['Nombre'].unique()) if not df_prod.empty else [])
        suc_compra = c2.selectbox("Destino", sucursales)
        
        with st.form("compra_form"):
            cc1, cc2 = st.columns(2)
            cant_c = cc1.number_input("Cantidad", min_value=1, value=10)
            costo_c = cc2.number_input("Costo Total ($)", min_value=0.0, step=100.0)
            
            cc3, cc4 = st.columns(2)
            prov = cc3.text_input("Proveedor")
            metodo_c = cc4.selectbox("Método Pago", ["Efectivo", "Transferencia"])
            notas_c = st.text_input("Notas / Factura")
            
            if st.form_submit_button("📥 REGISTRAR INGRESO", type="primary"):
                if db.registrar_compra(prod_compra, cant_c, costo_c, prov, metodo_c, suc_compra, notas_c):
                    st.success(f"Ingreso registrado en {suc_compra}!")
                    time.sleep(1.5)
                    st.rerun()

# --- 3. MOVIMIENTOS ---
elif menu == "Movimientos":
    st.title("📜 Historial")
    fc1, fc2 = st.columns(2)
    f_suc = fc1.selectbox("Filtrar Sucursal", ["Todas"] + sucursales)
    f_prod = fc2.selectbox("Filtrar Producto", ["Todos"] + (sorted(df_prod['Nombre'].unique().tolist()) if not df_prod.empty else []))
    
    df_show = df_ventas.copy()
    if f_suc != "Todas": df_show = df_show[df_show['UBICACION'] == f_suc]
    if f_prod != "Todos": df_show = df_show[df_show['PRODUCTO'] == f_prod]
    
    st.dataframe(df_show, use_container_width=True, hide_index=True)
    st.divider()
    
    tab1, tab2 = st.tabs(["✏️ Editar", "🗑️ Eliminar"])
    opciones = df_show.apply(lambda x: f"ID {x['ID']} | {x['PRODUCTO']} | {x['FECHA']}", axis=1).tolist()
    
    if opciones:
        with tab1:
            sel_edit = st.selectbox("Editar venta:", opciones, key="s_edit")
            id_edit = int(sel_edit.split(" | ")[0].replace("ID ", ""))
            row = df_ventas[df_ventas['ID'] == id_edit].iloc[0]
            
            with st.form("f_edit"):
                ne1, ne2 = st.columns(2)
                np = ne1.selectbox("Producto", df_prod['Nombre'].unique(), index=list(df_prod['Nombre'].unique()).index(row['PRODUCTO']))
                ns = ne2.selectbox("Sucursal", sucursales, index=sucursales.index(row['UBICACION']))
                nc = st.number_input("Cantidad", value=int(row['CANTIDAD']))
                npr = st.number_input("Precio", value=float(row['PRECIO UNITARIO']))
                nm = st.selectbox("Pago", ["Efectivo", "Transferencia"], index=["Efectivo", "Transferencia"].index(row['METODO PAGO']))
                nn = st.text_input("Notas", value=str(row['NOTAS']))
                
                if st.form_submit_button("Guardar Cambios"):
                    d_new = {'producto': np, 'cantidad': nc, 'precio': npr, 'ubicacion': ns, 'metodo': nm, 'notas': nn}
                    if db.editar_venta(id_edit, row, d_new):
                        st.success("Editado correctamente")
                        time.sleep(1)
                        st.rerun()

        with tab2:
            sel_del = st.selectbox("Eliminar venta:", opciones, key="s_del")
            id_del = int(sel_del.split(" | ")[0].replace("ID ", ""))
            if st.button("🗑️ ELIMINAR DEFINITIVAMENTE", type="primary"):
                row_del = df_ventas[df_ventas['ID'] == id_del].iloc[0]
                if db.eliminar_venta(id_del, row_del):
                    st.success("Eliminado y stock restaurado")
                    time.sleep(1)
                    st.rerun()

# --- 4. STOCK ---
# --- 4. STOCK Y PRODUCTOS ---
elif menu == "Stock":
    st.title("📦 Gestión de Productos e Inventario")
    
    # Creamos pestañas
    tab1, tab2 = st.tabs(["📊 Ver Inventario", "➕ Nuevo Producto"])
    
    with tab1:
        # Mostramos la tabla tal cual estaba
        st.dataframe(df_prod, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("Dar de alta nuevo producto")
        with st.form("alta_producto"):
            nombre_nuevo = st.text_input("Nombre del Producto").upper()
            c1, c2 = st.columns(2)
            costo_nuevo = c1.number_input("Costo", min_value=0.0, step=100.0)
            precio_nuevo = c2.number_input("Precio Venta", min_value=0.0, step=100.0)
            
            submitted = st.form_submit_button("Guardar Producto")
            if submitted:
                if not nombre_nuevo:
                    st.error("El nombre no puede estar vacío.")
                else:
                    # Llamamos a la función que acabamos de poner en database.py
                    if db.crear_producto(nombre_nuevo, costo_nuevo, precio_nuevo):
                        st.success(f"¡Producto '{nombre_nuevo}' creado!")
                        time.sleep(1)
                        st.rerun()
# --- 5. FINANZAS ---
elif menu == "Finanzas":
    st.title("💰 Finanzas y Patrimonio")
    
    # Obtenemos datos crudos desde database.py
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
                # Ajuste inverso: NuevoBase = Real - Ventas + Compras
                n_base_ef = real_ef - v_ef + c_ef
                n_base_tr = real_tr - v_tr + c_tr
                
                db.actualizar_saldo_inicial('Efectivo', n_base_ef)
                db.actualizar_saldo_inicial('Transferencia', n_base_tr)
                st.success("¡Calibrado!")
                time.sleep(1)
                st.rerun()

    # Totales Finales (re-calculados con base fresca)
    final_ef = sis_ef # (Ya calculado arriba con la base leída)
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