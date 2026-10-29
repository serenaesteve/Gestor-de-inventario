"""Pruebas del gestor de inventario: reglas de negocio, base de datos SBD y API HTTP.

    python -m unittest discover -s tests -v
"""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from decimal import Decimal

from inventario import cuentas, seguridad
from inventario.api import crear_servidor
from inventario.bd import VERSION_ESQUEMA, BaseDatos, SBDError, migraciones, version_actual
from inventario.cuentas import CuentasServicio
from inventario.demo import cargar_demo
from inventario.errores import Conflicto, DemasiadosIntentos, ErrorValidacion, NoAutorizado, NoEncontrado
from inventario.servicio import InventarioServicio

# PBKDF2 con 600 000 iteraciones es lento a propósito; en los tests basta con pocas
seguridad.ITERACIONES = 1_000


class ConSBD(unittest.TestCase):
    """Cada test trabaja con una carpeta de SBD nueva y una conexión abierta (`self.conn`)."""

    def setUp(self):
        self._carpeta = tempfile.TemporaryDirectory()
        self.bd = BaseDatos(self._carpeta.name)
        self.bd.preparar()
        self._conexion = self.bd.conexion()
        self.conn = self._conexion.__enter__()

    def tearDown(self):
        self._conexion.__exit__(None, None, None)
        self.bd.cerrar()
        self._carpeta.cleanup()


def producto(**cambios):
    datos = {"codigo": "TST-001", "nombre": "Tornillo M6", "categoria": "Ferretería",
             "precio": "0,15", "stock_minimo": 100, "stock_inicial": 0}
    return {**datos, **cambios}


