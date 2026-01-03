-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Servidor: 127.0.0.1
-- Tiempo de generación: 03-01-2026 a las 02:29:18
-- Versión del servidor: 10.4.32-MariaDB
-- Versión de PHP: 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Base de datos: `aurum_db`
--

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `compras`
--

CREATE TABLE `compras` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `fecha` datetime DEFAULT NULL,
  `producto` varchar(255) DEFAULT NULL,
  `cantidad` int(11) DEFAULT NULL,
  `costo_total` decimal(10,2) DEFAULT NULL,
  `metodo_pago` varchar(50) DEFAULT NULL,
  `proveedor` varchar(255) DEFAULT NULL,
  `ubicacion` varchar(50) DEFAULT NULL,
  `notas` text DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `inventario`
--

CREATE TABLE `inventario` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `producto_nombre` varchar(255) DEFAULT NULL,
  `sucursal_nombre` varchar(100) DEFAULT NULL,
  `cantidad` int(11) DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_stock` (`producto_nombre`,`sucursal_nombre`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Volcado de datos para la tabla `inventario`
--

INSERT INTO `inventario` (`id`, `producto_nombre`, `sucursal_nombre`, `cantidad`) VALUES
(1, 'PROTEINA STAR NUTRITION DOYPACK', 'Rio Tercero', 0),
(2, 'PROTEINA STAR NUTRITION DOYPACK', 'Cordoba', 0),
(3, 'PROTEINA STAR NUTRITION DOYPACK', 'Mile Rizzo', 0),
(4, 'PROTEINA STAR NUTRITION DOYPACK', 'Negro Rivarola', 2),
(5, 'PROTEINA STAR NUTRITION POTE', 'Rio Tercero', 1),
(6, 'PROTEINA STAR NUTRITION POTE', 'Cordoba', 0),
(7, 'PROTEINA STAR NUTRITION POTE', 'Mile Rizzo', 0),
(8, 'PROTEINA STAR NUTRITION POTE', 'Negro Rivarola', 2),
(9, 'CREATINA STAR NUTRITION', 'Rio Tercero', 0),
(10, 'CREATINA STAR NUTRITION', 'Cordoba', 0),
(11, 'CREATINA STAR NUTRITION', 'Mile Rizzo', 0),
(12, 'CREATINA STAR NUTRITION', 'Negro Rivarola', 0),
(13, 'COLAGENO PLUS STAR NUTRITION', 'Rio Tercero', 2),
(14, 'COLAGENO PLUS STAR NUTRITION', 'Cordoba', 0),
(15, 'COLAGENO PLUS STAR NUTRITION', 'Mile Rizzo', 0),
(16, 'COLAGENO PLUS STAR NUTRITION', 'Negro Rivarola', 0),
(17, 'COLAGENO SPORT STAR NUTRITION', 'Rio Tercero', 0),
(18, 'COLAGENO SPORT STAR NUTRITION', 'Cordoba', 0),
(19, 'COLAGENO SPORT STAR NUTRITION', 'Mile Rizzo', 0),
(20, 'COLAGENO SPORT STAR NUTRITION', 'Negro Rivarola', 0),
(21, 'PROTEINA ENA TRUEMADE POTE', 'Rio Tercero', 1),
(22, 'PROTEINA ENA TRUEMADE POTE', 'Cordoba', 0),
(23, 'PROTEINA ENA TRUEMADE POTE', 'Mile Rizzo', 0),
(24, 'PROTEINA ENA TRUEMADE POTE', 'Negro Rivarola', 0),
(25, 'PROTEINA ENA TRUEMADE DOYPACK', 'Rio Tercero', 1),
(26, 'PROTEINA ENA TRUEMADE DOYPACK', 'Cordoba', 0),
(27, 'PROTEINA ENA TRUEMADE DOYPACK', 'Mile Rizzo', 0),
(28, 'PROTEINA ENA TRUEMADE DOYPACK', 'Negro Rivarola', 0),
(29, 'CREATINA ENA DOYPACK', 'Rio Tercero', 1),
(30, 'CREATINA ENA DOYPACK', 'Cordoba', 0),
(31, 'CREATINA ENA DOYPACK', 'Mile Rizzo', 0),
(32, 'CREATINA ENA DOYPACK', 'Negro Rivarola', 0),
(33, 'PRE ENTRENO PUMP V8', 'Rio Tercero', 0),
(34, 'PRE ENTRENO PUMP V8', 'Cordoba', 0),
(35, 'PRE ENTRENO PUMP V8', 'Mile Rizzo', 0),
(36, 'PRE ENTRENO PUMP V8', 'Negro Rivarola', 2),
(37, 'CREATINA GOLD NUTRITION DOYPACK', 'Rio Tercero', 0),
(38, 'CREATINA GOLD NUTRITION DOYPACK', 'Cordoba', 0),
(39, 'CREATINA GOLD NUTRITION DOYPACK', 'Mile Rizzo', 0),
(40, 'CREATINA GOLD NUTRITION DOYPACK', 'Negro Rivarola', 0);

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `productos`
--

CREATE TABLE `productos` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nombre` varchar(255) NOT NULL,
  `costo` decimal(10,2) DEFAULT 0.00,
  `precio` decimal(10,2) DEFAULT 0.00,
  PRIMARY KEY (`id`),
  UNIQUE KEY `nombre` (`nombre`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Volcado de datos para la tabla `productos`
--

INSERT INTO `productos` (`id`, `nombre`, `costo`, `precio`) VALUES
(1, 'PROTEINA STAR NUTRITION DOYPACK', 33854.00, 46500.00),
(2, 'PROTEINA STAR NUTRITION POTE', 37090.00, 49600.00),
(3, 'CREATINA STAR NUTRITION', 20480.00, 27000.00),
(4, 'COLAGENO PLUS STAR NUTRITION', 15400.00, 21500.00),
(5, 'COLAGENO SPORT STAR NUTRITION', 15400.00, 21500.00),
(6, 'PROTEINA ENA TRUEMADE POTE', 38647.00, 50700.00),
(7, 'PROTEINA ENA TRUEMADE DOYPACK', 25000.00, 25000.00),
(8, 'CREATINA ENA DOYPACK', 21389.00, 27800.00),
(9, 'PRE ENTRENO PUMP V8', 24488.00, 29700.00),
(10, 'CREATINA GOLD NUTRITION DOYPACK', 17900.00, 25000.00);

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `saldos_iniciales`
--

CREATE TABLE `saldos_iniciales` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `cuenta` varchar(50) DEFAULT NULL,
  `monto` decimal(10,2) DEFAULT 0.00,
  PRIMARY KEY (`id`),
  UNIQUE KEY `cuenta` (`cuenta`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Volcado de datos para la tabla `saldos_iniciales`
--

INSERT INTO `saldos_iniciales` (`id`, `cuenta`, `monto`) VALUES
(1, 'Efectivo', 0.00),
(2, 'Transferencia', 197272.00);

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `sucursales`
--

CREATE TABLE `sucursales` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nombre` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `nombre` (`nombre`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Volcado de datos para la tabla `sucursales`
--

INSERT INTO `sucursales` (`id`, `nombre`) VALUES
(2, 'Cordoba'),
(3, 'Mile Rizzo'),
(4, 'Negro Rivarola'),
(1, 'Rio Tercero');

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `ventas`
--

CREATE TABLE `ventas` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `fecha` datetime DEFAULT NULL,
  `producto` varchar(255) DEFAULT NULL,
  `cantidad` int(11) DEFAULT NULL,
  `precio_unitario` decimal(10,2) DEFAULT NULL,
  `total` decimal(10,2) DEFAULT NULL,
  `metodo_pago` varchar(50) DEFAULT NULL,
  `ubicacion` varchar(100) DEFAULT NULL,
  `notas` text DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Volcado de datos para la tabla `ventas`
--

INSERT INTO `ventas` (`id`, `fecha`, `producto`, `cantidad`, `precio_unitario`, `total`, `metodo_pago`, `ubicacion`, `notas`) VALUES
(1, '2026-01-02 19:36:13', 'CREATINA STAR NUTRITION', 3, 24576.00, 73728.00, 'Transferencia', 'Negro Rivarola', '');

COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;