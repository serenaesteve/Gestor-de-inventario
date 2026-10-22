#!/usr/bin/env python3
"""Arranca el gestor de inventario.

    python app.py                   # http://127.0.0.1:8000 (con material de ejemplo si la BD está vacía)
    python app.py --sin-ejemplos    # base de datos vacía, con un administrador inicial
    python app.py --puerto 9000 --bd otra.db --abrir
"""

import argparse
import errno
import logging
import secrets
import sqlite3
import webbrowser
from contextlib import closing
from pathlib import Path

from inventario.api import crear_servidor
from inventario.conexion import conectar
from inventario.cuentas import CuentasServicio
from inventario.demo import USUARIOS_EJEMPLO, cargar_demo


CARPETA = Path(__file__).resolve().parent


def en_carpeta_de_red(carpeta):
    """¿Está el proyecto en un montaje de red (SFTP/SMB de GNOME, /run/user/…/gvfs)?

    SQLite necesita bloqueos de fichero que esos montajes no ofrecen: la base de
    datos se queda colgada o en solo lectura.
    """
    ruta = str(carpeta)
    return "/gvfs/" in ruta or ruta.startswith("/run/user/")


def ruta_bd_por_defecto():
    if en_carpeta_de_red(CARPETA):
        local = Path.home() / ".local" / "share" / "gestor-inventario"
        local.mkdir(parents=True, exist_ok=True)
        return local / "inventario.db"
    return CARPETA / "inventario.db"


AYUDA_RED = """
No se puede escribir en la base de datos: {ruta}
Suele pasar si está en una carpeta de red (SFTP, SMB…) o sin permisos de escritura.
Solución: copia el proyecto a tu disco y arráncalo desde allí:
    cp -r "{carpeta}" ~/gestor-inventario
    cd ~/gestor-inventario && python3 app.py
o indica otra ubicación para la base de datos:  python3 app.py --bd ~/inventario.db
"""


def preparar_datos(ruta_bd, con_ejemplos):
    """Carga el ejemplo o, si no hay ningún usuario, crea un administrador inicial."""
    if con_ejemplos:
        resumen = cargar_demo(ruta_bd)
        if resumen:
            print(f"Material de ejemplo cargado: {resumen['referencias']} referencias y "
                  f"{resumen['movimientos']} movimientos de los últimos {resumen['dias']} días.")
    with closing(conectar(ruta_bd)) as conn:
        cuentas = CuentasServicio(conn)
        if not cuentas.hay_usuarios():
            contrasena = secrets.token_urlsafe(9)
            cuentas.crear_usuario("admin", "Administración", contrasena, "admin")
            print("Usuario inicial creado (apúntalo, no se volverá a mostrar):")
            print(f"    usuario: admin    contraseña: {contrasena}")
        elif cuentas.datos_de_ejemplo():
            print("Usuarios de ejemplo:")
            for usuario, nombre, contrasena, rol in USUARIOS_EJEMPLO:
                print(f"    {usuario:<8} / {contrasena:<12} ({nombre}, {'administración' if rol == 'admin' else 'operario'})")


def arrancar_servidor(host, puerto_inicial, ruta_bd):
    """Crea el servidor en el primer puerto libre a partir de `puerto_inicial`."""
    for puerto in range(puerto_inicial, puerto_inicial + 20):
        try:
            return crear_servidor(host, puerto, ruta_bd)
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
            print(f"El puerto {puerto} está ocupado por otro programa; pruebo el {puerto + 1}…")
    raise SystemExit(f"No hay puertos libres entre {puerto_inicial} y {puerto_inicial + 19}. Usa --puerto con otro número.")


def main():
    parser = argparse.ArgumentParser(description="Gestor de inventario")
    parser.add_argument("--host", default="127.0.0.1", help="interfaz de red (por defecto 127.0.0.1)")
    parser.add_argument("--puerto", type=int, default=8000, help="puerto HTTP (por defecto 8000)")
    parser.add_argument("--bd", default=None, help="fichero SQLite (por defecto, inventario.db junto a app.py)")
    parser.add_argument("--sin-ejemplos", action="store_true", help="no cargar el material de ejemplo")
    parser.add_argument("--demo", action="store_true", help=argparse.SUPPRESS)  # compatibilidad: ya es lo normal
    parser.add_argument("--abrir", action="store_true", help="abre el navegador al arrancar")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")

    if args.bd is None:
        args.bd = str(ruta_bd_por_defecto())
        if en_carpeta_de_red(CARPETA):
            print("Aviso: estás ejecutando el proyecto desde una carpeta de red. SQLite no funciona ahí,")
            print(f"así que la base de datos se guarda en tu disco: {args.bd}")
            print("Irá más rápido si copias el proyecto a tu disco y lo arrancas desde allí.\n")

    try:
        servidor = arrancar_servidor(args.host, args.puerto, args.bd)
        preparar_datos(args.bd, con_ejemplos=not args.sin_ejemplos)
    except sqlite3.OperationalError as error:
        if any(clave in str(error) for clave in ("readonly", "locked", "unable to open", "disk I/O")):
            raise SystemExit(AYUDA_RED.format(ruta=args.bd, carpeta=CARPETA)) from None
        raise

    url = f"http://{args.host}:{servidor.server_port}"
    print(f"Gestor de inventario en {url}  (base de datos: {args.bd})")
    print("Pulsa Ctrl+C para detenerlo.", flush=True)
    if args.abrir:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
