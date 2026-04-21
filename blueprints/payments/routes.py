"""blueprints/payments/routes.py"""
import uuid
import threading

import stripe
from flask import (
    render_template, request, redirect, url_for,
    flash, session, jsonify, current_app
)
import mysql.connector

from extensions import get_db
from decorators import login_requerido
from . import payments_bp


# ─────────────────────────────────────────────
#  HELPER: configurar Stripe
# ─────────────────────────────────────────────
def get_stripe():
    stripe.api_key = current_app.config.get("STRIPE_SECRET_KEY")
    return stripe


# ─────────────────────────────────────────────
#  CORREO RESUMEN DE COMPRA (múltiples tickets)
# ─────────────────────────────────────────────
def _enviar_correo_resumen_worker(cfg: dict, destinatario: str, nombre: str,
                                   evento_nombre: str, cantidad: int,
                                   zona_nombre: str, precio_unitario,
                                   imagen_url: str):
    """
    Hilo independiente. Envía un correo resumen cuando el usuario compra
    múltiples entradas. No incluye QR individual — invita a ver /mis-entradas.
    Compatible con Brevo SMTP (smtp-relay.brevo.com:587).
    """
    import smtplib, base64, os
    from email.mime.multipart import MIMEMultipart
    from email.mime.text      import MIMEText
    from email.mime.image     import MIMEImage

    try:
        remitente = cfg["EMAIL_REMITENTE"]
        app_pass  = cfg["EMAIL_APP_PASS"]
        smtp_host = cfg.get("EMAIL_SMTP_HOST", "smtp-relay.brevo.com")
        smtp_user = cfg.get("EMAIL_SMTP_USER", "")

        precio_total = float(precio_unitario) * cantidad

        msg_root = MIMEMultipart("related")
        msg_root["Subject"] = f"🎟️ {cantidad} ticket{'s' if cantidad > 1 else ''} confirmado{'s' if cantidad > 1 else ''} — {evento_nombre}"
        msg_root["From"]    = f"SoundPass <{remitente}>"
        msg_root["To"]      = destinatario

        msg_alt = MIMEMultipart("alternative")
        msg_root.attach(msg_alt)

        # ── Imagen del evento (embebida por CID) ──
        evento_img_html = '<div style="height:120px;background:linear-gradient(135deg,#1a1a2e,#0d0d1a);display:flex;align-items:center;justify-content:center;font-size:3rem;">🎸</div>'
        if imagen_url:
            try:
                ruta_limpia   = imagen_url.lstrip("/")
                ruta_absoluta = os.path.join("/var/www/concert_tickets", ruta_limpia)
                with open(ruta_absoluta, "rb") as f:
                    img_data = f.read()
                ext = os.path.splitext(ruta_absoluta)[1].lower().replace(".", "") or "png"
                if ext == "jpg": ext = "jpeg"
                img_mime = MIMEImage(img_data, _subtype=ext)
                img_mime.add_header("Content-ID", "<evento_img>")
                img_mime.add_header("Content-Disposition", "inline")
                msg_root.attach(img_mime)
                evento_img_html = '<img src="cid:evento_img" style="display:block;max-width:100%;max-height:160px;margin:0 auto;object-fit:contain;"/>'
            except Exception as e:
                print(f"[CORREO RESUMEN] No se pudo cargar imagen del evento: {e}")

        # ── Filas de detalle ──
        detalle_rows = f"""
          <tr>
            <td style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
              <span style="font-size:10px;color:rgba(255,255,255,0.4);text-transform:uppercase;letter-spacing:1px;display:block;margin-bottom:3px;">Evento</span>
              <span style="font-size:16px;color:#ffffff;font-weight:bold;">{evento_nombre}</span>
            </td>
          </tr>
          <tr>
            <td style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
              <span style="font-size:10px;color:rgba(255,255,255,0.4);text-transform:uppercase;letter-spacing:1px;display:block;margin-bottom:3px;">Zona</span>
              <span style="display:inline-block;background:rgba(240,165,0,0.1);color:#f0a500;border:1px solid rgba(240,165,0,0.25);border-radius:6px;padding:5px 14px;font-size:14px;font-weight:bold;">{zona_nombre}</span>
            </td>
          </tr>
          <tr>
            <td style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
              <span style="font-size:10px;color:rgba(255,255,255,0.4);text-transform:uppercase;letter-spacing:1px;display:block;margin-bottom:3px;">Entradas</span>
              <span style="font-size:16px;color:#ffffff;font-weight:bold;">{cantidad} entrada{'s' if cantidad > 1 else ''} × ${precio_unitario}</span>
            </td>
          </tr>
          <tr>
            <td style="padding:10px 0;">
              <span style="font-size:10px;color:rgba(255,255,255,0.4);text-transform:uppercase;letter-spacing:1px;display:block;margin-bottom:3px;">Total pagado</span>
              <span style="font-family:Arial Black,sans-serif;font-size:24px;color:#f0a500;letter-spacing:1px;">${precio_total:.2f}</span>
            </td>
          </tr>
        """

        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <body style="margin:0;padding:0;background-color:#ffffff;font-family:Arial,sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f5f5f0;padding:40px 0;">
          <tr><td align="center">

            <table width="520" cellpadding="0" cellspacing="0"
                   style="max-width:520px;background-color:#12121e;border-radius:20px;
                          box-shadow:0 10px 25px rgba(0,0,0,0.25);
                          border:1px solid rgba(240,165,0,0.1);overflow:hidden;">

              <!-- HEADER -->
              <tr><td style="padding:28px 32px 20px;text-align:center;">
                <div style="margin-bottom:12px;">
                  <span style="font-size:24px;vertical-align:middle;margin-right:6px;">🎸</span>
                  <span style="font-size:24px;color:#f0a500;font-family:'Arial Black',Impact,sans-serif;
                               font-weight:bold;letter-spacing:1px;vertical-align:middle;">SOUNDPASS</span>
                </div>
                <p style="margin:0 0 6px;font-size:11px;letter-spacing:3px;text-transform:uppercase;color:rgba(240,165,0,0.6);">
                  ✅ COMPRA CONFIRMADA
                </p>
                <h1 style="margin:4px 0 0;font-size:26px;color:#f0a500;letter-spacing:1px;
                            font-family:Arial Black,sans-serif;">
                  ¡{cantidad} ticket{'s' if cantidad > 1 else ''} listo{'s' if cantidad > 1 else ''}!
                </h1>
              </td></tr>

              <!-- IMAGEN EVENTO -->
              <tr><td style="padding:0 24px 0;">
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr><td align="center" style="background-color:#080810;border-radius:12px;overflow:hidden;padding:10px 0;">
                    {evento_img_html}
                  </td></tr>
                </table>
              </td></tr>

              <!-- SEPARADOR -->
              <tr><td style="padding:20px 32px 0;">
                <table width="100%"><tr><td style="border-top:1px dashed rgba(240,165,0,0.15);"></td></tr></table>
              </td></tr>

              <!-- DETALLE -->
              <tr><td style="padding:16px 32px 0;">
                <table width="100%" cellpadding="0" cellspacing="0">
                  {detalle_rows}
                </table>
              </td></tr>

              <!-- SEPARADOR -->
              <tr><td style="padding:20px 32px 0;">
                <table width="100%"><tr><td style="border-top:2px dashed rgba(240,165,0,0.15);"></td></tr></table>
              </td></tr>

              <!-- CTA: VER MIS ENTRADAS -->
              <tr><td style="padding:28px 32px;text-align:center;">
                <p style="margin:0 0 6px;font-size:13px;color:rgba(255,255,255,0.5);">
                  Hola <strong style="color:#fff;">{nombre}</strong>, tus entradas están listas.<br/>
                  Accede a ellas en cualquier momento desde tu perfil.
                </p>
                <p style="margin:0 0 20px;font-size:11px;color:rgba(255,255,255,0.3);">
                  Cada entrada tiene su propio código QR de acceso único.
                </p>
                <a href="https://soundpass.shop/mis-entradas"
                   style="display:inline-block;padding:14px 36px;
                          background:linear-gradient(135deg,#f0a500,#c8870a);
                          color:#000000;font-weight:bold;font-size:15px;
                          text-decoration:none;border-radius:12px;
                          font-family:Arial,sans-serif;letter-spacing:0.5px;
                          box-shadow:0 6px 20px rgba(240,165,0,0.3);">
                  🎟️ Ver mis entradas
                </a>
              </td></tr>

              <!-- FOOTER -->
              <tr><td style="background:rgba(0,0,0,0.2);padding:14px 32px;text-align:center;
                             border-top:1px solid rgba(255,255,255,0.04);">
                <p style="margin:0;font-size:11px;color:rgba(255,255,255,0.25);">
                  🔒 Cada entrada es de un solo uso · No compartas tus códigos QR
                </p>
              </td></tr>

            </table>

            <p style="font-size:12px;color:#888888;margin-top:20px;text-align:center;">
              ¿Problemas? Escríbenos a <a href="mailto:soporte@soundpass.shop" style="color:#f0a500;">soporte@soundpass.shop</a>
            </p>

          </td></tr>
        </table>
        </body></html>
        """

        msg_alt.attach(MIMEText(html, "html"))

        with smtplib.SMTP(smtp_host, 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, app_pass)
            server.send_message(msg_root)

        print(f"[CORREO RESUMEN] ✅ Enviado a {destinatario} — {cantidad} ticket(s) para '{evento_nombre}'")

    except smtplib.SMTPAuthenticationError:
        print("[CORREO RESUMEN ERROR] ❌ Credenciales SMTP incorrectas")
    except Exception as e:
        print(f"[CORREO RESUMEN ERROR] ❌ {type(e).__name__}: {e}")


# ─────────────────────────────────────────────
#  HELPER INTERNO: crear tickets en DB
#  Usado tanto por /success como por el webhook.
#  Retorna la lista de códigos UUID creados,
#  o [] si la session ya fue procesada (idempotente).
# ─────────────────────────────────────────────
def _crear_tickets_en_db(conn, cursor, stripe_session_id,
                          cantidad, usuario_id, evento_id,
                          zona_id, nombre, correo):
    """
    Inserta `cantidad` tickets individuales en la tabla `tickets`.
    Cada uno lleva su propio UUID. El stripe_session_id solo se guarda
    en el PRIMER ticket del lote para garantizar idempotencia.
    Retorna lista de UUIDs creados, o [] si ya existían.
    """
    # Verificar idempotencia — ¿ya existe algún ticket con esta sesión?
    cursor.execute(
        "SELECT id FROM tickets WHERE stripe_session_id = %s LIMIT 1",
        (stripe_session_id,)
    )
    if cursor.fetchone():
        print(f"[DB] Tickets ya creados para session {stripe_session_id}")
        return []

    codigos = []
    for i in range(cantidad):
        codigo = str(uuid.uuid4())
        # stripe_session_id solo en el ticket #0 para el check de idempotencia
        ssid = stripe_session_id if i == 0 else None
        cursor.execute("""
            INSERT INTO tickets
            (codigo, usuario_id, evento_id, zona_id, nombre, correo, estado, stripe_session_id)
            VALUES (%s, %s, %s, %s, %s, %s, 'activo', %s)
        """, (codigo, usuario_id, evento_id, zona_id, nombre, correo, ssid))
        codigos.append(codigo)

    # Sumar toda la cantidad de una sola vez
    cursor.execute(
        "UPDATE zonas_evento SET vendidos = vendidos + %s WHERE id = %s",
        (cantidad, zona_id)
    )
    conn.commit()
    return codigos


# ─────────────────────────────────────────────
#  PASO 1: checkout — crear Stripe Session
# ─────────────────────────────────────────────
@payments_bp.route("/checkout/<int:evento_id>", methods=["POST"])
@login_requerido
def checkout(evento_id):
    zona_id  = request.form.get("zona_id",  "").strip()
    nombre   = request.form.get("nombre",   "").strip()
    correo   = request.form.get("correo",   "").strip()

    # ── Validar cantidad: entre 1 y 5 ──
    try:
        cantidad = int(request.form.get("cantidad", 1))
        if not 1 <= cantidad <= 5:
            raise ValueError
    except (ValueError, TypeError):
        flash("La cantidad debe ser entre 1 y 5 entradas.", "danger")
        return redirect(url_for("public.evento", evento_id=evento_id))

    if not zona_id or not nombre or not correo:
        flash("Por favor completa todos los campos.", "danger")
        return redirect(url_for("public.evento", evento_id=evento_id))

    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT zev.*,
                   e.nombre      AS evento_nombre,
                   e.imagen_url  AS evento_imagen,
                   e.fecha       AS evento_fecha,
                   e.hora        AS evento_hora
            FROM zonas_evento zev
            JOIN eventos e ON zev.evento_id = e.id
            WHERE zev.id = %s AND zev.evento_id = %s
        """, (zona_id, evento_id))
        zona = cursor.fetchone()

        if not zona:
            flash("Zona no válida.", "danger")
            return redirect(url_for("public.evento", evento_id=evento_id))

        disponibles = zona["capacidad"] - zona["vendidos"]
        if disponibles < cantidad:
            flash(f"Solo quedan {disponibles} lugar{'es' if disponibles != 1 else ''} en esta zona.", "warning")
            return redirect(url_for("public.evento", evento_id=evento_id))

        s       = get_stripe()
        dominio = "https://soundpass.shop"

        images = []
        if zona.get("evento_imagen"):
            img = zona["evento_imagen"]
            images = [f"{dominio}{img}" if img.startswith("/") else img]

        checkout_session = s.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency":     "usd",
                    "unit_amount":  int(float(zona["precio"]) * 100),
                    "product_data": {
                        "name":        f"{zona['evento_nombre']} — {zona['nombre']}",
                        "description": (
                            f"{cantidad} entrada{'s' if cantidad > 1 else ''} · Asistente: {nombre}"
                        ),
                        "images": images,
                    },
                },
                "quantity": cantidad,   # ← Stripe multiplica el precio automáticamente
            }],
            mode="payment",
            success_url=f"{dominio}/payments/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{dominio}/evento/{evento_id}",
            customer_email=correo,
            metadata={
                "evento_id":   str(evento_id),
                "zona_id":     str(zona_id),
                "nombre":      nombre,
                "correo":      correo,
                "usuario_id":  str(session.get("usuario_id", "")),
                "cantidad":    str(cantidad),           # ← pasamos la cantidad
            }
        )

        return redirect(checkout_session.url, code=303)

    except stripe.error.StripeError as e:
        flash(f"Error con el pago: {e.user_message}", "danger")
        return redirect(url_for("public.evento", evento_id=evento_id))
    except mysql.connector.Error as e:
        flash(f"Error de base de datos: {e}", "danger")
        return redirect(url_for("public.evento", evento_id=evento_id))
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────
#  PASO 2A: success — verificar y crear tickets
# ─────────────────────────────────────────────
@payments_bp.route("/success")
@login_requerido
def success():
    session_id = request.args.get("session_id")
    if not session_id:
        flash("Sesión de pago no válida.", "danger")
        return redirect(url_for("public.index"))

    try:
        s = get_stripe()
        checkout_session = s.checkout.Session.retrieve(session_id)

        if checkout_session.payment_status != "paid":
            flash("El pago no fue completado.", "warning")
            return redirect(url_for("public.index"))

        session_dict = checkout_session.to_dict()
        meta         = session_dict.get("metadata", {})

        evento_id         = int(meta["evento_id"])
        zona_id           = int(meta["zona_id"])
        nombre            = meta["nombre"]
        correo            = meta["correo"]
        usuario_id        = int(meta["usuario_id"]) if meta.get("usuario_id") else None
        stripe_session_id = session_dict["id"]
        cantidad          = max(1, min(5, int(meta.get("cantidad", 1))))  # sanity clamp

        conn = cursor = None
        try:
            conn   = get_db()
            cursor = conn.cursor(dictionary=True)

            codigos = _crear_tickets_en_db(
                conn, cursor, stripe_session_id,
                cantidad, usuario_id, evento_id, zona_id, nombre, correo
            )
            # codigos == [] → webhook ya los creó; igual renderizamos éxito
            # (no necesitamos los códigos aquí porque redirigimos a /mis-entradas)

            # Obtener info del evento para el correo
            cursor.execute("""
                SELECT zev.nombre AS zona_nombre, zev.precio,
                       e.nombre AS evento_nombre, e.imagen_url,
                       e.fecha, e.hora
                FROM zonas_evento zev
                JOIN eventos e ON zev.evento_id = e.id
                WHERE zev.id = %s
            """, (zona_id,))
            info = cursor.fetchone()

            if info:
                cfg = {
                    "EMAIL_REMITENTE": current_app.config.get("EMAIL_REMITENTE", ""),
                    "EMAIL_APP_PASS":  current_app.config.get("EMAIL_APP_PASS",  ""),
                    "EMAIL_SMTP_HOST": current_app.config.get("EMAIL_SMTP_HOST", "smtp-relay.brevo.com"),
                    "EMAIL_SMTP_USER": current_app.config.get("EMAIL_SMTP_USER", ""),
                }
                threading.Thread(
                    target=_enviar_correo_resumen_worker,
                    args=(
                        cfg, correo, nombre,
                        info["evento_nombre"], cantidad,
                        info["zona_nombre"], info["precio"],
                        info.get("imagen_url") or "",
                    ),
                    daemon=True
                ).start()

            return render_template("tickets/confirmacion.html",
                nombre   = nombre,
                correo   = correo,
                zona     = info["zona_nombre"] if info else "—",
                precio   = info["precio"]      if info else 0,
                evento   = info["evento_nombre"] if info else "—",
                cantidad = cantidad,
                pago_ok  = True,
            )

        except mysql.connector.Error as e:
            flash(f"Error al guardar los tickets: {e}", "danger")
            return redirect(url_for("public.index"))
        finally:
            if cursor: cursor.close()
            if conn:   conn.close()

    except stripe.error.StripeError as e:
        flash(f"Error verificando el pago: {e.user_message}", "danger")
        return redirect(url_for("public.index"))


