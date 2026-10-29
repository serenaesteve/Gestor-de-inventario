"""Conexión del inventario con SBD, la base de datos con lenguaje propio en español.

Dos formas de trabajar, con el mismo código en los DAO:

- **local**: SBD funciona dentro de este programa, sobre una carpeta de datos
  (por defecto `datos/`, con la base `inventario.base`). Es lo normal.
- **servidor**: el inventario se conecta por HTTP a un `sbd servidor` en marcha,
  con una clave de API, como cualquier aplicación contra su servidor de datos.

Los DAO solo ven `Conexion`: `ejecutar`, `consultar`, `una`, `valor` y `transaccion`.
"""

import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import sbd
from sbd import BaseOcupada, SBDError

BASE = "inventario"
DIR_MIGRACIONES = Path(__file__).with_name("migraciones")


def migraciones():
    """Migraciones disponibles en orden: [(número, ruta)], p. ej. (2, 002_usuarios.sbd)."""
    return sorted((int(ruta.name[:3]), ruta) for ruta in DIR_MIGRACIONES.glob("[0-9][0-9][0-9]_*.sbd"))


VERSION_ESQUEMA = migraciones()[-1][0]


def iso(valor):
    """Un `fechahora` de SBD (hora local, sin zona) en ISO 8601 con zona, para la web."""
    if not valor:
        return valor
    return datetime.fromisoformat(str(valor)).astimezone().isoformat(timespec="seconds")


def texto_fecha(momento):
    """Un datetime de Python como lo escribe SBD: «2026-10-29 10:17:22»."""
    return momento.strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------- ejecutores

class _Local:
    """Órdenes contra un sbd.Servidor de este mismo proceso."""

    def __init__(self, servidor, base, etiqueta):
        self.sesion = sbd.Sesion(servidor, base, etiqueta=etiqueta)

    def ejecutar(self, orden, params):
        return self.sesion.ejecutar(orden, params)

    def empezar(self):
        self.sesion.ejecutar("empezar")

    def confirmar(self):
        self.sesion.ejecutar("confirmar")

    def deshacer(self):
        self.sesion.ejecutar("deshacer")

    def firmar(self, quien):
        self.sesion.etiqueta = quien

    def cerrar(self):
        self.sesion.cerrar()


class _Remoto:
    """Órdenes contra un `sbd servidor` por su API (sbd.Cliente)."""

    def __init__(self, cliente):
        self.cliente = cliente
        self._transaccion = None
        self._activo = None

    def ejecutar(self, orden, params):
        return (self._activo or self.cliente).ejecutar(orden, list(params))

    def empezar(self):
        self._transaccion = self.cliente.transaccion()
        self._activo = self._transaccion.__enter__()

    def _terminar(self, error):
        transaccion, self._transaccion, self._activo = self._transaccion, None, None
        transaccion.__exit__(type(error) if error else None, error, None)

    def confirmar(self):
        self._terminar(None)

    def deshacer(self):
        self._terminar(SBDError("deshacer"))

    def firmar(self, quien):
        pass  # en el servidor, los cambios los firma el usuario de la clave de API

    def cerrar(self):
        if self._transaccion is not None:
            self.deshacer()


# ---------------------------------------------------------------------- conexión

class Conexion:
    """Una conversación con la base del inventario (una por petición web)."""

    def __init__(self, ejecutor):
        self._ejecutor = ejecutor
        self._profundidad = 0

    def ejecutar(self, orden, params=()):
        """Ejecuta una o varias órdenes de SBD y devuelve el resultado de la última."""
        return self._ejecutor.ejecutar(orden, params)

    def consultar(self, orden, params=()):
        """Las filas como lista de diccionarios."""
        return self.ejecutar(orden, params).dicts()

    def una(self, orden, params=()):
        filas = self.consultar(orden, params)
        return filas[0] if filas else None

    def valor(self, orden, params=()):
        return self.ejecutar(orden, params).scalar()

    def tablas(self):
        return {fila[0] for fila in self.ejecutar("tablas").rows}

    def firmar(self, quien):
        """Quién aparece en el historial de SBD como autor de los cambios."""
        self._ejecutor.firmar(quien)

    @contextmanager
    def transaccion(self):
        """Todo o nada: `empezar` … `confirmar`, o `deshacer` si algo falla dentro."""
        if self._profundidad:  # ya dentro de una transacción: forma parte de ella
            self._profundidad += 1
            try:
                yield self
            finally:
                self._profundidad -= 1
            return
        self._ejecutor.empezar()
        self._profundidad = 1
        try:
            yield self
        except BaseException:
            self._profundidad = 0
            self._ejecutor.deshacer()
            raise
        self._profundidad = 0
        self._ejecutor.confirmar()

    def cerrar(self):
        self._ejecutor.cerrar()


class BaseDatos:
    """El acceso a SBD de todo el programa: uno por proceso.

    Las peticiones web se atienden de una en una, igual que hace el propio servidor
    de SBD: cada orden y cada transacción ven siempre datos coherentes.
    """

    def __init__(self, directorio=None, *, url=None, clave=None, base=BASE):
        self.base = base
        self._cerrojo = threading.RLock()
        self._servidor = None
        self._cliente = None
        if url:
            if not clave:
                raise SBDError("para conectar con un servidor de SBD hace falta su clave de API (--sbd-clave o SBD_CLAVE)")
            self._cliente = sbd.conectar_servidor(url, clave, base)
            self.descripcion = f"servidor SBD {url} · base «{base}»"
        else:
            self.directorio = Path(directorio or "datos").resolve()
            self._servidor = sbd.servidor(str(self.directorio))
            self.descripcion = f"SBD local en {self.directorio / (base + '.base')}"

    @property
    def remota(self):
        return self._cliente is not None

    @contextmanager
    def conexion(self, quien="inventario"):
        with self._cerrojo:
            ejecutor = _Remoto(self._cliente) if self.remota else _Local(self._servidor, self.base, quien)
            conexion = Conexion(ejecutor)
            try:
                yield conexion
            finally:
                conexion.cerrar()

    def preparar(self):
        """Crea la base si hace falta (en local) y aplica las migraciones pendientes."""
        with self._cerrojo:
            if not self.remota and not self._servidor.existe(self.base):
                self._servidor.crear(self.base)
            with self.conexion("inventario · migraciones") as conexion:
                migrar(conexion)

    def cerrar(self):
        with self._cerrojo:
            if self._servidor is not None:
                self._servidor.cerrar()
                self._servidor = None


# -------------------------------------------------------------------- migraciones

def version_actual(conexion):
    if "ajustes" not in conexion.tablas():
        return 0
    valor = conexion.valor('buscar ajustes donde clave = "version_esquema" mostrar valor')
    return int(valor) if valor else 0


def migrar(conexion):
    """Lleva el esquema a la última versión. Cada migración, con su número, va en una transacción."""
    version = version_actual(conexion)
    for numero, ruta in migraciones():
        if numero <= version:
            continue
        with conexion.transaccion():
            conexion.ejecutar(ruta.read_text(encoding="utf-8"))
            conexion.ejecutar('insertar o actualizar en ajustes { clave: "version_esquema", valor: ? }', [str(numero)])
    return version


__all__ = ["BASE", "BaseDatos", "BaseOcupada", "Conexion", "SBDError", "VERSION_ESQUEMA", "iso", "migrar",
           "migraciones", "texto_fecha", "version_actual"]