class ServicioTest(ConSBD):
    def setUp(self):
        super().setUp()
        self.srv = InventarioServicio(self.conn)

    def mover(self, producto_id, tipo, cantidad, motivo=""):
        return self.srv.registrar_movimiento(
            {"producto_id": producto_id, "tipo": tipo, "cantidad": cantidad, "motivo": motivo}
        )

    def suma_movimientos(self, producto_id):
        return self.conn.valor("buscar movimientos donde producto_id = ? mostrar si_nulo(sumar(cantidad), 0)",
                               [producto_id])

    # ---------------------------------------------------------------- productos

    def test_alta_con_stock_inicial_genera_una_entrada(self):
        p = self.srv.crear_producto(producto(stock_inicial=250))
        self.assertEqual(p["stock_actual"], 250)
        self.assertEqual(p["precio"], 0.15)
        self.assertEqual(p["codigo"], "TST-001")
        movimientos = self.srv.listar_movimientos({"producto_id": p["id"]})
        self.assertEqual(len(movimientos), 1)
        self.assertEqual(movimientos[0]["tipo"], "ENTRADA")
        self.assertEqual(movimientos[0]["motivo"], "Stock inicial")

    def test_codigo_duplicado_sin_distinguir_mayusculas(self):
        self.srv.crear_producto(producto(codigo="abc-1"))
        with self.assertRaises(Conflicto) as ctx:
            self.srv.crear_producto(producto(codigo="ABC-1"))
        self.assertEqual(ctx.exception.campo, "codigo")

    def test_alta_fallida_no_deja_nada_a_medias(self):
        self.srv.crear_producto(producto(codigo="X"))
        with self.assertRaises(Conflicto):
            self.srv.crear_producto(producto(codigo="X", stock_inicial=10))
        self.assertEqual(self.conn.valor("buscar movimientos mostrar contar()"), 0)

    def test_validaciones_de_producto(self):
        casos = [
            ({"nombre": "  "}, "nombre"),
            ({"codigo": ""}, "codigo"),
            ({"precio": -1}, "precio"),
            ({"precio": "doce"}, "precio"),
            ({"stock_minimo": 2.5}, "stock_minimo"),
            ({"stock_minimo": True}, "stock_minimo"),
            ({"stock_inicial": -3}, "stock_inicial"),
        ]
        for cambios, campo in casos:
            with self.subTest(cambios=cambios), self.assertRaises(ErrorValidacion) as ctx:
                self.srv.crear_producto(producto(**cambios))
            self.assertEqual(ctx.exception.campo, campo)

    def test_precio_se_redondea_a_centimos(self):
        p = self.srv.crear_producto(producto(precio=19.999))
        self.assertEqual(p["precio"], 20.0)
        guardado = self.conn.valor("buscar productos mostrar precio")
        self.assertEqual(guardado, Decimal("20.00"))  # dinero exacto, sin coma flotante

    def test_editar_no_toca_el_stock(self):
        p = self.srv.crear_producto(producto(stock_inicial=5))
        editado = self.srv.actualizar_producto(p["id"], producto(nombre="Tornillo M8", stock_inicial=999))
        self.assertEqual(editado["nombre"], "Tornillo M8")
        self.assertEqual(editado["stock_actual"], 5)

    def test_baja_logica_conserva_historial(self):
        p = self.srv.crear_producto(producto(stock_inicial=5))
        self.srv.dar_de_baja(p["id"])
        self.assertEqual(self.srv.listar_productos(), [])
        self.assertFalse(self.srv.obtener_producto(p["id"])["activo"])
        self.assertEqual(len(self.srv.listar_movimientos({"producto_id": p["id"]})), 1)
        with self.assertRaises(NoEncontrado):
            self.mover(p["id"], "ENTRADA", 1)

    def test_estado_de_existencias(self):
        ok = self.srv.crear_producto(producto(codigo="A", stock_minimo=5, stock_inicial=10))
        bajo = self.srv.crear_producto(producto(codigo="B", stock_minimo=5, stock_inicial=5))
        agotado = self.srv.crear_producto(producto(codigo="C", stock_minimo=5))
        estados = {p["id"]: p["estado"] for p in self.srv.listar_productos()}
        self.assertEqual(estados, {ok["id"]: "OK", bajo["id"]: "BAJO", agotado["id"]: "AGOTADO"})
        self.assertEqual(len(self.srv.listar_productos(estado="ALERTA")), 2)

    def test_busqueda_escapa_comodines_de_like(self):
        self.srv.crear_producto(producto(codigo="A", nombre="Descuento 50%"))
        self.srv.crear_producto(producto(codigo="B", nombre="Descuento 500"))
        self.assertEqual([p["codigo"] for p in self.srv.listar_productos(texto="50%")], ["A"])
        self.assertEqual(len(self.srv.listar_productos(texto="descuento")), 2)

    # ------------------------------------------------------------- movimientos

    def test_entrada_y_salida_actualizan_stock(self):
        p = self.srv.crear_producto(producto(stock_inicial=10))
        entrada = self.mover(p["id"], "ENTRADA", 5, "Compra")
        salida = self.mover(p["id"], "SALIDA", 12, "Venta")
        self.assertEqual((entrada["stock_anterior"], entrada["stock_resultante"]), (10, 15))
        self.assertEqual((salida["cantidad"], salida["stock_resultante"]), (-12, 3))
        self.assertEqual(self.srv.obtener_producto(p["id"])["stock_actual"], 3)

    def test_salida_sin_stock_suficiente_se_rechaza_sin_efectos(self):
        p = self.srv.crear_producto(producto(stock_inicial=3))
        with self.assertRaises(Conflicto) as ctx:
            self.mover(p["id"], "SALIDA", 4)
        self.assertEqual(ctx.exception.campo, "cantidad")
        self.assertEqual(self.srv.obtener_producto(p["id"])["stock_actual"], 3)
        self.assertEqual(len(self.srv.listar_movimientos({"producto_id": p["id"]})), 1)

    def test_recuento_guarda_la_diferencia(self):
        p = self.srv.crear_producto(producto(stock_inicial=20))
        ajuste = self.mover(p["id"], "AJUSTE", 17, "Inventario físico")
        self.assertEqual((ajuste["cantidad"], ajuste["stock_resultante"]), (-3, 17))
        a_cero = self.mover(p["id"], "AJUSTE", 0)
        self.assertEqual(a_cero["stock_resultante"], 0)
        with self.assertRaises(ErrorValidacion):
            self.mover(p["id"], "AJUSTE", 0)

    def test_movimientos_invalidos(self):
        p = self.srv.crear_producto(producto(stock_inicial=1))
        for tipo, cantidad in [("ENTRADA", 0), ("SALIDA", -1), ("REGALO", 1), ("ENTRADA", "muchos")]:
            with self.subTest(tipo=tipo, cantidad=cantidad), self.assertRaises(ErrorValidacion):
                self.mover(p["id"], tipo, cantidad)
        with self.assertRaises(NoEncontrado):
            self.mover(9999, "ENTRADA", 1)

    def test_invariante_stock_igual_a_suma_de_movimientos(self):
        p = self.srv.crear_producto(producto(stock_inicial=40))
        for tipo, cantidad in [("SALIDA", 7), ("ENTRADA", 12), ("AJUSTE", 41), ("SALIDA", 41), ("ENTRADA", 3)]:
            self.mover(p["id"], tipo, cantidad)
        actual = self.srv.obtener_producto(p["id"])["stock_actual"]
        self.assertEqual(actual, 3)
        self.assertEqual(actual, self.suma_movimientos(p["id"]))

    def test_resumen(self):
        a = self.srv.crear_producto(producto(codigo="A", precio=2, stock_minimo=1, stock_inicial=10))
        self.srv.crear_producto(producto(codigo="B", precio=1, stock_minimo=1))
        self.mover(a["id"], "SALIDA", 4)
        r = self.srv.resumen()
        self.assertEqual((r["productos"], r["unidades"], r["valor"], r["agotados"]), (2, 6, 12.0, 1))
        self.assertEqual(r["hoy"], {"movimientos": 2, "unidades_entrada": 10, "unidades_salida": 4})

    def test_csv_neutraliza_formulas(self):
        self.srv.crear_producto(producto(codigo="F", nombre="=HYPERLINK(\"http://x\")"))
        csv = self.srv.exportar_existencias_csv()
        self.assertTrue(csv.startswith("﻿Código;"))
        self.assertIn("'=HYPERLINK", csv)

    # ---------------------------------------------------------- base de datos

    def test_la_bd_impide_stock_negativo_aunque_falle_la_aplicacion(self):
        p = self.srv.crear_producto(producto())
        with self.assertRaises(SBDError):
            self.conn.ejecutar("actualizar productos poner stock_actual = -1 donde id = ?", [p["id"]])

    def test_la_bd_rechaza_movimientos_incoherentes(self):
        p = self.srv.crear_producto(producto(stock_inicial=5))
        incoherentes = [
            ("SALIDA", 3, 5, 8),     # una salida con cantidad positiva
            ("ENTRADA", 3, 5, 9),    # el saldo no es anterior + cantidad
            ("REGALO", 1, 5, 6),     # tipo que no existe
        ]
        for tipo, cantidad, anterior, resultante in incoherentes:
            with self.subTest(tipo=tipo), self.assertRaises(SBDError):
                self.conn.ejecutar(
                    "insertar en movimientos { producto_id: ?, tipo: ?, cantidad: ?, stock_anterior: ?, stock_resultante: ? }",
                    [p["id"], tipo, cantidad, anterior, resultante],
                )

    def test_clave_ajena_activa(self):
        with self.assertRaises(SBDError):
            self.conn.ejecutar(
                'insertar en movimientos { producto_id: 12345, tipo: "ENTRADA", cantidad: 1, stock_anterior: 0, stock_resultante: 1 }'
            )

    def test_una_orden_que_falla_en_una_transaccion_no_deja_nada(self):
        p = self.srv.crear_producto(producto(stock_inicial=2))
        with self.assertRaises(SBDError):
            with self.conn.transaccion():
                self.conn.ejecutar("actualizar productos poner stock_actual = 50 donde id = ?", [p["id"]])
                self.conn.ejecutar("actualizar productos poner stock_actual = -1 donde id = ?", [p["id"]])
        self.assertEqual(self.srv.obtener_producto(p["id"])["stock_actual"], 2)


