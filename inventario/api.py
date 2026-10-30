"""API REST (JSON) y servidor de los ficheros estáticos del frontend.

Solo usa la biblioteca estándar y SBD. Cada petición pide su conexión a la
BaseDatos del programa, que las atiende de una en una.

Seguridad: toda la API pide sesión salvo lo marcado como `publica`. La sesión
viaja en una cookie HttpOnly + SameSite=Strict, y las escrituras exigen cuerpo
JSON: un formulario de otra web no puede enviar JSON sin permiso (CSRF).
"""

import json
import logging
import mimetypes
import re
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .bd import BaseOcupada, SBDError
from .cuentas import CONTRASENA_DEMO, DURACION_SESION, NOMBRE_DEMO, USUARIO_DEMO, CuentasServicio, frenar_visitante
from .demo import USUARIOS_EJEMPLO
from .errores import ErrorInventario, ErrorValidacion, NoAutorizado, Prohibido, TipoNoAdmitido
from .servicio import InventarioServicio, comprobar_movimiento_demo

log = logging.getLogger("inventario")

DIR_ESTATICO = (Path(__file__).resolve().parent.parent / "static").resolve()
TAM_MAX_CUERPO = 64 * 1024
COOKIE_SESION = "sesion"
PAGINA_APP = "index.html"
PAGINA_ACCESO = "login.html"

# ---------------------------------------------------------------------- rutas

_RUTAS = []


def ruta(metodo, patron, *, publica=False, rol=None):
    """Registra una ruta. `publica` no pide sesión; `rol` exige ese rol (p. ej. 'admin')."""
    def registrar(funcion):
        _RUTAS.append((metodo, re.compile(f"^{patron}$"), funcion, publica, rol))
        return funcion
    return registrar


class Peticion:
    def __init__(self, consulta, cuerpo, usuario, token, ip=None, publico=False, demostracion=False):
        self.consulta, self.cuerpo, self.usuario, self.token = consulta, cuerpo, usuario, token
        self.ip, self.publico, self.demostracion = ip, publico, demostracion

    @property
    def usuario_id(self):
        return self.usuario["id"] if self.usuario else None


class Contexto:
    def __init__(self, conexion):
        self.inventario = InventarioServicio(conexion)
        self.cuentas = CuentasServicio(conexion)


class Respuesta:
    def __init__(self, datos=None, estado=HTTPStatus.OK, cabeceras=None):
        self.datos, self.estado, self.cabeceras = datos, estado, cabeceras or {}


class Archivo:
    def __init__(self, nombre, contenido, tipo):
        self.nombre, self.contenido, self.tipo = nombre, contenido, tipo


def _cookie_sesion(token, max_age, segura):
    # «Secure»: en internet, el navegador solo la envía por HTTPS
    return f"{COOKIE_SESION}={token}; Max-Age={max_age}; Path=/; HttpOnly; SameSite=Strict" + ("; Secure" if segura else "")


# ----------------------------------------------------------- sesión

@ruta("GET", r"/api/sesion", publica=True)
def _sesion(ctx, pet):
    a_la_vista = []
    if pet.demostracion:
        a_la_vista = [{"usuario": USUARIO_DEMO, "nombre": NOMBRE_DEMO, "contrasena": CONTRASENA_DEMO,
                       "rol": "operario", "demo": True}]
    elif ctx.cuentas.datos_de_ejemplo() and not pet.publico:
        a_la_vista = [{"usuario": u, "nombre": n, "contrasena": c, "rol": r} for u, n, c, r in USUARIOS_EJEMPLO]
    return {"usuario": pet.usuario, "usuarios_ejemplo": [] if pet.usuario else a_la_vista}


@ruta("POST", r"/api/sesion", publica=True)
def _iniciar_sesion(ctx, pet):
    token, usuario = ctx.cuentas.iniciar_sesion(pet.cuerpo, ip=pet.ip)
    max_age = int(DURACION_SESION.total_seconds())
    return Respuesta({"usuario": usuario}, cabeceras={"Set-Cookie": _cookie_sesion(token, max_age, pet.publico)})


@ruta("DELETE", r"/api/sesion", publica=True)
def _cerrar_sesion(ctx, pet):
    ctx.cuentas.cerrar_sesion(pet.token)
    return Respuesta(estado=HTTPStatus.NO_CONTENT, cabeceras={"Set-Cookie": _cookie_sesion("", 0, pet.publico)})


# ---------------------------------------------------------- inventario

@ruta("GET", r"/api/resumen")
def _resumen(ctx, pet):
    return ctx.inventario.resumen()


@ruta("GET", r"/api/categorias")
def _categorias(ctx, pet):
    return ctx.inventario.categorias()


