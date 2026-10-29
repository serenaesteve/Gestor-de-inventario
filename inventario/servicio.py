"""Lógica de negocio del inventario.

Esta capa valida los datos, aplica las reglas (no vender lo que no hay, todo
cambio de stock deja un movimiento...) y decide los límites de cada
transacción. No sabe nada de HTTP: la puede usar igual una API, una consola
o los tests.
"""

import csv
import io

from . import validacion as v
from .bd import SBDError
from .errores import Conflicto, ErrorValidacion, NoEncontrado
from .movimiento_dao import TIPOS, MovimientoDAO
from .producto_dao import ESTADOS, ProductoDAO


class InventarioServicio:
    def __init__(self, conexion):
        self._con = conexion
        self.productos = ProductoDAO(conexion)
        self.movimientos = MovimientoDAO(conexion)

    # ------------------------------------------------------------------ productos

    def listar_productos(self, texto="", categoria="", estado=""):
        estado = estado.upper()
        if estado and estado not in ESTADOS:
            raise ErrorValidacion("Estado de stock no válido", "estado")
        return self.productos.listar(texto.strip(), categoria.strip(), estado)

    def obtener_producto(self, producto_id):
        producto = self.productos.obtener(producto_id)
        if producto is None:
            raise NoEncontrado(f"No existe el producto {producto_id}")
        return producto

    def crear_producto(self, datos, usuario_id=None):
        campos = _validar_producto(datos)
        stock_inicial = v.entero(datos, "stock_inicial", "El stock inicial", defecto=0, maximo=1_000_000)
        try:
            # Alta y stock inicial van juntos: o se guardan los dos o ninguno
            with self._con.transaccion():
                producto_id = self.productos.insertar(campos)
                if stock_inicial:
                    self._aplicar_movimiento(producto_id, "ENTRADA", stock_inicial, "Stock inicial", usuario_id=usuario_id)
        except SBDError as error:
            raise _traducir_integridad(error, campos) from None
        return self.obtener_producto(producto_id)

    def actualizar_producto(self, producto_id, datos):
        campos = _validar_producto(datos)
        try:
            actualizado = self.productos.actualizar(producto_id, campos)
        except SBDError as error:
            raise _traducir_integridad(error, campos) from None
        if not actualizado:
            raise NoEncontrado(f"No existe el producto {producto_id} o está dado de baja")
        return self.obtener_producto(producto_id)

    def dar_de_baja(self, producto_id):
        if not self.productos.desactivar(producto_id):
            raise NoEncontrado(f"No existe el producto {producto_id} o ya está dado de baja")

    def categorias(self):
        return self.productos.categorias()

    # ---------------------------------------------------------------- movimientos

    def registrar_movimiento(self, datos, usuario_id=None):
        producto_id = v.entero(datos, "producto_id", "El producto", minimo=1)
        tipo = str(datos.get("tipo", "")).upper()
        if tipo not in TIPOS:
            raise ErrorValidacion("El tipo de movimiento debe ser ENTRADA, SALIDA o AJUSTE", "tipo")
        cantidad = v.entero(
            datos, "cantidad", "La cantidad", minimo=0 if tipo == "AJUSTE" else 1, maximo=1_000_000
        )
        motivo = v.texto(datos, "motivo", "El motivo", maximo=200, obligatorio=False)

        with self._con.transaccion():
            movimiento_id = self._aplicar_movimiento(producto_id, tipo, cantidad, motivo, usuario_id=usuario_id)
        return self.movimientos.obtener(movimiento_id)

    def importar_movimiento(self, producto_id, tipo, cantidad, motivo, *, fecha, usuario_id=None):
        """Registra un movimiento con fecha pasada. Solo lo usan los datos de ejemplo."""
        with self._con.transaccion():
            return self._aplicar_movimiento(producto_id, tipo, cantidad, motivo, usuario_id=usuario_id, fecha=fecha)

    def listar_movimientos(self, filtros):
        producto_id = None
        if filtros.get("producto_id"):
            producto_id = v.entero(filtros, "producto_id", "El producto", minimo=1)
        tipo = str(filtros.get("tipo", "")).upper()
        if tipo and tipo not in TIPOS:
            raise ErrorValidacion("Tipo de movimiento no válido", "tipo")
        limite = v.entero(filtros, "limite", "El límite", minimo=1, maximo=1000, defecto=200)
        return self.movimientos.listar(producto_id, tipo, limite)

    def _aplicar_movimiento(self, producto_id, tipo, cantidad, motivo, *, usuario_id=None, fecha=None):
        """Actualiza el stock y registra el movimiento. Debe llamarse dentro de una transacción.

        Para AJUSTE, `cantidad` es el recuento físico: se guarda la diferencia.
        """
        producto = self.productos.obtener(producto_id)
        if producto is None or not producto["activo"]:
            raise NoEncontrado(f"No existe el producto {producto_id} o está dado de baja", "producto_id")

        anterior = producto["stock_actual"]
        if tipo == "ENTRADA":
            delta = cantidad
        elif tipo == "SALIDA":
            if cantidad > anterior:
                raise Conflicto(
                    f"Stock insuficiente: hay {anterior} uds y se intentan retirar {cantidad}",
                    "cantidad",
                )
            delta = -cantidad
        else:
            delta = cantidad - anterior
            if delta == 0:
                raise ErrorValidacion(
                    "El recuento coincide con el stock actual: no hay nada que ajustar", "cantidad"
                )

        nuevo = anterior + delta
        if not self.productos.fijar_stock(producto_id, nuevo, esperado=anterior):
            raise Conflicto("El stock ha cambiado mientras se registraba el movimiento; inténtalo de nuevo")
        return self.movimientos.insertar(producto_id, tipo, delta, anterior, nuevo, motivo, usuario_id, fecha)

    # ------------------------------------------------------------------- consultas

    def resumen(self):
        return {
            **self.productos.totales(),
            "hoy": self.movimientos.actividad_hoy(),
            "alertas": self.productos.en_alerta(limite=8),
            "ultimos_movimientos": self.movimientos.listar(limite=8),
        }

    def exportar_existencias_csv(self):
        """CSV con ';' y BOM para que Excel en español lo abra bien a la primera."""
        salida = io.StringIO()
        escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
        escritor.writerow(
            ["Código", "Nombre", "Categoría", "Precio (€)", "Stock actual", "Stock mínimo", "Estado", "Valor (€)"]
        )
        for p in self.productos.listar():
            escritor.writerow([
                _celda_segura(p["codigo"]),
                _celda_segura(p["nombre"]),
                _celda_segura(p["categoria"]),
                _euros(p["precio"]),
                p["stock_actual"],
                p["stock_minimo"],
                p["estado"],
                _euros(p["valor"]),
            ])
        return "﻿" + salida.getvalue()


