// Almacén · libro de existencias. Cliente web sin dependencias (la nave 3D usa Three.js, incluido en /vendor).

import { anchosCode128 } from './code128.js';

/* =========================================================== Utilidades */

const $ = (selector, raiz = document) => raiz.querySelector(selector);
const $$ = (selector, raiz = document) => [...raiz.querySelectorAll(selector)];

const fmt = {
  eur: new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' }),
  num: new Intl.NumberFormat('es-ES'),
  fecha: new Intl.DateTimeFormat('es-ES', { day: '2-digit', month: 'short', year: 'numeric' }),
  fechaCorta: new Intl.DateTimeFormat('es-ES', { day: '2-digit', month: '2-digit', year: '2-digit' }),
  hora: new Intl.DateTimeFormat('es-ES', { hour: '2-digit', minute: '2-digit' }),
  diaLargo: new Intl.DateTimeFormat('es-ES', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }),
  relativa: new Intl.RelativeTimeFormat('es', { numeric: 'auto' }),
};

const conSigno = (n) => (n > 0 ? `+${fmt.num.format(n)}` : `−${fmt.num.format(Math.abs(n))}`);
const unidades = (n) => `${fmt.num.format(n)} ${n === 1 ? 'ud.' : 'uds.'}`;
const numeroAlbaran = (id) => String(id).padStart(6, '0');
const movimientoReducido = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const esperar = (ms) => new Promise((resolver) => setTimeout(resolver, ms));

function haceCuanto(iso) {
  const segundos = (new Date(iso) - Date.now()) / 1000;
  const escalas = [['year', 31536000], ['month', 2592000], ['week', 604800], ['day', 86400], ['hour', 3600], ['minute', 60]];
  for (const [unidad, s] of escalas) {
    if (Math.abs(segundos) >= s) return fmt.relativa.format(Math.round(segundos / s), unidad);
  }
  return 'ahora mismo';
}

function debounce(funcion, ms) {
  let temporizador;
  return (...args) => {
    clearTimeout(temporizador);
    temporizador = setTimeout(() => funcion(...args), ms);
  };
}

function leerPreferencia(clave, permitidos, defecto) {
  try {
    const valor = localStorage.getItem(clave);
    return permitidos.includes(valor) ? valor : defecto;
  } catch {
    return defecto;
  }
}

function guardarPreferencia(clave, valor) {
  try { localStorage.setItem(clave, valor); } catch { /* sin almacenamiento: vale solo para esta sesión */ }
}

/* Plantillas HTML que escapan por defecto todo lo que se interpola (evita XSS) */

class HTMLSeguro {
  constructor(texto) { this.texto = texto; }
}

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

function aHTML(valor) {
  if (valor instanceof HTMLSeguro) return valor.texto;
  if (Array.isArray(valor)) return valor.map(aHTML).join('');
  if (valor === null || valor === undefined || valor === false) return '';
  return String(valor).replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

function html(partes, ...valores) {
  return new HTMLSeguro(partes.reduce((acc, parte, i) => acc + aHTML(valores[i - 1]) + parte));
}

const pintar = (elemento, contenido) => { elemento.innerHTML = aHTML(contenido); };

/* ============================================================== Iconos */

// Trazos del set Lucide (ISC), todos a 24×24 y grosor 2
const ICONOS = {
  caja: '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
  albaran: '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M8 7h8M8 11h8M8 15h5"/>',
  mas: '<path d="M12 5v14M5 12h14"/>',
  lapiz: '<path d="M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5z"/><path d="m15 5 4 4"/>',
  archivar: '<rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>',
  imprimir: '<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect width="12" height="8" x="6" y="14"/>',
  buscar: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  descargar: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
  cerrar: '<path d="M18 6 6 18M6 6l12 12"/>',
  recuento: '<rect width="8" height="4" x="8" y="2" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
  alerta: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  entrada: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
  salida: '<path d="M12 21V9"/><path d="m17 14-5-5-5 5"/><path d="M5 3h14"/>',
  flecha: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  etiquetas: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  lista: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  tema: '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" style="fill:currentColor"/>',
  sol: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2m-7.07-2.93 1.41-1.41M17.66 6.34l1.41-1.41M2 12h2m16 0h2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41"/>',
  luna: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
};

const icono = (nombre) => new HTMLSeguro(`<svg class="icono" viewBox="0 0 24 24" aria-hidden="true">${ICONOS[nombre]}</svg>`);

/* ================================================== Código de barras */

/** Código de barras Code 128-B real (escaneable) en SVG. Devuelve '' si el texto no es ASCII imprimible. */
function codigoBarras(texto) {
  const anchos = anchosCode128(texto);
  if (!anchos) return '';
  const zonaMuda = 10;
  let x = zonaMuda;
  let barras = '';
  anchos.forEach((ancho, i) => {
    if (i % 2 === 0) barras += `<rect x="${x}" width="${ancho}" height="1"/>`;
    x += ancho;
  });
  return new HTMLSeguro(`<svg class="barras" viewBox="0 0 ${x + zonaMuda} 1" preserveAspectRatio="none" aria-hidden="true">${barras}</svg>`);
}

/* ============================================================== API */

class ErrorApi extends Error {
  constructor(mensaje, campo) {
    super(mensaje);
    this.campo = campo;
  }
}

async function peticion(metodo, ruta, cuerpo) {
  const opciones = { method: metodo, headers: { Accept: 'application/json' } };
  if (cuerpo !== undefined) {
    opciones.headers['Content-Type'] = 'application/json';
    opciones.body = JSON.stringify(cuerpo);
  }
  let respuesta;
  try {
    respuesta = await fetch(ruta, opciones);
  } catch {
    throw new ErrorApi('No hay conexión con el servidor. Comprueba que «python3 app.py» sigue en marcha.');
  }
  const datos = respuesta.status === 204 ? null : await respuesta.json().catch(() => null);
  if (respuesta.status === 401 && ruta !== '/api/sesion') {
    // La sesión ha caducado: a la pantalla de acceso, recordando dónde estaba
    location.replace(`/login.html?volver=${encodeURIComponent(location.hash || '#nave')}`);
    throw new ErrorApi('Tu sesión ha caducado. Vuelve a entrar.');
  }
  if (!respuesta.ok) throw new ErrorApi(datos?.error ?? `Error ${respuesta.status} del servidor`, datos?.campo);
  return datos;
}

const consulta = (filtros) => {
  const params = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v !== '' && v != null));
  return params.size ? `?${params}` : '';
};

const api = {
  sesion: () => peticion('GET', '/api/sesion'),
  cerrarSesion: () => peticion('DELETE', '/api/sesion'),
  resumen: () => peticion('GET', '/api/resumen'),
  categorias: () => peticion('GET', '/api/categorias'),
  productos: (filtros = {}) => peticion('GET', `/api/productos${consulta(filtros)}`),
  producto: (id) => peticion('GET', `/api/productos/${id}`),
  crearProducto: (datos) => peticion('POST', '/api/productos', datos),
  actualizarProducto: (id, datos) => peticion('PUT', `/api/productos/${id}`, datos),
  darDeBaja: (id) => peticion('DELETE', `/api/productos/${id}`),
  movimientos: (filtros = {}) => peticion('GET', `/api/movimientos${consulta(filtros)}`),
  registrarMovimiento: (datos) => peticion('POST', '/api/movimientos', datos),
};

/* ============================================================== Estado */

