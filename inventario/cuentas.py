"""Usuarios, inicio de sesión y sesiones."""

import re
import threading
import time
from datetime import timedelta

from . import seguridad
from . import validacion as v
from .errores import Conflicto, DemasiadosIntentos, ErrorValidacion, NoAutorizado
from .usuario_dao import UsuarioDAO

DURACION_SESION = timedelta(hours=8)
ROLES = ("admin", "operario")
_USUARIO_VALIDO = re.compile(r"[a-z0-9._-]{3,30}")

# Freno a los ataques de fuerza bruta: 5 fallos seguidos bloquean ese usuario 5 minutos
MAX_FALLOS = 5
BLOQUEO_SEGUNDOS = 300
_fallos = {}
_cerrojo = threading.Lock()


def _publico(fila):
    return {"id": fila["id"], "usuario": fila["usuario"], "nombre": fila["nombre"], "rol": fila["rol"]}


class CuentasServicio:
    def __init__(self, conexion):
        self._con = conexion
        self.usuarios = UsuarioDAO(conexion)

    def hay_usuarios(self):
        return self.usuarios.contar() > 0

    def crear_usuario(self, usuario, nombre, contrasena, rol="operario"):
        usuario = str(usuario).strip().lower()
        if not _USUARIO_VALIDO.fullmatch(usuario):
            raise ErrorValidacion("El usuario debe tener de 3 a 30 letras minúsculas, números, puntos o guiones", "usuario")
        nombre = v.texto({"nombre": nombre}, "nombre", "El nombre", maximo=80)
        if not isinstance(contrasena, str) or len(contrasena) < 8:
            raise ErrorValidacion("La contraseña necesita al menos 8 caracteres", "contrasena")
        if rol not in ROLES:
            raise ErrorValidacion("El rol debe ser admin u operario", "rol")
        if self.usuarios.por_usuario(usuario):
            raise Conflicto(f"Ya existe el usuario «{usuario}»", "usuario")
        usuario_id = self.usuarios.insertar(usuario, nombre, rol, seguridad.cifrar_contrasena(contrasena))
        return _publico(self.usuarios.por_id(usuario_id))

    def iniciar_sesion(self, datos):
        """Comprueba usuario y contraseña. Devuelve (token, usuario) o lanza NoAutorizado."""
        if not isinstance(datos, dict):
            raise ErrorValidacion("Faltan el usuario y la contraseña")
        usuario = str(datos.get("usuario", "")).strip().lower()
        contrasena = datos.get("contrasena")
        if not usuario:
            raise ErrorValidacion("Escribe tu usuario", "usuario")
        if not isinstance(contrasena, str) or not contrasena:
            raise ErrorValidacion("Escribe tu contraseña", "contrasena")
        _comprobar_bloqueo(usuario)

        fila = self.usuarios.por_usuario(usuario)
        # Siempre se calcula un PBKDF2, exista o no el usuario (mismo tiempo de respuesta)
        correcta = seguridad.comprobar_contrasena(contrasena, fila["hash_contrasena"] if fila else seguridad.hash_señuelo())
        if not (fila and correcta and fila["activo"]):
            _anotar_fallo(usuario)
            raise NoAutorizado("Usuario o contraseña incorrectos")
        _olvidar_fallos(usuario)

        token = seguridad.nuevo_token()
        with self._con.transaccion():
            self.usuarios.purgar_sesiones()
            self.usuarios.crear_sesion(seguridad.huella_token(token), fila["id"], DURACION_SESION.total_seconds() / 3600)
            self.usuarios.registrar_acceso(fila["id"])
        return token, _publico(fila)

    def usuario_de_sesion(self, token):
        if not token:
            return None
        return self.usuarios.usuario_de_sesion(seguridad.huella_token(token))

    def cerrar_sesion(self, token):
        if token:
            self.usuarios.borrar_sesion(seguridad.huella_token(token))

    # -------------------------------------------------------------- ajustes

    def datos_de_ejemplo(self):
        return self.usuarios.leer_ajuste("datos_ejemplo") == "1"

    def marcar_datos_de_ejemplo(self):
        self.usuarios.guardar_ajuste("datos_ejemplo", "1")


def _comprobar_bloqueo(usuario):
    with _cerrojo:
        fallos, desde = _fallos.get(usuario, (0, 0))
        if fallos >= MAX_FALLOS and time.monotonic() - desde < BLOQUEO_SEGUNDOS:
            minutos = max(1, round((BLOQUEO_SEGUNDOS - (time.monotonic() - desde)) / 60))
            raise DemasiadosIntentos(f"Demasiados intentos fallidos. Vuelve a probar en {minutos} min")
        if fallos >= MAX_FALLOS:
            _fallos.pop(usuario, None)


def _anotar_fallo(usuario):
    with _cerrojo:
        fallos, _ = _fallos.get(usuario, (0, 0))
        _fallos[usuario] = (fallos + 1, time.monotonic())


def _olvidar_fallos(usuario):
    with _cerrojo:
        _fallos.pop(usuario, None)
