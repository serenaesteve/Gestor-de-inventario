"""Gestión de la conexión con SQLite, migraciones del esquema y transacciones."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DIR_MIGRACIONES = Path(__file__).with_name("migraciones")


def migraciones():
    """Migraciones disponibles en orden: [(número, ruta)], p. ej. (2, 002_usuarios.sql)."""
    return sorted((int(ruta.name[:3]), ruta) for ruta in DIR_MIGRACIONES.glob("[0-9][0-9][0-9]_*.sql"))


VERSION_ESQUEMA = migraciones()[-1][0]


def conectar(ruta_bd):
    """Abre una conexión configurada para la aplicación.

    - isolation_level=None: modo autocommit; las transacciones se abren
      explícitamente con `transaccion()` para controlar cuándo empiezan.
    - foreign_keys: SQLite no comprueba las claves ajenas si no se activa.
    - WAL: permite leer mientras otra conexión escribe.
    """
    conn = sqlite3.connect(ruta_bd, isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def inicializar(conn):
    """Lleva el esquema a la última versión aplicando las migraciones pendientes.

    `PRAGMA user_version` guarda la versión dentro del propio fichero. Cada migración
    y el cambio de versión van en la misma transacción: o se aplica entera o no se aplica.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for numero, ruta in migraciones():
        if numero <= version:
            continue
        sql = ruta.read_text(encoding="utf-8")
        try:
            conn.executescript(f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {numero};\nCOMMIT;")
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise


@contextmanager
def transaccion(conn):
    """Ejecuta un bloque como una única transacción atómica.

    BEGIN IMMEDIATE reserva el bloqueo de escritura desde el principio, de modo
    que leer el stock y actualizarlo no puede intercalarse con otra petición.
    Si algo falla dentro del bloque, se deshace todo con ROLLBACK.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
