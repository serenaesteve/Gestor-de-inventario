-- =====================================================================
--  Migración 001 · Esquema inicial: productos, movimientos, triggers y vista
-- =====================================================================
--  Reglas que garantiza la propia base de datos (no solo la aplicación):
--   · El stock nunca puede ser negativo                    (CHECK)
--   · El código de producto es único, sin distinguir mayúsculas (UNIQUE NOCASE)
--   · Cada movimiento apunta a un producto existente        (FOREIGN KEY)
--   · stock_resultante = stock_anterior + cantidad          (CHECK)
--   · Los movimientos son un registro inmutable             (TRIGGER)
-- =====================================================================

CREATE TABLE IF NOT EXISTS productos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo           TEXT    NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(codigo)) > 0),
    nombre           TEXT    NOT NULL CHECK (length(trim(nombre)) > 0),
    descripcion      TEXT    NOT NULL DEFAULT '',
    categoria        TEXT    NOT NULL DEFAULT 'General',
    -- Los importes se guardan en céntimos (entero) para evitar errores de redondeo de REAL
    precio_centimos  INTEGER NOT NULL DEFAULT 0 CHECK (precio_centimos >= 0),
    stock_minimo     INTEGER NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
    stock_actual     INTEGER NOT NULL DEFAULT 0 CHECK (stock_actual >= 0),
    -- Borrado lógico: un producto con historial no se elimina, se da de baja
    activo           INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    creado_en        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    actualizado_en   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_productos_categoria ON productos (categoria);

CREATE TABLE IF NOT EXISTS movimientos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id       INTEGER NOT NULL REFERENCES productos (id) ON DELETE RESTRICT,
    tipo              TEXT    NOT NULL CHECK (tipo IN ('ENTRADA', 'SALIDA', 'AJUSTE')),
    -- Cantidad con signo: positiva suma stock, negativa lo resta
    cantidad          INTEGER NOT NULL,
    stock_anterior    INTEGER NOT NULL CHECK (stock_anterior >= 0),
    stock_resultante  INTEGER NOT NULL CHECK (stock_resultante >= 0),
    motivo            TEXT    NOT NULL DEFAULT '',
    fecha             TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (
        (tipo = 'ENTRADA' AND cantidad > 0) OR
        (tipo = 'SALIDA'  AND cantidad < 0) OR
        (tipo = 'AJUSTE'  AND cantidad <> 0)
    ),
    CHECK (stock_resultante = stock_anterior + cantidad)
);

CREATE INDEX IF NOT EXISTS idx_movimientos_producto_fecha ON movimientos (producto_id, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_movimientos_fecha ON movimientos (fecha DESC);

-- Mantiene actualizado_en al día sin depender de la aplicación
CREATE TRIGGER IF NOT EXISTS trg_productos_actualizado
AFTER UPDATE OF codigo, nombre, descripcion, categoria, precio_centimos,
                stock_minimo, stock_actual, activo ON productos
BEGIN
    UPDATE productos SET actualizado_en = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE id = NEW.id;
END;

-- El historial de movimientos es de solo inserción (trazabilidad)
CREATE TRIGGER IF NOT EXISTS trg_movimientos_sin_modificar
BEFORE UPDATE ON movimientos
BEGIN
    SELECT RAISE(ABORT, 'Los movimientos no se pueden modificar');
END;

CREATE TRIGGER IF NOT EXISTS trg_movimientos_sin_borrar
BEFORE DELETE ON movimientos
BEGIN
    SELECT RAISE(ABORT, 'Los movimientos no se pueden borrar');
END;

-- Vista de consulta de existencias con el estado y el valor ya calculados
CREATE VIEW IF NOT EXISTS v_existencias AS
SELECT
    p.id,
    p.codigo,
    p.nombre,
    p.descripcion,
    p.categoria,
    p.precio_centimos,
    p.stock_minimo,
    p.stock_actual,
    p.activo,
    p.creado_en,
    p.actualizado_en,
    p.stock_actual * p.precio_centimos AS valor_centimos,
    CASE
        WHEN p.stock_actual = 0              THEN 'AGOTADO'
        WHEN p.stock_actual <= p.stock_minimo THEN 'BAJO'
        ELSE 'OK'
    END AS estado
FROM productos p;


-- La transacción la abre y la cierra conexion.inicializar() junto con PRAGMA user_version.
