// Recorrido por el almacén: un mundo en maqueta por el que la cámara vuela al hacer scroll.
// Cinco islas (muelle → recepción → pasillos → expedición → Kardex) unidas por una sola
// curva de cámara continua: no hay cortes que disimular. El scroll solo mueve el tiempo.

import * as THREE from 'three';
import { RoundedBoxGeometry } from '/vendor/three/RoundedBoxGeometry.js';
import {
  PALETA, SANS, MONO, azar, lienzo, fuente, texturaDe, texturaHormigon, texturaCaja,
  texturaCintaSeguridad, texturaAgotado, texturaMuelle, dibujarEtiqueta, curvas, esperarFuentes,
} from './nave.js';
import { bajarCalidad, densidadPixeles, fusionarEstaticos, renderizadoPorSoftware, vigilarRendimiento } from './rendimiento3d.js';

const V = (x, y, z) => new THREE.Vector3(x, y, z);
const limitar = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const tramo = (v, desde, hasta) => limitar((v - desde) / (hasta - desde));
const suave = (k) => k * k * (3 - 2 * k);
const reducido = matchMedia('(prefers-reduced-motion: reduce)').matches;
// ?sin-inercia: la cámara sigue el scroll sin suavizado (útil para capturas y pruebas)
const sinInercia = reducido || new URLSearchParams(location.search).has('sin-inercia');
const movil = matchMedia('(max-width: 700px), (pointer: coarse)').matches;

/* ============================================================ Datos de la maqueta */

const MUNDO = V(-2, 0, -4);

const ESCENAS = [
  // giro: desde dónde se mira la isla · cerca: distancia del primer plano (1 = normal)
  { id: 'muelle', centro: V(-16, 0, 6), foco: V(-15.9, 1.2, 3.6), giro: 1.05, cerca: 1.35 },
  { id: 'recepcion', centro: V(-1, 0, 4), foco: V(-1, 1.05, 4.2), giro: 0.3, cerca: 1 },
  { id: 'pasillos', centro: V(14, 0, -4), foco: V(14, 1.0, -3.2), giro: 0.6, cerca: 1.2 },
  { id: 'expedicion', centro: V(4, 0, -18), foco: V(5.2, 1.1, -18), giro: -0.55, cerca: 1.6 },
  { id: 'kardex', centro: V(-13, 0, -16), foco: V(-12.6, 1.7, -16.4), giro: 0.35, cerca: 1.1 },
];

const PRODUCTOS_DEMO = [
  [{ codigo: 'PAP-001', nombre: 'Folios A4 80 g', stock_actual: 64, estado: 'OK', cajas: 14 },
   { codigo: 'PAP-002', nombre: 'Bolígrafo azul', stock_actual: 32, estado: 'BAJO', cajas: 6 },
   { codigo: 'PAP-003', nombre: 'Archivador de palanca', stock_actual: 18, estado: 'OK', cajas: 16 },
   { codigo: 'PAP-004', nombre: 'Grapadora metálica', stock_actual: 40, estado: 'OK', cajas: 12 }],
  [{ codigo: 'INF-001', nombre: 'Ratón inalámbrico', stock_actual: 9, estado: 'OK', cajas: 13 },
   { codigo: 'INF-002', nombre: 'Teclado USB', stock_actual: 0, estado: 'AGOTADO', cajas: 0, repone: 10 },
   { codigo: 'INF-003', nombre: 'Cable HDMI 2 m', stock_actual: 35, estado: 'OK', cajas: 18 },
   { codigo: 'INF-004', nombre: 'Memoria USB 64 GB', stock_actual: 4, estado: 'BAJO', cajas: 4 }],
  [{ codigo: 'ALM-001', nombre: 'Cinta de embalar', stock_actual: 12, estado: 'BAJO', cajas: 7 },
   { codigo: 'ALM-002', nombre: 'Caja de cartón 40×30', stock_actual: 120, estado: 'OK', cajas: 18 },
   { codigo: 'ALM-003', nombre: 'Etiquetas adhesivas', stock_actual: 0, estado: 'AGOTADO', cajas: 0 },
   { codigo: 'LIM-001', nombre: 'Gel hidroalcohólico', stock_actual: 40, estado: 'OK', cajas: 15 }],
];

const ASIENTOS_KARDEX = [
  ['02/10', 'Entrada · Stock inicial', 60, null, 60],
  ['05/10', 'Salida · Venta', null, 28, 32],
  ['09/10', 'Entrada · Compra', 40, null, 72],
  ['12/10', 'Salida · Pedido oficina', null, 16, 56],
  ['15/10', 'Recuento · Inventario', null, 2, 54],
  ['18/10', 'Salida · Venta', null, 22, 32],
  ['20/10', 'Entrada · Compra', 30, null, 62],
  ['22/10', 'Salida · Venta', null, 12, 50],
];

/* ============================================================ Texturas propias */

function texturaRayas(renderer, color = '#d8d6d0', fondo = '#c4c1ba') {
  const { c, ctx } = lienzo(64, 128);
  ctx.fillStyle = fondo;
  ctx.fillRect(0, 0, 64, 128);
  ctx.fillStyle = color;
  for (let y = 0; y < 128; y += 16) ctx.fillRect(0, y, 64, 11);
  return texturaDe(c, renderer);
}

function texturaRemolque(renderer) {
  const { c, ctx } = lienzo(1024, 384);
  ctx.fillStyle = '#efede7';
  ctx.fillRect(0, 0, 1024, 384);
  ctx.fillStyle = PALETA.senal;
  ctx.fillRect(0, 250, 1024, 46);
  ctx.fillStyle = PALETA.negro;
  ctx.fillRect(0, 296, 1024, 10);
  fuente(ctx, 900, 120, SANS, true);
  ctx.fillText('ALMACÉN', 60, 200);
  fuente(ctx, 600, 30, MONO);
  ctx.fillStyle = '#6b6860';
  ctx.fillText('LOGÍSTICA · LIBRO DE EXISTENCIAS', 64, 240);
  return texturaDe(c, renderer);
}