@ruta("GET", r"/api/productos")
def _listar_productos(ctx, pet):
    return ctx.inventario.listar_productos(
        texto=pet.consulta.get("q", ""),
        categoria=pet.consulta.get("categoria", ""),
        estado=pet.consulta.get("estado", ""),
    )


@ruta("POST", r"/api/productos", rol="admin")
def _crear_producto(ctx, pet):
    return HTTPStatus.CREATED, ctx.inventario.crear_producto(pet.cuerpo, usuario_id=pet.usuario_id)


@ruta("GET", r"/api/productos/(\d+)")
def _obtener_producto(ctx, pet, producto_id):
    return ctx.inventario.obtener_producto(producto_id)


@ruta("PUT", r"/api/productos/(\d+)", rol="admin")
def _actualizar_producto(ctx, pet, producto_id):
    return ctx.inventario.actualizar_producto(producto_id, pet.cuerpo)


@ruta("DELETE", r"/api/productos/(\d+)", rol="admin")
def _baja_producto(ctx, pet, producto_id):
    ctx.inventario.dar_de_baja(producto_id)
    return HTTPStatus.NO_CONTENT, None


@ruta("GET", r"/api/movimientos")
def _listar_movimientos(ctx, pet):
    return ctx.inventario.listar_movimientos(pet.consulta)


@ruta("POST", r"/api/movimientos")
def _registrar_movimiento(ctx, pet):
    if pet.usuario["demo"]:
        comprobar_movimiento_demo(pet.cuerpo)
        frenar_visitante(pet.ip)
    return HTTPStatus.CREATED, ctx.inventario.registrar_movimiento(pet.cuerpo, usuario_id=pet.usuario_id)


@ruta("GET", r"/api/exportar/existencias\.csv")
def _exportar_csv(ctx, pet):
    return Archivo("existencias.csv", ctx.inventario.exportar_existencias_csv(), "text/csv; charset=utf-8")


# -------------------------------------------------------------------- servidor


class ServidorInventario(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, direccion, bd, publico=False, demostracion=False):
        self.bd = bd
        self.publico = publico  # en internet, detrás de un proxy con HTTPS
        self.demostracion = demostracion  # con el usuario visitante a la vista
        super().__init__(direccion, ManejadorHTTP)


