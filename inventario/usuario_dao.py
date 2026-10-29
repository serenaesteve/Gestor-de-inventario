"""DAO de usuarios, sesiones y ajustes."""


class UsuarioDAO:
    def __init__(self, conexion):
        self._con = conexion

    # ------------------------------------------------------------------ usuarios

    def insertar(self, usuario, nombre, rol, hash_contrasena):
        return self._con.valor(
            "insertar en usuarios { usuario: ?, nombre: ?, rol: ?, hash_contrasena: ? } devolver id",
            [usuario, nombre, rol, hash_contrasena],
        )

    def por_usuario(self, usuario):
        return self._con.una("buscar usuarios donde usuario = ?", [usuario])

    def por_id(self, usuario_id):
        return self._con.una("buscar usuarios donde id = ?", [usuario_id])

    def contar(self):
        return self._con.valor("buscar usuarios mostrar contar()")

    def registrar_acceso(self, usuario_id):
        self._con.ejecutar("actualizar usuarios poner ultimo_acceso = ahora() donde id = ?", [usuario_id])

    # ------------------------------------------------------------------ sesiones

    def crear_sesion(self, huella, usuario_id, horas):
        self._con.ejecutar(
            "insertar en sesiones { token_hash: ?, usuario_id: ?, expira_en: ahora() + horas(?) }",
            [huella, usuario_id, horas],
        )

    def usuario_de_sesion(self, huella):
        """Usuario dueño de una sesión vigente, o None si no existe, caducó o está desactivado."""
        return self._con.una(
            """buscar sesiones como s {
                 unir usuarios como u en u.id = s.usuario_id
                 donde s.token_hash = ? y s.expira_en > ahora() y u.activo
                 mostrar u.id, u.usuario, u.nombre, u.rol
               }""",
            [huella],
        )

    def borrar_sesion(self, huella):
        self._con.ejecutar("borrar de sesiones donde token_hash = ?", [huella])

    def purgar_sesiones(self):
        self._con.ejecutar("borrar de sesiones donde expira_en <= ahora()")

    # ------------------------------------------------------------------- ajustes

    def leer_ajuste(self, clave):
        return self._con.valor("buscar ajustes donde clave = ? mostrar valor", [clave])

    def guardar_ajuste(self, clave, valor):
        self._con.ejecutar("insertar o actualizar en ajustes { clave: ?, valor: ? }", [clave, valor])
