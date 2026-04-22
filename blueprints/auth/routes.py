"""blueprints/auth/routes.py"""
import secrets
import smtplib
import threading
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText

from flask import (
    render_template, request, redirect, url_for,
    flash, session, current_app
)
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector

from extensions import get_db
from . import auth_bp


# ─────────────────────────────────────────────
#  HELPER: enviar correo de reseteo en hilo
# ─────────────────────────────────────────────
def _enviar_correo_reset_worker(cfg: dict, destinatario: str,
                                 nombre: str, reset_url: str):
    """
    Envía el correo con el enlace de reseteo.
    Corre en threading.Thread para no bloquear la respuesta web.
    Compatible con Brevo SMTP (smtp-relay.brevo.com:587).
    """
    try:
        remitente = cfg["EMAIL_REMITENTE"]
        app_pass  = cfg["EMAIL_APP_PASS"]
        smtp_host = cfg.get("EMAIL_SMTP_HOST", "smtp-relay.brevo.com")
        smtp_user = cfg.get("EMAIL_SMTP_USER", "")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "🔑 Restablecer contraseña — SoundPass"
        msg["From"]    = f"SoundPass <{remitente}>"
        msg["To"]      = destinatario

        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <body style="margin:0;padding:0;background:#f5f5f0;font-family:Arial,sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:#f5f5f0;padding:40px 0;">
          <tr><td align="center">

            <table width="480" cellpadding="0" cellspacing="0"
                   style="max-width:480px;background:#12121e;border-radius:20px;
                          border:1px solid rgba(240,165,0,0.12);
                          box-shadow:0 10px 30px rgba(0,0,0,0.3);overflow:hidden;">

              <!-- HEADER -->
              <tr><td style="padding:32px 32px 22px;text-align:center;">
                <div style="margin-bottom:14px;">
                  <span style="font-size:22px;vertical-align:middle;margin-right:5px;">🎸</span>
                  <span style="font-size:22px;color:#f0a500;
                               font-family:'Arial Black',Impact,sans-serif;
                               font-weight:bold;letter-spacing:1px;
                               vertical-align:middle;">SOUNDPASS</span>
                </div>

                <!-- Ícono de llave -->
                <div style="width:64px;height:64px;border-radius:50%;
                            background:rgba(240,165,0,0.1);
                            border:2px solid rgba(240,165,0,0.3);
                            display:inline-flex;align-items:center;
                            justify-content:center;font-size:1.8rem;
                            margin-bottom:16px;">🔑</div>

                <h1 style="margin:0 0 6px;font-size:22px;color:#ffffff;
                            font-family:'Arial Black',sans-serif;letter-spacing:0.5px;">
                  Restablecer contraseña
                </h1>
                <p style="margin:0;font-size:13px;color:rgba(255,255,255,0.4);">
                  Hola <strong style="color:#fff;">{nombre}</strong>,
                  recibimos una solicitud para cambiar tu contraseña.
                </p>
              </td></tr>

              <!-- SEPARADOR -->
              <tr><td style="padding:0 32px;">
                <div style="border-top:1px dashed rgba(240,165,0,0.15);"></div>
              </td></tr>

              <!-- CUERPO -->
              <tr><td style="padding:24px 32px;text-align:center;">
                <p style="margin:0 0 22px;font-size:13px;
                           color:rgba(255,255,255,0.5);line-height:1.7;">
                  Haz clic en el botón para crear una contraseña nueva.<br/>
                  Este enlace es válido por <strong style="color:#f0a500;">15 minutos</strong>
                  y solo puede usarse una vez.
                </p>

                <a href="{reset_url}"
                   style="display:inline-block;padding:14px 36px;
                          background:linear-gradient(135deg,#f0a500,#c8870a);
                          color:#000;font-weight:bold;font-size:15px;
                          text-decoration:none;border-radius:12px;
                          font-family:Arial,sans-serif;letter-spacing:0.3px;
                          box-shadow:0 6px 20px rgba(240,165,0,0.3);">
                  🔑 Restablecer contraseña
                </a>

                <p style="margin:22px 0 0;font-size:11px;
                           color:rgba(255,255,255,0.2);">
                  Si no solicitaste este cambio, ignora este correo.<br/>
                  Tu contraseña actual seguirá siendo la misma.
                </p>
              </td></tr>

              <!-- URL de respaldo -->
              <tr><td style="padding:0 32px 20px;">
                <div style="background:rgba(0,0,0,0.25);border-radius:8px;
                            padding:10px 14px;word-break:break-all;">
                  <p style="margin:0 0 4px;font-size:10px;
                             color:rgba(255,255,255,0.25);letter-spacing:1px;
                             text-transform:uppercase;">
                    O copia este enlace en tu navegador:
                  </p>
                  <span style="font-size:10px;color:rgba(240,165,0,0.5);
                                font-family:'Courier New',monospace;">
                    {reset_url}
                  </span>
                </div>
              </td></tr>

              <!-- FOOTER -->
              <tr><td style="background:rgba(0,0,0,0.2);padding:14px 32px;
                             text-align:center;
                             border-top:1px solid rgba(255,255,255,0.04);">
                <p style="margin:0;font-size:11px;color:rgba(255,255,255,0.2);">
                  🔒 Enlace de un solo uso · Expira en 15 minutos
                </p>
              </td></tr>

            </table>

            <p style="font-size:12px;color:#888;margin-top:18px;text-align:center;">
              ¿Necesitas ayuda?
              <a href="mailto:soporte@soundpass.shop"
                 style="color:#f0a500;">soporte@soundpass.shop</a>
            </p>

          </td></tr>
        </table>
        </body></html>
        """

        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(smtp_host, 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, app_pass)
            server.send_message(msg)

        print(f"[RESET] ✅ Correo enviado a {destinatario}")

    except smtplib.SMTPAuthenticationError:
        print("[RESET ERROR] ❌ Credenciales SMTP incorrectas")
    except Exception as e:
        print(f"[RESET ERROR] ❌ {type(e).__name__}: {e}")


# ─────────────────────────────────────────────
#  LOGIN
# ─────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    session.clear()

    if request.method == "POST":
        correo   = request.form.get("correo",   "").strip().lower()
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

            session.permanent     = True
            session["usuario_id"] = usuario["id"]
            session["nombre"]     = usuario["nombre"]
            session["correo"]     = usuario["correo"]
            session["rol"]        = usuario["rol"]

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


# ─────────────────────────────────────────────
#  REGISTRO
# ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────
#  LOGOUT
# ─────────────────────────────────────────────
@auth_bp.route("/logout")
def logout():
    session.clear()
    session.modified = True
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("auth.login"))


# ─────────────────────────────────────────────
#  PASO 1: Solicitar reseteo — mostrar formulario
#          y generar token si el correo existe
# ─────────────────────────────────────────────
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """
    GET  → muestra el formulario "¿Olvidaste tu contraseña?"
    POST → busca el correo, genera token, envía correo.
           Siempre muestra el mismo mensaje de éxito para no
           revelar si el correo existe o no (seguridad).
    """
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()

        if not correo:
            flash("Por favor ingresa tu correo electrónico.", "danger")
            return render_template("auth/forgot_password.html")

        conn = cursor = None
        try:
            conn   = get_db()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                "SELECT id, nombre FROM usuarios WHERE correo = %s", (correo,)
            )
            usuario = cursor.fetchone()

            # Si el usuario existe, crear token y enviar correo
            if usuario:
                # Invalidar tokens anteriores del mismo usuario (limpieza)
                cursor.execute(
                    "UPDATE password_reset_tokens SET usado = 1 "
                    "WHERE usuario_id = %s AND usado = 0",
                    (usuario["id"],)
                )

                # Generar token seguro: 48 bytes → 64 chars URL-safe
                token     = secrets.token_urlsafe(48)
                expira_en = datetime.now() + timedelta(minutes=15)

                cursor.execute("""
                    INSERT INTO password_reset_tokens
                    (usuario_id, token, expira_en)
                    VALUES (%s, %s, %s)
                """, (usuario["id"], token, expira_en))
                conn.commit()

                # Construir URL y enviar correo en hilo separado
                reset_url = f"https://soundpass.shop/auth/reset-password?token={token}"
                cfg = {
                    "EMAIL_REMITENTE": current_app.config.get("EMAIL_REMITENTE", ""),
                    "EMAIL_APP_PASS":  current_app.config.get("EMAIL_APP_PASS",  ""),
                    "EMAIL_SMTP_HOST": current_app.config.get("EMAIL_SMTP_HOST", "smtp-relay.brevo.com"),
                    "EMAIL_SMTP_USER": current_app.config.get("EMAIL_SMTP_USER", ""),
                }
                threading.Thread(
                    target=_enviar_correo_reset_worker,
                    args=(cfg, correo, usuario["nombre"], reset_url),
                    daemon=True
                ).start()

            # Siempre mostramos el mismo mensaje → no revela si el correo existe
            flash(
                "Si ese correo está registrado, recibirás un enlace en los próximos minutos. "
                "Revisa también tu carpeta de spam.",
                "success"
            )
            return redirect(url_for("auth.forgot_password"))

        except mysql.connector.Error as e:
            flash(f"Error: {e}", "danger")
        finally:
            if cursor: cursor.close()
            if conn:   conn.close()

    return render_template("auth/forgot_password.html")


# ─────────────────────────────────────────────
#  PASO 2: Resetear contraseña con el token
# ─────────────────────────────────────────────
@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """
    GET  → valida el token de la URL y muestra formulario de nueva contraseña.
    POST → valida token de nuevo (en campo hidden), actualiza la contraseña,
           marca el token como usado y redirige al login.
    """
    token = request.args.get("token") or request.form.get("token", "")

    if not token:
        flash("Enlace inválido o incompleto.", "danger")
        return redirect(url_for("auth.forgot_password"))

    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        # Buscar token válido: existe, no usado y no expirado
        cursor.execute("""
            SELECT prt.*, u.nombre, u.correo
            FROM password_reset_tokens prt
            JOIN usuarios u ON prt.usuario_id = u.id
            WHERE prt.token = %s
              AND prt.usado = 0
              AND prt.expira_en > NOW()
        """, (token,))
        registro = cursor.fetchone()

        if not registro:
            flash(
                "Este enlace no es válido o ya expiró. "
                "Solicita uno nuevo.",
                "danger"
            )
            return redirect(url_for("auth.forgot_password"))

        # ── GET: mostrar formulario ──
        if request.method == "GET":
            return render_template("auth/reset_password.html",
                token  = token,
                nombre = registro["nombre"],
            )

        # ── POST: procesar nueva contraseña ──
        nueva      = request.form.get("password",  "")
        confirmar  = request.form.get("confirm",   "")

        if not nueva or len(nueva) < 8:
            flash("La contraseña debe tener al menos 8 caracteres.", "danger")
            return render_template("auth/reset_password.html",
                token=token, nombre=registro["nombre"])

        if nueva != confirmar:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("auth/reset_password.html",
                token=token, nombre=registro["nombre"])

        hashed = generate_password_hash(nueva)

        # Actualizar contraseña
        cursor.execute(
            "UPDATE usuarios SET password = %s WHERE id = %s",
            (hashed, registro["usuario_id"])
        )
        # Marcar token como usado (nunca puede reutilizarse)
        cursor.execute(
            "UPDATE password_reset_tokens SET usado = 1 WHERE token = %s",
            (token,)
        )
        conn.commit()

        flash(
            "¡Contraseña actualizada correctamente! Ya puedes iniciar sesión.",
            "success"
        )
        return redirect(url_for("auth.login"))

    except mysql.connector.Error as e:
        flash(f"Error: {e}", "danger")
        return redirect(url_for("auth.forgot_password"))
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()