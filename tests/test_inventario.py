"""Pruebas del gestor de inventario: reglas de negocio, base de datos SBD y API HTTP.

    python -m unittest discover -s tests -v
"""

import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest import mock

from inventario import cuentas, seguridad
from inventario.api import crear_servidor
from inventario.bd import VERSION_ESQUEMA, BaseDatos, SBDError, migraciones, version_actual
from inventario.cuentas import CuentasServicio
from app import FICHERO_CREDENCIALES, preparar_datos
from inventario import demo
from inventario.demo import USUARIOS_EJEMPLO, cargar_demo
from inventario.errores import Conflicto, DemasiadosIntentos, ErrorValidacion, NoAutorizado, NoEncontrado
from inventario.movimiento_dao import MovimientoDAO
from inventario.servicio import MOTIVOS_DEMO, InventarioServicio

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

    def test_limite_por_ip_aunque_cambie_el_usuario(self):
        for n in range(cuentas.MAX_FALLOS_IP):
            with self.assertRaises(NoAutorizado):
                self.cuentas.iniciar_sesion({"usuario": f"nadie{n}", "contrasena": "x"}, ip="203.0.113.9")
        with self.assertRaises(DemasiadosIntentos):
            self.cuentas.iniciar_sesion({"usuario": "ana", "contrasena": "contraseña-larga"}, ip="203.0.113.9")
        # Desde otra dirección se sigue pudiendo entrar
        self.cuentas.iniciar_sesion({"usuario": "ana", "contrasena": "contraseña-larga"}, ip="203.0.113.10")

    def test_los_fallos_antiguos_caducan(self):
        for _ in range(cuentas.MAX_FALLOS - 1):
            with self.assertRaises(NoAutorizado):
                self.cuentas.iniciar_sesion({"usuario": "ana", "contrasena": "mala"})
        fallos, desde = cuentas._fallos["usuario:ana"]
        cuentas._fallos["usuario:ana"] = (fallos, desde - cuentas.BLOQUEO_SEGUNDOS - 1)
        with self.assertRaises(NoAutorizado):  # este cuenta como el primero, no como el quinto
            self.cuentas.iniciar_sesion({"usuario": "ana", "contrasena": "mala"})
        self.assertEqual(cuentas._fallos["usuario:ana"][0], 1)
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


