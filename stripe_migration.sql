-- ============================================================
--  MIGRACIÓN: Agregar columna stripe_session_id a tickets
--  Ejecutar en el VPS:
--  mysql -u soundpass -p concert_tickets < stripe_migration.sql
-- ============================================================

USE concert_tickets;

-- Agregar columna para idempotencia de pagos Stripe
ALTER TABLE tickets
  ADD COLUMN stripe_session_id VARCHAR(255) NULL UNIQUE
  AFTER estado;

-- Índice para búsquedas rápidas por session_id
CREATE INDEX idx_tickets_stripe ON tickets(stripe_session_id);

-- Verificar
DESCRIBE tickets;