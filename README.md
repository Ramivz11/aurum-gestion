# Sistema de Gestión - Aurum Suplementos

Aplicación web desarrollada en Python para el control de stock, registro de ventas y seguimiento financiero. Utiliza Google Sheets como backend para permitir la sincronización de datos en tiempo real y facilitar la administración manual.

## Funcionalidades Principales

- **Tablero de Control:** Visualización en tiempo real de caja (efectivo y bancos), patrimonio total y valuación de mercadería.
- **Control de Inventario:** Descuento automático de stock por sucursal al confirmar ventas.
- **Registro de Ventas:** Interfaz simplificada para carga rápida de transacciones.
- **Soporte Multi-sucursal:** Gestión de stock dividido por ubicaciones físicas.
- **Limpieza de Datos:** Procesamiento automático de formatos de moneda para evitar errores de cálculo.

## Stack Tecnológico

- Python 3.x
- Streamlit (Interfaz de usuario)
- Pandas (Procesamiento de datos)
- Google Sheets API (gspread)

## Instalación y Uso

1. Clonar el repositorio.
2. Instalar las dependencias necesarias:
   pip install -r requirements.txt
3. Configuración de credenciales:
   - El sistema requiere un archivo `credenciales.json` (Service Account de Google Cloud) en la raíz del proyecto para funcionar localmente.
   - Para despliegue en la nube, las credenciales se configuran mediante variables de entorno (Secrets).
4. Ejecutar la aplicación:
   streamlit run app.py

## Estructura de Datos

El sistema espera un archivo de Google Sheets con las siguientes hojas:
- **Productos:** Debe contener columnas de `Costo`, `Precio` y columnas de stock con el prefijo `Stock_` seguido del nombre de la sucursal.
- **Sucursales:** Lista de ubicaciones habilitadas.
- **Ventas:** Historial de transacciones.
- **Caja:** Saldos iniciales de efectivo y banco.