class ManejadorHTTP(BaseHTTPRequestHandler):
    server_version = "GestorInventario/1.0"
    timeout = 30  # una conexión que no envía nada no retiene su hilo para siempre

    def do_GET(self):
        self._atender("GET")

    def do_POST(self):
        self._atender("POST")

    def do_PUT(self):
        self._atender("PUT")

    def do_DELETE(self):
        self._atender("DELETE")

    def log_message(self, formato, *args):
        log.info("%s %s", self._ip(), formato % args)

    def _ip(self):
        """La dirección del cliente. Detrás del proxy, la última de X-Forwarded-For, que es la que
        añade Apache: las anteriores las escribe el propio cliente y podrían ser falsas."""
        reenviada = self.headers.get("X-Forwarded-For") if self.server.publico and self.headers else None
        return reenviada.split(",")[-1].strip() if reenviada else self.client_address[0]

    # -------------------------------------------------------------- despacho

    def _atender(self, metodo):
        url = urlsplit(self.path)
        if url.path.startswith("/api/"):
            self._atender_api(metodo, url)
        elif metodo == "GET":
            self._servir_estatico(url.path)
        else:
            self._enviar_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Método no permitido"})

    def _token(self):
        try:
            galleta = SimpleCookie(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        return galleta[COOKIE_SESION].value if COOKIE_SESION in galleta else None

    def _usuario_actual(self, conexion):
        return CuentasServicio(conexion).usuario_de_sesion(self._token())

    def _atender_api(self, metodo, url):
        encontrada, argumentos, ruta_existe = None, (), False
        for metodo_ruta, patron, funcion, publica, rol in _RUTAS:
            coincidencia = patron.match(url.path)
            if coincidencia:
                ruta_existe = True
                if metodo_ruta == metodo:
                    encontrada = (funcion, publica, rol)
                    argumentos = tuple(int(g) for g in coincidencia.groups())
                    break
        if encontrada is None:
            if ruta_existe:
                self._enviar_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Método no permitido"})
            else:
                self._enviar_json(HTTPStatus.NOT_FOUND, {"error": "Recurso no encontrado"})
            return

        funcion, publica, rol = encontrada
        try:
            with self.server.bd.conexion() as conexion:
                usuario = self._usuario_actual(conexion)
                if usuario:
                    # En el historial de SBD, cada cambio queda firmado por quien lo hizo
                    conexion.firmar(f"inventario · {usuario['usuario']}")
                if not publica and usuario is None:
                    raise NoAutorizado("Tu sesión ha caducado. Vuelve a entrar.")
                if rol and (usuario is None or usuario["rol"] != rol):
                    raise Prohibido("Esta acción solo la puede hacer un administrador")
                consulta = {clave: valores[0] for clave, valores in parse_qs(url.query).items()}
                cuerpo = self._leer_json() if metodo in ("POST", "PUT") else {}
                peticion = Peticion(consulta, cuerpo, usuario, self._token(), self._ip(),
                                    self.server.publico, self.server.demostracion)
                resultado = funcion(Contexto(conexion), peticion, *argumentos)
        except ErrorInventario as error:
            self._enviar_json(error.estado, error.como_dict())
            return
        except BaseOcupada:
            self._enviar_json(HTTPStatus.SERVICE_UNAVAILABLE,
                              {"error": "La base de datos está ocupada con otra operación. Inténtalo en un momento."})
            return
        except SBDError as error:
            log.error("SBD rechazó la orden en %s %s: %s", metodo, url.path, error)
            self._enviar_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Error de la base de datos: {error}"})
            return
        except Exception:
            log.exception("Error no controlado en %s %s", metodo, url.path)
            self._enviar_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Error interno del servidor"})
            return

        if isinstance(resultado, Archivo):
            self._enviar(
                HTTPStatus.OK,
                resultado.contenido.encode("utf-8"),
                resultado.tipo,
                {"Content-Disposition": f'attachment; filename="{resultado.nombre}"'},
            )
        elif isinstance(resultado, Respuesta):
            self._enviar_json(resultado.estado, resultado.datos, resultado.cabeceras)
        else:
            estado, datos = resultado if isinstance(resultado, tuple) else (HTTPStatus.OK, resultado)
            self._enviar_json(estado, datos)

    def _leer_json(self):
        try:
            longitud = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ErrorValidacion("Cabecera Content-Length no válida") from None
        if longitud > TAM_MAX_CUERPO:
            raise ErrorValidacion("El cuerpo de la petición es demasiado grande")
        if longitud == 0:
            return {}
        # Solo JSON: un formulario HTML de otra web no puede enviar este tipo sin permiso (CSRF)
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            raise TipoNoAdmitido("El cuerpo debe ser JSON (Content-Type: application/json)")
        try:
            datos = json.loads(self.rfile.read(longitud).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ErrorValidacion("El cuerpo de la petición no es un JSON válido") from None
        if not isinstance(datos, dict):
            raise ErrorValidacion("Se esperaba un objeto JSON")
        return datos

    # ------------------------------------------------------------- respuestas

    def _servir_estatico(self, ruta_url):
        relativa = unquote(ruta_url).lstrip("/") or PAGINA_APP
        # La aplicación pide sesión; la pantalla de acceso, no tenerla
        if relativa in (PAGINA_APP, PAGINA_ACCESO):
            with self.server.bd.conexion() as conexion:
                conectado = self._usuario_actual(conexion) is not None
            if relativa == PAGINA_APP and not conectado:
                self._redirigir(f"/{PAGINA_ACCESO}")
                return
            if relativa == PAGINA_ACCESO and conectado:
                self._redirigir("/")
                return

        destino = (DIR_ESTATICO / relativa).resolve()
        # Impide salir de la carpeta static con rutas del tipo /../../etc/passwd
        if not destino.is_relative_to(DIR_ESTATICO) or not destino.is_file():
            self._enviar(HTTPStatus.NOT_FOUND, "No encontrado".encode(), "text/plain; charset=utf-8")
            return
        tipo = mimetypes.guess_type(destino.name)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo in ("application/javascript", "image/svg+xml"):
            tipo += "; charset=utf-8"
        # Las librerías de /vendor tienen versión fija: el navegador puede guardarlas un año
        cache = "public, max-age=31536000, immutable" if relativa.startswith("vendor/") else "no-cache"
        self._enviar(HTTPStatus.OK, destino.read_bytes(), tipo, {"Cache-Control": cache})

    def _redirigir(self, destino):
        self._enviar(HTTPStatus.FOUND, b"", None, {"Location": quote(destino, safe="/?=&#.")})

    def _enviar_json(self, estado, datos, cabeceras=None):
        cabeceras = {"Cache-Control": "no-store", **(cabeceras or {})}
        if estado == HTTPStatus.NO_CONTENT:
            self._enviar(estado, b"", None, cabeceras)
            return
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self._enviar(estado, cuerpo, "application/json; charset=utf-8", cabeceras)

    def _enviar(self, estado, cuerpo, tipo, cabeceras=None):
        self.send_response(estado)
        if tipo:
            self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        for nombre, valor in (cabeceras or {}).items():
            self.send_header(nombre, valor)
        self.end_headers()
        if cuerpo:
            self.wfile.write(cuerpo)


def crear_servidor(host, puerto, bd, publico=False, demostracion=False):
    """`bd` es la BaseDatos del programa; aquí se aplican sus migraciones pendientes."""
    bd.preparar()
    return ServidorInventario((host, puerto), bd, publico, demostracion)
