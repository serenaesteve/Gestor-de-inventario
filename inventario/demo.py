"""Material de ejemplo: referencias, usuarios y ~45 días de historial de movimientos.

Se carga solo cuando la base de datos está vacía. El historial se simula con una
semilla fija, así que siempre sale el mismo almacén, con fechas relativas a hoy.
"""

import random
from datetime import datetime, timedelta

from .bd import texto_fecha
from .cuentas import CuentasServicio
from .servicio import InventarioServicio

DIAS_DE_HISTORIAL = 45

# usuario, nombre, contraseña, rol. El aviso de la pantalla de acceso los muestra.
USUARIOS_EJEMPLO = [
    ("laura", "Laura Méndez", "almacen2026", "admin"),
    ("diego", "Diego Ruiz", "almacen2026", "operario"),
]

# (código, nombre, categoría, precio €, stock mínimo, descripción)
REFERENCIAS = [
    ("PAP-001", "Folios A4 80 g (paquete 500)", "Papelería", 4.95, 20, "Papel blanco multifunción"),
    ("PAP-002", "Bolígrafo azul (caja 50)", "Papelería", 9.90, 10, "Punta media 1 mm"),
    ("PAP-003", "Archivador de palanca", "Papelería", 2.80, 15, "Lomo ancho, tamaño folio"),
    ("PAP-004", "Cuaderno espiral A5", "Papelería", 1.75, 30, "80 hojas cuadriculadas"),
    ("PAP-005", "Notas adhesivas 76×76 (12 blocs)", "Papelería", 6.40, 12, "Amarillo"),
    ("PAP-006", "Grapas 26/6 (caja 5000)", "Papelería", 1.20, 25, ""),
    ("INF-001", "Ratón inalámbrico", "Informática", 12.90, 8, "Receptor USB, 2,4 GHz"),
    ("INF-002", "Teclado USB español", "Informática", 15.50, 6, "Distribución ES con Ñ"),
    ("INF-003", "Cable HDMI 2 m", "Informática", 6.75, 10, "4K a 60 Hz"),
    ("INF-004", "Memoria USB 64 GB", "Informática", 9.99, 12, "USB 3.1"),
    ("INF-005", "Monitor 24\" Full HD", "Informática", 129.00, 3, "Panel IPS, HDMI y DisplayPort"),
    ("INF-006", "Auriculares con micrófono", "Informática", 18.40, 5, "Conector USB"),
    ("LIM-001", "Gel hidroalcohólico 500 ml", "Limpieza", 3.20, 20, ""),
    ("LIM-002", "Bayeta microfibra (pack 10)", "Limpieza", 7.90, 10, ""),
    ("LIM-003", "Papel higiénico industrial (12 rollos)", "Limpieza", 14.50, 8, ""),
    ("LIM-004", "Desinfectante multiusos 1 L", "Limpieza", 2.65, 15, ""),
    ("EMB-001", "Cinta de embalar marrón 48 mm", "Embalaje", 1.85, 30, "66 m por rollo"),
    ("EMB-002", "Caja de cartón 40×30×30", "Embalaje", 1.10, 50, "Canal doble"),
    ("EMB-003", "Film estirable 23 µm", "Embalaje", 9.80, 10, "Bobina manual de 300 m"),
    ("EMB-004", "Etiquetas adhesivas 100×150 (rollo)", "Embalaje", 7.40, 8, "500 etiquetas térmicas"),
    ("FER-001", "Tornillo DIN 933 M6×20 (caja 100)", "Ferretería", 6.40, 10, "Acero zincado"),
    ("FER-002", "Taco de nailon 8 mm (caja 100)", "Ferretería", 3.90, 10, ""),
    ("FER-003", "Cúter profesional 18 mm", "Ferretería", 4.75, 6, "Cuchilla retráctil"),
    ("FER-004", "Guantes de trabajo T9 (par)", "Ferretería", 2.30, 24, "Nitrilo"),
    ("MOB-001", "Silla de oficina ergonómica", "Mobiliario", 149.00, 2, "Respaldo de malla"),
    ("MOB-002", "Lámpara de escritorio LED", "Mobiliario", 24.90, 4, "Brazo articulado"),
    ("MOB-003", "Reposapiés regulable", "Mobiliario", 21.50, 3, ""),
    ("MOB-004", "Bandeja portadocumentos (3 niveles)", "Mobiliario", 11.20, 5, ""),
]

# Para que el ejemplo enseñe todos los estados de stock
TERMINAN_AGOTADAS = {"INF-002", "EMB-004", "MOB-003"}
TERMINAN_BAJO_MINIMO = {"PAP-002", "INF-004", "LIM-003", "EMB-001", "FER-004"}

MOTIVOS_SALIDA = [("Venta", 6), ("Pedido oficina central", 2), ("Consumo interno", 2), ("Merma o rotura", 1)]
MOTIVOS_ENTRADA = [("Compra a proveedor", 5), ("Devolución de cliente", 1)]


def _elegir(azar, opciones):
    textos, pesos = zip(*opciones)
    return azar.choices(textos, weights=pesos)[0]


