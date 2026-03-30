"""
decorators.py — Decoradores de protección de rutas
Importar en cualquier blueprint que necesite protección.
"""
from functools import wraps
from flask import session, redirect, url_for, flash


def login_requerido(f):
    """Redirige al login si el usuario no está autenticado."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("usuario_id"):
            flash("Debes iniciar sesión para continuar.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def staff_requerido(f):
    """Solo permite acceso a usuarios con rol staff o admin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("usuario_id"):
            flash("Debes iniciar sesión.", "warning")
            return redirect(url_for("auth.login"))
        if session.get("rol") not in ("staff", "admin"):
            flash("No tienes permisos para esta sección.", "danger")
            return redirect(url_for("public.index"))
        return f(*args, **kwargs)
    return decorated


def admin_requerido(f):
    """Solo permite acceso a usuarios con rol admin."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("usuario_id"):
            flash("Debes iniciar sesión.", "warning")
            return redirect(url_for("auth.login"))
        if session.get("rol") != "admin":
            flash("Acceso restringido a administradores.", "danger")
            return redirect(url_for("public.index"))
        return f(*args, **kwargs)
    return decorated