class ModoPublicoTest(unittest.TestCase):
    """--publico: detrás de un proxy con HTTPS, en internet."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.bd = BaseDatos(cls.dir.name)
        cls.servidor = crear_servidor("127.0.0.1", 0, cls.bd, publico=True)
        with redirect_stdout(io.StringIO()) as cls.salida:
            preparar_datos(cls.bd, con_ejemplos=True, publico=True)
        cls.url = f"http://127.0.0.1:{cls.servidor.server_port}"
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.ruta_credenciales = Path(cls.dir.name) / FICHERO_CREDENCIALES
        cls.credenciales = dict(linea.split() for linea in cls.ruta_credenciales.read_text().splitlines())

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.bd.cerrar()
        cls.dir.cleanup()

    def setUp(self):
        cuentas._fallos.clear()

    def entrar(self, usuario, contrasena, cabeceras=None):
        peticion = urllib.request.Request(
            self.url + "/api/sesion", method="POST",
            headers={"Content-Type": "application/json", **(cabeceras or {})},
            data=json.dumps({"usuario": usuario, "contrasena": contrasena}).encode(),
        )
        try:
            with urllib.request.urlopen(peticion) as r:
                return r.status, r.headers["Set-Cookie"]
        except urllib.error.HTTPError as error:
            return error.code, None

    def test_la_pantalla_de_acceso_no_ensena_usuarios(self):
        with urllib.request.urlopen(self.url + "/api/sesion") as r:
            self.assertEqual(json.loads(r.read())["usuarios_ejemplo"], [])

    def test_sin_demostracion_no_existe_el_visitante(self):
        self.assertEqual(self.entrar(cuentas.USUARIO_DEMO, cuentas.CONTRASENA_DEMO)[0], 401)

    def test_las_contrasenas_de_ejemplo_no_valen(self):
        for usuario, _, contrasena, _ in USUARIOS_EJEMPLO:
            self.assertEqual(self.entrar(usuario, contrasena)[0], 401)

    def test_las_contrasenas_generadas_si_y_la_cookie_es_secure(self):
        estado, cookie = self.entrar("laura", self.credenciales["laura"])
        self.assertEqual(estado, 200)
        self.assertIn("Secure", cookie)

    def test_las_contrasenas_no_salen_por_la_consola_y_el_fichero_es_privado(self):
        for contrasena in self.credenciales.values():
            self.assertNotIn(contrasena, self.salida.getvalue())
        self.assertEqual(self.ruta_credenciales.stat().st_mode & 0o777, 0o600)

    def test_la_ip_es_la_que_anade_el_proxy_no_la_que_escribe_el_cliente(self):
        for n in range(cuentas.MAX_FALLOS_IP):
            # El cliente cambia su X-Forwarded-For; el proxy añade siempre la real al final
            cabecera = {"X-Forwarded-For": f"10.0.0.{n}, 198.51.100.7"}
            self.assertEqual(self.entrar(f"nadie{n}", "x", cabecera)[0], 401)
        self.assertEqual(self.entrar("laura", self.credenciales["laura"], {"X-Forwarded-For": "1.1.1.1, 198.51.100.7"})[0], 429)
        self.assertEqual(self.entrar("laura", self.credenciales["laura"], {"X-Forwarded-For": "198.51.100.8"})[0], 200)


class DemostracionTest(unittest.TestCase):
    """--demostracion: usuario visitante a la vista, con cambios limitados y datos restablecidos cada noche."""

    def setUp(self):
        cuentas._fallos.clear()
        cuentas._cambios_demo.clear()
        self.dir = tempfile.TemporaryDirectory()
        self.bd = BaseDatos(self.dir.name)
        self.servidor = crear_servidor("127.0.0.1", 0, self.bd, publico=True, demostracion=True)
        with redirect_stdout(io.StringIO()):
            preparar_datos(self.bd, con_ejemplos=True, publico=True)
        with self.bd.conexion() as conexion:
            CuentasServicio(conexion).asegurar_usuario_demo()
            CuentasServicio(conexion).asegurar_usuario_demo()  # en cada arranque: no debe fallar
        self.url = f"http://127.0.0.1:{self.servidor.server_port}"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.cookie = self.entrar()[1]
        self.producto = self.pedir("GET", "/api/productos")[1][0]

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.bd.cerrar()
        self.dir.cleanup()

    def pedir(self, metodo, ruta, cuerpo=None, cabeceras=None):
        peticion = urllib.request.Request(
            self.url + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
            headers={"Content-Type": "application/json", "Cookie": getattr(self, "cookie", "") or "", **(cabeceras or {})},
        )
        try:
            with urllib.request.urlopen(peticion) as r:
                contenido = r.read()
                self.ultima_cookie = r.headers["Set-Cookie"]
                return r.status, json.loads(contenido) if contenido else None
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def entrar(self, contrasena=cuentas.CONTRASENA_DEMO, cabeceras=None):
        estado, cuerpo = self.pedir("POST", "/api/sesion", {"usuario": cuentas.USUARIO_DEMO, "contrasena": contrasena}, cabeceras)
        return estado, self.ultima_cookie.split(";")[0] if estado == 200 else None, cuerpo

    def movimiento(self, **campos):
        return {"producto_id": self.producto["id"], "tipo": "ENTRADA", "cantidad": 1, "motivo": "Venta", **campos}

    def test_la_pantalla_de_acceso_ensena_solo_al_visitante(self):
        self.cookie = None
        ejemplos = self.pedir("GET", "/api/sesion")[1]["usuarios_ejemplo"]
        self.assertEqual([c["usuario"] for c in ejemplos], [cuentas.USUARIO_DEMO])
        self.assertTrue(ejemplos[0]["demo"])

    def test_con_sesion_no_se_ofrece_ningun_usuario(self):
        estado, sesion = self.pedir("GET", "/api/sesion")
        self.assertEqual(estado, 200)
        self.assertTrue(sesion["usuario"]["demo"])
        self.assertEqual(sesion["usuarios_ejemplo"], [])

    def test_el_visitante_no_toca_las_referencias(self):
        ruta = f"/api/productos/{self.producto['id']}"
        self.assertEqual(self.pedir("POST", "/api/productos", {"codigo": "X-1", "nombre": "X", "precio": "1"})[0], 403)
        self.assertEqual(self.pedir("PUT", ruta, {"nombre": "Otra cosa"})[0], 403)
        self.assertEqual(self.pedir("DELETE", ruta)[0], 403)

    def test_el_visitante_registra_movimientos_con_los_conceptos_propuestos(self):
        for motivo in sorted(MOTIVOS_DEMO):
            self.assertEqual(self.pedir("POST", "/api/movimientos", self.movimiento(motivo=motivo))[0], 201, motivo)

    def test_los_conceptos_son_los_que_propone_el_albaran(self):
        app_js = (Path(__file__).parent.parent / "static" / "js" / "app.js").read_text(encoding="utf-8")
        for motivo in MOTIVOS_DEMO - {""}:
            self.assertIn(f"'{motivo}'", app_js)

    def test_el_visitante_no_escribe_texto_libre(self):
        estado, error = self.pedir("POST", "/api/movimientos", self.movimiento(motivo="Visita mi web"))
        self.assertEqual(estado, 400)
        self.assertEqual(error["campo"], "motivo")

    def test_el_visitante_tiene_un_tope_de_cantidad(self):
        self.assertEqual(self.pedir("POST", "/api/movimientos", self.movimiento(cantidad=500))[0], 201)
        estado, error = self.pedir("POST", "/api/movimientos", self.movimiento(cantidad=501))
        self.assertEqual(estado, 400)
        self.assertEqual(error["campo"], "cantidad")

    def test_el_visitante_tiene_un_limite_de_cambios(self):
        cabeceras = {"X-Forwarded-For": "198.51.100.20"}
        for _ in range(cuentas.MAX_CAMBIOS_DEMO_IP):
            self.assertEqual(self.pedir("POST", "/api/movimientos", self.movimiento(), cabeceras)[0], 201)
        self.assertEqual(self.pedir("POST", "/api/movimientos", self.movimiento(), cabeceras)[0], 429)
        # Otra persona sigue pudiendo
        self.assertEqual(self.pedir("POST", "/api/movimientos", self.movimiento(), {"X-Forwarded-For": "198.51.100.21"})[0], 201)

    def test_entrar_una_y_otra_vez_tambien_cuenta(self):
        cabeceras = {"X-Forwarded-For": "198.51.100.30"}
        for _ in range(cuentas.MAX_CAMBIOS_DEMO_IP):
            self.assertEqual(self.entrar(cabeceras=cabeceras)[0], 200)
        self.assertEqual(self.entrar(cabeceras=cabeceras)[0], 429)

    def test_nadie_bloquea_al_visitante_fallando_su_contrasena(self):
        for numero in range(cuentas.MAX_FALLOS + 1):
            self.assertEqual(self.entrar("mala", {"X-Forwarded-For": f"198.51.100.{numero + 40}"})[0], 401)
        self.assertEqual(self.entrar(cabeceras={"X-Forwarded-For": "198.51.100.99"})[0], 200)

    def test_restablecer_deja_el_material_como_nuevo_y_conserva_usuarios_y_sesiones(self):
        with self.bd.conexion() as conexion:
            inventario = InventarioServicio(conexion)
            referencias = len(inventario.listar_productos())
            movimientos = conexion.valor("buscar movimientos mostrar contar()")
        self.assertEqual(self.pedir("POST", "/api/movimientos", self.movimiento(cantidad=500))[0], 201)

        demo.restablecer_demo(self.bd)

        with self.bd.conexion() as conexion:
            inventario = InventarioServicio(conexion)
            self.assertEqual(len(inventario.listar_productos()), referencias)
            self.assertEqual(conexion.valor("buscar movimientos mostrar contar()"), movimientos)
            self.assertEqual(MovimientoDAO(conexion).descuadres(), [])
        # La misma sesión sigue valiendo; laura y diego siguen existiendo
        self.assertEqual(self.pedir("GET", "/api/sesion")[1]["usuario"]["usuario"], cuentas.USUARIO_DEMO)
        with self.bd.conexion() as conexion:
            for usuario, *_ in USUARIOS_EJEMPLO:
                self.assertIsNotNone(CuentasServicio(conexion).usuarios.por_usuario(usuario))

    def test_restablecer_es_todo_o_nada(self):
        with self.bd.conexion() as conexion:
            antes = conexion.valor("buscar movimientos mostrar contar()")
        with mock.patch.object(demo, "_cargar_referencias", side_effect=RuntimeError("a medias")):
            with self.assertRaises(RuntimeError):
                demo.restablecer_demo(self.bd)
        with self.bd.conexion() as conexion:
            self.assertEqual(conexion.valor("buscar movimientos mostrar contar()"), antes)

    def test_restablecer_no_engorda_la_auditoria(self):
        carpeta = Path(self.dir.name) / ".auditoria"
        tamano = lambda: sum(f.stat().st_size for f in carpeta.rglob("*") if f.is_file())
        antes = tamano()
        demo.restablecer_demo(self.bd)
        self.assertLess(tamano() - antes, 2_000)

    def test_se_restablece_una_vez_al_dia_a_partir_de_la_hora(self):
        hoy = datetime.now().replace(hour=demo.HORA_RESTABLECIMIENTO, minute=0)
        self.assertFalse(demo.toca_restablecer(self.bd, hoy.replace(hour=demo.HORA_RESTABLECIMIENTO - 1)))
        self.assertTrue(demo.toca_restablecer(self.bd, hoy))
        demo.restablecer_demo(self.bd)
        self.assertFalse(demo.toca_restablecer(self.bd, hoy))


if __name__ == "__main__":
    unittest.main()
