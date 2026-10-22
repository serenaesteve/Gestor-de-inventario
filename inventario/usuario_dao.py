"""DAO de usuarios, sesiones y ajustes."""


class UsuarioDAO:
    def __init__(self, conn):
        self._conn = conn

    # ------------------------------------------------------------------ usuarios

    def insertar(self, usuario, nombre, rol, hash_contrasena):
        cursor = self._conn.execute(
            "INSERT INTO usuarios (usuario, nombre, rol, hash_contrasena) VALUES (?, ?, ?, ?)",
            (usuario, nombre, rol, hash_contrasena),
        )
        return cursor.lastrowid

    def por_usuario(self, usuario):
        fila = self._conn.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
        return dict(fila) if fila else None

    def por_id(self, usuario_id):
        fila = self._conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        return dict(fila) if fila else None

    def contar(self):
        return self._conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]

    def registrar_acceso(self, usuario_id, ahora):
        self._conn.execute("UPDATE usuarios SET ultimo_acceso = ? WHERE id = ?", (ahora, usuario_id))

    # ------------------------------------------------------------------ sesiones

    def crear_sesion(self, huella, usuario_id, expira_en):
        self._conn.execute(
            "INSERT INTO sesiones (token_hash, usuario_id, expira_en) VALUES (?, ?, ?)",
            (huella, usuario_id, expira_en),
        )

    def usuario_de_sesion(self, huella, ahora):
        """Usuario dueño de una sesión vigente, o None si no existe, caducó o está desactivado."""
        fila = self._conn.execute(
            """
            SELECT u.id, u.usuario, u.nombre, u.rol
            FROM sesiones s
            JOIN usuarios u ON u.id = s.usuario_id
            WHERE s.token_hash = ? AND s.expira_en > ? AND u.activo = 1
            """,
            (huella, ahora),
        ).fetchone()
        return dict(fila) if fila else None

    def borrar_sesion(self, huella):
        self._conn.execute("DELETE FROM sesiones WHERE token_hash = ?", (huella,))

    def purgar_sesiones(self, ahora):
        self._conn.execute("DELETE FROM sesiones WHERE expira_en <= ?", (ahora,))

    # ------------------------------------------------------------------- ajustes

    def leer_ajuste(self, clave):
        fila = self._conn.execute("SELECT valor FROM ajustes WHERE clave = ?", (clave,)).fetchone()
        return fila[0] if fila else None

    def guardar_ajuste(self, clave, valor):
        self._conn.execute(
            "INSERT INTO ajustes (clave, valor) VALUES (?, ?) ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
            (clave, valor),
        )