function texturaLineasDiscontinuas(renderer) {
  const { c, ctx } = lienzo(128, 16);
  ctx.clearRect(0, 0, 128, 16);
  ctx.fillStyle = PALETA.senal;
  ctx.fillRect(0, 0, 80, 16);
  const t = texturaDe(c, renderer);
  t.wrapS = THREE.RepeatWrapping;
  return t;
}

function texturaFlecha(renderer) {
  const { c, ctx } = lienzo(256, 256);
  ctx.fillStyle = '#ffffff';
  ctx.beginPath();
  ctx.moveTo(40, 100);
  ctx.lineTo(150, 100);
  ctx.lineTo(150, 50);
  ctx.lineTo(230, 128);
  ctx.lineTo(150, 206);
  ctx.lineTo(150, 156);
  ctx.lineTo(40, 156);
  ctx.closePath();
  ctx.fill();
  return texturaDe(c, renderer);
}

function texturaRotulo(renderer, texto, { color = PALETA.senal, ancho = 512, alto = 160 } = {}) {
  const { c, ctx } = lienzo(ancho, alto);
  fuente(ctx, 900, alto * 0.62, SANS, true);
  ctx.fillStyle = color;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(texto, ancho / 2, alto / 2);
  ctx.globalCompositeOperation = 'destination-out';
  for (let i = 0; i < 500; i++) {
    ctx.fillStyle = `rgba(0,0,0,${0.2 + azar(i + 900) * 0.5})`;
    ctx.fillRect(azar(i + 901) * ancho, azar(i + 902) * alto, 2 + azar(i + 903) * 5, 1 + azar(i + 904) * 2);
  }
  return texturaDe(c, renderer);
}

function dibujarAlbaran(ctx) {
  const W = 700;
  const H = 512;
  ctx.fillStyle = '#fbfaf6';
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = '#2f8a57';
  ctx.fillRect(0, 0, W, 16);
  ctx.fillStyle = '#2f8a57';
  fuente(ctx, 700, 20, MONO);
  ctx.fillText('LLEGA MERCANCÍA AL ALMACÉN', 40, 62);
  ctx.fillStyle = PALETA.negro;
  fuente(ctx, 900, 60, SANS, true);
  ctx.fillText('ALBARÁN DE ENTRADA', 40, 124);
  ctx.strokeStyle = '#9b978d';
  ctx.setLineDash([10, 8]);
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(30, 152);
  ctx.lineTo(W - 30, 152);
  ctx.stroke();
  ctx.setLineDash([]);
  const filas = [['PAP-001', 'Folios A4 80 g', '+80'], ['INF-003', 'Cable HDMI 2 m', '+25'], ['ALM-002', 'Caja de cartón', '+120'], ['LIM-002', 'Bayeta microfibra', '+75']];
  filas.forEach(([codigo, nombre, cantidad], i) => {
    const y = 214 + i * 66;
    ctx.strokeStyle = PALETA.negro;
    ctx.lineWidth = 2;
    ctx.strokeRect(40, y - 30, 126, 40);
    fuente(ctx, 700, 22, MONO);
    ctx.fillStyle = PALETA.negro;
    ctx.fillText(codigo, 52, y - 2);
    fuente(ctx, 500, 26, SANS);
    ctx.fillText(nombre, 190, y - 2);
    fuente(ctx, 700, 30, MONO);
    ctx.fillStyle = '#2f8a57';
    ctx.textAlign = 'right';
    ctx.fillText(cantidad, W - 40, y - 2);
    ctx.textAlign = 'left';
    ctx.fillStyle = '#d9d6ce';
    ctx.fillRect(40, y + 22, W - 80, 2);
  });
}

function texturaSelloTinta(renderer) {
  const { c, ctx } = lienzo(512, 256);
  ctx.translate(256, 128);
  ctx.rotate(-0.16);
  ctx.strokeStyle = '#2f8a57';
  ctx.fillStyle = '#2f8a57';
  ctx.lineWidth = 12;
  ctx.strokeRect(-220, -84, 440, 168);
  ctx.lineWidth = 4;
  ctx.strokeRect(-206, -70, 412, 140);
  fuente(ctx, 900, 104, SANS, true);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('RECIBIDO', 0, 4);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalCompositeOperation = 'destination-out';
  for (let i = 0; i < 1400; i++) {
    ctx.fillStyle = `rgba(0,0,0,${0.3 + azar(i + 400) * 0.6})`;
    ctx.fillRect(azar(i + 401) * 512, azar(i + 402) * 256, 1 + azar(i + 403) * 4, 1 + azar(i + 404) * 3);
  }
  return texturaDe(c, renderer);
}

function dibujarKardex(ctx, filasVisibles) {
  const W = 900;
  const H = 1200;
  ctx.fillStyle = '#fbfaf6';
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = PALETA.negro;
  ctx.fillRect(0, 0, W, 16);
  fuente(ctx, 700, 30, MONO);
  ctx.strokeStyle = PALETA.negro;
  ctx.lineWidth = 3;
  ctx.strokeRect(50, 60, 190, 54);
  ctx.fillText('PAP-002', 66, 98);
  fuente(ctx, 800, 56, SANS);
  ctx.fillText('Bolígrafo azul', 50, 190);
  fuente(ctx, 900, 74, SANS, true);
  ctx.fillText('TARJETA KARDEX', 50, 290);

  const columnas = [50, 190, 560, 670, 780];
  const cabecera = ['FECHA', 'CONCEPTO', 'ENTRA', 'SALE', 'SALDO'];
  ctx.fillStyle = '#ecebe5';
  ctx.fillRect(40, 330, W - 80, 64);
  ctx.strokeRect(40, 330, W - 80, 64);
  fuente(ctx, 600, 24, MONO);
  ctx.fillStyle = '#4a4740';
  cabecera.forEach((t, i) => {
    ctx.textAlign = i >= 2 ? 'right' : 'left';
    ctx.fillText(t, i >= 2 ? columnas[i] + 90 : columnas[i], 372);
  });
  ASIENTOS_KARDEX.slice(0, filasVisibles).forEach(([fecha, concepto, entra, sale, saldo], i) => {
    const y = 394 + i * 92;
    ctx.fillStyle = i % 2 ? '#f3f2ec' : '#fbfaf6';
    ctx.fillRect(40, y, W - 80, 92);
    ctx.fillStyle = '#ecebe5';
    ctx.fillRect(columnas[4] - 10, y, W - 40 - columnas[4] + 10, 92);
    ctx.strokeStyle = '#c9c6bd';
    ctx.lineWidth = 2;
    ctx.strokeRect(40, y, W - 80, 92);
    ctx.textAlign = 'left';
    fuente(ctx, 500, 26, MONO);
    ctx.fillStyle = '#6b6860';
    ctx.fillText(fecha, columnas[0], y + 56);
    fuente(ctx, 600, 30, SANS);
    ctx.fillStyle = PALETA.negro;
    ctx.fillText(concepto, columnas[1], y + 56);
    ctx.textAlign = 'right';
    fuente(ctx, 700, 30, MONO);
    if (entra) { ctx.fillStyle = '#2f8a57'; ctx.fillText(String(entra), columnas[2] + 90, y + 56); }
    if (sale) { ctx.fillStyle = '#2d58b5'; ctx.fillText(String(sale), columnas[3] + 90, y + 56); }
    ctx.fillStyle = PALETA.negro;
    fuente(ctx, 800, 32, MONO);
    ctx.fillText(String(saldo), columnas[4] + 90, y + 56);
  });
  ctx.textAlign = 'left';
}

