# Sistema de Gestión - Aurum Suplementos

Aplicación web desarrollada en Python para el control de stock, registro de ventas y gestión de inventario. Utiliza **MySQL** como base de datos relacional para garantizar la integridad y escalabilidad de los datos, reemplazando el antiguo sistema basado en hojas de cálculo.

## 🚀 Funcionalidades Principales

- **Gestión de Stock Centralizada:** Vista global de productos con sus costos y precios actualizados.
- **Registro de Ventas:** Interfaz optimizada para registrar salidas de mercancía, calculando totales y validando stock disponible en tiempo real.
- **Control de Movimientos:**
  - Historial completo de ventas con filtros por Sucursal y Producto.
  - **Edición de Ventas:** Permite modificar transacciones pasadas, ajustando automáticamente el stock (revierte la operación anterior y aplica la nueva).
  - **Eliminación de Ventas:** Borrado lógico de ventas con devolución automática de los productos al inventario.
- **Soporte Multi-sucursal:** Control de inventario dividido por ubicaciones físicas (gestionado vía base de datos).

## 🛠️ Stack Tecnológico

- **Lenguaje:** Python 3.11+
- **Interfaz:** [Streamlit](https://streamlit.io/)
- **Base de Datos:** MySQL
- **Librerías Clave:**
  - `pandas` (Manipulación de datos)
  - `mysql-connector-python` (Conexión a BD)

## ⚙️ Instalación y Configuración

### 1. Prerrequisitos
- Tener instalado Python.
- Tener un servidor MySQL corriendo (local o remoto).

### 2. Clonar el repositorio
```bash
git clone <URL_DEL_REPOSITORIO>
cd aurum-gestion