class CuentasTest(ConSBD):
    def setUp(self):
        super().setUp()
        self.cuentas = CuentasServicio(self.conn)
        self.cuentas.crear_usuario("ana", "Ana Gil", "contraseña-larga", "admin")
        cuentas._fallos.clear()

    def test_contrasena_cifrada_con_sal(self):
        guardado = self.conn.valor("buscar usuarios mostrar hash_contrasena")
        self.assertNotIn("contraseña-larga", guardado)
        self.assertTrue(guardado.startswith("pbkdf2_sha256$"))
        self.assertNotEqual(seguridad.cifrar_contrasena("x"), seguridad.cifrar_contrasena("x"))

    def test_inicio_y_cierre_de_sesion(self):
        token, usuario = self.cuentas.iniciar_sesion({"usuario": "ANA", "contrasena": "contraseña-larga"})
        self.assertEqual(usuario["rol"], "admin")
        self.assertEqual(self.cuentas.usuario_de_sesion(token)["nombre"], "Ana Gil")
        # En la BD solo está la huella del token
        self.assertIsNone(self.conn.una("buscar sesiones donde token_hash = ?", [token]))
        self.cuentas.cerrar_sesion(token)
        self.assertIsNone(self.cuentas.usuario_de_sesion(token))

    def test_credenciales_incorrectas_mismo_mensaje(self):
        for datos in ({"usuario": "ana", "contrasena": "mala"}, {"usuario": "nadie", "contrasena": "x"}):
            with self.subTest(datos=datos), self.assertRaises(NoAutorizado) as ctx:
                self.cuentas.iniciar_sesion(datos)
            self.assertEqual(ctx.exception.mensaje, "Usuario o contraseña incorrectos")

    def test_bloqueo_tras_varios_fallos(self):
        for _ in range(cuentas.MAX_FALLOS):
            with self.assertRaises(NoAutorizado):
                self.cuentas.iniciar_sesion({"usuario": "ana", "contrasena": "mala"})
        with self.assertRaises(DemasiadosIntentos):
            self.cuentas.iniciar_sesion({"usuario": "ana", "contrasena": "contraseña-larga"})

    def test_sesion_caducada(self):
        token, _ = self.cuentas.iniciar_sesion({"usuario": "ana", "contrasena": "contraseña-larga"})
        self.conn.ejecutar("actualizar sesiones poner expira_en = 2000-01-01 00:00 todas")
        self.assertIsNone(self.cuentas.usuario_de_sesion(token))

    def test_validaciones_de_usuario(self):
        for usuario, contrasena in [("ab", "contraseña-larga"), ("con espacio", "contraseña-larga"), ("pepe", "corta")]:
            with self.subTest(usuario=usuario), self.assertRaises(ErrorValidacion):
                self.cuentas.crear_usuario(usuario, "Pepe", contrasena)
        with self.assertRaises(Conflicto):
            self.cuentas.crear_usuario("ANA", "Otra Ana", "contraseña-larga")

    def test_movimiento_guarda_quien_lo_registra(self):
        token, usuario = self.cuentas.iniciar_sesion({"usuario": "ana", "contrasena": "contraseña-larga"})
        srv = InventarioServicio(self.conn)
        p = srv.crear_producto(producto(stock_inicial=5), usuario_id=usuario["id"])
        m = srv.registrar_movimiento({"producto_id": p["id"], "tipo": "SALIDA", "cantidad": 2}, usuario_id=usuario["id"])
        self.assertEqual(m["usuario"], "Ana Gil")
        self.assertTrue(all(x["usuario"] == "Ana Gil" for x in srv.listar_movimientos({"producto_id": p["id"]})))


