"""Contraseñas y tokens de sesión, solo con la biblioteca estándar."""

import hashlib
import hmac
import secrets

ALGORITMO = "pbkdf2_sha256"
# Recomendación OWASP para PBKDF2-SHA256. Los tests la bajan para ir rápido;
# como el número se guarda con cada contraseña, cambiarlo no invalida las antiguas.
ITERACIONES = 600_000


def cifrar_contrasena(contrasena):
    """Devuelve 'pbkdf2_sha256$iteraciones$sal$resumen', con una sal aleatoria por contraseña."""
    sal = secrets.token_bytes(16)
    resumen = hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"), sal, ITERACIONES)
    return f"{ALGORITMO}${ITERACIONES}${sal.hex()}${resumen.hex()}"


def comprobar_contrasena(contrasena, guardado):
    try:
        algoritmo, iteraciones, sal, resumen = guardado.split("$")
        calculado = hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"), bytes.fromhex(sal), int(iteraciones))
    except (ValueError, AttributeError):
        return False
    # Comparación en tiempo constante: no revela cuántos caracteres coinciden
    return algoritmo == ALGORITMO and hmac.compare_digest(calculado.hex(), resumen)


def nuevo_token():
    return secrets.token_urlsafe(32)


def huella_token(token):
    """Lo que se guarda en la BD: la huella del token, nunca el token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


_hash_señuelo = None


def hash_señuelo():
    """Resumen falso para comprobar contraseñas de usuarios que no existen.

    Así un usuario inexistente tarda lo mismo que uno con la contraseña mal
    y no se puede averiguar qué usuarios hay midiendo tiempos.
    """
    global _hash_señuelo
    if _hash_señuelo is None:
        _hash_señuelo = cifrar_contrasena(secrets.token_hex(16))
    return _hash_señuelo
