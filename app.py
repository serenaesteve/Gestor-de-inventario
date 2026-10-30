#!/usr/bin/env python3
"""Arranca el gestor de inventario sobre SBD.

    python3 app.py                       # http://127.0.0.1:8000 · SBD local en ./datos (con ejemplos si está vacía)
    python3 app.py --sin-ejemplos        # base vacía, con un administrador inicial
    python3 app.py --datos /otra/carpeta --puerto 9000 --abrir
    python3 app.py --publico             # en internet, detrás de un proxy con HTTPS (ver README)
    python3 app.py --demostracion        # con un usuario visitante a la vista y los datos restablecidos cada noche

    # Contra un servidor de SBD en marcha (sbd servidor), con una clave de API:
    SBD_CLAVE=sbd_… python3 app.py --sbd-servidor http://127.0.0.1:8080
"""

import argparse
import errno
import logging
import os
import secrets
import signal
import threading
import webbrowser
from pathlib import Path

from inventario.api import crear_servidor
from inventario.bd import BASE, BaseDatos, SBDError
from inventario.cuentas import CuentasServicio
from inventario.demo import USUARIOS_EJEMPLO, cargar_demo, vigilar_restablecimiento

CARPETA = Path(__file__).resolve().parent
FICHERO_CREDENCIALES = "credenciales-iniciales.txt"


def en_carpeta_de_red(carpeta):
    """¿Está el proyecto en un montaje de red (SFTP/SMB de GNOME, /run/user/…/gvfs)?

    SBD bloquea sus ficheros con cerrojos del sistema operativo, y esos montajes no
    los ofrecen: allí los datos tienen que ir a una carpeta del disco.
    """
    ruta = str(carpeta)
    return "/gvfs/" in ruta or ruta.startswith("/run/user/")


def carpeta_de_datos_por_defecto():
    if en_carpeta_de_red(CARPETA):
        return Path.home() / ".local" / "share" / "gestor-inventario" / "datos"
    return CARPETA / "datos"


AYUDA_CARPETA = """
No se puede usar la carpeta de datos de SBD: {carpeta}
  {error}
Si es una carpeta de red (SFTP, SMB…), copia el proyecto a tu disco y arráncalo desde allí:
    cp -r "{proyecto}" ~/gestor-inventario
    cd ~/gestor-inventario && python3 app.py
Si la tiene abierta otro programa de SBD (la consola o el panel), ciérralo, o conecta el
inventario a ese servidor:  python3 app.py --sbd-servidor http://127.0.0.1:8080 --sbd-clave sbd_…
"""


def guardar_credenciales(bd, cuentas_nuevas):
    """Modo público: las contraseñas van a un fichero que solo lee su dueño, no a los registros del sistema."""
    ruta = bd.directorio / FICHERO_CREDENCIALES
    with os.fdopen(os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "w", encoding="utf-8") as fichero:
        for usuario, contrasena in cuentas_nuevas.items():
            fichero.write(f"{usuario}  {contrasena}\n")
    print(f"Contraseñas iniciales guardadas en {ruta} (bórralo cuando las hayas apuntado).")


def preparar_datos(bd, con_ejemplos, publico=False):
    """Carga el ejemplo o, si no hay ningún usuario, crea un administrador inicial."""
    if con_ejemplos:
        # Las contraseñas de ejemplo son públicas: en internet cada instalación tiene las suyas
        contrasenas = {u[0]: secrets.token_urlsafe(12) for u in USUARIOS_EJEMPLO} if publico else None
        resumen = cargar_demo(bd, contrasenas=contrasenas)
        if resumen:
            print(f"Material de ejemplo cargado: {resumen['referencias']} referencias y "
                  f"{resumen['movimientos']} movimientos de los últimos {resumen['dias']} días.")
            if contrasenas:
                guardar_credenciales(bd, contrasenas)
    with bd.conexion("inventario · arranque") as conexion:
        cuentas = CuentasServicio(conexion)
        if not cuentas.hay_usuarios():
            contrasena = secrets.token_urlsafe(12 if publico else 9)
            cuentas.crear_usuario("admin", "Administración", contrasena, "admin")
            if publico:
                guardar_credenciales(bd, {"admin": contrasena})
            else:
                print("Usuario inicial creado (apúntalo, no se volverá a mostrar):")
                print(f"    usuario: admin    contraseña: {contrasena}")
        elif cuentas.datos_de_ejemplo() and not publico:
            print("Usuarios de ejemplo:")
            for usuario, nombre, contrasena, rol in USUARIOS_EJEMPLO:
                print(f"    {usuario:<8} / {contrasena:<12} ({nombre}, {'administración' if rol == 'admin' else 'operario'})")