const estado = {
  usuario: null,
  filtrosExistencias: { q: '', categoria: '', estado: '' },
  filtrosMovimientos: { producto_id: '', tipo: '' },
  vistaExistencias: leerPreferencia('inventario.vista', ['etiquetas', 'lista'], 'etiquetas'),
  productosMovimiento: new Map(),
  productoEditando: null,
  fichaId: null,
  fichaProducto: null,
  panelContado: false,
  estanteriaColocada: false,
  turnos: { existencias: 0, movimientos: 0, ficha: 0 },
};

const ESTADOS_STOCK = {
  OK: { texto: 'En stock', clase: 'ok' },
  BAJO: { texto: 'Bajo mínimo', clase: 'bajo' },
  AGOTADO: { texto: 'Agotado', clase: 'agotado' },
};

const TIPOS_MOVIMIENTO = {
  ENTRADA: {
    nombre: 'Entrada', corto: 'ENT', clase: 'entrada', icono: 'entrada',
    titulo: 'Albarán de entrada', antetitulo: 'Llega mercancía al almacén',
    etiquetaCantidad: 'Unidades que entran', boton: 'Registrar entrada', sello: 'Recibido',
    motivos: ['Compra a proveedor', 'Devolución de cliente', 'Traspaso desde otro almacén'],
  },
  SALIDA: {
    nombre: 'Salida', corto: 'SAL', clase: 'salida', icono: 'salida',
    titulo: 'Albarán de salida', antetitulo: 'Sale mercancía del almacén',
    etiquetaCantidad: 'Unidades que salen', boton: 'Registrar salida', sello: 'Expedido',
    motivos: ['Venta', 'Consumo interno', 'Merma o rotura', 'Devolución a proveedor'],
  },
  AJUSTE: {
    nombre: 'Recuento', corto: 'REC', clase: 'ajuste', icono: 'recuento',
    titulo: 'Hoja de recuento', antetitulo: 'Inventario físico',
    etiquetaCantidad: 'Unidades contadas en la estantería', boton: 'Ajustar al recuento', sello: 'Contado',
    motivos: ['Inventario físico', 'Corrección de un error'],
  },
};

/* ============================================================ Avisos */

function avisar(mensaje, tipo = 'ok') {
  const aviso = document.createElement('div');
  aviso.className = `aviso aviso--${tipo}`;
  if (tipo === 'error') aviso.setAttribute('role', 'alert');
  pintar(aviso, html`${icono(tipo === 'error' ? 'alerta' : 'check')}<span>${mensaje}</span>`);
  $('#avisos').append(aviso);
  setTimeout(() => {
    aviso.classList.add('aviso--saliendo');
    setTimeout(() => aviso.remove(), 200);
  }, tipo === 'error' ? 6000 : 4000);
}

/* ===================================================== Piezas de interfaz */

const etiquetaCodigo = (codigo, grande = false) => html`<span class="codigo ${grande ? 'codigo--grande' : ''}">${codigo}</span>`;

function insigniaEstado(codigo) {
  const e = ESTADOS_STOCK[codigo];
  return html`<span class="insignia insignia--${e.clase}">${e.texto}</span>`;
}

const selloTipo = (tipo) => {
  const t = TIPOS_MOVIMIENTO[tipo];
  return html`<span class="sello-mini sello-mini--${t.clase}">${t.nombre}</span>`;
};

/** Medidor de cajas: el 100 % es el doble del mínimo; la raya roja marca el mínimo. */
function medidor(p, { cajas = 14, compacto = false } = {}) {
  const referencia = Math.max(p.stock_minimo * 2, p.stock_actual, 1);
  const llenas = p.stock_actual === 0 ? 0 : Math.max(1, Math.round((p.stock_actual / referencia) * cajas));
  const cajaMinimo = p.stock_minimo > 0 ? Math.round((p.stock_minimo / referencia) * cajas) - 1 : -1;
  const segmentos = Array.from({ length: cajas }, (_, i) => {
    const clases = ['medidor__caja', i < llenas && 'medidor__caja--llena', i === cajaMinimo && 'medidor__caja--minimo'].filter(Boolean).join(' ');
    return html`<span class="${clases}"></span>`;
  });
  const descripcion = `${unidades(p.stock_actual)} de un mínimo de ${p.stock_minimo}. ${ESTADOS_STOCK[p.estado].texto}`;
  return html`<div class="medidor medidor--${ESTADOS_STOCK[p.estado].clase} ${compacto ? 'medidor--compacto' : ''}" role="img" aria-label="${descripcion}">${segmentos}</div>`;
}

function etiquetaEstanteria(p, { interactiva = true, indice = 0 } = {}) {
  const estadoStock = ESTADOS_STOCK[p.estado];
  const nombre = interactiva
    ? html`<button class="enlace-ficha" type="button" data-accion="ficha" data-id="${p.id}">${p.nombre}</button>`
    : p.nombre;
  return html`
    <article class="etiqueta-estanteria etiqueta-estanteria--${estadoStock.clase}" style="--i:${indice}">
      <div class="etiqueta-estanteria__banda"><span>${estadoStock.texto}</span></div>
      <header class="etiqueta-estanteria__cabecera">
        ${etiquetaCodigo(p.codigo)}
        <span class="etiqueta-estanteria__categoria">${p.categoria}</span>
      </header>
      <h3 class="etiqueta-estanteria__nombre">${nombre}</h3>
      ${codigoBarras(p.codigo)}
      <div class="etiqueta-estanteria__stock">
        <p class="cifra"><strong>${fmt.num.format(p.stock_actual)}</strong><span>${p.stock_actual === 1 ? 'ud.' : 'uds.'}</span></p>
        ${medidor(p)}
        <dl class="etiqueta-estanteria__datos">
          <div><dt>Mín.</dt><dd>${fmt.num.format(p.stock_minimo)}</dd></div>
          <div><dt>Precio</dt><dd>${fmt.eur.format(p.precio)}</dd></div>
          <div><dt>Valor</dt><dd>${fmt.eur.format(p.valor)}</dd></div>
        </dl>
      </div>
      ${interactiva ? html`
        <footer class="etiqueta-estanteria__acciones">
          <button class="boton boton--pequeno boton--entrada" type="button" data-accion="entrada" data-id="${p.id}"
            aria-label="Registrar entrada de ${p.nombre}">${icono('entrada')}Entrada</button>
          <button class="boton boton--pequeno boton--salida" type="button" data-accion="salida" data-id="${p.id}"
            aria-label="Registrar salida de ${p.nombre}" ${p.stock_actual === 0 ? new HTMLSeguro('disabled') : ''}>${icono('salida')}Salida</button>
        </footer>` : ''}
      ${p.estado === 'AGOTADO' ? html`<span class="sello-agotado" aria-hidden="true">Agotado</span>` : ''}
    </article>`;
}

function fechaMovimiento(iso) {
  const fecha = new Date(iso);
  return html`<time class="fecha" datetime="${iso}">${haceCuanto(iso)}<small>${fmt.fecha.format(fecha)} · ${fmt.hora.format(fecha)}</small></time>`;
}

const saldoPaso = (m) =>
  html`<span class="saldo-paso">${fmt.num.format(m.stock_anterior)} → <strong>${fmt.num.format(m.stock_resultante)}</strong></span>`;

function estadoVacio({ icono: nombreIcono = 'caja', titulo, texto, accion, tono = '', compacto = false }) {
  return html`
    <div class="vacio ${tono ? `vacio--${tono}` : ''} ${compacto ? 'vacio--compacto' : ''}">
      <span class="vacio__icono">${icono(nombreIcono)}</span>
      <strong>${titulo}</strong>
      ${texto ? html`<p>${texto}</p>` : ''}
      ${accion ?? ''}
    </div>`;
}

