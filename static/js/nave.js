// La nave en 3D. Cada categoría es un pasillo con su estantería; cada referencia ocupa
// un hueco con un palé y tantas cajas como indica su stock. Se carga solo al abrir la vista.

import * as THREE from 'three';
import { OrbitControls } from '/vendor/three/OrbitControls.js';
import { RoundedBoxGeometry } from '/vendor/three/RoundedBoxGeometry.js';
import { mergeGeometries } from '/vendor/three/BufferGeometryUtils.js';
import { anchosCode128 } from './code128.js';
import { bajarCalidad, densidadPixeles, dialogoTapando, fusionarEstaticos, renderizadoPorSoftware, vigilarRendimiento } from './rendimiento3d.js';

/* ============================================================ Medidas (m) */

const M = {
  hueco: 1.5,
  fondo: 1.1,
  alturaLarguero: 1.72,
  alturaPuntal: 2.05,
  separacionFilas: 4.8,
  huecosPorFila: 8,
  palet: 0.13,
  caja: { x: 0.42, y: 0.34, z: 0.46 },
  holgura: 0.025,
};
const REJILLA = { x: 3, z: 2, y: 3 };
const CAPACIDAD = REJILLA.x * REJILLA.z * REJILLA.y; // 18 cajas = hueco lleno = doble del mínimo

export const PALETA = {
  senal: '#f2c500',
  negro: '#1a1916',
  papel: '#f7f6f2',
  rojo: '#c8312b',
  kraft: '#b98a5c',
  madera: '#a3825a',
  puntal: '#2a2b2e',
};

const AMBIENTES = {
  claro: { fondo: '#e7e5e0', suelo: '#d3d0c9', cielo: '#ffffff', tierra: '#b8b2a6', hemisferio: 1.15, sol: 2.6, exposicion: 1.0, lamparas: false },
  oscuro: { fondo: '#0e0d0c', suelo: '#2b2925', cielo: '#5b6170', tierra: '#141312', hemisferio: 0.22, sol: 0.2, exposicion: 1.15, lamparas: true },
};

const fmtNum = new Intl.NumberFormat('es-ES');

/* ============================================================ Utilidades */

const reducido = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const esMovil = () => matchMedia('(max-width: 700px), (pointer: coarse)').matches;

export const curvas = {
  salida: (k) => 1 - (1 - k) ** 3,
  suave: (k) => (k < 0.5 ? 4 * k ** 3 : 1 - (-2 * k + 2) ** 3 / 2),
  rebote(k) {
    const n = 7.5625;
    const d = 2.75;
    if (k < 1 / d) return n * k * k;
    if (k < 2 / d) return n * (k -= 1.5 / d) * k + 0.75;
    if (k < 2.5 / d) return n * (k -= 2.25 / d) * k + 0.9375;
    return n * (k -= 2.625 / d) * k + 0.984375;
  },
};

