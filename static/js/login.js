// Control de acceso: inicia la sesión y vuelve a donde estaba el usuario.

const formulario = document.getElementById('form-acceso');
const destino = (() => {
  const volver = new URLSearchParams(location.search).get('volver') ?? '';
  return /^#[a-z]+$/.test(volver) ? `/${volver}` : '/';
})();

function marcarError(campo, mensaje) {
  const control = campo && formulario.elements[campo];
  if (control) {
    control.setAttribute('aria-invalid', 'true');
    control.closest('.campo').querySelector('.campo__error').textContent = mensaje;
    control.focus();
  } else {
    formulario.querySelector('.formulario__error').textContent = mensaje;
  }
}

function limpiarErrores() {
  formulario.querySelectorAll('[aria-invalid]').forEach((el) => el.removeAttribute('aria-invalid'));
  formulario.querySelectorAll('.campo__error, .formulario__error').forEach((el) => { el.textContent = ''; });
}

formulario.addEventListener('submit', async (evento) => {
  evento.preventDefault();
  limpiarErrores();
  const usuario = formulario.elements.usuario.value.trim();
  const contrasena = formulario.elements.contrasena.value;
  if (!usuario) return marcarError('usuario', 'Escribe tu usuario');
  if (!contrasena) return marcarError('contrasena', 'Escribe tu contraseña');

  const boton = formulario.querySelector('[type="submit"]');
  boton.disabled = true;
  boton.setAttribute('aria-busy', 'true');
  try {
    const respuesta = await fetch('/api/sesion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ usuario, contrasena }),
    });
    if (respuesta.ok) {
      location.replace(destino);
      return;
    }
    const datos = await respuesta.json().catch(() => ({}));
    marcarError(respuesta.status === 401 ? null : datos.campo, datos.error ?? 'No se ha podido entrar. Inténtalo de nuevo.');
    if (respuesta.status === 401) {
      formulario.elements.contrasena.value = '';
      formulario.elements.contrasena.focus();
    }
  } catch {
    marcarError(null, 'No hay conexión con el servidor. Comprueba que «python3 app.py» sigue en marcha.');
  } finally {
    boton.disabled = false;
    boton.removeAttribute('aria-busy');
  }
});

// Mostrar u ocultar la contraseña
const verContrasena = document.getElementById('ver-contrasena');
verContrasena.addEventListener('click', () => {
  const campo = formulario.elements.contrasena;
  const visible = campo.type === 'password';
  campo.type = visible ? 'text' : 'password';
  verContrasena.setAttribute('aria-pressed', String(visible));
  verContrasena.setAttribute('aria-label', visible ? 'Ocultar la contraseña' : 'Mostrar la contraseña');
});

// Con el material de ejemplo cargado, se ofrecen sus usuarios para entrar con un clic
async function mostrarUsuariosEjemplo() {
  try {
    const respuesta = await fetch('/api/sesion', { headers: { Accept: 'application/json' } });
    const { usuario, usuarios_ejemplo: ejemplos = [] } = await respuesta.json();
    if (usuario) {
      location.replace(destino);
      return;
    }
    if (!ejemplos.length) return;
    const lista = document.getElementById('lista-ejemplo');
    for (const cuenta of ejemplos) {
      const boton = document.createElement('button');
      boton.type = 'button';
      boton.className = 'cuenta-ejemplo';
      const inicial = document.createElement('span');
      inicial.className = 'cuenta-ejemplo__inicial';
      inicial.setAttribute('aria-hidden', 'true');
      inicial.textContent = cuenta.nombre.charAt(0);
      const textos = document.createElement('span');
      textos.className = 'cuenta-ejemplo__textos';
      const fila = document.createElement('span');
      fila.className = 'cuenta-ejemplo__fila';
      const nombre = document.createElement('strong');
      nombre.textContent = cuenta.nombre;
      const rol = document.createElement('span');
      rol.className = `insignia ${cuenta.rol === 'admin' ? 'insignia--bajo' : 'insignia--ok'}`;
      rol.textContent = cuenta.rol === 'admin' ? 'Administración' : 'Operario';
      fila.append(nombre, rol);
      const credenciales = document.createElement('small');
      credenciales.textContent = `${cuenta.usuario} · ${cuenta.contrasena}`;
      textos.append(fila, credenciales);
      boton.append(inicial, textos);
      boton.addEventListener('click', () => {
        formulario.elements.usuario.value = cuenta.usuario;
        formulario.elements.contrasena.value = cuenta.contrasena;
        formulario.querySelector('[type="submit"]').focus();
      });
      const item = document.createElement('li');
      item.append(boton);
      lista.append(item);
    }
    document.getElementById('usuarios-ejemplo').hidden = false;
  } catch {
    // Sin servidor no hay ejemplos que mostrar; el formulario sigue funcionando
  }
}

mostrarUsuariosEjemplo();
formulario.elements.usuario.focus();
