-- =====================================================================
--  Migración 002 · Usuarios, sesiones y autoría de los movimientos
-- =====================================================================
--  Se aplica sola sobre una base de datos de la versión 1 sin perder datos:
--  los movimientos antiguos quedan con usuario_id = NULL ("sin registrar").
-- =====================================================================

CREATE TABLE usuarios (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario          TEXT    NOT NULL UNIQUE COLLATE NOCASE CHECK (length(usuario) BETWEEN 3 AND 30),
    nombre           TEXT    NOT NULL CHECK (length(trim(nombre)) > 0),
    rol              TEXT    NOT NULL DEFAULT 'operario' CHECK (rol IN ('admin', 'operario')),
    -- Nunca la contraseña: solo su resumen PBKDF2 con sal (algoritmo$iteraciones$sal$resumen)
    hash_contrasena  TEXT    NOT NULL,
    activo           INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    creado_en        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    ultimo_acceso    TEXT
);

CREATE TABLE sesiones (
    -- Se guarda la huella SHA-256 del token, no el token: si alguien copia la BD no puede suplantar a nadie
    token_hash   TEXT    PRIMARY KEY,
    usuario_id   INTEGER NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    creada_en    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expira_en    TEXT    NOT NULL
);

CREATE INDEX idx_sesiones_usuario ON sesiones (usuario_id);
CREATE INDEX idx_sesiones_expira ON sesiones (expira_en);

-- Quién registró cada movimiento (NULL en los anteriores a esta versión)
ALTER TABLE movimientos ADD COLUMN usuario_id INTEGER REFERENCES usuarios (id);

-- Ajustes clave-valor de la instalación (por ejemplo, si se cargaron los datos de ejemplo)
CREATE TABLE ajustes (
    clave  TEXT PRIMARY KEY,
    valor  TEXT NOT NULL
);