function contar(elemento, destino, formato, retraso = 0) {
  if (movimientoReducido()) {
    elemento.textContent = formato(destino);
    return;
  }
  const duracion = 750;
  let inicio = null;
  const paso = (t) => {
    inicio ??= t + retraso;
    const k = Math.min(1, Math.max(0, (t - inicio) / duracion));
    elemento.textContent = formato(destino * (1 - (1 - k) ** 3));
    if (k < 1) requestAnimationFrame(paso);
  };
  elemento.textContent = formato(0);
  requestAnimationFrame(paso);
}

/* ================================================================ Vistas */

const VISTAS = { nave: 'La nave', panel: 'Panel', existencias: 'Existencias', movimientos: 'Libro de movimientos' };

const vistaActual = () => {
  const vista = location.hash.slice(1);
  return vista in VISTAS ? vista : 'nave';
};

function mostrarVista() {
  const vista = vistaActual();
  document.body.dataset.vista = vista;
  if (vista !== 'nave') nave?.pausar();
  $$('.vista').forEach((s) => { s.hidden = s.dataset.vista !== vista; });
  $$('.pasillos a').forEach((a) => {
    if (a.dataset.vista === vista) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
  document.title = `${VISTAS[vista]} · Almacén`;
  return refrescar(vista);
}

function irA(vista) {
  if (vista !== vistaActual()) history.pushState(null, '', `#${vista}`);
  return mostrarVista();
}

async function refrescar(vista = vistaActual()) {
  try {
    const cargas = { nave: cargarNave, panel: cargarPanel, existencias: cargarExistencias, movimientos: cargarMovimientos };
    await Promise.all([cargas[vista](), estado.fichaId ? cargarFicha(estado.fichaId) : null]);
  } catch (error) {
    avisar(error.message, 'error');
  }
}

/* ---------------------------------------------------- 01 · Nave en 3D */

let nave = null;
let naveCargando = null;

/** Importa Three.js y monta la escena solo la primera vez que se abre la nave. */
function prepararNave() {
  naveCargando ??= import('./nave.js')
    .then(({ crearNave }) => crearNave($('#nave3d'), {
      alElegir: (id) => {
        nave.enfocar(id, { dejarSitioDerecha: innerWidth > 900 });
        abrirFicha(id).catch((error) => avisar(error.message, 'error'));
      },
      alPasar: mostrarFichaFlotante,
    }))
    .then((instancia) => {
      nave = instancia;
      return instancia;
    })
    .catch((error) => {
      naveCargando = null;
      throw error;
    });
  return naveCargando;
}

const letraPasillo = (i) => String.fromCharCode(65 + (i % 26));

function categoriasOrdenadas(productos) {
  return [...new Set(productos.map((p) => p.categoria))].sort((a, b) => a.localeCompare(b, 'es'));
}

async function cargarNave() {
  const [productos, r] = await Promise.all([api.productos(), api.resumen()]);
  const avisos = r.bajo + r.agotados;
  pintar($('#nave-cifras'), html`
    <div><dt>Unidades</dt><dd>${fmt.num.format(r.unidades)}</dd></div>
    <div><dt>Valor</dt><dd>${fmt.eur.format(r.valor)}</dd></div>
    <div class="${avisos ? 'nave3d__cifra--alerta' : ''}"><dt>Avisos</dt><dd>${fmt.num.format(avisos)}</dd></div>`);

  const categorias = categoriasOrdenadas(productos);
  pintar($('#nave-indice'), html`
    <h2>Contenido de la nave</h2>
    ${categorias.map((categoria, i) => html`
      <h3>Pasillo ${letraPasillo(i)}: ${categoria}</h3>
      <ul>${productos.filter((p) => p.categoria === categoria).map((p) =>
        html`<li>${p.codigo}, ${p.nombre}: ${unidades(p.stock_actual)}, ${ESTADOS_STOCK[p.estado].texto.toLowerCase()}</li>`)}</ul>`)}`);

  const carga = $('#nave-carga');
  const sin3d = $('#nave-sin-3d');
  if (!productos.length) {
    carga.classList.add('oculta');
    sin3d.hidden = false;
    pintar(sin3d, estadoVacio({ titulo: 'La nave está vacía',
      texto: 'Da de alta la primera referencia y aparecerá aquí su estantería.',
      accion: html`<button class="boton boton--tinta" type="button" data-accion="nuevo-producto" data-solo-admin>${icono('mas')}Nueva referencia</button>` }));
    return;
  }
  sin3d.hidden = true;

  try {
    await prepararNave();
  } catch {
    carga.classList.add('oculta');
    sin3d.hidden = false;
    pintar(sin3d, estadoVacio({ icono: 'alerta', titulo: 'Sin 3D en este navegador',
      texto: 'No se ha podido iniciar WebGL. Las existencias están completas en la vista de etiquetas.',
      accion: html`<a class="boton boton--tinta" href="#existencias">Ver existencias</a>` }));
    return;
  }
  if (vistaActual() !== 'nave') return;

  nave.actualizar(productos);
  $('#nave-aviso').hidden = !nave.modoLigero;
  pintar($('#nave-pasillos'), html`
    <button class="pasillo-boton pasillo-boton--general" type="button" data-accion="nave-general">Vista general</button>
    ${categorias.map((categoria, i) => html`
      <button class="pasillo-boton" type="button" data-accion="nave-pasillo" data-categoria="${categoria}">
        <span class="pasillo-boton__letra" aria-hidden="true">${letraPasillo(i)}</span>${categoria}
      </button>`)}`);
  nave.reanudar();
  carga.classList.add('oculta');
}

function mostrarFichaFlotante(p, evento) {
  const ficha = $('#nave-tooltip');
  if (!p || !evento || matchMedia('(pointer: coarse)').matches) {
    ficha.hidden = true;
    return;
  }
  pintar(ficha, html`
    ${etiquetaCodigo(p.codigo)}
    <strong>${p.nombre}</strong>
    <span class="nave3d__ficha-stock"><b>${unidades(p.stock_actual)}</b> · mín. ${fmt.num.format(p.stock_minimo)} · ${ESTADOS_STOCK[p.estado].texto}</span>
    <small>Pulsa para abrir su tarjeta Kardex</small>`);
  ficha.hidden = false;
  const caja = $('#nave3d').getBoundingClientRect();
  let x = evento.clientX - caja.left + 18;
  let y = evento.clientY - caja.top + 18;
  if (x + ficha.offsetWidth > caja.width - 8) x -= ficha.offsetWidth + 36;
  if (y + ficha.offsetHeight > caja.height - 8) y -= ficha.offsetHeight + 36;
  ficha.style.transform = `translate(${x}px, ${y}px)`;
}

/* ------------------------------------------------------- 02 · Panel */

async function cargarPanel() {
  const r = await api.resumen();
  const hoy = new Date();
  $('#fecha-hoy').textContent = `${fmt.diaLargo.format(hoy)} · ${fmt.hora.format(hoy)}`;
  $('#ticket-fecha').textContent = `${fmt.fechaCorta.format(hoy)}  ${fmt.hora.format(hoy)}`;

  const avisos = r.bajo + r.agotados;
  const entero = (n) => fmt.num.format(Math.round(n));
  const celdas = [
    { etiqueta: 'Unidades en almacén', valor: r.unidades, formato: entero,
      nota: r.hoy.movimientos ? `hoy ${conSigno(r.hoy.unidades_entrada)} / ${conSigno(-r.hoy.unidades_salida)}` : 'sin movimientos hoy' },
    { etiqueta: 'Valor del stock', valor: r.valor, formato: (n) => fmt.eur.format(n), nota: 'existencias × precio unitario' },
    { etiqueta: 'Referencias', valor: r.productos, formato: entero,
      nota: `en ${r.categorias} ${r.categorias === 1 ? 'categoría' : 'categorías'}` },
    { etiqueta: 'Avisos de reposición', valor: avisos, formato: entero, alerta: avisos > 0,
      nota: avisos ? `${r.agotados} agotadas · ${r.bajo} bajo mínimo` : 'todo por encima del mínimo' },
  ];
  const tablero = $('#tablero');
  pintar(tablero, celdas.map((c) => html`
    <div class="tablero__celda ${c.alerta ? 'tablero__celda--alerta' : ''}">
      <p class="tablero__etiqueta">${c.etiqueta}</p>
      <p class="tablero__cifra">${c.formato(c.valor)}</p>
      <p class="tablero__nota">${c.nota}</p>
    </div>`));
  tablero.removeAttribute('aria-busy');
  if (!estado.panelContado) {
    $$('.tablero__cifra', tablero).forEach((el, i) => contar(el, celdas[i].valor, celdas[i].formato, i * 70));
    estado.panelContado = true;
  }

  pintar($('#lista-reponer'), r.alertas.length
    ? html`<ul class="reponer">${r.alertas.map((p) => {
        const sugerida = Math.max(p.stock_minimo * 2 - p.stock_actual, 1);
        return html`
          <li>
            ${etiquetaCodigo(p.codigo)}
            <div class="reponer__producto">
              <button class="enlace-ficha" type="button" data-accion="ficha" data-id="${p.id}">${p.nombre}</button>
              ${medidor(p, { cajas: 20, compacto: true })}
            </div>
            <p class="reponer__cifras ${p.estado === 'AGOTADO' ? 'reponer__cifras--agotado' : ''}"><strong>${fmt.num.format(p.stock_actual)}</strong> / ${fmt.num.format(p.stock_minimo)} mín.</p>
            <button class="boton boton--pequeno boton--entrada" type="button" data-accion="entrada" data-id="${p.id}" data-cantidad="${sugerida}"
              aria-label="Reponer ${sugerida} unidades de ${p.nombre}">${icono('entrada')}Reponer ${conSigno(sugerida)}</button>
          </li>`;
      })}</ul>`
    : estadoVacio({ icono: 'check', tono: 'ok', compacto: true, titulo: 'Nada que reponer',
        texto: 'Todas las referencias están por encima de su stock mínimo.' }));

  pintar($('#lista-ultimos'), r.ultimos_movimientos.length
    ? html`
      <ol class="ticket__lineas">${r.ultimos_movimientos.map((m) => {
        const tipo = TIPOS_MOVIMIENTO[m.tipo];
        return html`
          <li>
            <span class="ticket__hora">${fmt.hora.format(new Date(m.fecha))}</span>
            <span class="ticket__concepto">
              <span><span class="ticket__tipo ticket__tipo--${tipo.clase}">${tipo.corto}</span>${m.producto}</span>
              <small>${m.motivo || tipo.nombre} · ${haceCuanto(m.fecha)}</small>
            </span>
            <span class="cantidad cantidad--${m.cantidad > 0 ? 'positiva' : 'negativa'}">${conSigno(m.cantidad)}</span>
          </li>`;
      })}</ol>
      <p class="ticket__total"><span>Total hoy</span><span>${conSigno(r.hoy.unidades_entrada)} / ${conSigno(-r.hoy.unidades_salida)}</span></p>`
    : estadoVacio({ icono: 'albaran', compacto: true, titulo: 'Sin albaranes',
        texto: 'Cada entrada, salida o recuento se imprime aquí.',
        accion: html`<button class="boton" type="button" data-accion="nuevo-movimiento">Registrar el primero</button>` }));
}

/* ------------------------------------------------- 03 · Existencias */

async function cargarCategorias() {
  const categorias = await api.categorias();
  const selector = $('#filtro-categoria');
  const actual = estado.filtrosExistencias.categoria;
  pintar(selector, html`<option value="">Todas las categorías</option>${categorias.map((c) =>
    html`<option value="${c.categoria}">${c.categoria} (${c.productos})</option>`)}`);
  selector.value = categorias.some((c) => c.categoria === actual) ? actual : '';
  estado.filtrosExistencias.categoria = selector.value;
  pintar($('#lista-categorias'), categorias.map((c) => html`<option value="${c.categoria}"></option>`));
}

function filaExistencia(p) {
  return html`
    <tr>
      <td class="ancho-completo sin-titulo" data-etiqueta="Referencia">
        <div class="referencia">
          <button class="enlace-ficha" type="button" data-accion="ficha" data-id="${p.id}">${p.nombre}</button>
          ${etiquetaCodigo(p.codigo)}
        </div>
      </td>
      <td data-etiqueta="Categoría" class="texto-2">${p.categoria}</td>
      <td data-etiqueta="Precio" class="num mono">${fmt.eur.format(p.precio)}</td>
      <td class="ancho-completo" data-etiqueta="Existencias">
        <div class="tabla-existencias__stock">
          <p class="cifra"><strong>${fmt.num.format(p.stock_actual)}</strong><span>/ mín. ${fmt.num.format(p.stock_minimo)}</span>
            ${p.estado !== 'OK' ? insigniaEstado(p.estado) : ''}</p>
          ${medidor(p, { cajas: 20, compacto: true })}
        </div>
      </td>
      <td data-etiqueta="Valor" class="num mono">${fmt.eur.format(p.valor)}</td>
      <td class="acciones ancho-completo">
        <div class="acciones__grupo">
          <button class="boton boton--pequeno boton--entrada" type="button" data-accion="entrada" data-id="${p.id}"
            aria-label="Registrar entrada de ${p.nombre}">${icono('entrada')}Entrada</button>
          <button class="boton boton--pequeno boton--salida" type="button" data-accion="salida" data-id="${p.id}"
            aria-label="Registrar salida de ${p.nombre}" ${p.stock_actual === 0 ? new HTMLSeguro('disabled') : ''}>${icono('salida')}Salida</button>
        </div>
      </td>
    </tr>`;
}

async function cargarExistencias() {
  const turno = ++estado.turnos.existencias;
  const estanteria = $('#existencias-etiquetas');
  estanteria.setAttribute('aria-busy', 'true');
  await cargarCategorias();
  const productos = await api.productos(estado.filtrosExistencias);
  if (turno !== estado.turnos.existencias) return; // ya llegó una respuesta más nueva
  estanteria.removeAttribute('aria-busy');

  const hayFiltros = Object.values(estado.filtrosExistencias).some(Boolean);
  const unidadesTotales = productos.reduce((suma, p) => suma + p.stock_actual, 0);
  $('#existencias-contador').textContent = productos.length
    ? `${fmt.num.format(productos.length)} ${productos.length === 1 ? 'referencia' : 'referencias'} · ${unidades(unidadesTotales)}${hayFiltros ? ' · filtrado' : ''}`
    : ' ';

  const enLista = estado.vistaExistencias === 'lista';
  const hayProductos = productos.length > 0;
  estanteria.hidden = enLista || !hayProductos;
  $('#existencias-lista').hidden = !enLista || !hayProductos;
  if (enLista) {
    pintar($('#existencias-lista tbody'), productos.map(filaExistencia));
  } else {
    estanteria.classList.toggle('estanteria--entrando', !estado.estanteriaColocada);
    pintar(estanteria, productos.map((p, indice) => etiquetaEstanteria(p, { indice })));
    if (hayProductos) estado.estanteriaColocada = true;
  }

  const vacio = $('#existencias-vacio');
  vacio.hidden = hayProductos;
  if (!hayProductos) {
    pintar(vacio, hayFiltros
      ? estadoVacio({ icono: 'buscar', titulo: 'Nada en esta estantería',
          texto: 'Ninguna referencia coincide. Prueba con otro código o nombre, o quita algún filtro.',
          accion: html`<button class="boton" type="button" data-accion="limpiar-filtros">Quitar filtros</button>` })
      : estadoVacio({ titulo: 'El almacén está vacío',
          texto: 'Da de alta la primera referencia para empezar a llevar sus existencias.',
          accion: html`<button class="boton boton--tinta" type="button" data-accion="nuevo-producto" data-solo-admin>${icono('mas')}Nueva referencia</button>` }));
  }
}

/* ------------------------------------------------- 04 · Movimientos */

async function cargarSelectorReferencias() {
  const productos = await api.productos();
  const selector = $('#filtro-mov-producto');
  const actual = String(estado.filtrosMovimientos.producto_id);
  pintar(selector, html`<option value="">Todas las referencias</option>${productos.map((p) =>
    html`<option value="${p.id}">${p.codigo} · ${p.nombre}</option>`)}`);
  // Una referencia dada de baja sigue pudiendo filtrarse desde su tarjeta Kardex
  if (actual && !productos.some((p) => String(p.id) === actual)) {
    selector.insertAdjacentHTML('beforeend', aHTML(html`<option value="${actual}">Referencia ${actual} (dada de baja)</option>`));
  }
  selector.value = actual;
}

function filaLibro(m) {
  const entra = m.cantidad > 0;
  return html`
    <tr>
      <td data-etiqueta="Nº albarán">#${numeroAlbaran(m.id)}</td>
      <td data-etiqueta="Fecha">${fechaMovimiento(m.fecha)}</td>
      <td class="ancho-completo sin-titulo" data-etiqueta="Referencia">
        <div class="referencia">
          <button class="enlace-ficha" type="button" data-accion="ficha" data-id="${m.producto_id}">${m.producto}</button>
          ${etiquetaCodigo(m.codigo)}
        </div>
      </td>
      <td class="ancho-completo" data-etiqueta="Concepto">
        <span class="concepto">${selloTipo(m.tipo)}${m.motivo || html`<span class="sin-dato">Sin concepto</span>`}</span>
        ${m.usuario ? html`<span class="autor">por ${m.usuario}</span>` : ''}
      </td>
      <td data-etiqueta="Entrada" class="num ${entra ? '' : 'celda-vacia'}">${entra ? html`<span class="cantidad cantidad--positiva">${conSigno(m.cantidad)}</span>` : ''}</td>
      <td data-etiqueta="Salida" class="num ${entra ? 'celda-vacia' : ''}">${entra ? '' : html`<span class="cantidad cantidad--negativa">${conSigno(m.cantidad)}</span>`}</td>
      <td data-etiqueta="Saldo" class="num">${saldoPaso(m)}</td>
    </tr>`;
}

async function cargarMovimientos() {
  const turno = ++estado.turnos.movimientos;
  const tabla = $('#tabla-movimientos');
  tabla.setAttribute('aria-busy', 'true');
  const limite = 300;
  const [movimientos] = await Promise.all([
    api.movimientos({ ...estado.filtrosMovimientos, limite }),
    cargarSelectorReferencias(),
  ]);
  if (turno !== estado.turnos.movimientos) return;
  tabla.removeAttribute('aria-busy');

  $('#movimientos-contador').textContent = movimientos.length
    ? `${movimientos.length === limite ? 'Últimos ' : ''}${fmt.num.format(movimientos.length)} ${movimientos.length === 1 ? 'asiento' : 'asientos'} · del más reciente al más antiguo · no se pueden borrar`
    : ' ';

  pintar($('tbody', tabla), movimientos.map(filaLibro));
  tabla.hidden = movimientos.length === 0;
  const hayFiltros = Object.values(estado.filtrosMovimientos).some(Boolean);
  const vacio = $('#movimientos-vacio');
  vacio.hidden = movimientos.length > 0;
  if (!movimientos.length) {
    pintar(vacio, hayFiltros
      ? estadoVacio({ icono: 'buscar', titulo: 'Ningún asiento con estos filtros',
          accion: html`<button class="boton" type="button" data-accion="limpiar-filtros-mov">Ver todo el libro</button>` })
      : estadoVacio({ icono: 'albaran', titulo: 'El libro está en blanco',
          texto: 'Cada albarán de entrada, de salida o recuento queda aquí anotado para siempre.',
          accion: html`<button class="boton boton--senal" type="button" data-accion="nuevo-movimiento">${icono('albaran')}Registrar movimiento</button>` }));
  }
}

/* ======================================================= Tarjeta Kardex */

async function abrirFicha(id) {
  estado.fichaId = id;
  const dialogo = $('#dlg-ficha');
  // Se abre al momento con un aviso de carga; los datos llegan después
  if (!dialogo.open) {
    pintar($('#ficha-contenido'), html`
      <header class="ficha__cabecera">
        <p class="ficha__cargando" role="status">Cargando la tarjeta Kardex…</p>
        <button class="boton boton--icono boton--fantasma" type="button" data-cerrar aria-label="Cerrar">${icono('cerrar')}</button>
      </header>`);
    dialogo.showModal();
  }
  await cargarFicha(id);
}

async function cargarFicha(id) {
  const turno = ++estado.turnos.ficha;
  const [p, movimientos] = await Promise.all([api.producto(id), api.movimientos({ producto_id: id, limite: 100 })]);
  if (turno !== estado.turnos.ficha) return;
  estado.fichaProducto = p;

  pintar($('#ficha-contenido'), html`
    <header class="ficha__cabecera">
      <div class="ficha__titulo">
        ${etiquetaCodigo(p.codigo, true)}
        <h2 id="ficha-titulo">${p.nombre}</h2>
        <p class="ficha__meta">${p.categoria}${p.descripcion ? ` · ${p.descripcion}` : ''}</p>
        ${p.activo ? '' : html`<span class="insignia insignia--agotado">Dada de baja</span>`}
      </div>
      <div class="ficha__herramientas">
        <button class="boton boton--icono boton--fantasma" type="button" data-accion="imprimir" aria-label="Imprimir etiqueta" title="Imprimir etiqueta">${icono('imprimir')}</button>
        ${p.activo ? html`
          <button class="boton boton--icono boton--fantasma" type="button" data-accion="editar" data-id="${p.id}" aria-label="Editar referencia" title="Editar" data-solo-admin>${icono('lapiz')}</button>
          <button class="boton boton--icono boton--fantasma boton--peligro-suave" type="button" data-accion="baja" data-id="${p.id}" aria-label="Dar de baja" title="Dar de baja" data-solo-admin>${icono('archivar')}</button>` : ''}
        <button class="boton boton--icono boton--fantasma" type="button" data-cerrar aria-label="Cerrar" title="Cerrar">${icono('cerrar')}</button>
      </div>
    </header>
    <div class="ficha__cuerpo">
      ${codigoBarras(p.codigo) ? html`<div class="ficha__barras">${codigoBarras(p.codigo)}<span>${p.codigo}</span></div>` : ''}
      <dl class="datos">
        <div><dt>Saldo</dt><dd>${fmt.num.format(p.stock_actual)}</dd></div>
        <div><dt>Mínimo</dt><dd>${fmt.num.format(p.stock_minimo)}</dd></div>
        <div><dt>Precio</dt><dd>${fmt.eur.format(p.precio)}</dd></div>
        <div><dt>Valor</dt><dd>${fmt.eur.format(p.valor)}</dd></div>
      </dl>
      ${medidor(p, { cajas: 24 })}
      ${p.activo ? html`
        <div class="ficha__acciones">
          <button class="boton boton--entrada" type="button" data-accion="entrada" data-id="${p.id}">${icono('entrada')}Entrada</button>
          <button class="boton boton--salida" type="button" data-accion="salida" data-id="${p.id}" ${p.stock_actual === 0 ? new HTMLSeguro('disabled') : ''}>${icono('salida')}Salida</button>
          <button class="boton" type="button" data-accion="recuento" data-id="${p.id}">${icono('recuento')}Recuento</button>
        </div>` : ''}
      <section class="kardex-tarjeta" aria-labelledby="kardex-titulo">
        <header class="kardex-tarjeta__cabecera">
          <h3 id="kardex-titulo">Tarjeta Kardex</h3>
          ${movimientos.length ? html`<button class="enlace" type="button" data-accion="historial" data-id="${p.id}">Ver en el libro</button>` : ''}
        </header>
        ${movimientos.length ? html`
          <table class="kardex">
            <thead><tr><th>Fecha</th><th>Concepto</th><th class="num">Entra</th><th class="num">Sale</th><th class="num">Saldo</th></tr></thead>
            <tbody>${movimientos.map((m) => html`
              <tr>
                <td class="kardex__fecha">${fmt.fechaCorta.format(new Date(m.fecha))}</td>
                <td class="kardex__concepto"><b>${TIPOS_MOVIMIENTO[m.tipo].nombre}</b>${m.motivo ? ` · ${m.motivo}` : ''}${m.usuario ? html`<span class="autor">${m.usuario}</span>` : ''}</td>
                <td class="num cantidad--positiva">${m.cantidad > 0 ? fmt.num.format(m.cantidad) : ''}</td>
                <td class="num cantidad--negativa">${m.cantidad < 0 ? fmt.num.format(-m.cantidad) : ''}</td>
                <td class="num saldo-col">${fmt.num.format(m.stock_resultante)}</td>
              </tr>`)}</tbody>
          </table>`
        : estadoVacio({ icono: 'albaran', compacto: true, titulo: 'Tarjeta en blanco', texto: 'Esta referencia aún no ha tenido movimientos.' })}
      </section>
    </div>`);
}

function imprimirEtiqueta() {
  if (!estado.fichaProducto) return;
  pintar($('#impresion'), etiquetaEstanteria(estado.fichaProducto, { interactiva: false }));
  window.print();
}

/* ======================================================== Formularios */

function limpiarErrores(formulario) {
  $$('[aria-invalid]', formulario).forEach((el) => el.removeAttribute('aria-invalid'));
  $$('.campo__error, .formulario__error', formulario).forEach((el) => { el.textContent = ''; });
}

function marcarError(formulario, campo, mensaje) {
  const control = campo && formulario.elements[campo];
  const contenedor = control?.closest?.('.campo');
  if (contenedor && !contenedor.hidden) {
    control.setAttribute('aria-invalid', 'true');
    $('.campo__error', contenedor).textContent = mensaje;
    control.focus();
  } else {
    $('.formulario__error', formulario).textContent = mensaje;
  }
}

/** Validación nativa del navegador, con los mensajes pintados en nuestro diseño. */
function validarFormulario(formulario) {
  limpiarErrores(formulario);
  const invalidos = $$('input, select, textarea', formulario).filter((el) => !el.closest('[hidden]') && !el.checkValidity());
  invalidos.forEach((el) => {
    el.setAttribute('aria-invalid', 'true');
    const error = $('.campo__error', el.closest('.campo'));
    if (error) error.textContent = el.validationMessage;
  });
  invalidos[0]?.focus();
  return invalidos.length === 0;
}

async function enviarFormulario(formulario, accion) {
  const boton = $('[type="submit"]', formulario);
  boton.disabled = true;
  boton.setAttribute('aria-busy', 'true');
  try {
    await accion();
  } catch (error) {
    if (!(error instanceof ErrorApi)) throw error;
    marcarError(formulario, error.campo, error.message);
  } finally {
    boton.disabled = false;
    boton.removeAttribute('aria-busy');
  }
}

/* ---------------------------------------------------------- Referencia */

function abrirFormularioProducto(producto = null) {
  const f = $('#form-producto');
  f.reset();
  limpiarErrores(f);
  estado.productoEditando = producto;
  const editando = Boolean(producto);
  $('#producto-antetitulo').textContent = editando ? `Referencia ${producto.codigo}` : 'Ficha nueva';
  $('#producto-titulo').textContent = editando ? 'Editar referencia' : 'Alta de referencia';
  $('[type="submit"]', f).textContent = editando ? 'Guardar cambios' : 'Dar de alta';
  $('#campo-stock-inicial').hidden = editando;
  $('#nota-stock').hidden = !editando;
  f.elements.id.value = producto?.id ?? '';
  if (editando) {
    for (const campo of ['codigo', 'nombre', 'categoria', 'descripcion', 'stock_minimo']) f.elements[campo].value = producto[campo];
    f.elements.precio.value = producto.precio.toFixed(2);
  }
  actualizarPrevia();
  $('#dlg-producto').showModal();
  f.elements[editando ? 'nombre' : 'codigo'].focus();
}

/** Vista previa en vivo de la etiqueta de estantería mientras se rellena la ficha. */
function actualizarPrevia() {
  const f = $('#form-producto');
  const entero = (valor) => Math.max(0, Number.parseInt(valor, 10) || 0);
  const minimo = entero(f.elements.stock_minimo.value);
  const stock = estado.productoEditando ? estado.productoEditando.stock_actual : entero(f.elements.stock_inicial.value);
  const precio = Math.max(0, Number.parseFloat(f.elements.precio.value) || 0);
  pintar($('#prod-previa'), etiquetaEstanteria({
    codigo: f.elements.codigo.value.trim().toUpperCase() || 'REF-000',
    nombre: f.elements.nombre.value.trim() || 'Nombre de la referencia',
    categoria: f.elements.categoria.value.trim() || 'General',
    precio,
    stock_minimo: minimo,
    stock_actual: stock,
    valor: stock * precio,
    estado: stock === 0 ? 'AGOTADO' : stock <= minimo ? 'BAJO' : 'OK',
  }, { interactiva: false }));
}

async function guardarProducto(evento) {
  evento.preventDefault();
  const f = evento.currentTarget;
  if (!validarFormulario(f)) return;
  const id = Number(f.elements.id.value) || null;
  const datos = {
    codigo: f.elements.codigo.value,
    nombre: f.elements.nombre.value,
    categoria: f.elements.categoria.value,
    descripcion: f.elements.descripcion.value,
    precio: f.elements.precio.value || 0,
    stock_minimo: Number(f.elements.stock_minimo.value || 0),
  };
  if (!id) datos.stock_inicial = Number(f.elements.stock_inicial.value || 0);

  await enviarFormulario(f, async () => {
    const producto = id ? await api.actualizarProducto(id, datos) : await api.crearProducto(datos);
    $('#dlg-producto').close();
    avisar(id
      ? `${producto.codigo} actualizada`
      : `${producto.codigo} · «${producto.nombre}» dada de alta con ${unidades(producto.stock_actual)}`);
    await refrescar();
  });
}

async function darDeBaja(id) {
  const p = await api.producto(id);
  const confirmado = await confirmar({
    titulo: `¿Dar de baja ${p.codigo}?`,
    mensaje: p.stock_actual > 0
      ? `«${p.nombre}» aún tiene ${unidades(p.stock_actual)} en la estantería. Dejará de aparecer en existencias, pero su tarjeta Kardex se conserva.`
      : `«${p.nombre}» dejará de aparecer en existencias, pero su tarjeta Kardex se conserva.`,
    boton: 'Dar de baja',
  });
  if (!confirmado) return;
  await api.darDeBaja(id);
  if (estado.fichaId === id) {
    estado.fichaId = null;
    $('#dlg-ficha').close();
  }
  avisar(`${p.codigo} dada de baja`);
  await refrescar();
}

function confirmar({ titulo, mensaje, boton }) {
  const dialogo = $('#dlg-confirmar');
  $('#conf-titulo').textContent = titulo;
  $('#conf-mensaje').textContent = mensaje;
  $('#conf-aceptar').textContent = boton;
  dialogo.returnValue = '';
  dialogo.showModal();
  $('#conf-cancelar').focus();
  return new Promise((resolver) => {
    dialogo.addEventListener('close', () => resolver(dialogo.returnValue === 'si'), { once: true });
  });
}

/* ------------------------------------------------------------- Albarán */

async function abrirAlbaran({ productoId = null, tipo = 'ENTRADA', cantidad = '' } = {}) {
  const productos = await api.productos();
  if (!productos.length) {
    avisar('Primero da de alta alguna referencia', 'error');
    return;
  }
  estado.productosMovimiento = new Map(productos.map((p) => [p.id, p]));

  const f = $('#form-movimiento');
  f.reset();
  limpiarErrores(f);
  pintar(f.elements.producto_id, html`
    ${productoId ? '' : html`<option value="" disabled selected>Elige una referencia…</option>`}
    ${productos.map((p) => html`<option value="${p.id}">${p.codigo} · ${p.nombre} — ${unidades(p.stock_actual)}</option>`)}`);
  if (productoId) f.elements.producto_id.value = String(productoId);
  f.elements.tipo.value = tipo;
  f.elements.cantidad.value = cantidad;
  const ahora = new Date();
  $('#mov-fecha').textContent = `${fmt.fechaCorta.format(ahora)} · ${fmt.hora.format(ahora)}`;

  alCambiarTipo();
  $('#dlg-movimiento').showModal();
  (productoId ? f.elements.cantidad : f.elements.producto_id).focus();
}

function alCambiarTipo() {
  const f = $('#form-movimiento');
  const tipo = TIPOS_MOVIMIENTO[f.elements.tipo.value];
  $('#dlg-movimiento').dataset.tipo = tipo.clase;
  $('#mov-titulo').textContent = tipo.titulo;
  $('#mov-antetitulo').textContent = tipo.antetitulo;
  $('#mov-cantidad-etiqueta').textContent = tipo.etiquetaCantidad;
  $('#mov-enviar').textContent = tipo.boton;
  f.elements.cantidad.min = f.elements.tipo.value === 'AJUSTE' ? 0 : 1;
  pintar($('#mov-sugerencias'), tipo.motivos.map((m) =>
    html`<button class="chip" type="button" data-motivo="${m}" aria-pressed="${f.elements.motivo.value === m}">${m}</button>`));
  actualizarSaldo();
}

function actualizarSaldo() {
  const f = $('#form-movimiento');
  const tipo = f.elements.tipo.value;
  const producto = estado.productosMovimiento.get(Number(f.elements.producto_id.value));
  const saldo = $('#mov-saldo');
  const boton = $('#mov-enviar');
  saldo.classList.remove('saldo--error');
  if (!producto) {
    pintar(saldo, '');
    boton.disabled = false;
    return;
  }

  const texto = f.elements.cantidad.value.trim();
  const cantidad = Number(texto);
  const valida = texto !== '' && Number.isInteger(cantidad) && cantidad >= Number(f.elements.cantidad.min);
  const actual = producto.stock_actual;
  let nuevo = null;
  let problema = '';
  if (valida) {
    nuevo = { ENTRADA: actual + cantidad, SALIDA: actual - cantidad, AJUSTE: cantidad }[tipo];
    if (nuevo < 0) problema = `Solo quedan ${unidades(actual)} en la estantería`;
    else if (tipo === 'AJUSTE' && nuevo === actual) problema = 'El recuento coincide con el saldo';
  }

  saldo.classList.toggle('saldo--error', Boolean(problema));
  const nota = problema || (nuevo === null ? 'Indica la cantidad' : `${conSigno(nuevo - actual)} uds.`);
  pintar(saldo, html`
    <span class="saldo__bloque"><small>Saldo actual</small><strong>${fmt.num.format(actual)}</strong></span>
    ${icono('flecha')}
    <span class="saldo__bloque"><small>Saldo nuevo</small><strong>${nuevo === null || nuevo < 0 ? '—' : fmt.num.format(nuevo)}</strong></span>
    <span class="saldo__nota">${nota}</span>`);
  boton.disabled = Boolean(problema);
}

/** Estampa el sello de tinta sobre el albarán y espera a que se vea. */
async function sellar(movimiento) {
  const tipo = TIPOS_MOVIMIENTO[movimiento.tipo];
  const fecha = new Date(movimiento.fecha);
  const sello = $('#mov-sello');
  pintar(sello, html`
    <span class="sello__dato">Albarán nº ${numeroAlbaran(movimiento.id)}</span>
    <span class="sello__tipo">${tipo.sello}</span>
    <span class="sello__dato">${fmt.fechaCorta.format(fecha)} · ${fmt.hora.format(fecha)}</span>`);
  sello.hidden = false;
  $('#mov-enviar').removeAttribute('aria-busy');
  $('#dlg-movimiento').classList.add('sellado');
  await esperar(movimientoReducido() ? 600 : 1000);
}

async function guardarMovimiento(evento) {
  evento.preventDefault();
  const f = evento.currentTarget;
  if (!validarFormulario(f)) return;
  const datos = {
    producto_id: Number(f.elements.producto_id.value),
    tipo: f.elements.tipo.value,
    cantidad: Number(f.elements.cantidad.value),
    motivo: f.elements.motivo.value,
  };
  await enviarFormulario(f, async () => {
    const m = await api.registrarMovimiento(datos);
    await sellar(m);
    $('#dlg-movimiento').close();
    avisar(`Albarán nº ${numeroAlbaran(m.id)} · ${conSigno(m.cantidad)} ${m.producto}. Saldo: ${unidades(m.stock_resultante)}`);
    await refrescar();
  });
  actualizarSaldo();
}

/* ================================================================ Tema */

const TEMAS = ['auto', 'claro', 'oscuro'];
const NOMBRES_TEMA = { auto: 'automático', claro: 'claro', oscuro: 'oscuro' };

function aplicarTema(tema) {
  if (tema === 'auto') delete document.documentElement.dataset.tema;
  else document.documentElement.dataset.tema = tema;
  const boton = $('[data-accion="tema"]');
  boton.title = `Tema: ${NOMBRES_TEMA[tema]}`;
  boton.setAttribute('aria-label', `Cambiar tema (ahora ${NOMBRES_TEMA[tema]})`);
  pintar(boton, icono({ auto: 'tema', claro: 'sol', oscuro: 'luna' }[tema]));
  guardarPreferencia('inventario.tema', tema);
}

/* ============================================================ Eventos */

const esAdmin = () => estado.usuario?.rol === 'admin';

const ACCIONES = {
  'nuevo-producto': () => esAdmin() && abrirFormularioProducto(),
  salir: async () => {
    await api.cerrarSesion().catch(() => null);
    location.replace('/login.html');
  },
  'nuevo-movimiento': () => abrirAlbaran(),
  entrada: (id, b) => abrirAlbaran({ productoId: id, tipo: 'ENTRADA', cantidad: b.dataset.cantidad ?? '' }),
  salida: (id) => abrirAlbaran({ productoId: id, tipo: 'SALIDA' }),
  recuento: (id) => abrirAlbaran({ productoId: id, tipo: 'AJUSTE' }),
  editar: async (id) => abrirFormularioProducto(await api.producto(id)),
  ficha: (id) => abrirFicha(id),
  baja: (id) => darDeBaja(id),
  imprimir: () => imprimirEtiqueta(),
  'nave-general': () => nave?.vistaGeneral(),
  'nave-pasillo': (id, b) => {
    const indice = nave?.pasillos().findIndex((f) => f.categoria === b.dataset.categoria) ?? -1;
    if (indice >= 0) nave.irAPasillo(indice);
  },
  historial: (id) => {
    estado.filtrosMovimientos = { producto_id: id, tipo: '' };
    $('#filtro-mov-tipo').elements.tipo.value = '';
    estado.fichaId = null;
    $('#dlg-ficha').close();
    return irA('movimientos');
  },
  'ver-alertas': (id, b, evento) => {
    evento.preventDefault();
    estado.filtrosExistencias.estado = 'ALERTA';
    $('#filtro-estado').elements.estado.value = 'ALERTA';
    return irA('existencias');
  },
  'limpiar-filtros': () => {
    estado.filtrosExistencias = { q: '', categoria: '', estado: '' };
    $('#filtro-texto').value = '';
    $('#filtro-estado').elements.estado.value = '';
    return cargarExistencias();
  },
  'limpiar-filtros-mov': () => {
    estado.filtrosMovimientos = { producto_id: '', tipo: '' };
    $('#filtro-mov-tipo').elements.tipo.value = '';
    return cargarMovimientos();
  },
  tema: () => aplicarTema(TEMAS[(TEMAS.indexOf(leerPreferencia('inventario.tema', TEMAS, 'auto')) + 1) % TEMAS.length]),
};

function conectarEventos() {
  document.addEventListener('click', async (evento) => {
    const cerrar = evento.target.closest('[data-cerrar]');
    if (cerrar) {
      cerrar.closest('dialog').close();
      return;
    }
    const boton = evento.target.closest('[data-accion]');
    if (!boton || boton.disabled) return;
    try {
      await ACCIONES[boton.dataset.accion]?.(Number(boton.dataset.id) || null, boton, evento);
    } catch (error) {
      avisar(error.message, 'error');
    }
  });

  // Clic en el velo oscuro de un diálogo: cerrarlo
  $$('dialog').forEach((dialogo) => {
    dialogo.addEventListener('click', (evento) => {
      if (evento.target === dialogo) dialogo.close();
    });
  });
  $('#dlg-ficha').addEventListener('close', () => { estado.fichaId = null; });
  // Mientras hay un diálogo abierto la nave no se dibuja; al cerrarlo, se pone al día
  $$('dialog').forEach((d) => d.addEventListener('close', () => nave?.redibujar()));
  $('#dlg-producto').addEventListener('close', () => { estado.productoEditando = null; });
  $('#dlg-movimiento').addEventListener('close', (evento) => {
    evento.currentTarget.classList.remove('sellado');
    $('#mov-sello').hidden = true;
  });

  // Existencias
  const buscar = debounce(() => refrescar('existencias'), 200);
  $('#filtro-texto').addEventListener('input', (e) => {
    estado.filtrosExistencias.q = e.target.value.trim();
    buscar();
  });
  $('#filtro-categoria').addEventListener('change', (e) => {
    estado.filtrosExistencias.categoria = e.target.value;
    refrescar('existencias');
  });
  $('#filtro-estado').addEventListener('change', (e) => {
    estado.filtrosExistencias.estado = e.target.value;
    refrescar('existencias');
  });
  $('#vista-existencias').addEventListener('change', (e) => {
    estado.vistaExistencias = e.target.value;
    guardarPreferencia('inventario.vista', e.target.value);
    refrescar('existencias');
  });

  // Libro de movimientos
  $('#filtro-mov-producto').addEventListener('change', (e) => {
    estado.filtrosMovimientos.producto_id = e.target.value;
    refrescar('movimientos');
  });
  $('#filtro-mov-tipo').addEventListener('change', (e) => {
    estado.filtrosMovimientos.tipo = e.target.value;
    refrescar('movimientos');
  });

  // Formularios
  const formProducto = $('#form-producto');
  formProducto.addEventListener('submit', (e) => guardarProducto(e).catch((error) => avisar(error.message, 'error')));
  formProducto.addEventListener('input', actualizarPrevia);

  const formMovimiento = $('#form-movimiento');
  formMovimiento.addEventListener('submit', (e) => guardarMovimiento(e).catch((error) => avisar(error.message, 'error')));
  formMovimiento.addEventListener('change', (e) => {
    if (e.target.name === 'tipo') alCambiarTipo();
    else actualizarSaldo();
  });
  formMovimiento.addEventListener('input', (e) => {
    if (e.target.name === 'cantidad') actualizarSaldo();
    if (e.target.name === 'motivo') $$('.chip', formMovimiento).forEach((c) => c.setAttribute('aria-pressed', String(c.dataset.motivo === e.target.value)));
  });
  $('#mov-sugerencias').addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    formMovimiento.elements.motivo.value = chip.dataset.motivo;
    $$('.chip', formMovimiento).forEach((c) => c.setAttribute('aria-pressed', String(c === chip)));
  });

  // Atajos de teclado
  document.addEventListener('keydown', (e) => {
    if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.target.closest?.('input, textarea, select, [contenteditable]') || $('dialog[open]')) return;
    const atajos = {
      '/': () => irA('existencias').then(() => $('#filtro-texto').focus()),
      n: () => esAdmin() && abrirFormularioProducto(),
      m: () => abrirAlbaran().catch((error) => avisar(error.message, 'error')),
    };
    const atajo = atajos[e.key.toLowerCase()];
    if (atajo) {
      e.preventDefault();
      atajo();
    }
  });

  window.addEventListener('hashchange', mostrarVista);
}

