// Utilidades de rendimiento para las escenas 3D (nave y recorrido).

import * as THREE from 'three';
import { mergeGeometries } from '/vendor/three/BufferGeometryUtils.js';

const ATRIBUTOS = ['position', 'normal', 'uv'];

function esMovil(objeto, raiz) {
  for (let o = objeto; o && o !== raiz; o = o.parent) {
    if (o.userData.movil) return true;
  }
  return false;
}

/**
 * Fusiona todas las mallas estáticas de `raiz` en una sola malla por material.
 * Cientos de piezas (puntales, palés, suelo…) pasan a ser unas pocas llamadas de dibujo.
 * Se respetan: lo marcado con `userData.movil` (y su contenido), lo marcado con
 * `userData.fijo = false`, lo invisible (zonas de clic) y las mallas con varios materiales.
 */
export function fusionarEstaticos(raiz) {
  raiz.updateMatrixWorld(true);
  const inversa = raiz.matrixWorld.clone().invert();
  const relativa = new THREE.Matrix4();
  const lotes = new Map();
  const fusionadas = [];

  raiz.traverse((o) => {
    if (!o.isMesh || o.isInstancedMesh || Array.isArray(o.material)) return;
    if (!o.material.visible || !o.visible || o.userData.fijo === false || esMovil(o, raiz)) return;
    const geometria = o.geometry.index ? o.geometry.toNonIndexed() : o.geometry.clone();
    for (const nombre of Object.keys(geometria.attributes)) {
      if (!ATRIBUTOS.includes(nombre)) geometria.deleteAttribute(nombre);
    }
    if (!ATRIBUTOS.every((nombre) => geometria.attributes[nombre])) return;
    geometria.clearGroups();
    geometria.applyMatrix4(relativa.multiplyMatrices(inversa, o.matrixWorld));
    const clave = `${o.material.uuid}|${o.castShadow}|${o.receiveShadow}`;
    if (!lotes.has(clave)) lotes.set(clave, { material: o.material, sombra: o.castShadow, recibe: o.receiveShadow, geometrias: [] });
    lotes.get(clave).geometrias.push(geometria);
    fusionadas.push(o);
  });

  for (const o of fusionadas) o.removeFromParent();
  for (const { material, sombra, recibe, geometrias } of lotes.values()) {
    const malla = new THREE.Mesh(mergeGeometries(geometrias, false), material);
    malla.castShadow = sombra;
    malla.receiveShadow = recibe;
    malla.matrixAutoUpdate = false;
    raiz.add(malla);
    for (const g of geometrias) g.dispose();
  }
  return fusionadas.length;
}

/**
 * ¿Está el navegador dibujando el 3D sin tarjeta gráfica (SwiftShader, llvmpipe…)?
 * Pasa a menudo en Linux cuando el navegador desactiva la aceleración por hardware.
 */
export function renderizadoPorSoftware(renderer) {
  const gl = renderer.getContext();
  const extension = gl.getExtension('WEBGL_debug_renderer_info');
  const nombre = String(extension ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER));
  return /swiftshader|llvmpipe|softpipe|software|basic render/i.test(nombre);
}

/**
 * Mide cuánto tarda cada fotograma cuando se dibuja de forma seguida y, si va lento,
 * avisa con `alIrLento(nivel)`: nivel 1 y, si sigue lento, nivel 2.
 * `continuo` indica que el fotograma anterior también se dibujó (si no, el hueco es una pausa).
 */
export function vigilarRendimiento(alIrLento, { umbralMs = 45, muestrasNecesarias = 12 } = {}) {
  let anterior = 0;
  let nivel = 0;
  let muestras = [];
  return (ahora, continuo) => {
    const delta = ahora - anterior;
    anterior = ahora;
    if (nivel >= 2 || !continuo || delta <= 0) return;
    muestras.push(delta);
    if (muestras.length < muestrasNecesarias) return;
    const media = muestras.reduce((a, b) => a + b, 0) / muestras.length;
    muestras = [];
    if (media > umbralMs) {
      nivel += 1;
      alIrLento(nivel, media);
    }
  };
}

/**
 * Baja la calidad sin recompilar sombreadores (recompilar congela la página varios segundos
 * en equipos lentos): solo se reduce la resolución. Las sombras dejan de recalcularse.
 */
export function bajarCalidad(renderer, nivel) {
  renderer.setPixelRatio(nivel >= 2 ? 0.6 : 0.85);
}

/** Densidad de píxeles razonable: nítido sin multiplicar el trabajo por 4 en pantallas retina. */
export function densidadPixeles(movil, software = false) {
  if (software) return 0.75;
  return Math.min(window.devicePixelRatio || 1, movil ? 1 : 1.5);
}

/** Hay un diálogo modal abierto que tapa la escena (no cuenta el cajón lateral). */
export function dialogoTapando() {
  return Boolean(document.querySelector('dialog.dialogo:not(.cajon)[open], dialog.albaran[open]'));
}