# ─────────────────────────────────────────────
#  PASO 2B: webhook — respaldo de Stripe
# ─────────────────────────────────────────────
@payments_bp.route("/webhook", methods=["POST"])
def webhook():
    payload        = request.get_data(as_text=True)
    sig_header     = request.headers.get("Stripe-Signature")
    webhook_secret = current_app.config.get("STRIPE_WEBHOOK_SECRET", "")

    if not webhook_secret:
        print("[WEBHOOK] No hay STRIPE_WEBHOOK_SECRET configurado")
        return jsonify({"status": "no_secret"}), 200

    try:
        s     = get_stripe()
        event = s.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "Invalid signature"}), 400

    if event["type"] == "checkout.session.completed":
        obj = event["data"]["object"]
        if obj["payment_status"] == "paid":
            _procesar_pago_webhook(obj)

    return jsonify({"status": "ok"}), 200


def _procesar_pago_webhook(checkout_session):
    """
    Crea los tickets desde el webhook de Stripe.
    Idéntica lógica a /success pero sin contexto HTTP.
    """
    try:
        session_dict      = checkout_session.to_dict() if hasattr(checkout_session, "to_dict") else checkout_session
        meta              = session_dict.get("metadata", {})

        evento_id         = int(meta["evento_id"])
        zona_id           = int(meta["zona_id"])
        nombre            = meta["nombre"]
        correo            = meta["correo"]
        usuario_id        = int(meta.get("usuario_id") or 0) or None
        stripe_session_id = session_dict["id"]
        cantidad          = max(1, min(5, int(meta.get("cantidad", 1))))

        conn = cursor = None
        try:
            conn   = get_db()
            cursor = conn.cursor(dictionary=True)

            codigos = _crear_tickets_en_db(
                conn, cursor, stripe_session_id,
                cantidad, usuario_id, evento_id, zona_id, nombre, correo
            )

            if not codigos:
                # Ya procesado por /success
                return

            print(f"[WEBHOOK] ✅ {len(codigos)} ticket(s) creados para session {stripe_session_id}")

            # Correo resumen desde el webhook (no tenemos current_app aquí,
            # pero get_db() funciona porque usa la app context en gunicorn)
            cursor.execute("""
                SELECT zev.nombre AS zona_nombre, zev.precio,
                       e.nombre AS evento_nombre, e.imagen_url
                FROM zonas_evento zev
                JOIN eventos e ON zev.evento_id = e.id
                WHERE zev.id = %s
            """, (zona_id,))
            info = cursor.fetchone()

            if info:
                # Leer config directamente desde variables de entorno como fallback
                import os
                cfg = {
                    "EMAIL_REMITENTE": os.getenv("EMAIL_REMITENTE", ""),
                    "EMAIL_APP_PASS":  os.getenv("EMAIL_APP_PASS",  ""),
                    "EMAIL_SMTP_HOST": os.getenv("EMAIL_SMTP_HOST", "smtp-relay.brevo.com"),
                    "EMAIL_SMTP_USER": os.getenv("EMAIL_SMTP_USER", ""),
                }
                threading.Thread(
                    target=_enviar_correo_resumen_worker,
                    args=(
                        cfg, correo, nombre,
                        info["evento_nombre"], cantidad,
                        info["zona_nombre"], info["precio"],
                        info.get("imagen_url") or "",
                    ),
                    daemon=True
                ).start()

        except mysql.connector.Error as e:
            print(f"[WEBHOOK ERROR] DB: {e}")
        finally:
            if cursor: cursor.close()
            if conn:   conn.close()

    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")