"""blueprints/auth/routes.py"""
from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import get_db
import mysql.connector
from . import auth_bp


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Limpiar sesión previa siempre
    session.clear()

    if request.method == "POST":
        correo   = request.form.get("correo", "").strip().lower()
        password = request.form.get("password", "")

        conn = cursor = None
        try:
            conn   = get_db()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM usuarios WHERE correo = %s", (correo,))
            usuario = cursor.fetchone()

            if not usuario or not check_password_hash(usuario["password"], password):
                flash("Correo o contraseña incorrectos.", "danger")
                return render_template("auth/login.html")

            session.permanent    = True
            session["usuario_id"] = usuario["id"]
            session["nombre"]     = usuario["nombre"]
            session["correo"]     = usuario["correo"]
            session["rol"]        = usuario["rol"]

            # Redirigir según rol
            next_url = request.args.get("next")
            if next_url:
                return redirect(next_url)
            if usuario["rol"] == "admin":
                return redirect(url_for("admin.dashboard"))
            if usuario["rol"] == "staff":
                return redirect(url_for("staff.pwa"))
            return redirect(url_for("public.index"))

        except mysql.connector.Error as e:
            flash(f"Error: {e}", "danger")
        finally:
            if cursor: cursor.close()
            if conn:   conn.close()

    return render_template("auth/login.html")


@auth_bp.route("/registro", methods=["GET", "POST"])
def registro():
    session.clear()

    if request.method == "POST":
        nombre   = request.form.get("nombre",   "").strip()
        correo   = request.form.get("correo",   "").strip().lower()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm",  "")

        if not nombre or not correo or not password:
            flash("Todos los campos son obligatorios.", "danger")
            return render_template("auth/registro.html")
        if password != confirm:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("auth/registro.html")
        if len(password) < 8:
            flash("La contraseña debe tener al menos 8 caracteres.", "danger")
            return render_template("auth/registro.html")

        conn = cursor = None
        try:
            conn   = get_db()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id FROM usuarios WHERE correo = %s", (correo,))
            if cursor.fetchone():
                flash("Este correo ya está registrado.", "warning")
                return render_template("auth/registro.html")

            hashed = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO usuarios (nombre, correo, password, rol) VALUES (%s,%s,%s,'cliente')",
                (nombre, correo, hashed)
            )
            conn.commit()
            flash("¡Cuenta creada! Ya puedes iniciar sesión.", "success")
            return redirect(url_for("auth.login"))

        except mysql.connector.Error as e:
            flash(f"Error al crear cuenta: {e}", "danger")
        finally:
            if cursor: cursor.close()
            if conn:   conn.close()

    return render_template("auth/registro.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    session.modified = True
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("auth.login"))