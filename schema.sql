-- ============================================================
--  SoundPass — Base de datos completa
--  Ejecutar: mysql -u soundpass -p concert_tickets < schema.sql
-- ============================================================

USE concert_tickets;

-- ─────────────────────────────────────────────
--  1. USUARIOS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usuarios (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    nombre           VARCHAR(100) NOT NULL,
    correo           VARCHAR(150) NOT NULL UNIQUE,
    password         VARCHAR(255) NOT NULL,
    rol              ENUM('admin','staff','cliente') NOT NULL DEFAULT 'cliente',
    fecha_registro   DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────
--  2. CATEGORÍAS (admin puede crear nuevas)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categorias (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    nombre      VARCHAR(50)  NOT NULL UNIQUE,   -- 'Música', 'Fútbol', 'NBA', 'NFL'
    slug        VARCHAR(50)  NOT NULL UNIQUE,   -- 'musica', 'futbol', 'nba', 'nfl'
    icono       VARCHAR(10)  NOT NULL,           -- emoji: 🎸 ⚽ 🏀
    color       VARCHAR(7)   NOT NULL,           -- hex: #f0a500
    mapa_tipo   ENUM('concierto','futbol','nba') NOT NULL DEFAULT 'concierto',
    activa      TINYINT(1)   NOT NULL DEFAULT 1,
    creada_en   DATETIME     DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Categorías iniciales
INSERT IGNORE INTO categorias (nombre, slug, icono, color, mapa_tipo) VALUES
('Música',  'musica', '🎸', '#f0a500', 'concierto'),
('Fútbol',  'futbol', '⚽', '#22d97a', 'futbol'),
('NBA',     'nba',    '🏀', '#f43f5e', 'nba');

-- ─────────────────────────────────────────────
--  3. EVENTOS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS eventos (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    categoria_id    INT          NOT NULL,
    nombre          VARCHAR(200) NOT NULL,       -- 'Bad Bunny World Tour', 'Barcelona vs Real Madrid'
    descripcion     TEXT,
    lugar           VARCHAR(200) NOT NULL,        -- 'Estadio Nacional', 'Camp Nou'
    fecha           DATE         NOT NULL,
    hora            TIME         NOT NULL,
    imagen_url      VARCHAR(500),                -- URL o path del poster
    estado          ENUM('proximo','en_curso','finalizado','cancelado','agotado')
                    NOT NULL DEFAULT 'proximo',
    creado_en       DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (categoria_id) REFERENCES categorias(id)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────
--  4. ZONAS POR EVENTO (precios dinámicos)
--     Cada evento tiene sus propias zonas con precio
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS zonas_evento (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    evento_id   INT          NOT NULL,
    nombre      VARCHAR(100) NOT NULL,   -- 'Platea', 'VIP', 'Cancha', 'Courtside'
    precio      DECIMAL(10,2) NOT NULL,
    capacidad   INT          NOT NULL,
    vendidos    INT          NOT NULL DEFAULT 0,
    color       VARCHAR(7)   NOT NULL DEFAULT '#f0a500',
    descripcion VARCHAR(200),
    FOREIGN KEY (evento_id) REFERENCES eventos(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────
--  5. TICKETS (compras)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tickets (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    codigo          VARCHAR(36)  NOT NULL UNIQUE,  -- UUID
    usuario_id      INT,                            -- NULL si compró sin cuenta
    evento_id       INT          NOT NULL,
    zona_id         INT          NOT NULL,
    nombre          VARCHAR(100) NOT NULL,          -- nombre del comprador
    correo          VARCHAR(150) NOT NULL,
    estado          ENUM('activo','ingresado','cancelado') NOT NULL DEFAULT 'activo',
    fecha_compra    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (evento_id)  REFERENCES eventos(id),
    FOREIGN KEY (zona_id)    REFERENCES zonas_evento(id)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────
--  ÍNDICES para consultas rápidas
-- ─────────────────────────────────────────────
CREATE INDEX idx_tickets_codigo    ON tickets(codigo);
CREATE INDEX idx_tickets_evento    ON tickets(evento_id);
CREATE INDEX idx_eventos_categoria ON eventos(categoria_id);
CREATE INDEX idx_eventos_estado    ON eventos(estado);