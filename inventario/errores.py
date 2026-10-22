"""Excepciones de dominio. Cada una sabe qué código HTTP le corresponde."""


class ErrorInventario(Exception):
    estado = 500

    def __init__(self, mensaje, campo=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.campo = campo

    def como_dict(self):
        datos = {"error": self.mensaje}
        if self.campo:
            datos["campo"] = self.campo
        return datos


class ErrorValidacion(ErrorInventario):
    estado = 400


class NoAutorizado(ErrorInventario):
    estado = 401


class Prohibido(ErrorInventario):
    estado = 403


class NoEncontrado(ErrorInventario):
    estado = 404


class Conflicto(ErrorInventario):
    estado = 409


class TipoNoAdmitido(ErrorInventario):
    estado = 415


class DemasiadosIntentos(ErrorInventario):
    estado = 429
