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

# Freno a los ataques de fuerza bruta: 5 fallos seguidos bloquean ese usuario 5 minutos,
# y 20 desde una misma dirección IP, aunque cada uno sea con un usuario distinto
MAX_FALLOS = 5
MAX_FALLOS_IP = 20
BLOQUEO_SEGUNDOS = 300
MAX_ANOTADOS = 10_000

# Usuario de la demostración pública: su contraseña se enseña a propósito en la pantalla de acceso
USUARIO_DEMO = "demo"
NOMBRE_DEMO = "Visitante"
CONTRASENA_DEMO = "demostracion"
# Entradas y cambios del visitante en cada ventana de tiempo, para que no se pueda inflar la base
MAX_CAMBIOS_DEMO_IP = 30
MAX_CAMBIOS_DEMO_TOTAL = 500
VENTANA_DEMO_SEGUNDOS = 600
_fallos = {}
_cambios_demo = {}
_cerrojo = threading.Lock()


def _publico(fila):
    return {"id": fila["id"], "usuario": fila["usuario"], "nombre": fila["nombre"], "rol": fila["rol"],
            "demo": fila["usuario"] == USUARIO_DEMO}


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

    def iniciar_sesion(self, datos, ip=None):
        """Comprueba usuario y contraseña. Devuelve (token, usuario) o lanza NoAutorizado."""
        if not isinstance(datos, dict):
            raise ErrorValidacion("Faltan el usuario y la contraseña")
        usuario = str(datos.get("usuario", "")).strip().lower()
        contrasena = datos.get("contrasena")
        if not usuario:
            raise ErrorValidacion("Escribe tu usuario", "usuario")
        if not isinstance(contrasena, str) or not contrasena:
            raise ErrorValidacion("Escribe tu contraseña", "contrasena")
        clave_ip = f"ip:{ip}" if ip else None
        # El visitante no se bloquea por usuario: si no, cualquiera lo dejaría sin entrar a propósito
        clave_usuario = None if usuario == USUARIO_DEMO else f"usuario:{usuario}"
        if clave_usuario:
            _comprobar_bloqueo(clave_usuario, MAX_FALLOS)
        else:
            frenar_visitante(ip)  # cada entrada crea una sesión: también cuenta
        if clave_ip:
            _comprobar_bloqueo(clave_ip, MAX_FALLOS_IP)

        fila = self.usuarios.por_usuario(usuario)
        # Siempre se calcula un PBKDF2, exista o no el usuario (mismo tiempo de respuesta)
        correcta = seguridad.comprobar_contrasena(contrasena, fila["hash_contrasena"] if fila else seguridad.hash_señuelo())
        if not (fila and correcta and fila["activo"]):
            _anotar_fallo(*filter(None, (clave_usuario, clave_ip)))
            raise NoAutorizado("Usuario o contraseña incorrectos")
        _olvidar_fallos(f"usuario:{usuario}")

        token = seguridad.nuevo_token()
        with self._con.transaccion():
            self.usuarios.purgar_sesiones()
            self.usuarios.crear_sesion(seguridad.huella_token(token), fila["id"], DURACION_SESION.total_seconds() / 3600)
            self.usuarios.registrar_acceso(fila["id"])
        return token, _publico(fila)

    def usuario_de_sesion(self, token):
        if not token:
            return None
        fila = self.usuarios.usuario_de_sesion(seguridad.huella_token(token))
        return _publico(fila) if fila else None

    def cerrar_sesion(self, token):
        if token:
            self.usuarios.borrar_sesion(seguridad.huella_token(token))

    # -------------------------------------------------------------- ajustes

    def datos_de_ejemplo(self):
        return self.usuarios.leer_ajuste("datos_ejemplo") == "1"

    def marcar_datos_de_ejemplo(self):
        self.usuarios.guardar_ajuste("datos_ejemplo", "1")

    def asegurar_usuario_demo(self):
        if not self.usuarios.por_usuario(USUARIO_DEMO):
            self.crear_usuario(USUARIO_DEMO, NOMBRE_DEMO, CONTRASENA_DEMO, "operario")


def _comprobar_bloqueo(clave, maximo):
    with _cerrojo:
        fallos, desde = _fallos.get(clave, (0, 0))
        restante = BLOQUEO_SEGUNDOS - (time.monotonic() - desde)
        if fallos >= maximo and restante > 0:
            raise DemasiadosIntentos(f"Demasiados intentos fallidos. Vuelve a probar en {max(1, round(restante / 60))} min")


def _anotar_fallo(*claves):
    ahora = time.monotonic()
    with _cerrojo:
        if len(_fallos) >= MAX_ANOTADOS:  # quien pruebe millones de nombres no llena la memoria
            for vieja in [c for c, (_, desde) in _fallos.items() if ahora - desde >= BLOQUEO_SEGUNDOS]:
                del _fallos[vieja]
            if len(_fallos) >= MAX_ANOTADOS:
                _fallos.clear()
        for clave in claves:
            fallos, desde = _fallos.get(clave, (0, 0))
            # Los fallos caducan: los de hace tiempo no cuentan para el bloqueo de hoy
            _fallos[clave] = (fallos + 1 if ahora - desde < BLOQUEO_SEGUNDOS else 1, ahora)


def _olvidar_fallos(clave):
    with _cerrojo:
        _fallos.pop(clave, None)


def frenar_visitante(ip):
    """Cuenta un cambio del visitante; si ha hecho demasiados en poco tiempo, lo rechaza."""
    ahora = time.monotonic()
    with _cerrojo:
        if len(_cambios_demo) >= MAX_ANOTADOS:
            _cambios_demo.clear()
        for clave, maximo in ((f"ip:{ip}", MAX_CAMBIOS_DEMO_IP), ("total", MAX_CAMBIOS_DEMO_TOTAL)):
            cuenta, desde = _cambios_demo.get(clave, (0, ahora))
            if ahora - desde >= VENTANA_DEMO_SEGUNDOS:
                cuenta, desde = 0, ahora
            if cuenta >= maximo:
                raise DemasiadosIntentos("La demostración tiene un límite de uso. Vuelve a probar en unos minutos")
            _cambios_demo[clave] = (cuenta + 1, desde)