def _validar_producto(datos):
    if not isinstance(datos, dict):
        raise ErrorValidacion("Se esperaba un objeto JSON con los datos del producto")
    return {
        "codigo": v.texto(datos, "codigo", "El código", maximo=30).upper(),
        "nombre": v.texto(datos, "nombre", "El nombre", maximo=120),
        "descripcion": v.texto(datos, "descripcion", "La descripción", maximo=500, obligatorio=False),
        "categoria": v.texto(datos, "categoria", "La categoría", maximo=50, obligatorio=False) or "General",
        "precio": v.importe(datos, "precio", "El precio"),
        "stock_minimo": v.entero(datos, "stock_minimo", "El stock mínimo", defecto=0, maximo=1_000_000),
    }


def _traducir_integridad(error, campos):
    """Un error de SBD al guardar, explicado para quien usa la aplicación."""
    texto = str(error)
    if "codigo" in texto and "único" in texto:
        return Conflicto(f"Ya existe un producto con el código «{campos['codigo']}»", "codigo")
    return ErrorValidacion(f"Los datos no cumplen las reglas de la base de datos: {texto}")


def _euros(importe):
    return f"{importe:.2f}".replace(".", ",")


def _celda_segura(texto):
    """Evita la inyección de fórmulas al abrir el CSV en una hoja de cálculo."""
    return f"'{texto}" if texto[:1] in ("=", "+", "-", "@") else texto
