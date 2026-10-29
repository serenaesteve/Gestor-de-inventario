"""DAO de productos: todas las órdenes SBD de la tabla `productos` y la vista `v_existencias`.

Los valores del usuario van siempre como parámetros `?`, nunca pegados al texto de
la orden: así no hay inyección posible.
"""

from .bd import iso

ESTADOS = ("OK", "BAJO", "AGOTADO", "ALERTA")


def _a_dict(fila):
    """Una fila de v_existencias en el formato que expone la aplicación."""
    if fila is None:
        return None
    producto = dict(fila)
    producto["precio"] = float(producto["precio"])  # dinero (Decimal exacto) → número para el JSON
    producto["valor"] = float(producto["valor"])
    producto["activo"] = bool(producto["activo"])
    producto["creado_en"] = iso(producto["creado_en"])
    producto["actualizado_en"] = iso(producto["actualizado_en"])
    return producto


class ProductoDAO:
    def __init__(self, conexion):
        self._con = conexion

    def listar(self, texto="", categoria="", estado=""):
        # Los fragmentos de «donde» son fijos; los valores van siempre como parámetros
        condiciones = ["activo"]
        parametros = []
        if texto:
            # «contiene» busca el texto tal cual: un «%» o un «_» no son comodines
            condiciones.append("(minusculas(codigo) contiene ? o minusculas(nombre) contiene ?)")
            parametros += [texto.lower(), texto.lower()]
        if categoria:
            condiciones.append("categoria = ?")
            parametros.append(categoria)
        if estado == "ALERTA":
            condiciones.append('estado != "OK"')
        elif estado:
            condiciones.append("estado = ?")
            parametros.append(estado)
        orden = f"buscar v_existencias donde {' y '.join(condiciones)} ordenar minusculas(nombre)"
        return [_a_dict(fila) for fila in self._con.consultar(orden, parametros)]

    def obtener(self, producto_id):
        return _a_dict(self._con.una("buscar v_existencias donde id = ?", [producto_id]))

    def insertar(self, campos):
        return self._con.valor(
            """insertar en productos {
                 codigo: ?, nombre: ?, descripcion: ?, categoria: ?, precio: ?, stock_minimo: ?
               } devolver id""",
            [campos["codigo"], campos["nombre"], campos["descripcion"], campos["categoria"],
             campos["precio"], campos["stock_minimo"]],
        )

    def actualizar(self, producto_id, campos):
        resultado = self._con.ejecutar(
            """actualizar productos
               poner codigo = ?, nombre = ?, descripcion = ?, categoria = ?, precio = ?, stock_minimo = ?,
                     actualizado_en = ahora()
               donde id = ? y activo""",
            [campos["codigo"], campos["nombre"], campos["descripcion"], campos["categoria"],
             campos["precio"], campos["stock_minimo"], producto_id],
        )
        return resultado.rowcount == 1

    def fijar_stock(self, producto_id, nuevo, esperado):
        """Cambia el stock solo si sigue valiendo `esperado` (control de concurrencia optimista)."""
        resultado = self._con.ejecutar(
            "actualizar productos poner stock_actual = ?, actualizado_en = ahora() donde id = ? y stock_actual = ?",
            [nuevo, producto_id, esperado],
        )
        return resultado.rowcount == 1

    def desactivar(self, producto_id):
        resultado = self._con.ejecutar(
            "actualizar productos poner activo = falso, actualizado_en = ahora() donde id = ? y activo", [producto_id]
        )
        return resultado.rowcount == 1

    def fijar_creado_en(self, producto_id, fecha):
        """Solo para el material de ejemplo: la referencia «existía» desde el principio del historial."""
        self._con.ejecutar("actualizar productos poner creado_en = ?, actualizado_en = ? donde id = ?",
                           [fecha, fecha, producto_id])

    def contar(self):
        return self._con.valor("buscar productos mostrar contar()")

    def categorias(self):
        return self._con.consultar(
            "buscar productos donde activo agrupar categoria mostrar categoria, contar() como productos "
            "ordenar minusculas(categoria)"
        )

    def totales(self):
        totales = self._con.una(
            """buscar v_existencias donde activo mostrar
                 contar() como productos,
                 contar(distintos categoria) como categorias,
                 si_nulo(sumar(stock_actual), 0) como unidades,
                 si_nulo(sumar(valor), 0) como valor,
                 si_nulo(sumar(caso cuando estado = "BAJO" entonces 1 sino 0 fin), 0) como bajo,
                 si_nulo(sumar(caso cuando estado = "AGOTADO" entonces 1 sino 0 fin), 0) como agotados"""
        )
        totales["valor"] = float(totales["valor"])
        return totales

    def en_alerta(self, limite=10):
        """Productos agotados o bajo mínimo, los más urgentes primero."""
        filas = self._con.consultar(
            """buscar v_existencias donde activo y estado != "OK"
               ordenar caso cuando estado = "AGOTADO" entonces 0 sino 1 fin,
                       decimal(stock_actual) / mayor(stock_minimo, 1),
                       minusculas(nombre)
               limite ?""",
            [limite],
        )
        return [_a_dict(fila) for fila in filas]
