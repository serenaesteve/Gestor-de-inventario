"""DAO de movimientos: entradas, salidas y ajustes de stock."""

TIPOS = ("ENTRADA", "SALIDA", "AJUSTE")

_SELECT = """
    SELECT m.id, m.producto_id, p.codigo, p.nombre AS producto, m.tipo, m.cantidad,
           m.stock_anterior, m.stock_resultante, m.motivo, m.fecha, u.nombre AS usuario
    FROM movimientos m
    JOIN productos p ON p.id = m.producto_id
    LEFT JOIN usuarios u ON u.id = m.usuario_id
"""


class MovimientoDAO:
    def __init__(self, conn):
        self._conn = conn

    def insertar(self, producto_id, tipo, cantidad, stock_anterior, stock_resultante, motivo,
                 usuario_id=None, fecha=None):
        """`fecha` solo se indica al importar historial; si no, la pone la base de datos."""
        cursor = self._conn.execute(
            """
            INSERT INTO movimientos (producto_id, tipo, cantidad, stock_anterior, stock_resultante, motivo, usuario_id, fecha)
            VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
            """,
            (producto_id, tipo, cantidad, stock_anterior, stock_resultante, motivo, usuario_id, fecha),
        )
        return cursor.lastrowid

    def obtener(self, movimiento_id):
        fila = self._conn.execute(f"{_SELECT} WHERE m.id = ?", (movimiento_id,)).fetchone()
        return dict(fila) if fila else None

    def listar(self, producto_id=None, tipo="", limite=200):
        condiciones = []
        parametros = []
        if producto_id is not None:
            condiciones.append("m.producto_id = ?")
            parametros.append(producto_id)
        if tipo:
            condiciones.append("m.tipo = ?")
            parametros.append(tipo)
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        filas = self._conn.execute(
            f"{_SELECT} {where} ORDER BY m.fecha DESC, m.id DESC LIMIT ?",
            (*parametros, limite),
        )
        return [dict(fila) for fila in filas]

    def actividad_hoy(self):
        fila = self._conn.execute(
            """
            SELECT COUNT(*) AS movimientos,
                   COALESCE(SUM(CASE WHEN tipo = 'ENTRADA' THEN cantidad END), 0)  AS unidades_entrada,
                   COALESCE(SUM(CASE WHEN tipo = 'SALIDA'  THEN -cantidad END), 0) AS unidades_salida
            FROM movimientos
            WHERE date(fecha, 'localtime') = date('now', 'localtime')
            """
        ).fetchone()
        return dict(fila)
