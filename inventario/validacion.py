"""Validación y normalización de los datos que llegan desde fuera."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .errores import ErrorValidacion

_ENTERO = re.compile(r"\s*-?\d+\s*")


def texto(datos, campo, etiqueta, *, maximo, obligatorio=True, defecto=""):
    valor = datos.get(campo)
    if valor is None:
        valor = defecto
    if not isinstance(valor, str):
        raise ErrorValidacion(f"{etiqueta} debe ser texto", campo)
    valor = valor.strip()
    if obligatorio and not valor:
        raise ErrorValidacion(f"{etiqueta} es obligatorio", campo)
    if len(valor) > maximo:
        raise ErrorValidacion(f"{etiqueta} no puede superar los {maximo} caracteres", campo)
    return valor


def entero(datos, campo, etiqueta, *, minimo=0, maximo=1_000_000_000, defecto=None):
    valor = datos.get(campo, defecto)
    if valor is None or valor == "":
        raise ErrorValidacion(f"{etiqueta} es obligatorio", campo)
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    elif isinstance(valor, str) and _ENTERO.fullmatch(valor):
        valor = int(valor)
    # bool es subclase de int en Python: hay que descartarlo explícitamente
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErrorValidacion(f"{etiqueta} debe ser un número entero", campo)
    if valor < minimo:
        raise ErrorValidacion(f"{etiqueta} debe ser como mínimo {minimo}", campo)
    if valor > maximo:
        raise ErrorValidacion(f"{etiqueta} no puede superar {maximo}", campo)
    return valor


def importe(datos, campo, etiqueta, *, maximo=10_000_000):
    """Un importe en euros (número o texto, admite coma decimal) como Decimal exacto con 2 decimales.

    Se guarda en una columna `dinero` de SBD, que tampoco usa coma flotante.
    """
    valor = datos.get(campo, 0)
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
        raise ErrorValidacion(f"{etiqueta} debe ser un número", campo)
    try:
        cantidad = Decimal(str(valor).strip().replace(",", ".") or "0")
    except InvalidOperation:
        raise ErrorValidacion(f"{etiqueta} debe ser un número", campo) from None
    if not cantidad.is_finite():
        raise ErrorValidacion(f"{etiqueta} debe ser un número", campo)
    if cantidad < 0:
        raise ErrorValidacion(f"{etiqueta} no puede ser negativo", campo)
    if cantidad > maximo:
        raise ErrorValidacion(f"{etiqueta} no puede superar {maximo} €", campo)
    return cantidad.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