def _historial(azar, minimo, ahora, codigo):
    """Simula los movimientos de una referencia: [(fecha, tipo, cantidad, motivo, quien)].

    Las horas solo avanzan, así que el orden de la lista es el orden real y el stock
    simulado coincide con el que calculará la base de datos al registrarlos.
    """
    inicio = (ahora - timedelta(days=DIAS_DE_HISTORIAL)).replace(hour=7, minute=30, second=0, microsecond=0)
    stock = azar.randint(int(minimo * 1.8) + 3, minimo * 4 + 6)
    eventos = [(inicio + timedelta(minutes=azar.randint(0, 50)), "ENTRADA", stock, "Stock inicial", "laura")]

    for dia in range(1, DIAS_DE_HISTORIAL):
        reloj = inicio + timedelta(days=dia)
        if reloj.weekday() >= 5:  # el almacén no abre en fin de semana
            continue
        if azar.random() < 0.45 and stock > 0:
            reloj += timedelta(minutes=azar.randint(30, 240))
            cantidad = min(stock, azar.randint(1, max(2, minimo // 2 + 2)))
            stock -= cantidad
            eventos.append((reloj, "SALIDA", cantidad, _elegir(azar, MOTIVOS_SALIDA), "diego"))
        if stock <= minimo and azar.random() < 0.6:
            reloj += timedelta(minutes=azar.randint(20, 180))
            cantidad = minimo * 3 - stock + azar.randint(0, minimo)
            stock += cantidad
            eventos.append((reloj, "ENTRADA", cantidad, _elegir(azar, MOTIVOS_ENTRADA), "laura"))
        if azar.random() < 0.025 and stock > 3:
            reloj += timedelta(minutes=azar.randint(15, 90))
            contado = stock - azar.randint(1, 2)
            eventos.append((reloj, "AJUSTE", contado, "Inventario físico", "laura"))
            stock = contado

    # Hoy: un único movimiento que deja la referencia en el estado que queremos enseñar
    hoy = max(eventos[-1][0] + timedelta(minutes=5), ahora - timedelta(minutes=azar.randint(10, 300)))
    if codigo in TERMINAN_AGOTADAS and stock > 0:
        eventos.append((hoy, "SALIDA", stock, "Venta", "diego"))
    elif codigo in TERMINAN_BAJO_MINIMO:
        objetivo = azar.randint(1, minimo)
        if stock > objetivo:
            eventos.append((hoy, "SALIDA", stock - objetivo, "Pedido oficina central", "diego"))
        elif stock < objetivo:
            eventos.append((hoy, "ENTRADA", objetivo - stock, "Compra a proveedor", "laura"))
    elif stock <= minimo:
        eventos.append((hoy, "ENTRADA", minimo * 3 - stock, "Compra a proveedor", "laura"))
    else:
        suerte = azar.random()
        if suerte < 0.25:
            eventos.append((hoy, "SALIDA", azar.randint(1, max(1, stock - minimo - 1)), "Venta", "diego"))
        elif suerte < 0.45:
            eventos.append((hoy, "ENTRADA", minimo + azar.randint(0, minimo), "Compra a proveedor", "laura"))
    return eventos


def cargar_demo(bd, semilla=2026):
    """Carga el material de ejemplo si no hay ninguna referencia. Devuelve un resumen o None.

    `bd` es la BaseDatos del programa (SBD local o servidor).
    """
    bd.preparar()
    with bd.conexion("inventario · material de ejemplo") as conexion:
        inventario = InventarioServicio(conexion)
        if inventario.productos.contar():
            return None
        azar = random.Random(semilla)
        ahora = datetime.now().replace(microsecond=0)  # SBD guarda las fechas en hora local
        cuentas = CuentasServicio(conexion)

        ids_usuario = {}
        for usuario, nombre, contrasena, rol in USUARIOS_EJEMPLO:
            existente = cuentas.usuarios.por_usuario(usuario)
            ids_usuario[usuario] = existente["id"] if existente else cuentas.crear_usuario(usuario, nombre, contrasena, rol)["id"]

        movimientos = 0
        for codigo, nombre, categoria, precio, minimo, descripcion in REFERENCIAS:
            producto = inventario.crear_producto({
                "codigo": codigo, "nombre": nombre, "categoria": categoria,
                "precio": str(precio), "stock_minimo": minimo, "descripcion": descripcion,
            })
            eventos = _historial(azar, minimo, ahora, codigo)
            inventario.productos.fijar_creado_en(producto["id"], texto_fecha(eventos[0][0]))
            for fecha, tipo, cantidad, motivo, quien in eventos:
                inventario.importar_movimiento(
                    producto["id"], tipo, cantidad, motivo, fecha=texto_fecha(fecha), usuario_id=ids_usuario[quien]
                )
                movimientos += 1

        cuentas.marcar_datos_de_ejemplo()
        return {"referencias": len(REFERENCIAS), "movimientos": movimientos, "dias": DIAS_DE_HISTORIAL}
