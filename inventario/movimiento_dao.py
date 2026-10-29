"""DAO de movimientos: entradas, salidas y ajustes de stock.

SBD no tiene disparadores, así que la regla «los movimientos no se modifican ni se
borran» la garantiza este DAO: solo sabe insertar y consultar. No hay ninguna orden
«actualizar movimientos» ni «borrar de movimientos» en todo el programa.
"""

from .bd import iso

TIPOS = ("ENTRADA", "SALIDA", "AJUSTE")

_CONSULTA = """buscar movimientos como m {{
  unir productos como p en p.id = m.producto_id
  unir opcional usuarios como u en u.id = m.usuario_id
  {donde}
  mostrar m.id, m.producto_id, p.codigo, p.nombre como producto, m.tipo, m.cantidad,
          m.stock_anterior, m.stock_resultante, m.motivo, m.fecha, u.nombre como usuario
  ordenar m.fecha desc, m.id desc
  {limite}
}}"""


def _a_dict(fila):
    movimiento = dict(fila)
    movimiento["fecha"] = iso(movimiento["fecha"])
    return movimiento


class MovimientoDAO:
    def __init__(self, conexion):
        self._con = conexion

    def insertar(self, producto_id, tipo, cantidad, stock_anterior, stock_resultante, motivo,
                 usuario_id=None, fecha=None):
        """`fecha` solo se indica al importar historial; si no, la pone SBD con ahora()."""
        return self._con.valor(
            """insertar en movimientos {
                 producto_id: ?, tipo: ?, cantidad: ?, stock_anterior: ?, stock_resultante: ?,
                 motivo: ?, usuario_id: ?, fecha: si_nulo(?, ahora())
               } devolver id""",
            [producto_id, tipo, cantidad, stock_anterior, stock_resultante, motivo, usuario_id, fecha],
        )

    def obtener(self, movimiento_id):
        fila = self._con.una(_CONSULTA.format(donde="donde m.id = ?", limite=""), [movimiento_id])
        return _a_dict(fila) if fila else None

    def listar(self, producto_id=None, tipo="", limite=200):
        condiciones = []
        parametros = []
        if producto_id is not None:
            condiciones.append("m.producto_id = ?")
            parametros.append(producto_id)
        if tipo:
            condiciones.append("m.tipo = ?")
            parametros.append(tipo)
        donde = f"donde {' y '.join(condiciones)}" if condiciones else ""
        filas = self._con.consultar(_CONSULTA.format(donde=donde, limite="limite ?"), [*parametros, limite])
        return [_a_dict(fila) for fila in filas]

    def actividad_hoy(self):
        return self._con.una(
            """buscar movimientos donde dia_de(fecha) = hoy() mostrar
                 contar() como movimientos,
                 si_nulo(sumar(caso cuando tipo = "ENTRADA" entonces cantidad sino 0 fin), 0) como unidades_entrada,
                 si_nulo(sumar(caso cuando tipo = "SALIDA" entonces 0 - cantidad sino 0 fin), 0) como unidades_salida"""
        )

    def descuadres(self):
        """Referencias cuyo stock no es la suma de sus movimientos (debería ser siempre 0)."""
        sumas = {
            fila["producto_id"]: fila["suma"]
            for fila in self._con.consultar(
                "buscar movimientos agrupar producto_id mostrar producto_id, sumar(cantidad) como suma"
            )
        }
        productos = self._con.consultar("buscar productos mostrar id, stock_actual")
        return [p["id"] for p in productos if p["stock_actual"] != sumas.get(p["id"], 0)]