/* ============================================================= Inicio */

function pintarUsuario(usuario) {
  estado.usuario = usuario;
  document.body.dataset.rol = usuario.rol;
  if (usuario.demo) {
    // El visitante elige el concepto de la lista: no escribe nada que vayan a ver los demás
    $('#aviso-demo').hidden = false;
    const motivo = $('#mov-motivo');
    motivo.readOnly = true;
    motivo.placeholder = 'Elige uno de los conceptos de abajo';
  }
  pintar($('#usuario-actual'), html`
    <span class="usuario__inicial" aria-hidden="true">${usuario.nombre.charAt(0)}</span>
    <span class="usuario__texto"><strong>${usuario.nombre}</strong><small>${usuario.demo ? 'Demostración' : usuario.rol === 'admin' ? 'Administración' : 'Operario'}</small></span>`);
}

async function iniciar() {
  let sesion;
  try {
    sesion = await api.sesion();
  } catch (error) {
    avisar(error.message, 'error');
    return;
  }
  if (!sesion.usuario) {
    location.replace(`/login.html?volver=${encodeURIComponent(location.hash || '#nave')}`);
    return;
  }
  pintarUsuario(sesion.usuario);
  $$('[data-icono]').forEach((el) => { el.outerHTML = icono(el.dataset.icono).texto; });
  new ResizeObserver(([entrada]) => {
    document.documentElement.style.setProperty('--alto-cabecera', `${entrada.target.offsetHeight}px`);
  }).observe($('.nave'));
  $('#vista-existencias').elements.vista.value = estado.vistaExistencias;
  aplicarTema(leerPreferencia('inventario.tema', TEMAS, 'auto'));
  conectarEventos();
  mostrarVista();
}

iniciar();