def arrancar_servidor(host, puerto_inicial, bd, publico=False, demostracion=False):
    """Crea el servidor en el primer puerto libre a partir de `puerto_inicial`."""
    for puerto in range(puerto_inicial, puerto_inicial + 20):
        try:
            return crear_servidor(host, puerto, bd, publico, demostracion)
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
            print(f"El puerto {puerto} está ocupado por otro programa; pruebo el {puerto + 1}…")
    raise SystemExit(f"No hay puertos libres entre {puerto_inicial} y {puerto_inicial + 19}. Usa --puerto con otro número.")


def main():
    parser = argparse.ArgumentParser(description="Gestor de inventario sobre SBD")
    parser.add_argument("--host", default="127.0.0.1", help="interfaz de red (por defecto 127.0.0.1)")
    parser.add_argument("--puerto", type=int, default=8000, help="puerto HTTP (por defecto 8000)")
    parser.add_argument("--datos", default=None, help="carpeta de datos de SBD (por defecto ./datos)")
    parser.add_argument("--demostracion", action="store_true",
                        help="usuario visitante a la vista y TODOS los datos restablecidos cada noche: solo para datos de ejemplo")
    parser.add_argument("--sbd-servidor", metavar="URL", help="usar un servidor de SBD en marcha en lugar de la carpeta local")
    parser.add_argument("--sbd-clave", metavar="CLAVE", default=os.environ.get("SBD_CLAVE"),
                        help="clave de API del servidor de SBD (o la variable SBD_CLAVE)")
    parser.add_argument("--sbd-base", default=BASE, help=f"nombre de la base en SBD (por defecto «{BASE}»)")
    parser.add_argument("--sin-ejemplos", action="store_true", help="no cargar el material de ejemplo")
    parser.add_argument("--demo", action="store_true", help=argparse.SUPPRESS)  # compatibilidad: ya es lo normal
    parser.add_argument("--abrir", action="store_true", help="abre el navegador al arrancar")
    parser.add_argument("--publico", action="store_true",
                        help="para internet, detrás de un proxy con HTTPS: sin usuarios a la vista, contraseñas aleatorias y cookie Secure")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    if args.publico and args.sbd_servidor:
        parser.error("--publico guarda las contraseñas iniciales en la carpeta de datos: úsalo con SBD local")
    if args.demostracion and args.sin_ejemplos:
        parser.error("--demostracion restablece el material de ejemplo cada noche: no se puede usar con --sin-ejemplos")

    carpeta = None
    try:
        if args.sbd_servidor:
            bd = BaseDatos(url=args.sbd_servidor, clave=args.sbd_clave, base=args.sbd_base)
        else:
            carpeta = Path(args.datos).expanduser() if args.datos else carpeta_de_datos_por_defecto()
            if args.datos is None and en_carpeta_de_red(CARPETA):
                print("Aviso: estás ejecutando el proyecto desde una carpeta de red, donde SBD no puede")
                print(f"bloquear sus ficheros. Los datos se guardan en tu disco: {carpeta}")
                print("Irá más rápido si copias el proyecto a tu disco y lo arrancas desde allí.\n")
            carpeta.mkdir(parents=True, exist_ok=True)
            bd = BaseDatos(carpeta, base=args.sbd_base)
        servidor = arrancar_servidor(args.host, args.puerto, bd, args.publico, args.demostracion)
        preparar_datos(bd, con_ejemplos=not args.sin_ejemplos, publico=args.publico)
        if args.demostracion:
            with bd.conexion("inventario · arranque") as conexion:
                CuentasServicio(conexion).asegurar_usuario_demo()
    except (SBDError, OSError) as error:
        if carpeta is None:
            raise SystemExit(f"\nNo se puede usar el servidor de SBD {args.sbd_servidor}:\n  {error}\n") from None
        raise SystemExit(AYUDA_CARPETA.format(carpeta=carpeta, error=error, proyecto=CARPETA)) from None

    url = f"http://{args.host}:{servidor.server_port}"
    print(f"Gestor de inventario en {url}")
    print(f"Base de datos: {bd.descripcion}")
    print("Pulsa Ctrl+C para detenerlo.", flush=True)
    if args.abrir:
        webbrowser.open(url)

    def parar(*_):
        raise KeyboardInterrupt

    # Si lo para el sistema (kill, systemd…), se cierra igual de ordenado que con Ctrl+C:
    # SBD compacta su diario en inventario.base y suelta sus cerrojos
    signal.signal(signal.SIGTERM, parar)
    fin_de_la_demostracion = threading.Event()
    if args.demostracion:
        print("Demostración: el usuario visitante está a la vista y los datos se restablecen cada noche.", flush=True)
        threading.Thread(target=vigilar_restablecimiento, args=(bd, fin_de_la_demostracion),
                         name="restablecer-demostracion", daemon=True).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        fin_de_la_demostracion.set()
        servidor.server_close()
        bd.cerrar()


if __name__ == "__main__":
    main()