class MigracionYEjemploTest(unittest.TestCase):
    def test_migra_una_base_de_la_version_1_sin_perder_datos(self):
        with tempfile.TemporaryDirectory() as carpeta:
            bd = BaseDatos(carpeta)
            bd._servidor.crear("inventario")
            with bd.conexion() as conn:
                numero, ruta = migraciones()[0]
                conn.ejecutar(ruta.read_text())
                conn.ejecutar('insertar en ajustes { clave: "version_esquema", valor: "1" }')
                conn.ejecutar('insertar en productos { codigo: "V1-1", nombre: "Antiguo", stock_actual: 3 }')
                conn.ejecutar('insertar en movimientos { producto_id: 1, tipo: "ENTRADA", cantidad: 3, stock_anterior: 0, stock_resultante: 3 }')
            bd.preparar()
            with bd.conexion() as conn:
                self.assertEqual(version_actual(conn), VERSION_ESQUEMA)
                fila = conn.una("buscar movimientos mostrar usuario_id, cantidad")
                self.assertEqual((fila["usuario_id"], fila["cantidad"]), (None, 3))
                self.assertIn("usuarios", conn.tablas())
            bd.preparar()  # volver a preparar no hace nada
            bd.cerrar()

    def test_material_de_ejemplo_coherente(self):
        with tempfile.TemporaryDirectory() as carpeta:
            bd = BaseDatos(carpeta)
            resumen = cargar_demo(bd)
            self.assertEqual(resumen["referencias"], 28)
            self.assertIsNone(cargar_demo(bd))  # solo se carga en una base vacía
            with bd.conexion() as conn:
                srv = InventarioServicio(conn)
                self.assertEqual(srv.movimientos.descuadres(), [])
                self.assertEqual({p["estado"] for p in srv.listar_productos()}, {"OK", "BAJO", "AGOTADO"})
                self.assertTrue(CuentasServicio(conn).datos_de_ejemplo())
            bd.cerrar()

    def test_los_datos_sobreviven_al_reinicio(self):
        with tempfile.TemporaryDirectory() as carpeta:
            bd = BaseDatos(carpeta)
            bd.preparar()
            with bd.conexion() as conn:
                InventarioServicio(conn).crear_producto(producto(codigo="PERS-1", stock_inicial=4))
            bd.cerrar()
            otra = BaseDatos(carpeta)  # como si se volviera a arrancar el programa
            otra.preparar()
            with otra.conexion() as conn:
                self.assertEqual(InventarioServicio(conn).listar_productos()[0]["stock_actual"], 4)
            otra.cerrar()


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.bd = BaseDatos(cls.dir.name)
        cls.servidor = crear_servidor("127.0.0.1", 0, cls.bd)
        with cls.bd.conexion() as conn:
            CuentasServicio(conn).crear_usuario("jefa", "Jefa de almacén", "clave-segura-1", "admin")
            CuentasServicio(conn).crear_usuario("mozo", "Mozo de almacén", "clave-segura-2", "operario")
        cls.url = f"http://127.0.0.1:{cls.servidor.server_port}"
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.bd.cerrar()
        cls.dir.cleanup()

    def setUp(self):
        cuentas._fallos.clear()
        self.navegador = self.nuevo_navegador()
        self.entrar(self.navegador, "jefa", "clave-segura-1")

    @staticmethod
    def nuevo_navegador():
        class SinRedirecciones(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(), SinRedirecciones())

    def entrar(self, navegador, usuario, contrasena):
        estado, datos = self.pedir("POST", "/api/sesion", {"usuario": usuario, "contrasena": contrasena}, navegador)
        self.assertEqual(estado, 200, datos)

    def pedir(self, metodo, ruta, cuerpo=None, navegador=None, tipo="application/json"):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        peticion = urllib.request.Request(self.url + ruta, data=datos, method=metodo, headers={"Content-Type": tipo})
        try:
            with (navegador or self.navegador).open(peticion) as r:
                contenido = r.read()
                return r.status, json.loads(contenido) if contenido and "json" in r.headers["Content-Type"] else contenido
        except urllib.error.HTTPError as error:
            contenido = error.read()
            return error.code, json.loads(contenido) if "json" in (error.headers["Content-Type"] or "") else contenido

    def test_flujo_completo(self):
        estado, p = self.pedir("POST", "/api/productos", producto(codigo="API-1", stock_inicial=8))
        self.assertEqual(estado, 201)

        estado, m = self.pedir("POST", "/api/movimientos", {"producto_id": p["id"], "tipo": "SALIDA", "cantidad": 3})
        self.assertEqual((estado, m["stock_resultante"], m["usuario"]), (201, 5, "Jefa de almacén"))

        estado, error = self.pedir("POST", "/api/movimientos", {"producto_id": p["id"], "tipo": "SALIDA", "cantidad": 6})
        self.assertEqual(estado, 409)
        self.assertIn("Stock insuficiente", error["error"])

        estado, lista = self.pedir("GET", "/api/productos?q=api-1")
        self.assertEqual((estado, lista[0]["stock_actual"]), (200, 5))

        estado, _ = self.pedir("DELETE", f"/api/productos/{p['id']}")
        self.assertEqual(estado, 204)

    def test_sin_sesion_no_hay_api(self):
        anonimo = self.nuevo_navegador()
        self.assertEqual(self.pedir("GET", "/api/productos", navegador=anonimo)[0], 401)
        estado, sesion = self.pedir("GET", "/api/sesion", navegador=anonimo)
        self.assertEqual((estado, sesion["usuario"]), (200, None))

    def test_operario_no_gestiona_referencias(self):
        operario = self.nuevo_navegador()
        self.entrar(operario, "mozo", "clave-segura-2")
        self.assertEqual(self.pedir("POST", "/api/productos", producto(codigo="OP-1"), operario)[0], 403)
        self.assertEqual(self.pedir("GET", "/api/productos", navegador=operario)[0], 200)

    def test_cerrar_sesion(self):
        navegador = self.nuevo_navegador()
        self.entrar(navegador, "mozo", "clave-segura-2")
        self.assertEqual(self.pedir("DELETE", "/api/sesion", navegador=navegador)[0], 204)
        self.assertEqual(self.pedir("GET", "/api/resumen", navegador=navegador)[0], 401)

    def test_escrituras_solo_en_json(self):
        estado, _ = self.pedir("POST", "/api/movimientos", {"producto_id": 1}, tipo="text/plain")
        self.assertEqual(estado, 415)

    def test_cookie_de_sesion_segura(self):
        peticion = urllib.request.Request(
            self.url + "/api/sesion", method="POST", headers={"Content-Type": "application/json"},
            data=json.dumps({"usuario": "jefa", "contrasena": "clave-segura-1"}).encode(),
        )
        with urllib.request.urlopen(peticion) as r:
            cookie = r.headers["Set-Cookie"]
        for atributo in ("HttpOnly", "SameSite=Strict", "Path=/"):
            self.assertIn(atributo, cookie)

    def test_errores_http(self):
        self.assertEqual(self.pedir("GET", "/api/productos/999999")[0], 404)
        self.assertEqual(self.pedir("GET", "/api/no-existe")[0], 404)
        self.assertEqual(self.pedir("PATCH", "/api/productos")[0], 501)  # método no implementado
        self.assertEqual(self.pedir("DELETE", "/api/productos")[0], 405)
        estado, error = self.pedir("POST", "/api/productos", {"nombre": "Sin código"})
        self.assertEqual((estado, error["campo"]), (400, "codigo"))

    def test_paginas_y_proteccion_de_rutas(self):
        anonimo = self.nuevo_navegador()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            anonimo.open(self.url + "/")
        self.assertEqual((ctx.exception.code, ctx.exception.headers["Location"]), (302, "/login.html"))
        with anonimo.open(self.url + "/login.html") as r:
            self.assertIn("Control de acceso", r.read().decode())
        with self.navegador.open(self.url + "/") as r:
            self.assertIn("<title>Almacén</title>", r.read().decode())
        for ruta in ("/../inventario/servicio.py", "/%2e%2e/app.py", "/no-existe.css"):
            with self.subTest(ruta=ruta), self.assertRaises(urllib.error.HTTPError) as ctx:
                self.navegador.open(self.url + ruta)
            self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
