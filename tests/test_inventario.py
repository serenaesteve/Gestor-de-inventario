"""Pruebas del gestor de inventario: reglas de negocio, base de datos y API HTTP.

    python -m unittest discover -s tests -v
"""

import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

from inventario import cuentas, seguridad
from inventario.api import crear_servidor
from inventario.conexion import VERSION_ESQUEMA, conectar, inicializar
from inventario.cuentas import CuentasServicio
from inventario.demo import cargar_demo
from inventario.errores import Conflicto, DemasiadosIntentos, ErrorValidacion, NoAutorizado, NoEncontrado
from inventario.servicio import InventarioServicio

# PBKDF2 con 600 000 iteraciones es lento a propósito; en los tests basta con pocas
seguridad.ITERACIONES = 1_000


def producto(**cambios):
    datos = {"codigo": "TST-001", "nombre": "Tornillo M6", "categoria": "Ferretería",
             "precio": "0,15", "stock_minimo": 100, "stock_inicial": 0}
    return {**datos, **cambios}


class ServicioTest(unittest.TestCase):
    def setUp(self):
        self.conn = conectar(":memory:")
        inicializar(self.conn)
        self.srv = InventarioServicio(self.conn)

    def tearDown(self):
        self.conn.close()

    def mover(self, producto_id, tipo, cantidad, motivo=""):
        return self.srv.registrar_movimiento(
            {"producto_id": producto_id, "tipo": tipo, "cantidad": cantidad, "motivo": motivo}
        )

    def suma_movimientos(self, producto_id):
        return self.conn.execute(
            "SELECT COALESCE(SUM(cantidad), 0) FROM movimientos WHERE producto_id = ?", (producto_id,)
        ).fetchone()[0]

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
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM movimientos").fetchone()[0], 0)

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
        guardado = self.conn.execute("SELECT precio_centimos FROM productos").fetchone()[0]
        self.assertEqual(guardado, 2000)

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
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE productos SET stock_actual = -1 WHERE id = ?", (p["id"],))

    def test_los_movimientos_son_inmutables(self):
        p = self.srv.crear_producto(producto(stock_inicial=1))
        for sql in ("UPDATE movimientos SET cantidad = 99", "DELETE FROM movimientos"):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.conn.execute(sql)
        self.assertEqual(self.suma_movimientos(p["id"]), 1)

    def test_clave_ajena_activa(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO movimientos (producto_id, tipo, cantidad, stock_anterior, stock_resultante)"
                " VALUES (12345, 'ENTRADA', 1, 0, 1)"
            )


class CuentasTest(unittest.TestCase):
    def setUp(self):
        self.conn = conectar(":memory:")
        inicializar(self.conn)
        self.cuentas = CuentasServicio(self.conn)
        self.cuentas.crear_usuario("ana", "Ana Gil", "contraseña-larga", "admin")
        cuentas._fallos.clear()

    def tearDown(self):
        self.conn.close()

    def test_contrasena_cifrada_con_sal(self):
        guardado = self.conn.execute("SELECT hash_contrasena FROM usuarios").fetchone()[0]
        self.assertNotIn("contraseña-larga", guardado)
        self.assertTrue(guardado.startswith("pbkdf2_sha256$"))
        self.assertNotEqual(seguridad.cifrar_contrasena("x"), seguridad.cifrar_contrasena("x"))

    def test_inicio_y_cierre_de_sesion(self):
        token, usuario = self.cuentas.iniciar_sesion({"usuario": "ANA", "contrasena": "contraseña-larga"})
        self.assertEqual(usuario["rol"], "admin")
        self.assertEqual(self.cuentas.usuario_de_sesion(token)["nombre"], "Ana Gil")
        # En la BD solo está la huella del token
        self.assertIsNone(self.conn.execute("SELECT 1 FROM sesiones WHERE token_hash = ?", (token,)).fetchone())
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
        self.conn.execute("UPDATE sesiones SET expira_en = '2000-01-01T00:00:00Z'")
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
    def test_migra_una_bd_de_la_version_1_sin_perder_datos(self):
        with tempfile.TemporaryDirectory() as directorio:
            ruta = str(Path(directorio) / "v1.db")
            conn = conectar(ruta)
            sql = (Path(__file__).resolve().parent.parent / "inventario/migraciones/001_inicial.sql").read_text()
            conn.executescript(f"BEGIN; {sql} PRAGMA user_version = 1; COMMIT;")
            conn.execute("INSERT INTO productos (codigo, nombre, stock_actual) VALUES ('V1-1', 'Antiguo', 3)")
            conn.execute("INSERT INTO movimientos (producto_id, tipo, cantidad, stock_anterior, stock_resultante) VALUES (1, 'ENTRADA', 3, 0, 3)")
            inicializar(conn)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], VERSION_ESQUEMA)
            fila = conn.execute("SELECT usuario_id, cantidad FROM movimientos").fetchone()
            self.assertEqual((fila["usuario_id"], fila["cantidad"]), (None, 3))
            inicializar(conn)  # volver a inicializar no hace nada
            conn.close()

    def test_material_de_ejemplo_coherente(self):
        with tempfile.TemporaryDirectory() as directorio:
            ruta = str(Path(directorio) / "ejemplo.db")
            resumen = cargar_demo(ruta)
            self.assertEqual(resumen["referencias"], 28)
            self.assertIsNone(cargar_demo(ruta))  # solo se carga en una BD vacía
            conn = conectar(ruta)
            descuadres = conn.execute(
                "SELECT COUNT(*) FROM productos p WHERE stock_actual <> "
                "(SELECT COALESCE(SUM(cantidad), 0) FROM movimientos WHERE producto_id = p.id)"
            ).fetchone()[0]
            self.assertEqual(descuadres, 0)
            estados = {r[0] for r in conn.execute("SELECT estado FROM v_existencias")}
            self.assertEqual(estados, {"OK", "BAJO", "AGOTADO"})
            self.assertTrue(CuentasServicio(conn).datos_de_ejemplo())
            conn.close()


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        ruta = str(Path(cls.dir.name) / "test.db")
        cls.servidor = crear_servidor("127.0.0.1", 0, ruta)
        with closing(conectar(ruta)) as conn:
            CuentasServicio(conn).crear_usuario("jefa", "Jefa de almacén", "clave-segura-1", "admin")
            CuentasServicio(conn).crear_usuario("mozo", "Mozo de almacén", "clave-segura-2", "operario")
        cls.url = f"http://127.0.0.1:{cls.servidor.server_port}"
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
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