/* ============================================================ Montaje */

async function iniciar() {
  const lienzoMundo = document.getElementById('mundo');
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: lienzoMundo, antialias: true, powerPreference: 'high-performance' });
  } catch {
    document.documentElement.classList.add('sin-3d');
    return;
  }
  await esperarFuentes();

  const software = renderizadoPorSoftware(renderer);
  if (software) document.documentElement.classList.add('sin-aceleracion');
  renderer.setPixelRatio(densidadPixeles(movil, software));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.shadowMap.enabled = !movil && !software;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  // Las sombras solo se recalculan cuando se mueve algo de la maqueta, no al mover la cámara
  renderer.shadowMap.autoUpdate = false;
  let sombrasSucias = true;

  const escena = new THREE.Scene();
  const camara = new THREE.PerspectiveCamera(34, 1, 0.1, 400);

  /* ------------------------------------------------ Materiales */
  const tex = {
    hormigon: texturaHormigon(renderer),
    caja: texturaCaja(renderer),
    cinta: texturaCintaSeguridad(renderer),
    agotado: texturaAgotado(renderer),
    muelle: texturaMuelle(renderer),
    persiana: texturaRayas(renderer),
    remolque: texturaRemolque(renderer),
    discontinua: texturaLineasDiscontinuas(renderer),
    flecha: texturaFlecha(renderer),
    salida: texturaRotulo(renderer, 'SALIDA'),
    tinta: texturaSelloTinta(renderer),
  };
  tex.hormigon.repeat.set(30, 30);
  const losaTex = tex.hormigon.clone();
  losaTex.repeat.set(2, 2);
  losaTex.needsUpdate = true;

  const estandar = (opciones) => new THREE.MeshStandardMaterial({ roughness: 0.8, ...opciones });
  const mat = {
    suelo: estandar({ map: tex.hormigon, color: '#c9c5bc', roughness: 0.95 }),
    losa: estandar({ map: losaTex, color: '#e2dfd8', roughness: 0.9 }),
    plataforma: estandar({ map: losaTex, color: '#bdb9b0', roughness: 0.9 }),
    caja: estandar({ map: tex.caja, roughness: 0.82 }),
    madera: estandar({ color: PALETA.madera, roughness: 0.9 }),
    maderaClara: estandar({ color: '#c9a77c', roughness: 0.7 }),
    negro: estandar({ color: '#26262a', roughness: 0.55, metalness: 0.3 }),
    puntal: estandar({ color: PALETA.puntal, roughness: 0.55, metalness: 0.4 }),
    senal: estandar({ color: PALETA.senal, roughness: 0.45, metalness: 0.15 }),
    gris: estandar({ color: '#8d8a83', roughness: 0.6, metalness: 0.2 }),
    pared: estandar({ color: '#d9d6cf', roughness: 0.85 }),
    persiana: estandar({ map: tex.persiana, roughness: 0.6, metalness: 0.3 }),
    rueda: estandar({ color: '#151515', roughness: 0.9 }),
    cristal: new THREE.MeshPhysicalMaterial({ color: '#cfe3e6', roughness: 0.05, transmission: 0, transparent: true, opacity: 0.28 }),
    pantalla: estandar({ color: '#101114', emissive: '#1d2a2a', roughness: 0.3 }),
    cinta: estandar({ map: tex.cinta, roughness: 0.7 }),
    agotado: estandar({ map: tex.agotado, transparent: true, roughness: 0.75 }),
    muelle: estandar({ map: tex.muelle, transparent: true, roughness: 0.75 }),
    discontinua: estandar({ map: tex.discontinua, transparent: true, roughness: 0.7 }),
    flecha: estandar({ map: tex.flecha, transparent: true, roughness: 0.7 }),
    salida: estandar({ map: tex.salida, transparent: true, roughness: 0.7 }),
    tinta: new THREE.MeshBasicMaterial({ map: tex.tinta, transparent: true, opacity: 0, depthWrite: false }),
    rojo: estandar({ color: '#b52a24', roughness: 0.5 }),
    invisible: new THREE.MeshBasicMaterial({ visible: false }),
  };
  const geo = {
    caja: new RoundedBoxGeometry(0.42, 0.34, 0.46, 2, 0.018),
    tabla: new THREE.BoxGeometry(0.2, 0.026, 1.0),
    taco: new THREE.BoxGeometry(1.25, 0.09, 0.1),
    etiqueta: new THREE.PlaneGeometry(1.28, 1.28 * (168 / 640)),
  };

  const en = (objeto, x, y, z) => {
    objeto.position.set(x, y, z);
    return objeto;
  };
  const sombra = (m, recibe = true) => {
    m.castShadow = true;
    m.receiveShadow = recibe;
    return m;
  };
  const caja = (x, y, z, semilla = 0) => {
    const m = sombra(new THREE.Mesh(geo.caja, mat.caja));
    m.position.set(x + (azar(semilla) - 0.5) * 0.03, y, z + (azar(semilla + 1) - 0.5) * 0.03);
    m.rotation.y = (azar(semilla + 2) - 0.5) * 0.08;
    return m;
  };
  const bloque = (w, h, d, material, x = 0, y = 0, z = 0) => {
    const m = sombra(new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material));
    m.position.set(x, y, z);
    return m;
  };
  const plano = (w, h, material, x, y, z, { tumbado = true, giro = 0 } = {}) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), material);
    if (tumbado) m.rotation.x = -Math.PI / 2;
    m.rotation.z = giro;
    m.position.set(x, y, z);
    m.receiveShadow = true;
    return m;
  };

  function palet(cajas = 0, semilla = 0) {
    const g = new THREE.Group();
    for (const z of [-0.43, 0, 0.43]) {
      const t = sombra(new THREE.Mesh(geo.taco, mat.madera));
      t.position.set(0, 0.045, z);
      g.add(t);
    }
    for (let i = 0; i < 6; i++) {
      const t = sombra(new THREE.Mesh(geo.tabla, mat.madera));
      t.position.set(-0.55 + i * 0.22, 0.103, 0);
      g.add(t);
    }
    for (let i = 0; i < cajas; i++) {
      const capa = Math.floor(i / 6);
      const resto = i % 6;
      g.add(caja((resto % 3 - 1) * 0.445, 0.13 + 0.17 + capa * 0.344, (Math.floor(resto / 3) - 0.5) * 0.485, semilla * 31 + i));
    }
    return g;
  }

  function losa(ancho, fondo, dx = 0, dz = 0) {
    const g = new THREE.Group();
    const base = bloque(ancho, 0.6, fondo, mat.losa, dx, -0.3, dz);
    g.add(base);
    const tiraTex = tex.cinta.clone();
    tiraTex.wrapS = THREE.RepeatWrapping;
    tiraTex.repeat.set(Math.round(ancho * 1.5), 1);
    tiraTex.needsUpdate = true;
    const borde = new THREE.Mesh(new THREE.BoxGeometry(ancho + 0.03, 0.14, fondo + 0.03), estandar({ map: tiraTex }));
    borde.position.set(dx, -0.13, dz);
    g.add(borde);
    return g;
  }

  /* ------------------------------------------------ Suelo y caminos */
  const decorado = new THREE.Group();
  decorado.add(Object.assign(plano(400, 400, mat.suelo, MUNDO.x, -0.6, MUNDO.z), { receiveShadow: true }));
  for (let i = 0; i < ESCENAS.length - 1; i++) {
    const a = ESCENAS[i].centro;
    const b = ESCENAS[i + 1].centro;
    const largo = a.distanceTo(b);
    const t = tex.discontinua.clone();
    t.wrapS = THREE.RepeatWrapping;
    t.repeat.set(largo / 1.4, 1);
    t.needsUpdate = true;
    const camino = new THREE.Mesh(new THREE.PlaneGeometry(largo, 0.22), estandar({ map: t, transparent: true }));
    camino.rotation.x = -Math.PI / 2;
    camino.rotation.z = -Math.atan2(b.z - a.z, b.x - a.x);
    camino.position.set((a.x + b.x) / 2, -0.595, (a.z + b.z) / 2);
    decorado.add(camino);
  }

  const islas = [];

  /* ------------------------------------------------ 1 · Muelle */
  {
    const g = new THREE.Group();
    g.position.copy(ESCENAS[0].centro);
    g.add(losa(11, 15, 0, 1.5));
    g.add(bloque(11, 1.1, 4, mat.plataforma, 0, 0.55, -4));
    g.add(bloque(11, 0.03, 0.14, mat.senal, 0, 1.115, -2.1));
    for (let x = -4.5; x <= 4.5; x += 1.5) g.add(bloque(0.45, 0.35, 0.18, mat.negro, x, 0.75, -1.93));
    g.add(bloque(11, 3.6, 0.3, mat.pared, 0, 2.9, -5.85));
    g.add(bloque(3.2, 2.1, 0.06, mat.persiana, 2.4, 2.25, -5.68));
    g.add(bloque(3.5, 0.18, 0.12, mat.senal, 2.4, 3.36, -5.66));
    g.add(plano(3.4, 1.7, mat.muelle, -2.2, 1.12, -4.2));
    g.add(en(palet(12, 1), 2.2, 1.1, -4.2));
    g.add(en(palet(6, 2), 3.8, 1.1, -3.3));
    g.add(en(palet(18, 3), 4.2, 1.1, -4.9));

    // Camión con el remolque abierto contra el muelle
    const camion = new THREE.Group();
    camion.position.set(-1.6, 0, 2.6);
    const lado = estandar({ map: tex.remolque, side: THREE.DoubleSide });
    const remolque = sombra(new THREE.Mesh(new THREE.BoxGeometry(2.5, 2.7, 7), [lado, lado, mat.pared, mat.pared, mat.pared, mat.invisible]));
    remolque.position.set(0, 2.55, 0);
    camion.add(remolque);
    camion.add(bloque(2.3, 0.35, 7.6, mat.negro, 0, 1.0, 0.4));
    camion.add(bloque(2.5, 2.3, 1.9, mat.negro, 0, 2.05, 4.7));
    camion.add(bloque(2.2, 0.9, 0.04, estandar({ color: '#3a4a52', roughness: 0.15, metalness: 0.5 }), 0, 2.55, 5.66));
    camion.add(bloque(2.52, 0.3, 1.92, mat.senal, 0, 1.45, 4.7));
    const geoRueda = new THREE.CylinderGeometry(0.46, 0.46, 0.36, 20);
    for (const z of [-2.6, -1.6, 4.4]) {
      for (const x of [-1.15, 1.15]) {
        const r = sombra(new THREE.Mesh(geoRueda, mat.rueda));
        r.rotation.z = Math.PI / 2;
        r.position.set(x, 0.46, z);
        camion.add(r);
      }
    }
    for (let i = 0; i < 3; i++) {
      const p = palet(12, 10 + i);
      p.position.set(0, 1.2, -1.4 + i * 1.6);
      camion.add(p);
    }
    g.add(camion);

    // El palé que sale del camión al muelle (animado con el scroll)
    const movil = palet(15, 7);
    movil.userData.movil = true;
    g.add(movil);
    const desde = V(-1.6, 1.2, -0.6);
    const hasta = V(0.6, 1.1, -3.6);
    islas.push({
      grupo: g,
      animar(a) {
        const k = suave(tramo(a, 0.05, 0.8));
        movil.position.lerpVectors(desde, hasta, k);
        movil.position.y += Math.sin(k * Math.PI) * 0.15;
        movil.rotation.y = k * -0.35;
      },
    });
    fusionarEstaticos(g);
    escena.add(g);
  }

  /* ------------------------------------------------ 2 · Recepción */
  {
    const g = new THREE.Group();
    g.position.copy(ESCENAS[1].centro);
    g.add(losa(10, 10));
    // Zona marcada en el suelo
    for (const [w, d, x, z] of [[5.2, 0.1, 0, -2], [5.2, 0.1, 0, 2.4], [0.1, 4.4, -2.6, 0.2], [0.1, 4.4, 2.6, 0.2]]) {
      g.add(bloque(w, 0.01, d, mat.senal, x, 0.005, z));
    }
    // Mesa
    g.add(bloque(3.4, 0.08, 1.7, mat.maderaClara, 0, 0.95, 0.2));
    for (const [x, z] of [[-1.6, -0.5], [1.6, -0.5], [-1.6, 0.9], [1.6, 0.9]]) g.add(bloque(0.07, 0.92, 0.07, mat.negro, x, 0.46, z));

    const { c, ctx } = lienzo(700, 512);
    dibujarAlbaran(ctx);
    const papel = plano(1.5, 1.1, estandar({ map: texturaDe(c, renderer), roughness: 0.9 }), -0.3, 0.995, 0.25);
    papel.rotation.z = 0.06;
    g.add(papel);
    const marca = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.45), mat.tinta);
    marca.rotation.x = -Math.PI / 2;
    marca.rotation.z = 0.06;
    marca.position.set(-0.1, 0.999, 0.42);
    g.add(marca);

    // El sello de goma
    const sello = new THREE.Group();
    sello.add(bloque(0.95, 0.16, 0.5, mat.negro, 0, 0.08, 0));
    sello.add(bloque(0.92, 0.03, 0.47, estandar({ color: '#2f8a57' }), 0, 0.0, 0));
    const mango = sombra(new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.09, 0.42, 16), mat.maderaClara));
    mango.position.y = 0.37;
    sello.add(mango);
    const pomo = sombra(new THREE.Mesh(new THREE.SphereGeometry(0.14, 20, 14), mat.rojo));
    pomo.position.y = 0.62;
    sello.add(pomo);
    sello.position.set(-0.1, 1.9, 0.42);
    sello.userData.movil = true;
    g.add(sello);

    // Palés esperando, lector de códigos y cajetín
    g.add(en(palet(18, 20), 3.4, 0, -2.8));
    g.add(en(palet(9, 21), -3.5, 0, -2.6));
    g.add(bloque(0.05, 1.3, 0.05, mat.negro, 1.9, 0.65, -0.9));
    g.add(bloque(0.32, 0.2, 0.22, mat.senal, 1.9, 1.38, -0.9));
    g.add(bloque(0.6, 0.35, 0.45, mat.gris, 1.2, 1.17, -0.15));

    islas.push({
      grupo: g,
      animar(a) {
        const baja = suave(tramo(a, 0.25, 0.48));
        const sube = suave(tramo(a, 0.56, 0.85));
        sello.position.y = 1.0 + 0.9 * (1 - baja) + 0.7 * sube;
        mat.tinta.opacity = tramo(a, 0.47, 0.5);
      },
    });
    fusionarEstaticos(g);
    escena.add(g);
  }

  /* ------------------------------------------------ 3 · Pasillos */
  {
    const g = new THREE.Group();
    g.position.copy(ESCENAS[2].centro);
    g.add(losa(10, 12, 0, 0.5));
    const caidas = [];
    let etiquetaRepuesta = null;
    PRODUCTOS_DEMO.forEach((fila, f) => {
      const z = -3.6 + f * 3.4;
      const rack = new THREE.Group();
      rack.position.set(0, 0, z);
      const ancho = fila.length * 1.5;
      for (let i = 0; i <= fila.length; i++) {
        for (const lado of [-0.55, 0.55]) rack.add(bloque(0.075, 2.05, 0.075, mat.puntal, -ancho / 2 + i * 1.5, 1.025, lado));
      }
      for (const y of [0.16, 1.72]) for (const lado of [-0.585, 0.585]) rack.add(bloque(ancho + 0.08, 0.11, 0.055, mat.senal, 0, y, lado));
      fila.forEach((p, i) => {
        const x = -ancho / 2 + (i + 0.5) * 1.5;
        const pal = palet(p.cajas, f * 10 + i);
        pal.position.set(x, 0, 0);
        rack.add(pal);
        const { c, ctx } = lienzo(640, 168);
        dibujarEtiqueta(ctx, p);
        const textura = texturaDe(c, renderer);
        const etiqueta = new THREE.Mesh(geo.etiqueta, estandar({ map: textura, roughness: 0.5 }));
        etiqueta.position.set(x, 1.73, 0.62);
        rack.add(etiqueta);
        if (p.estado !== 'OK') {
          const marca = plano(1.3, 0.48, p.estado === 'AGOTADO' ? mat.agotado : mat.cinta, x, 0.004, 1.15);
          marca.userData.fijo = false;
          rack.add(marca);
          if (p.repone) {
            // Este hueco se repone durante el recorrido: caen cajas y la etiqueta cambia
            etiquetaRepuesta = { ctx, textura, producto: p, marca, repuesta: false };
            for (let j = 0; j < 12; j++) {
              const capa = Math.floor(j / 6);
              const resto = j % 6;
              const cj = caja((resto % 3 - 1) * 0.445, 0.3 + capa * 0.344, (Math.floor(resto / 3) - 0.5) * 0.485, 500 + j);
              cj.userData.movil = true;
              pal.add(cj);
              caidas.push({ caja: cj, reposo: cj.position.y, j });
            }
          }
        }
      });
      g.add(rack);
    });
    islas.push({
      grupo: g,
      animar(a) {
        for (const { caja: cj, reposo, j } of caidas) {
          const k = tramo(a, 0.12 + j * 0.035, 0.3 + j * 0.035);
          cj.visible = k > 0;
          cj.position.y = reposo + 3.2 * (1 - curvas.rebote(k));
        }
        if (etiquetaRepuesta) {
          const repuesta = a > 0.62;
          if (repuesta !== etiquetaRepuesta.repuesta) {
            etiquetaRepuesta.repuesta = repuesta;
            const p = etiquetaRepuesta.producto;
            dibujarEtiqueta(etiquetaRepuesta.ctx, repuesta ? { ...p, stock_actual: p.repone, estado: 'OK' } : p);
            etiquetaRepuesta.textura.needsUpdate = true;
            etiquetaRepuesta.marca.visible = !repuesta;
          }
        }
      },
    });
    fusionarEstaticos(g);
    escena.add(g);
  }

  /* ------------------------------------------------ 4 · Expedición */
  {
    const g = new THREE.Group();
    g.position.copy(ESCENAS[3].centro);
    g.add(losa(12, 9));
    // Puerta de salida con cinta de seguridad
    const tiraTex = tex.cinta.clone();
    tiraTex.wrapS = tiraTex.wrapT = THREE.RepeatWrapping;
    tiraTex.repeat.set(1, 6);
    tiraTex.needsUpdate = true;
    const matPoste = estandar({ map: tiraTex });
    for (const z of [-1.9, 1.9]) g.add(bloque(0.3, 3.2, 0.3, matPoste, 4.6, 1.6, z));
    g.add(bloque(0.34, 0.35, 4.2, mat.negro, 4.6, 3.3, 0));
    g.add(plano(2.4, 0.75, mat.salida, 5.5, 0.006, 0, { giro: Math.PI / 2 }));
    for (const x of [-1.5, 0.5, 2.5]) g.add(plano(0.9, 0.9, mat.flecha, x, 0.006, 0));
    g.add(en(palet(18, 30), -4.4, 0, -2.8));
    g.add(en(palet(12, 31), -4.4, 0, 2.6));
    g.add(en(palet(15, 32), -2.8, 0, -2.9));

    // Carretilla elevadora
    const carretilla = new THREE.Group();
    carretilla.add(bloque(1.15, 0.85, 1.7, mat.senal, 0, 0.62, 0));
    carretilla.add(bloque(1.15, 0.6, 0.45, mat.negro, -0.95, 0.7, 0));
    carretilla.rotation.y = 0;
    for (const [x, z] of [[-0.55, -0.5], [-0.55, 0.5], [0.55, -0.5], [0.55, 0.5]]) {
      carretilla.add(bloque(0.05, 1.3, 0.05, mat.negro, x * 0.9, 1.7, z * 1.0));
    }
    carretilla.add(bloque(1.15, 0.05, 1.2, mat.negro, 0, 2.36, 0));
    carretilla.add(bloque(0.4, 0.35, 0.45, mat.negro, -0.2, 1.2, 0));
    const geoRueda = new THREE.CylinderGeometry(0.28, 0.28, 0.22, 16);
    const ruedas = [];
    for (const x of [-0.55, 0.55]) {
      for (const z of [-0.62, 0.62]) {
        const r = sombra(new THREE.Mesh(geoRueda, mat.rueda));
        r.rotation.x = Math.PI / 2;
        r.position.set(x, 0.28, z);
        carretilla.add(r);
        ruedas.push(r);
      }
    }
    for (const z of [-0.35, 0.35]) carretilla.add(bloque(0.08, 2.4, 0.08, mat.negro, 0.98, 1.2, z));
    const horquillas = new THREE.Group();
    horquillas.add(bloque(0.06, 0.6, 0.9, mat.negro, 1.05, 0.3, 0));
    for (const z of [-0.3, 0.3]) horquillas.add(bloque(1.15, 0.05, 0.12, mat.gris, 1.62, 0.03, z));
    const carga = palet(12, 40);
    carga.position.set(1.7, 0.06, 0);
    carga.rotation.y = Math.PI / 2;
    horquillas.add(carga);
    carretilla.add(horquillas);
    carretilla.userData.movil = true;
    g.add(carretilla);

    islas.push({
      grupo: g,
      animar(a) {
        const avance = suave(tramo(a, 0.12, 0.88));
        const x = -3.6 + avance * 6.8;
        carretilla.position.set(x, 0, 0);
        horquillas.position.y = 0.08 + 0.32 * suave(tramo(a, 0, 0.14));
        for (const r of ruedas) r.rotation.y = x / 0.28;
      },
    });
    fusionarEstaticos(g);
    escena.add(g);
  }

  /* ------------------------------------------------ 5 · Oficina y tarjeta Kardex */
  {
    const g = new THREE.Group();
    g.position.copy(ESCENAS[4].centro);
    g.add(losa(10, 10));
    // Mamparas de cristal de la oficina
    for (const [w, d, x, z] of [[8, 0.06, 0, -3.8], [0.06, 7.6, -4, 0]]) {
      const m = new THREE.Mesh(new THREE.BoxGeometry(w, 2.4, d), mat.cristal);
      m.position.set(x, 1.2, z);
      g.add(m);
      g.add(bloque(w + 0.05, 0.08, d + 0.05, mat.negro, x, 2.42, z));
    }
    // Escritorio con monitor y archivadores
    g.add(bloque(2.4, 0.07, 1.1, mat.maderaClara, -1.8, 0.78, -2.6));
    for (const [x, z] of [[-2.9, -3.05], [-0.7, -3.05], [-2.9, -2.15], [-0.7, -2.15]]) g.add(bloque(0.06, 0.76, 0.06, mat.negro, x, 0.38, z));
    g.add(bloque(0.9, 0.55, 0.05, mat.pantalla, -1.8, 1.2, -2.9));
    g.add(bloque(0.08, 0.3, 0.08, mat.negro, -1.8, 0.95, -2.9));
    for (let i = 0; i < 3; i++) g.add(bloque(0.6, 1.3, 0.7, mat.gris, -3.4, 0.65, 1 + i * 0.75));

    // La tarjeta Kardex, grande, en un caballete
    const { c, ctx } = lienzo(900, 1200);
    dibujarKardex(ctx, 0);
    const texturaKardex = texturaDe(c, renderer);
    const tablero = sombra(new THREE.Mesh(new THREE.BoxGeometry(2.25, 3.0, 0.05), [mat.negro, mat.negro, mat.negro, mat.negro, estandar({ map: texturaKardex, roughness: 0.7 }), mat.negro]));
    tablero.position.set(0.8, 1.85, -0.6);
    tablero.rotation.y = -0.25;
    g.add(tablero);
    for (const x of [-0.85, 0.85]) {
      const pata = bloque(0.06, 2.0, 0.06, mat.negro, 0.8 + x * Math.cos(0.25), 1.0, -0.6 + x * Math.sin(0.25) - 0.15);
      pata.rotation.x = 0.12;
      g.add(pata);
    }
    let filas = -1;
    islas.push({
      grupo: g,
      animar(a) {
        const visibles = Math.round(tramo(a, 0.08, 0.72) * ASIENTOS_KARDEX.length);
        if (visibles !== filas) {
          filas = visibles;
          dibujarKardex(ctx, visibles);
          texturaKardex.needsUpdate = true;
        }
      },
    });
    fusionarEstaticos(g);
    escena.add(g);
  }

  fusionarEstaticos(decorado);
  escena.add(decorado);

  /* ------------------------------------------------ Luz y ambiente */
  escena.background = new THREE.Color('#e6e2da');
  escena.fog = new THREE.Fog('#e6e2da', 55, 140);
  escena.add(new THREE.HemisphereLight('#ffffff', '#b5ae9f', 1.15));
  const sol = new THREE.DirectionalLight('#fff3e2', 2.7);
  sol.position.set(MUNDO.x + 22, 34, MUNDO.z + 20);
  sol.target.position.copy(MUNDO);
  sol.castShadow = true;
  sol.shadow.mapSize.set(2048, 2048);
  Object.assign(sol.shadow.camera, { left: -34, right: 34, top: 34, bottom: -34, near: 1, far: 100 });
  sol.shadow.bias = -0.0004;
  sol.shadow.normalBias = 0.03;
  escena.add(sol, sol.target);

  /* ================================================ Guion de cámara */

  const rotar = (v, angulo) => v.clone().applyAxisAngle(V(0, 1, 0), angulo);
  const secciones = [...document.querySelectorAll('[data-escena]')];
  const claves = []; // { seccion, p, pos, mira }

  claves.push({ seccion: 0, p: 0, pos: MUNDO.clone().add(V(20, 34, 36)), mira: MUNDO.clone() });
  claves.push({ seccion: 0, p: 0.55, pos: MUNDO.clone().add(V(4, 26, 30)), mira: MUNDO.clone().add(V(-6, 0, 4)) });
  ESCENAS.forEach((e, i) => {
    const s = i + 1;
    claves.push({ seccion: s, p: 0, pos: e.centro.clone().add(rotar(V(1, 9.5, 12.5), e.giro)), mira: e.centro.clone().add(V(0, 0.4, 0)) });
    claves.push({ seccion: s, p: 0.36, pos: e.foco.clone().add(rotar(V(1.9, 2.1, 5.0).multiplyScalar(e.cerca), e.giro)), mira: e.foco.clone() });
    claves.push({ seccion: s, p: 0.62, pos: e.foco.clone().add(rotar(V(-1.7, 1.8, 4.7).multiplyScalar(e.cerca), e.giro)), mira: e.foco.clone().add(V(0.2, -0.05, 0)) });
    const siguiente = ESCENAS[i + 1];
    if (siguiente) {
      const medio = e.centro.clone().lerp(siguiente.centro, 0.5);
      claves.push({ seccion: s, p: 0.87, pos: medio.clone().add(V(0, 15, 10)), mira: medio.clone() });
    }
  });
  const final = ESCENAS.length + 1;
  claves.push({ seccion: final, p: 0, pos: MUNDO.clone().add(V(-14, 32, 34)), mira: MUNDO.clone().add(V(0, 0, 1)) });
  claves.push({ seccion: final, p: 0.85, pos: MUNDO.clone().add(V(14, 38, 36)), mira: MUNDO.clone().add(V(0, 0, -1)) });

  const curvaPos = new THREE.CatmullRomCurve3(claves.map((k) => k.pos), false, 'centripetal');
  const curvaMira = new THREE.CatmullRomCurve3(claves.map((k) => k.mira), false, 'centripetal');
  let posicionesY = [];

  function medir() {
    const maximo = document.documentElement.scrollHeight - innerHeight;
    posicionesY = claves.map((k) => {
      const sec = secciones[k.seccion];
      return Math.min(maximo, sec.offsetTop + k.p * sec.offsetHeight);
    });
  }

  function parametroPara(y) {
    if (y <= posicionesY[0]) return 0;
    for (let k = 0; k < posicionesY.length - 1; k++) {
      if (y < posicionesY[k + 1]) {
        const u = (y - posicionesY[k]) / Math.max(1, posicionesY[k + 1] - posicionesY[k]);
        return (k + u) / (claves.length - 1);
      }
    }
    return 1;
  }

  function progresoSeccion(indice, y) {
    const sec = secciones[indice];
    return limitar((y - sec.offsetTop) / sec.offsetHeight);
  }

  const posicion = new THREE.Vector3();
  const mira = new THREE.Vector3();
  function colocarCamara(y) {
    if (reducido) {
      // Sin vuelo: cada sección muestra un plano fijo de su escena
      const indice = secciones.findIndex((s) => y < s.offsetTop + s.offsetHeight);
      const activa = indice === -1 ? final : indice;
      const clave = claves.find((k) => k.seccion === activa && (k.p === 0.36 || activa === 0 || activa === final)) ?? claves[0];
      posicion.copy(clave.pos);
      mira.copy(clave.mira);
    } else {
      const t = parametroPara(y);
      curvaPos.getPoint(t, posicion);
      curvaMira.getPoint(t, mira);
    }
    // En vertical, la cámara se aleja a lo largo de su línea de visión para que quepa la escena
    if (camara.aspect < 1) posicion.sub(mira).multiplyScalar(1.2 + (1 - camara.aspect) * 0.8).add(mira);
    // En horizontal, desplaza la cámara de lado: el panel de texto ocupa la izquierda y la escena queda a la derecha
    if (camara.aspect > 1.1) {
      const derecha = mira.clone().sub(posicion).cross(V(0, 1, 0)).normalize();
      const lateral = derecha.multiplyScalar(-posicion.distanceTo(mira) * 0.17);
      posicion.add(lateral);
      mira.add(lateral);
    }
    camara.position.copy(posicion);
    camara.lookAt(mira);
  }

  /* ================================================ Interfaz ligada al scroll */

  const textos = secciones.map((s) => s.querySelector('.escena__panel'));
  const paradas = [...document.querySelectorAll('.ruta a')];
  const cinta = document.querySelector('.progreso__relleno');

  const ultimaVisibilidad = [];
  const ultimoProgreso = [];

  function actualizarInterfaz(y) {
    const maximo = document.documentElement.scrollHeight - innerHeight;
    cinta.style.transform = `scaleX(${limitar(y / Math.max(1, maximo))})`;
    let activa = 0;
    secciones.forEach((s, i) => {
      const p = progresoSeccion(i, y);
      if (y >= s.offsetTop - innerHeight * 0.5) activa = i;
      const panel = textos[i];
      if (!panel) return;
      let visible;
      if (i === 0) visible = 1 - tramo(p, 0.3, 0.5);
      else if (i === final) visible = tramo(p, 0.05, 0.25);
      else visible = Math.min(tramo(p, 0.12, 0.26), 1 - tramo(p, 0.7, 0.82));
      const redondeado = Math.round(visible * 100) / 100;
      if (ultimaVisibilidad[i] === redondeado) return;
      ultimaVisibilidad[i] = redondeado;
      panel.style.opacity = redondeado;
      panel.style.transform = reducido ? 'none' : `translateY(${(1 - redondeado) * 24}px)`;
      panel.style.visibility = redondeado < 0.01 ? 'hidden' : 'visible';
    });
    paradas.forEach((a, i) => {
      if (i + 1 === activa) a.setAttribute('aria-current', 'step');
      else a.removeAttribute('aria-current');
    });
    ESCENAS.forEach((_, i) => {
      const p = progresoSeccion(i + 1, y);
      const a = reducido ? 1 : Math.round(tramo(p, 0.1, 0.78) * 1000) / 1000;
      if (ultimoProgreso[i] === a) return;
      ultimoProgreso[i] = a;
      islas[i].animar(a);
      sombrasSucias = true;
    });
  }

  /* ================================================ Bucle */

  let yActual = scrollY;
  let ultimaY = -1;

  function ajustar() {
    const w = innerWidth;
    const h = innerHeight;
    renderer.setSize(w, h, false);
    camara.aspect = w / h;
    camara.fov = w / h < 1 ? 46 : 34;
    camara.updateProjectionMatrix();
    medir();
    ultimaY = -1;
  }
  let anchoAnterior = innerWidth;
  addEventListener('resize', () => {
    // En el móvil, al mostrarse u ocultarse la barra del navegador solo cambia la altura: no recalcular
    if (movil && innerWidth === anchoAnterior) {
      renderer.setSize(innerWidth, innerHeight, false);
      camara.aspect = innerWidth / innerHeight;
      camara.updateProjectionMatrix();
      ultimaY = -1;
      return;
    }
    anchoAnterior = innerWidth;
    ajustar();
  });
  ajustar();

  let sombrasCongeladas = false;
  let dibujoAnterior = false;
  const anotarFotograma = vigilarRendimiento((nivel) => {
    bajarCalidad(renderer, nivel);
    sombrasCongeladas = true;
    ultimaY = -1;
  });

  function fotograma(ahora) {
    const objetivo = scrollY;
    yActual = sinInercia ? objetivo : yActual + (objetivo - yActual) * 0.09;
    if (Math.abs(objetivo - yActual) < 0.3) yActual = objetivo;
    if (Math.abs(yActual - ultimaY) > 0.05) {
      ultimaY = yActual;
      colocarCamara(yActual);
      actualizarInterfaz(yActual);
      if (sombrasSucias && !sombrasCongeladas && renderer.shadowMap.enabled) renderer.shadowMap.needsUpdate = true;
      sombrasSucias = false;
      renderer.render(escena, camara);
      anotarFotograma(ahora, dibujoAnterior);
      dibujoAnterior = true;
    } else {
      dibujoAnterior = false;
    }
  }
  renderer.setAnimationLoop(fotograma);
  document.documentElement.classList.add('mundo-listo');
}

/** Cifras reales del almacén en el cierre del recorrido (si el servidor responde). */
async function cifrasFinales() {
  try {
    const respuesta = await fetch('/api/resumen');
    if (!respuesta.ok) return;
    const r = await respuesta.json();
    const num = new Intl.NumberFormat('es-ES');
    const eur = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' });
    const dl = document.getElementById('final-cifras');
    dl.innerHTML = '';
    for (const [etiqueta, valor] of [['Referencias', num.format(r.productos)], ['Unidades', num.format(r.unidades)], ['Valor', eur.format(r.valor)]]) {
      const fila = document.createElement('div');
      const dt = document.createElement('dt');
      const dd = document.createElement('dd');
      dt.textContent = etiqueta;
      dd.textContent = valor;
      fila.append(dt, dd);
      dl.append(fila);
    }
    dl.hidden = false;
  } catch {
    // Sin servidor el recorrido sigue funcionando; solo faltan las cifras
  }
}

iniciar();
cifrasFinales();
