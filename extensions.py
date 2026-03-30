"""
extensions.py — Helpers compartidos entre blueprints
"""
import mysql.connector
from flask import current_app


def get_db():
    """Retorna una conexión activa a MySQL usando la config de la app."""
    cfg = current_app.config
    return mysql.connector.connect(
        host     = cfg["DB_HOST"],
        user     = cfg["DB_USER"],
        password = cfg["DB_PASSWORD"],
        database = cfg["DB_NAME"]
    )