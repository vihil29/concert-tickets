"""
config.py — Configuración centralizada de SoundPass
Todas las variables sensibles vienen del archivo .env
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ── Flask ──
    SECRET_KEY = os.getenv("SECRET_KEY", "soundpass-dev-secret-2025")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY  = True
    SESSION_COOKIE_SAMESITE  = 'Lax'
    MAX_CONTENT_LENGTH       = 5 * 1024 * 1024  # 5MB max upload

    # ── Base de datos ──
    DB_HOST     = os.getenv("DB_HOST", "localhost")
    DB_USER     = os.getenv("DB_USER", "soundpass")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME     = os.getenv("DB_NAME", "concert_tickets")

    # ── Correo ──
    EMAIL_REMITENTE = os.getenv("EMAIL_REMITENTE")
    EMAIL_APP_PASS  = os.getenv("EMAIL_APP_PASS")

    # ── Uploads ──
    UPLOAD_FOLDER   = os.path.join(os.path.dirname(__file__), "static", "uploads")
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}