/** Pseudoaleatorio determinista: la misma caja siempre cae igual de torcida. */
export function azar(semilla) {
  const x = Math.sin(semilla * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

function cajasPara(p) {
  if (p.stock_actual === 0) return 0;
  const referencia = Math.max(p.stock_minimo * 2, p.stock_actual, 1);
  return Math.max(1, Math.round((p.stock_actual / referencia) * CAPACIDAD));
}

export function lienzo(ancho, alto) {
  const c = document.createElement('canvas');
  c.width = ancho;
  c.height = alto;
  const ctx = c.getContext('2d');
  return { c, ctx };
}

export function fuente(ctx, peso, tamano, familia, estrecha = false) {
  ctx.font = `${peso} ${tamano}px ${familia}`;
  if ('fontStretch' in ctx) ctx.fontStretch = estrecha ? 'condensed' : 'normal';
}

function recortar(ctx, texto, anchoMaximo) {
  if (ctx.measureText(texto).width <= anchoMaximo) return texto;
  let t = texto;
  while (t.length > 1 && ctx.measureText(`${t}…`).width > anchoMaximo) t = t.slice(0, -1);
  return `${t.trimEnd()}…`;
}

export const SANS = '"Archivo", system-ui, sans-serif';
export const MONO = '"Martian Mono", ui-monospace, monospace';

export async function esperarFuentes() {
  if (!document.fonts) return;
  const cargas = Promise.all([
    document.fonts.load(`800 40px ${SANS}`),
    document.fonts.load(`600 40px ${MONO}`),
  ]).catch(() => null);
  await Promise.race([cargas, new Promise((r) => setTimeout(r, 1500))]);
}

/* ============================================================ Texturas */

export function texturaDe(c, renderer, { repetir = null } = {}) {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = renderer.capabilities.getMaxAnisotropy();
  if (repetir) {
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(repetir, repetir);
  }
  return t;
}

export function texturaHormigon(renderer) {
  const { c, ctx } = lienzo(512, 512);
  ctx.fillStyle = '#808080';
  ctx.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 9000; i++) {
    const v = 110 + azar(i) * 40;
    ctx.fillStyle = `rgba(${v},${v},${v},${0.25 + azar(i + 7) * 0.3})`;
    ctx.fillRect(azar(i + 1) * 512, azar(i + 2) * 512, 1 + azar(i + 3) * 2, 1 + azar(i + 4) * 2);
  }
  for (let i = 0; i < 14; i++) {
    const x = azar(i + 50) * 512;
    const y = azar(i + 60) * 512;
    const g = ctx.createRadialGradient(x, y, 0, x, y, 40 + azar(i + 70) * 90);
    g.addColorStop(0, `rgba(${azar(i) > 0.5 ? 150 : 100},${azar(i) > 0.5 ? 150 : 100},${azar(i) > 0.5 ? 150 : 100},0.18)`);
    g.addColorStop(1, 'rgba(128,128,128,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 512, 512);
  }
  // Juntas de dilatación de la solera
  ctx.strokeStyle = 'rgba(60,60,60,0.35)';
  ctx.lineWidth = 2;
  ctx.strokeRect(0, 0, 512, 512);
  return texturaDe(c, renderer, { repetir: 1 });
}

export function texturaCaja(renderer) {
  const { c, ctx } = lienzo(256, 256);
  ctx.fillStyle = PALETA.kraft;
  ctx.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 2500; i++) {
    ctx.fillStyle = `rgba(${azar(i) > 0.5 ? '255,235,200' : '90,55,25'},${0.05 + azar(i + 9) * 0.08})`;
    ctx.fillRect(azar(i + 1) * 256, azar(i + 2) * 256, 1 + azar(i + 3) * 3, 1);
  }
  // Cinta de embalar
  ctx.fillStyle = 'rgba(214,176,120,0.85)';
  ctx.fillRect(104, 0, 48, 256);
  ctx.fillStyle = 'rgba(90,60,30,0.25)';
  ctx.fillRect(104, 0, 2, 256);
  ctx.fillRect(150, 0, 2, 256);
  // Flechas de «este lado arriba»
  ctx.strokeStyle = 'rgba(40,25,10,0.55)';
  ctx.lineWidth = 5;
  for (const x of [26, 52]) {
    ctx.beginPath();
    ctx.moveTo(x, 70);
    ctx.lineTo(x, 30);
    ctx.moveTo(x - 10, 42);
    ctx.lineTo(x, 30);
    ctx.lineTo(x + 10, 42);
    ctx.stroke();
  }
  ctx.strokeRect(14, 20, 50, 60);
  return texturaDe(c, renderer);
}

export function texturaCintaSeguridad(renderer) {
  const { c, ctx } = lienzo(256, 96);
  ctx.fillStyle = PALETA.senal;
  ctx.fillRect(0, 0, 256, 96);
  ctx.fillStyle = PALETA.negro;
  for (let x = -96; x < 256 + 96; x += 40) {
    ctx.beginPath();
    ctx.moveTo(x, 96);
    ctx.lineTo(x + 20, 96);
    ctx.lineTo(x + 116, 0);
    ctx.lineTo(x + 96, 0);
    ctx.fill();
  }
  return texturaDe(c, renderer);
}

export function texturaAgotado(renderer) {
  const { c, ctx } = lienzo(512, 192);
  ctx.fillStyle = PALETA.rojo;
  ctx.fillRect(0, 0, 512, 192);
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 8;
  ctx.strokeRect(14, 14, 484, 164);
  fuente(ctx, 900, 104, SANS, true);
  ctx.fillStyle = '#ffffff';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('AGOTADO', 256, 100);
  // Pintura gastada por el paso de las carretillas
  ctx.globalCompositeOperation = 'destination-out';
  for (let i = 0; i < 900; i++) {
    ctx.fillStyle = `rgba(0,0,0,${0.15 + azar(i) * 0.5})`;
    ctx.fillRect(azar(i + 1) * 512, azar(i + 2) * 192, 2 + azar(i + 3) * 6, 1 + azar(i + 4) * 3);
  }
  return texturaDe(c, renderer);
}

export function texturaMuelle(renderer) {
  const { c, ctx } = lienzo(512, 256);
  ctx.fillStyle = PALETA.senal;
  for (let x = -256; x < 512; x += 36) {
    ctx.beginPath();
    ctx.moveTo(x, 256);
    ctx.lineTo(x + 16, 256);
    ctx.lineTo(x + 272, 0);
    ctx.lineTo(x + 256, 0);
    ctx.fill();
  }
  ctx.clearRect(28, 28, 456, 200);
  fuente(ctx, 900, 92, SANS, true);
  ctx.fillStyle = PALETA.senal;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('MUELLE 1', 256, 112);
  fuente(ctx, 600, 26, MONO);
  ctx.fillText('RECEPCIÓN DE MERCANCÍA', 256, 182);
  ctx.globalCompositeOperation = 'destination-out';
  for (let i = 0; i < 700; i++) {
    ctx.fillStyle = `rgba(0,0,0,${0.2 + azar(i + 300) * 0.5})`;
    ctx.fillRect(azar(i + 301) * 512, azar(i + 302) * 256, 2 + azar(i + 303) * 5, 1 + azar(i + 304) * 2);
  }
  return texturaDe(c, renderer);
}

const COLOR_ETIQUETA = {
  OK: { fondo: PALETA.papel, texto: PALETA.negro },
  BAJO: { fondo: PALETA.senal, texto: PALETA.negro },
  AGOTADO: { fondo: PALETA.rojo, texto: '#ffffff' },
};

/** Etiqueta del larguero: código, nombre, código de barras y unidades, como la de la web. */
export function dibujarEtiqueta(ctx, p) {
  const W = 640;
  const H = 168;
  const color = COLOR_ETIQUETA[p.estado];
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = color.fondo;
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = PALETA.negro;
  ctx.lineWidth = 6;
  ctx.strokeRect(3, 3, W - 6, H - 6);

  ctx.fillStyle = color.texto;
  ctx.textBaseline = 'alphabetic';
  ctx.textAlign = 'left';
  fuente(ctx, 700, 34, MONO);
  ctx.fillText(recortar(ctx, p.codigo, 360), 24, 50);
  fuente(ctx, 600, 28, SANS);
  ctx.fillText(recortar(ctx, p.nombre, 380), 24, 88);

  const anchos = anchosCode128(p.codigo);
  if (anchos) {
    const total = anchos.reduce((a, b) => a + b, 0);
    const escala = Math.min(2, 360 / total);
    let x = 24;
    anchos.forEach((ancho, i) => {
      if (i % 2 === 0) ctx.fillRect(Math.round(x), 106, Math.max(1, Math.round(ancho * escala)), 44);
      x += ancho * escala;
    });
  }

  ctx.fillRect(424, 22, 4, H - 44);
  ctx.textAlign = 'right';
  fuente(ctx, 900, 92, SANS, true);
  ctx.fillText(fmtNum.format(p.stock_actual), W - 26, 112);
  fuente(ctx, 600, 22, MONO);
  ctx.fillText(p.estado === 'OK' ? 'UDS.' : p.estado === 'BAJO' ? 'BAJO MÍNIMO' : 'AGOTADO', W - 26, 146);
}

function dibujarCartelPasillo(ctx, letra, categoria, referencias) {
  const W = 1024;
  const H = 168;
  ctx.fillStyle = PALETA.negro;
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = PALETA.senal;
  ctx.fillRect(0, H - 14, W, 14);
  ctx.fillRect(22, 22, 110, 110);
  ctx.fillStyle = PALETA.negro;
  fuente(ctx, 900, 96, SANS, true);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(letra, 77, 82);
  ctx.textAlign = 'left';
  ctx.fillStyle = '#f4f2ec';
  fuente(ctx, 900, 84, SANS, true);
  ctx.fillText(recortar(ctx, categoria.toUpperCase(), 620), 160, 80);
  ctx.textAlign = 'right';
  ctx.fillStyle = PALETA.senal;
  fuente(ctx, 600, 26, MONO);
  ctx.fillText(`${referencias} REF.`, W - 30, 80);
}

/* ============================================================ La nave */

export async function crearNave(contenedor, { alElegir, alPasar }) {
  await esperarFuentes();

  const movil = esMovil();
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  // Sin tarjeta gráfica (muy común en Linux): modo ligero desde el principio, antes de compilar nada
  const software = renderizadoPorSoftware(renderer);
  renderer.setPixelRatio(densidadPixeles(movil, software));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.shadowMap.enabled = !movil && !software;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  // La nave casi siempre está quieta: las sombras se calculan solo cuando algo se mueve
  renderer.shadowMap.autoUpdate = false;
  renderer.domElement.className = 'nave3d__lienzo';
  renderer.domElement.setAttribute('aria-hidden', 'true');
  contenedor.prepend(renderer.domElement);

  const escena = new THREE.Scene();
  const camara = new THREE.PerspectiveCamera(36, 1, 0.1, 300);
  const controles = new OrbitControls(camara, renderer.domElement);
  controles.enableDamping = true;
  controles.dampingFactor = 0.08;
  controles.maxPolarAngle = Math.PI * 0.46;
  controles.minDistance = 2.5;
  controles.maxDistance = 45;
  controles.zoomSpeed = 0.8;
  controles.rotateSpeed = 0.6;

  /* ---------------------------------------------------- Materiales comunes */
  const tex = {
    hormigon: texturaHormigon(renderer),
    caja: texturaCaja(renderer),
    cinta: texturaCintaSeguridad(renderer),
    agotado: texturaAgotado(renderer),
    muelle: texturaMuelle(renderer),
  };
  const mat = {
    suelo: new THREE.MeshStandardMaterial({ map: tex.hormigon, roughness: 0.92 }),
    caja: new THREE.MeshStandardMaterial({ map: tex.caja, roughness: 0.82 }),
    madera: new THREE.MeshStandardMaterial({ color: PALETA.madera, roughness: 0.9 }),
    puntal: new THREE.MeshStandardMaterial({ color: PALETA.puntal, roughness: 0.55, metalness: 0.4 }),
    larguero: new THREE.MeshStandardMaterial({ color: PALETA.senal, roughness: 0.45, metalness: 0.2 }),
    linea: new THREE.MeshStandardMaterial({ color: PALETA.senal, roughness: 0.6 }),
    cinta: new THREE.MeshStandardMaterial({ map: tex.cinta, roughness: 0.7 }),
    agotado: new THREE.MeshStandardMaterial({ map: tex.agotado, roughness: 0.75, transparent: true }),
    muelle: new THREE.MeshStandardMaterial({ map: tex.muelle, roughness: 0.75, transparent: true }),
    cable: new THREE.MeshBasicMaterial({ color: '#55534e' }),
    lampara: new THREE.MeshStandardMaterial({ color: '#2a2a2a', emissive: '#fff1d6', emissiveIntensity: 0 }),
    contorno: new THREE.LineBasicMaterial({ color: PALETA.senal }),
    invisible: new THREE.MeshBasicMaterial({ visible: false }),
  };
  const geo = {
    caja: new RoundedBoxGeometry(M.caja.x, M.caja.y, M.caja.z, 2, 0.018),
    tabla: new THREE.BoxGeometry(0.2, 0.026, 1.0),
    taco: new THREE.BoxGeometry(1.25, 0.09, 0.1),
    puntal: new THREE.BoxGeometry(0.075, M.alturaPuntal, 0.075),
    riostra: new THREE.BoxGeometry(0.03, 0.03, M.fondo * 1.25),
    marca: new THREE.PlaneGeometry(1.32, 0.5),
    etiqueta: new THREE.PlaneGeometry(1.28, 1.28 * (168 / 640)),
    zona: new THREE.BoxGeometry(M.hueco, M.alturaLarguero + 0.1, M.fondo + 0.3),
  };
  geo.contorno = new THREE.EdgesGeometry(new THREE.BoxGeometry(M.hueco - 0.04, M.alturaLarguero + 0.06, M.fondo + 0.06));

  /* ---------------------------------------------------- Luces */
  const hemisferio = new THREE.HemisphereLight('#ffffff', '#999999', 1);
  escena.add(hemisferio);
  const sol = new THREE.DirectionalLight('#fff6e8', 2.5);
  sol.castShadow = true;
  sol.shadow.mapSize.set(2048, 2048);
  sol.shadow.bias = -0.0004;
  sol.shadow.normalBias = 0.02;
  escena.add(sol, sol.target);

  /* ---------------------------------------------------- Estado */
  let raiz = null;          // grupo con todo lo que depende de los datos
  let clave = '';
  const huecos = new Map(); // id → hueco
  const zonas = [];         // mallas invisibles para el raycasting
  const filasInfo = [];
  const lamparas = [];
  let encuadre = null;
  let primeraVez = true;
  let sucio = true;          // hay que volver a dibujar
  let sombrasSucias = true;  // hay que recalcular las sombras
  let sombrasCongeladas = false;
  let dibujoAnterior = false;

  const animaciones = new Set();
  function animar({ duracion, retraso = 0, curva = curvas.salida, alAvanzar, alTerminar, mueveObjetos = false }) {
    if (reducido()) duracion = 0;
    const a = { inicio: performance.now() + (reducido() ? 0 : retraso), duracion, curva, alAvanzar, alTerminar, mueveObjetos };
    animaciones.add(a);
    return a;
  }
  /** Devuelve true si alguna animación ha cambiado algo en este fotograma. */
  function avanzarAnimaciones(ahora) {
    let hubo = false;
    for (const a of animaciones) {
      if (ahora < a.inicio) continue;
      hubo = true;
      if (a.mueveObjetos) sombrasSucias = true;
      const k = a.duracion ? Math.min(1, (ahora - a.inicio) / a.duracion) : 1;
      a.alAvanzar?.(a.curva(k));
      if (k === 1) {
        animaciones.delete(a);
        a.alTerminar?.();
      }
    }
    return hubo;
  }

  /* ---------------------------------------------------- Construcción */

  const geoCajaPlana = geo.caja.toNonIndexed();
  const matriz = new THREE.Matrix4();
  const giroCaja = new THREE.Quaternion();
  const escalaUno = new THREE.Vector3(1, 1, 1);
  const ejeY = new THREE.Vector3(0, 1, 0);

  function colocacionCaja(hueco, indice) {
    const capa = Math.floor(indice / (REJILLA.x * REJILLA.z));
    const resto = indice % (REJILLA.x * REJILLA.z);
    const ix = resto % REJILLA.x;
    const iz = Math.floor(resto / REJILLA.x);
    const semilla = hueco.producto.id * 31 + indice;
    return {
      posicion: new THREE.Vector3(
        (ix - 1) * (M.caja.x + M.holgura) + (azar(semilla) - 0.5) * 0.03,
        M.palet + M.caja.y / 2 + capa * (M.caja.y + 0.004),
        (iz - 0.5) * (M.caja.z + M.holgura) + (azar(semilla + 3) - 0.5) * 0.03,
      ),
      giro: (azar(semilla + 5) - 0.5) * 0.07,
    };
  }

  /** Las cajas quietas de un hueco se fusionan en una malla: una sola llamada de dibujo por hueco. */
  function fijarPila(hueco, n) {
    hueco.n = n;
    hueco.pila.geometry.dispose();
    if (n === 0) {
      hueco.pila.geometry = new THREE.BufferGeometry();
      hueco.pila.visible = false;
    } else {
      const piezas = [];
      for (let i = 0; i < n; i++) {
        const { posicion, giro } = colocacionCaja(hueco, i);
        matriz.compose(posicion, giroCaja.setFromAxisAngle(ejeY, giro), escalaUno);
        piezas.push(geoCajaPlana.clone().applyMatrix4(matriz));
      }
      hueco.pila.geometry = mergeGeometries(piezas);
      for (const pieza of piezas) pieza.dispose();
      hueco.pila.visible = true;
    }
    sombrasSucias = true;
    sucio = true;
  }

  function cajaSuelta(hueco, indice) {
    const { posicion, giro } = colocacionCaja(hueco, indice);
    const caja = new THREE.Mesh(geo.caja, mat.caja);
    caja.castShadow = caja.receiveShadow = true;
    caja.position.copy(posicion);
    caja.rotation.y = giro;
    caja.userData.reposo = posicion.y;
    hueco.grupo.add(caja);
    return caja;
  }

  /** Deja caer las cajas [desde, hasta) y, cuando aterrizan todas, las incorpora a la pila. */
  function soltar(hueco, desde, hasta, retrasoBase, paso) {
    cerrarVuelo(hueco);
    fijarPila(hueco, desde);
    const sueltas = [];
    let pendientes = hasta - desde;
    for (let i = desde; i < hasta; i++) {
      const caja = cajaSuelta(hueco, i);
      sueltas.push(caja);
      caja.userData.animacion = dejarCaer(caja, retrasoBase + (i - desde) * paso, () => {
        pendientes -= 1;
        if (pendientes === 0) cerrarVuelo(hueco);
      });
    }
    hueco.vuelo = { sueltas, hasta };
  }

  function cerrarVuelo(hueco) {
    const vuelo = hueco.vuelo;
    if (!vuelo) return;
    hueco.vuelo = null;
    for (const caja of vuelo.sueltas) {
      animaciones.delete(caja.userData.animacion);
      caja.removeFromParent();
    }
    fijarPila(hueco, vuelo.hasta);
  }

  function nuevoPalet() {
    const palet = new THREE.Group();
    for (const z of [-0.43, 0, 0.43]) {
      const taco = new THREE.Mesh(geo.taco, mat.madera);
      taco.position.set(0, 0.045, z);
      taco.castShadow = taco.receiveShadow = true;
      palet.add(taco);
    }
    for (let i = 0; i < 6; i++) {
      const tabla = new THREE.Mesh(geo.tabla, mat.madera);
      tabla.position.set(-0.55 + i * 0.22, 0.103, 0);
      tabla.castShadow = tabla.receiveShadow = true;
      palet.add(tabla);
    }
    return palet;
  }

  function construir(productos) {
    if (raiz) {
      escena.remove(raiz);
      raiz.traverse((o) => {
        if (o.userData.pila) o.geometry.dispose();
        if (o.userData.propio) {
          o.material.map?.dispose();
          o.material.dispose();
        }
      });
    }
    huecos.clear();
    zonas.length = 0;
    filasInfo.length = 0;
    lamparas.length = 0;
    raiz = new THREE.Group();

    // Agrupar por categoría; las categorías largas se reparten en varias filas
    const porCategoria = new Map();
    for (const p of [...productos].sort((a, b) => a.categoria.localeCompare(b.categoria, 'es') || a.nombre.localeCompare(b.nombre, 'es'))) {
      if (!porCategoria.has(p.categoria)) porCategoria.set(p.categoria, []);
      porCategoria.get(p.categoria).push(p);
    }
    const filas = [];
    let letra = 0;
    for (const [categoria, lista] of porCategoria) {
      for (let i = 0; i < lista.length; i += M.huecosPorFila) {
        filas.push({ categoria, letra: String.fromCharCode(65 + (letra % 26)), productos: lista.slice(i, i + M.huecosPorFila), total: lista.length, continuacion: i > 0 });
      }
      letra++;
    }

    const anchoMaximo = Math.max(...filas.map((f) => f.productos.length * M.hueco), M.hueco * 3);
    filas.forEach((fila, f) => {
      const z = -f * M.separacionFilas;
      const ancho = fila.productos.length * M.hueco;
      const x0 = -ancho / 2;
      const grupoFila = new THREE.Group();
      grupoFila.position.set(0, 0, z);
      raiz.add(grupoFila);
      filasInfo.push({ categoria: fila.categoria, letra: fila.letra, centro: new THREE.Vector3(0, 0, z), ancho });

      // Puntales, riostras y largueros
      for (let i = 0; i <= fila.productos.length; i++) {
        const x = x0 + i * M.hueco;
        for (const lado of [-1, 1]) {
          const puntal = new THREE.Mesh(geo.puntal, mat.puntal);
          puntal.position.set(x, M.alturaPuntal / 2, lado * M.fondo / 2);
          puntal.castShadow = true;
          grupoFila.add(puntal);
        }
        for (const [y, giro] of [[0.55, 0.62], [1.35, -0.62]]) {
          const riostra = new THREE.Mesh(geo.riostra, mat.puntal);
          riostra.position.set(x, y, 0);
          riostra.rotation.x = giro;
          grupoFila.add(riostra);
        }
      }
      const geoLarguero = new THREE.BoxGeometry(ancho + 0.08, 0.11, 0.055);
      for (const y of [0.16, M.alturaLarguero]) {
        for (const lado of [-1, 1]) {
          const larguero = new THREE.Mesh(geoLarguero, mat.larguero);
          larguero.position.set(0, y, lado * (M.fondo / 2 + 0.035));
          larguero.castShadow = true;
          grupoFila.add(larguero);
        }
      }

      // Línea de pasillo pintada en el suelo
      const linea = new THREE.Mesh(new THREE.PlaneGeometry(ancho + 1.2, 0.09), mat.linea);
      linea.rotation.x = -Math.PI / 2;
      linea.position.set(0, 0.003, M.fondo / 2 + 1.35);
      linea.receiveShadow = true;
      grupoFila.add(linea);

      // Cartel colgado del techo
      const { c, ctx } = lienzo(1024, 168);
      dibujarCartelPasillo(ctx, fila.letra, fila.continuacion ? `${fila.categoria} (cont.)` : fila.categoria, fila.total);
      const cartelAncho = Math.min(Math.max(ancho * 0.6, 2.6), 4);
      const cartel = new THREE.Mesh(
        new THREE.PlaneGeometry(cartelAncho, cartelAncho * (168 / 1024)),
        new THREE.MeshStandardMaterial({ map: texturaDe(c, renderer), roughness: 0.6 }),
      );
      cartel.userData.propio = true;
      cartel.userData.fijo = false;
      cartel.position.set(0, 3.15, M.fondo / 2 - 0.1);
      cartel.castShadow = true;
      grupoFila.add(cartel);
      for (const lado of [-1, 1]) {
        const cable = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 1.2), mat.cable);
        cable.position.set(lado * cartelAncho * 0.42, 3.15 + cartelAncho * (84 / 1024) + 0.6, M.fondo / 2 - 0.1);
        grupoFila.add(cable);
      }

      // Lámpara del pasillo (solo luce en el turno de noche)
      const lampara = new THREE.Mesh(new THREE.BoxGeometry(Math.min(ancho * 0.8, 4), 0.04, 0.12), mat.lampara);
      lampara.position.set(0, 3.9, 0.2);
      grupoFila.add(lampara);
      const luz = new THREE.PointLight('#ffe2b0', 0, 12, 1.4);
      luz.position.set(0, 3.7, 0.9);
      grupoFila.add(luz);
      lampara.userData.fijo = false;
      lamparas.push({ luz, lampara });

      // Huecos
      fila.productos.forEach((p, i) => {
        const grupo = new THREE.Group();
        grupo.position.set(x0 + (i + 0.5) * M.hueco, 0, 0);
        grupoFila.add(grupo);
        grupo.add(nuevoPalet());

        const { c: lienzoEtiqueta, ctx: ctxEtiqueta } = lienzo(640, 168);
        const texturaEtiqueta = texturaDe(lienzoEtiqueta, renderer);
        const etiqueta = new THREE.Mesh(geo.etiqueta, new THREE.MeshStandardMaterial({ map: texturaEtiqueta, roughness: 0.5 }));
        etiqueta.userData.propio = true;
        etiqueta.position.set(0, M.alturaLarguero + 0.01, M.fondo / 2 + 0.066);
        grupo.add(etiqueta);

        const marca = new THREE.Mesh(geo.marca, mat.cinta);
        marca.rotation.x = -Math.PI / 2;
        marca.position.set(0, 0.004, M.fondo / 2 + 0.55);
        marca.receiveShadow = true;
        grupo.add(marca);

        const contorno = new THREE.LineSegments(geo.contorno, mat.contorno);
        contorno.position.set(0, (M.alturaLarguero + 0.06) / 2, 0);
        contorno.visible = false;
        grupo.add(contorno);

        const zona = new THREE.Mesh(geo.zona, mat.invisible);
        zona.position.set(0, (M.alturaLarguero + 0.1) / 2, 0.15);
        zona.userData.productoId = p.id;
        grupo.add(zona);
        zonas.push(zona);

        const pila = new THREE.Mesh(new THREE.BufferGeometry(), mat.caja);
        pila.castShadow = pila.receiveShadow = true;
        pila.userData.fijo = false;
        pila.userData.pila = true;
        grupo.add(pila);
        etiqueta.userData.fijo = false;
        marca.userData.fijo = false;

        const hueco = { producto: p, grupo, n: 0, pila, vuelo: null, etiqueta, ctxEtiqueta, texturaEtiqueta, marca, contorno, fila: f };
        huecos.set(p.id, hueco);
        pintarHueco(hueco, p);
      });
    });

    // Muelle de carga delante del primer pasillo
    const muelle = new THREE.Mesh(new THREE.PlaneGeometry(4, 2), mat.muelle);
    muelle.rotation.x = -Math.PI / 2;
    muelle.position.set(-anchoMaximo / 2 + 1.6, 0.004, M.fondo / 2 + 3.6);
    raiz.add(muelle);

    // Suelo
    const fondoEscena = (filas.length - 1) * M.separacionFilas;
    const tam = Math.max(anchoMaximo, fondoEscena) * 3 + 40;
    const suelo = new THREE.Mesh(new THREE.PlaneGeometry(tam, tam), mat.suelo);
    suelo.rotation.x = -Math.PI / 2;
    suelo.position.set(0, 0, -fondoEscena / 2);
    suelo.receiveShadow = true;
    tex.hormigon.repeat.set(tam / 6, tam / 6);
    raiz.add(suelo);

    // Puntales, largueros, palés, suelo… todo lo quieto pasa a ser unas pocas mallas
    fusionarEstaticos(raiz);
    escena.add(raiz);
    sombrasSucias = true;
    sucio = true;

    // Encuadre general y sombras ajustadas al tamaño de la nave
    const centro = new THREE.Vector3(0, 0.7, -fondoEscena / 2);
    const radio = Math.max(anchoMaximo * 0.62, fondoEscena * 0.75, 5);
    encuadre = { centro, radio, anchoMaximo, fondoEscena };
    sol.position.set(centro.x + radio * 0.8, 14, centro.z + radio * 0.9);
    sol.target.position.copy(centro);
    const s = radio * 1.6;
    Object.assign(sol.shadow.camera, { left: -s, right: s, top: s, bottom: -s, near: 1, far: 60 });
    sol.shadow.camera.updateProjectionMatrix();
    escena.fog = new THREE.Fog(AMBIENTES[tema()].fondo, radio * 2.6, radio * 6.5);
    aplicarAmbiente();
  }

  /** Etiqueta, marca del suelo y cajas de un hueco según los datos de su producto. */
  function pintarHueco(hueco, p, { animarCajas = false, retrasoBase = 0 } = {}) {
    const anterior = hueco.producto;
    hueco.producto = p;
    dibujarEtiqueta(hueco.ctxEtiqueta, p);
    hueco.texturaEtiqueta.needsUpdate = true;

    hueco.marca.visible = p.estado !== 'OK';
    hueco.marca.material = p.estado === 'AGOTADO' ? mat.agotado : mat.cinta;

    sucio = true;

    const objetivo = cajasPara(p);
    cerrarVuelo(hueco);
    const actuales = hueco.n;
    if (animarCajas && objetivo > actuales) {
      soltar(hueco, actuales, objetivo, retrasoBase, 70);
    } else if (animarCajas && objetivo < actuales) {
      fijarPila(hueco, objetivo);
      for (let i = actuales - 1, n = 0; i >= objetivo; i--, n++) sacar(cajaSuelta(hueco, i), hueco, n * 70);
    } else {
      fijarPila(hueco, objetivo);
      if (animarCajas && anterior && anterior.stock_actual !== p.stock_actual) latido(hueco.etiqueta);
    }
    if (animarCajas && objetivo !== actuales) latido(hueco.etiqueta, 300);
  }

  function dejarCaer(caja, retraso, alTerminar) {
    const reposo = caja.userData.reposo;
    const altura = 2.6 + azar(caja.id) * 0.8;
    caja.position.y = reposo + altura;
    caja.visible = false;
    return animar({
      duracion: 750,
      retraso,
      curva: curvas.rebote,
      mueveObjetos: true,
      alAvanzar: (k) => {
        caja.visible = true;
        caja.position.y = reposo + altura * (1 - k);
      },
      alTerminar,
    });
  }

  function sacar(caja, hueco, retraso) {
    const inicio = caja.position.clone();
    animar({
      duracion: 650,
      retraso,
      curva: curvas.suave,
      mueveObjetos: true,
      alAvanzar: (k) => {
        caja.position.set(inicio.x, inicio.y + Math.sin(k * Math.PI) * 0.5 + k * 0.2, inicio.z + k * 2.2);
        caja.scale.setScalar(1 - k * 0.85);
      },
      alTerminar: () => hueco.grupo.remove(caja),
    });
  }

  function latido(malla, retraso = 0) {
    animar({ duracion: 420, retraso, curva: (k) => k, alAvanzar: (k) => malla.scale.setScalar(1 + Math.sin(k * Math.PI) * 0.12) });
  }

  /* ---------------------------------------------------- Cámara */

  function encuadreGeneral() {
    const { centro, radio } = encuadre;
    // En pantallas verticales la cámara se pone más de frente y más lejos para que quepan todos los pasillos
    const vertical = camara.aspect < 1;
    const direccion = new THREE.Vector3(vertical ? 0.22 : 0.48, vertical ? 0.62 : 0.5, 1).normalize();
    const distancia = radio * (vertical ? 3.3 : 1.62);
    return { posicion: centro.clone().addScaledVector(direccion, distancia), objetivo: centro.clone() };
  }

  let vuelo = null;
  function volar({ posicion, objetivo }, duracion = 1100) {
    if (software) duracion = 0;
    if (vuelo) animaciones.delete(vuelo);
    const desde = camara.position.clone();
    const mirarDesde = controles.target.clone();
    controles.enabled = false;
    vuelo = animar({
      duracion,
      curva: curvas.suave,
      alAvanzar: (k) => {
        camara.position.lerpVectors(desde, posicion, k);
        controles.target.lerpVectors(mirarDesde, objetivo, k);
        camara.lookAt(controles.target);
      },
      alTerminar: () => {
        controles.enabled = true;
        vuelo = null;
      },
    });
  }

  function posicionHueco(id) {
    const hueco = huecos.get(id);
    if (!hueco) return null;
    return hueco.grupo.getWorldPosition(new THREE.Vector3());
  }

  /* ---------------------------------------------------- Ambiente (claro/oscuro) */

  function tema() {
    const forzado = document.documentElement.dataset.tema;
    if (forzado === 'claro' || forzado === 'oscuro') return forzado;
    return matchMedia('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro';
  }

  function aplicarAmbiente() {
    const a = AMBIENTES[tema()];
    escena.background = new THREE.Color(a.fondo);
    if (escena.fog) escena.fog.color.set(a.fondo);
    mat.suelo.color.set(a.suelo);
    hemisferio.color.set(a.cielo);
    hemisferio.groundColor.set(a.tierra);
    hemisferio.intensity = a.hemisferio;
    sol.intensity = a.sol;
    renderer.toneMappingExposure = a.exposicion;
    mat.lampara.emissiveIntensity = a.lamparas ? 2.2 : 0;
    for (const { luz, lampara } of lamparas) {
      luz.intensity = a.lamparas ? 18 : 0;
      lampara.visible = a.lamparas;
    }
    sucio = true;
  }

  const observadorTema = new MutationObserver(aplicarAmbiente);
  observadorTema.observe(document.documentElement, { attributes: true, attributeFilter: ['data-tema'] });
  const consultaOscuro = matchMedia('(prefers-color-scheme: dark)');
  consultaOscuro.addEventListener('change', aplicarAmbiente);

  /* ---------------------------------------------------- Puntero */

  const rayo = new THREE.Raycaster();
  const puntero = new THREE.Vector2();
  let punteroPendiente = null;
  let resaltado = null;
  let pulsacion = null;

  function huecoBajo(evento) {
    const r = renderer.domElement.getBoundingClientRect();
    puntero.set(((evento.clientX - r.left) / r.width) * 2 - 1, -((evento.clientY - r.top) / r.height) * 2 + 1);
    rayo.setFromCamera(puntero, camara);
    const [impacto] = rayo.intersectObjects(zonas, false);
    return impacto ? huecos.get(impacto.object.userData.productoId) : null;
  }

  function resaltar(hueco, evento) {
    if (resaltado !== hueco) sucio = true;
    if (resaltado && resaltado !== hueco) resaltado.contorno.visible = false;
    resaltado = hueco;
    if (hueco) hueco.contorno.visible = true;
    renderer.domElement.style.cursor = hueco ? 'pointer' : '';
    alPasar?.(hueco ? hueco.producto : null, evento);
  }

  renderer.domElement.addEventListener('pointermove', (e) => { punteroPendiente = e; });
  renderer.domElement.addEventListener('pointerleave', (e) => {
    punteroPendiente = null;
    resaltar(null, e);
  });
  renderer.domElement.addEventListener('pointerdown', (e) => { pulsacion = { x: e.clientX, y: e.clientY, t: performance.now() }; });
  renderer.domElement.addEventListener('pointerup', (e) => {
    if (!pulsacion) return;
    const movido = Math.hypot(e.clientX - pulsacion.x, e.clientY - pulsacion.y);
    const rapido = performance.now() - pulsacion.t < 450;
    pulsacion = null;
    if (movido > 6 || !rapido) return;
    const hueco = huecoBajo(e);
    if (hueco) alElegir?.(hueco.producto.id);
  });

  /* ---------------------------------------------------- Bucle */

  function ajustarTamano() {
    const { clientWidth: w, clientHeight: h } = contenedor;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camara.aspect = w / h;
    camara.updateProjectionMatrix();
    sucio = true;
  }
  const observadorTamano = new ResizeObserver(ajustarTamano);
  observadorTamano.observe(contenedor);
  ajustarTamano();

  const anotarFotograma = vigilarRendimiento((nivel) => {
    bajarCalidad(renderer, nivel);
    sombrasCongeladas = true;
    sucio = true;
  });

  function fotograma(ahora) {
    if (avanzarAnimaciones(ahora)) sucio = true;
    if (controles.enabled && controles.update()) sucio = true;
    if (punteroPendiente) {
      const e = punteroPendiente;
      punteroPendiente = null;
      resaltar(huecoBajo(e), e);
    }
    // Con un diálogo delante (o el cajón en un equipo lento) no se dibuja: el navegador
    // queda libre para el formulario. La escena se pone al día al cerrarlo.
    const tapada = dialogoTapando() || (software && document.querySelector('dialog.cajon[open]'));
    if (!sucio || tapada) {
      dibujoAnterior = false;
      return;
    }
    sucio = false;
    if (sombrasSucias && !sombrasCongeladas && renderer.shadowMap.enabled) renderer.shadowMap.needsUpdate = true;
    sombrasSucias = false;
    renderer.render(escena, camara);
    anotarFotograma(ahora, dibujoAnterior);
    dibujoAnterior = true;
  }

  /* ---------------------------------------------------- API pública */

  return {
    actualizar(productos) {
      const nuevaClave = productos.map((p) => `${p.id}:${p.categoria}`).sort().join('|');
      if (nuevaClave !== clave) {
        clave = nuevaClave;
        const habiaNave = Boolean(raiz);
        construir(productos);
        if (!habiaNave) {
          const general = encuadreGeneral();
          if (primeraVez && !reducido() && !software) {
            // Entrada: la cámara baja desde lo alto mientras se colocan las cajas
            camara.position.copy(general.posicion).add(new THREE.Vector3(encuadre.radio * 0.6, encuadre.radio * 1.4, encuadre.radio * 0.9));
            controles.target.copy(general.objetivo);
            camara.lookAt(controles.target);
            volar(general, 1900);
            let orden = 0;
            for (const hueco of huecos.values()) soltar(hueco, 0, hueco.n, 250 + orden++ * 90, 22);
          } else {
            camara.position.copy(general.posicion);
            controles.target.copy(general.objetivo);
          }
          primeraVez = false;
        }
        return;
      }
      let orden = 0;
      for (const p of productos) {
        const hueco = huecos.get(p.id);
        const a = hueco.producto;
        const cambia = a.stock_actual !== p.stock_actual || a.estado !== p.estado || a.nombre !== p.nombre || a.codigo !== p.codigo || a.stock_minimo !== p.stock_minimo;
        if (cambia) pintarHueco(hueco, p, { animarCajas: !software, retrasoBase: orden++ * 120 });
      }
    },

    enfocar(id, { dejarSitioDerecha = false } = {}) {
      const pos = posicionHueco(id);
      if (!pos) return;
      const objetivo = pos.clone().add(new THREE.Vector3(0, 0.9, 0));
      const desplazamiento = dejarSitioDerecha ? new THREE.Vector3(1.4, 0, 0) : new THREE.Vector3();
      volar({
        posicion: objetivo.clone().add(new THREE.Vector3(1.3, 1.1, 4.2)).add(desplazamiento),
        objetivo: objetivo.add(desplazamiento),
      });
    },

    irAPasillo(indice) {
      const fila = filasInfo[indice];
      if (!fila) return;
      const objetivo = fila.centro.clone().add(new THREE.Vector3(0, 1, 0));
      const distancia = Math.max(fila.ancho * (camara.aspect < 1 ? 1.5 : 0.85), 5.5);
      volar({ posicion: objetivo.clone().add(new THREE.Vector3(distancia * 0.35, distancia * 0.32, distancia)), objetivo });
    },

    vistaGeneral() {
      if (encuadre) volar(encuadreGeneral());
    },

    pasillos: () => filasInfo.map(({ categoria, letra }) => ({ categoria, letra })),

    /** true si el navegador dibuja sin tarjeta gráfica. */
    modoLigero: software,

    /** Fuerza un redibujado (por ejemplo, al cerrar un diálogo). */
    redibujar() {
      sucio = true;
    },

    reanudar() {
      ajustarTamano();
      sucio = true;
      renderer.setAnimationLoop(fotograma);
    },

    pausar() {
      renderer.setAnimationLoop(null);
      resaltar(null, null);
    },
  };
}
