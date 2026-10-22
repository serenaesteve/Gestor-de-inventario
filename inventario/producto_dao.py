"""DAO de productos: todo el SQL de la tabla `productos` y la vista `v_existencias`.

Todas las consultas usan sentencias preparadas (parámetros `?`), nunca se
concatenan valores del usuario en el SQL: así se evita la inyección SQL.
"""

ESTADOS = ("OK", "BAJO", "AGOTADO", "ALERTA")


def _escapar_like(texto):
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _a_dict(fila):
    """Convierte una fila de v_existencias al formato que expone la aplicación."""
    if fila is None:
        return None
    producto = dict(fila)
    producto["precio"] = producto.pop("precio_centimos") / 100
    producto["valor"] = producto.pop("valor_centimos") / 100
    producto["activo"] = bool(producto["activo"])
    return producto


class ProductoDAO:
    def __init__(self, conn):
        self._conn = conn

    def listar(self, texto="", categoria="", estado=""):
        # Los fragmentos del WHERE son fijos; los valores van siempre como parámetros
        condiciones = ["activo = 1"]
        parametros = []
        if texto:
            patron = f"%{_escapar_like(texto)}%"
            condiciones.append("(codigo LIKE ? ESCAPE '\\' OR nombre LIKE ? ESCAPE '\\')")
            parametros += [patron, patron]
        if categoria:
            condiciones.append("categoria = ?")
            parametros.append(categoria)
        if estado == "ALERTA":
            condiciones.append("estado <> 'OK'")
        elif estado:
            condiciones.append("estado = ?")
            parametros.append(estado)

        sql = f"""
            SELECT * FROM v_existencias
            WHERE {" AND ".join(condiciones)}
            ORDER BY nombre COLLATE NOCASE
        """
        return [_a_dict(fila) for fila in self._conn.execute(sql, parametros)]

    def obtener(self, producto_id):
        fila = self._conn.execute(
            "SELECT * FROM v_existencias WHERE id = ?", (producto_id,)
        ).fetchone()
        return _a_dict(fila)

    def insertar(self, campos):
        cursor = self._conn.execute(
            """
            INSERT INTO productos (codigo, nombre, descripcion, categoria, precio_centimos, stock_minimo)
            VALUES (:codigo, :nombre, :descripcion, :categoria, :precio_centimos, :stock_minimo)
            """,
            campos,
        )
        return cursor.lastrowid

    def actualizar(self, producto_id, campos):
        cursor = self._conn.execute(
            """
            UPDATE productos
            SET codigo = :codigo, nombre = :nombre, descripcion = :descripcion,
                categoria = :categoria, precio_centimos = :precio_centimos,
                stock_minimo = :stock_minimo
            WHERE id = :id AND activo = 1
            """,
            {**campos, "id": producto_id},
        )
        return cursor.rowcount == 1

    def fijar_stock(self, producto_id, nuevo, esperado):
        """Cambia el stock solo si sigue valiendo `esperado` (control de concurrencia)."""
        cursor = self._conn.execute(
            "UPDATE productos SET stock_actual = ? WHERE id = ? AND stock_actual = ?",
            (nuevo, producto_id, esperado),
        )
        return cursor.rowcount == 1

    def desactivar(self, producto_id):
        cursor = self._conn.execute(
            "UPDATE productos SET activo = 0 WHERE id = ? AND activo = 1", (producto_id,)
        )
        return cursor.rowcount == 1

    def categorias(self):
        filas = self._conn.execute(
            """
            SELECT categoria, COUNT(*) AS productos
            FROM productos
            WHERE activo = 1
            GROUP BY categoria
            ORDER BY categoria COLLATE NOCASE
            """
        )
        return [dict(fila) for fila in filas]

    def totales(self):
        fila = self._conn.execute(
            """
            SELECT COUNT(*)                          AS productos,
                   COUNT(DISTINCT categoria)         AS categorias,
                   COALESCE(SUM(stock_actual), 0)    AS unidades,
                   COALESCE(SUM(valor_centimos), 0)  AS valor_centimos,
                   COALESCE(SUM(estado = 'BAJO'), 0)    AS bajo,
                   COALESCE(SUM(estado = 'AGOTADO'), 0) AS agotados
            FROM v_existencias
            WHERE activo = 1
            """
        ).fetchone()
        totales = dict(fila)
        totales["valor"] = totales.pop("valor_centimos") / 100
        return totales

    def en_alerta(self, limite=10):
        """Productos agotados o bajo mínimo, los más urgentes primero."""
        filas = self._conn.execute(
            """
            SELECT * FROM v_existencias
            WHERE activo = 1 AND estado <> 'OK'
            ORDER BY estado = 'AGOTADO' DESC,
                     CAST(stock_actual AS REAL) / MAX(stock_minimo, 1),
                     nombre COLLATE NOCASE
            LIMIT ?
            """,
            (limite,),
        )
        return [_a_dict(fila) for fila in filas]
