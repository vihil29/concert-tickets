"""blueprints/payments/routes.py"""
import uuid
import json
import threading

import stripe
from flask import render_template, request, redirect, url_for, flash, session, jsonify, current_app
import mysql.connector

from extensions import get_db
from decorators import login_requerido
from . import payments_bp


def get_stripe():
    """Configura y retorna stripe con la clave secreta."""
    stripe.api_key = current_app.config.get("STRIPE_SECRET_KEY")
    return stripe


# ─────────────────────────────────────────────
#  PASO 1: El usuario selecciona zona → ve checkout
# ─────────────────────────────────────────────
@payments_bp.route("/checkout/<int:evento_id>", methods=["POST"])
@login_requerido
def checkout(evento_id):
    """
    Recibe zona_id, nombre, correo del formulario.
    Crea una Stripe Checkout Session y redirige al pago.
    El ticket NO se crea aquí — se crea cuando Stripe confirma el pago.
    """
    zona_id = request.form.get("zona_id", "").strip()
    nombre  = request.form.get("nombre",  "").strip()
    correo  = request.form.get("correo",  "").strip()

    if not zona_id or not nombre or not correo:
        flash("Por favor completa todos los campos.", "danger")
        return redirect(url_for("public.evento", evento_id=evento_id))

    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        # Obtener info de la zona y el evento
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

        if zona["vendidos"] >= zona["capacidad"]:
            flash("Esta zona está agotada.", "warning")
            return redirect(url_for("public.evento", evento_id=evento_id))

        s = get_stripe()
        dominio = "https://soundpass.shop"

        # Imagen del evento para mostrar en el checkout de Stripe
        images = []
        if zona.get("evento_imagen"):
            img = zona["evento_imagen"]
            images = [f"{dominio}{img}" if img.startswith("/") else img]

        # Crear la sesión de pago en Stripe
        # Stripe maneja toda la UI del pago — tarjeta, validación, 3D Secure, etc.
        checkout_session = s.checkout.Session.create(
            payment_method_types=["card"],   # acepta Visa, Mastercard, Amex
            line_items=[{
                "price_data": {
                    "currency":     "usd",
                    "unit_amount":  int(float(zona["precio"]) * 100),  # Stripe usa centavos
                    "product_data": {
                        "name":        f"{zona['evento_nombre']} — {zona['nombre']}",
                        "description": f"Asistente: {nombre}",
                        "images":      images,
                    },
                },
                "quantity": 1,
            }],
            mode="payment",
            # URLs de retorno después del pago
            success_url=f"{dominio}/payments/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{dominio}/evento/{evento_id}",
            customer_email=correo,
            # Metadata: datos que necesitamos cuando Stripe confirme el pago
            metadata={
                "evento_id":   str(evento_id),
                "zona_id":     str(zona_id),
                "nombre":      nombre,
                "correo":      correo,
                "usuario_id":  str(session.get("usuario_id", "")),
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
#  PASO 2A: Pago exitoso → crear ticket
# ─────────────────────────────────────────────
@payments_bp.route("/success")
@login_requerido
def success():
    """
    Stripe redirige aquí después de un pago exitoso.
    Verificamos la sesión con Stripe, creamos el ticket en la DB
    y enviamos el correo de confirmación.
    """
    session_id = request.args.get("session_id")
    if not session_id:
        flash("Sesión de pago no válida.", "danger")
        return redirect(url_for("public.index"))

    try:
        s = get_stripe()

        # Recuperar la sesión de Stripe para verificar que el pago fue real
        checkout_session = s.checkout.Session.retrieve(session_id)

        # Verificar que el pago fue completado
        if checkout_session.payment_status != "paid":
            flash("El pago no fue completado.", "warning")
            return redirect(url_for("public.index"))

        # Verificar que no procesamos este pago antes (idempotencia)
        meta       = checkout_session.metadata
        evento_id  = int(meta["evento_id"])
        zona_id    = int(meta["zona_id"])
        nombre     = meta["nombre"]
        correo     = meta["correo"]
        usuario_id = int(meta["usuario_id"]) if meta.get("usuario_id") else None
        stripe_session_id = checkout_session.id

        conn = cursor = None
        try:
            conn   = get_db()
            cursor = conn.cursor(dictionary=True)

            # Verificar si ya existe un ticket con este stripe_session_id
            # para evitar crear duplicados si el usuario recarga la página
            cursor.execute(
                "SELECT id, codigo FROM tickets WHERE stripe_session_id = %s",
                (stripe_session_id,)
            )
            existing = cursor.fetchone()

            if existing:
                # Ya fue procesado — mostrar confirmación igual
                codigo = existing["codigo"]
                from blueprints.tickets.routes import generar_qr_base64
                qr_base64 = generar_qr_base64(codigo)
            else:
                # Crear el ticket
                codigo    = str(uuid.uuid4())
                from blueprints.tickets.routes import generar_qr_base64
                qr_base64 = generar_qr_base64(codigo)

                cursor.execute("""
                    INSERT INTO tickets
                    (codigo, usuario_id, evento_id, zona_id, nombre, correo, estado, stripe_session_id)
                    VALUES (%s, %s, %s, %s, %s, %s, 'activo', %s)
                """, (codigo, usuario_id, evento_id, zona_id, nombre, correo, stripe_session_id))

                cursor.execute(
                    "UPDATE zonas_evento SET vendidos = vendidos + 1 WHERE id = %s", (zona_id,)
                )
                conn.commit()

                # Obtener datos del evento para el correo
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
                    # Formatear hora
                    hora_obj = info.get("hora")
                    if hora_obj and hasattr(hora_obj, 'total_seconds'):
                        t = int(hora_obj.total_seconds())
                        hora_str = f"{t//3600:02d}:{(t%3600)//60:02d}"
                    elif hora_obj and hasattr(hora_obj, 'strftime'):
                        hora_str = hora_obj.strftime('%H:%M')
                    else:
                        hora_str = "—"

                    fecha_obj = info.get("fecha")
                    fecha_str = fecha_obj.strftime('%d de %B de %Y') if fecha_obj else "—"

                    from blueprints.tickets.routes import _enviar_correo_worker
                    cfg = {
                        "EMAIL_REMITENTE": current_app.config.get("EMAIL_REMITENTE", ""),
                        "EMAIL_APP_PASS":  current_app.config.get("EMAIL_APP_PASS",  ""),
                        "EMAIL_SMTP_HOST": current_app.config.get("EMAIL_SMTP_HOST", "smtp-relay.brevo.com"),
                        "EMAIL_SMTP_USER": current_app.config.get("EMAIL_SMTP_USER", ""),
                    }
                    threading.Thread(
                        target=_enviar_correo_worker,
                        args=(cfg, correo, nombre, codigo,
                              info["evento_nombre"], fecha_str, hora_str,
                              info["zona_nombre"], info["precio"],
                              info.get("imagen_url") or "", qr_base64),
                        daemon=True
                    ).start()

                    return render_template("tickets/confirmacion.html",
                        nombre    = nombre,
                        correo    = correo,
                        zona      = info["zona_nombre"],
                        precio    = info["precio"],
                        evento    = info["evento_nombre"],
                        codigo    = codigo,
                        qr_base64 = qr_base64,
                        pago_ok   = True
                    )

        except mysql.connector.Error as e:
            flash(f"Error al guardar el ticket: {e}", "danger")
            return redirect(url_for("public.index"))
        finally:
            if cursor: cursor.close()
            if conn:   conn.close()

    except stripe.error.StripeError as e:
        flash(f"Error verificando el pago: {e.user_message}", "danger")
        return redirect(url_for("public.index"))

    return redirect(url_for("public.index"))


# ─────────────────────────────────────────────
#  PASO 2B: Webhook de Stripe (respaldo)
#  Stripe llama a este endpoint cuando confirma el pago
#  Funciona incluso si el usuario cierra el navegador
# ─────────────────────────────────────────────
@payments_bp.route("/webhook", methods=["POST"])
def webhook():
    """
    Stripe llama a este endpoint con eventos de pago.
    Es el método más seguro — no depende de que el usuario
    llegue a la página de success.
    Requiere configurar el Webhook en el dashboard de Stripe.
    """
    payload    = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = current_app.config.get("STRIPE_WEBHOOK_SECRET", "")

    if not webhook_secret:
        # Sin webhook secret configurado — solo logear
        print("[WEBHOOK] No hay STRIPE_WEBHOOK_SECRET configurado")
        return jsonify({"status": "no_secret"}), 200

    try:
        s     = get_stripe()
        event = s.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "Invalid signature"}), 400

    # Procesar el evento de pago completado
    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        if session_obj["payment_status"] == "paid":
            _procesar_pago_webhook(session_obj)

    return jsonify({"status": "ok"}), 200


def _procesar_pago_webhook(checkout_session):
    """
    Crea el ticket en la DB desde el webhook de Stripe.
    Funciona igual que /success pero sin contexto HTTP.
    """
    try:
        meta             = checkout_session["metadata"]
        evento_id        = int(meta["evento_id"])
        zona_id          = int(meta["zona_id"])
        nombre           = meta["nombre"]
        correo           = meta["correo"]
        usuario_id       = int(meta.get("usuario_id") or 0) or None
        stripe_session_id = checkout_session["id"]

        conn = cursor = None
        try:
            conn   = get_db()
            cursor = conn.cursor(dictionary=True)

            # Verificar idempotencia
            cursor.execute(
                "SELECT id FROM tickets WHERE stripe_session_id = %s",
                (stripe_session_id,)
            )
            if cursor.fetchone():
                print(f"[WEBHOOK] Ticket ya existe para session {stripe_session_id}")
                return

            codigo = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO tickets
                (codigo, usuario_id, evento_id, zona_id, nombre, correo, estado, stripe_session_id)
                VALUES (%s, %s, %s, %s, %s, %s, 'activo', %s)
            """, (codigo, usuario_id, evento_id, zona_id, nombre, correo, stripe_session_id))

            cursor.execute(
                "UPDATE zonas_evento SET vendidos = vendidos + 1 WHERE id = %s", (zona_id,)
            )
            conn.commit()
            print(f"[WEBHOOK] ✅ Ticket creado: {codigo}")

        except mysql.connector.Error as e:
            print(f"[WEBHOOK ERROR] DB: {e}")
        finally:
            if cursor: cursor.close()
            if conn:   conn.close()

    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")