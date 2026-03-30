"""blueprints/tickets/routes.py"""
import uuid, threading, smtplib, base64, io
from flask import render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
import qrcode
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import mysql.connector
from extensions import get_db
from decorators import login_requerido
from . import tickets_bp


def generar_qr_base64(codigo: str) -> str:
    """Genera QR en memoria y retorna Base64. Negro sobre blanco para máxima compatibilidad."""
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=8, border=3)
    qr.add_data(codigo)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#000000", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def enviar_correo(destinatario, nombre, codigo, evento_nombre, zona_nombre, precio, qr_b64):
    """Envía correo HTML con el ticket y QR embebido."""
    from flask import current_app
    cfg = current_app.config
    try:
        msg = MIMEMultipart("related")
        msg["Subject"] = f"🎟️ Tu Ticket — {evento_nombre}"
        msg["From"]    = cfg["EMAIL_REMITENTE"]
        msg["To"]      = destinatario

        alt = MIMEMultipart("alternative")
        msg.attach(alt)

        html = f"""
        <html><body style="background:#080810;font-family:Arial,sans-serif;padding:32px 0;">
        <table width="520" cellpadding="0" cellspacing="0" style="margin:auto;background:#12121e;
               border-radius:20px;border:1px solid rgba(240,165,0,0.25);">
          <tr><td style="background:linear-gradient(135deg,#1a1a2e,#0d0d1a);padding:32px;
                         text-align:center;border-radius:20px 20px 0 0;">
            <p style="color:rgba(240,165,0,.6);font-size:12px;letter-spacing:3px;
                      text-transform:uppercase;margin:0 0 8px">🎸 SOUNDPASS</p>
            <h1 style="color:#f0a500;margin:0;font-size:26px;letter-spacing:2px;">TICKET CONFIRMADO</h1>
          </td></tr>
          <tr><td style="padding:28px 32px;">
            <p style="color:#aaa;font-size:11px;margin:0 0 4px;text-transform:uppercase;letter-spacing:1px">Evento</p>
            <p style="color:#fff;font-size:18px;font-weight:bold;margin:0 0 20px">{evento_nombre}</p>
            <p style="color:#aaa;font-size:11px;margin:0 0 4px;text-transform:uppercase;letter-spacing:1px">Asistente</p>
            <p style="color:#fff;font-size:16px;margin:0 0 20px">{nombre}</p>
            <p style="color:#aaa;font-size:11px;margin:0 0 4px;text-transform:uppercase;letter-spacing:1px">Zona</p>
            <p style="margin:0 0 24px"><span style="background:rgba(240,165,0,.12);color:#f0a500;
               border:1px solid rgba(240,165,0,.3);border-radius:6px;padding:4px 14px;font-size:14px">
               {zona_nombre} — ${precio}</span></p>
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr><td align="center" style="background:#0d0d1a;border:2px dashed rgba(240,165,0,.3);
                      border-radius:16px;padding:24px;">
                <p style="color:#555;font-size:10px;letter-spacing:2px;text-transform:uppercase;margin:0 0 14px">
                  Código QR de Acceso</p>
                <img src="cid:qr_image" width="180" height="180"
                     style="border-radius:8px;display:block;margin:0 auto"/>
                <p style="color:#2a2a3a;font-size:9px;font-family:Courier New,monospace;
                          word-break:break-all;margin:14px 0 0">{codigo}</p>
              </td></tr>
            </table>
          </td></tr>
          <tr><td style="background:rgba(0,0,0,.3);padding:16px 32px;text-align:center;
                         border-radius:0 0 20px 20px;">
            <p style="color:#333;font-size:11px;margin:0">🔒 Presenta el QR en la entrada · Un solo uso</p>
          </td></tr>
        </table></body></html>"""

        alt.attach(MIMEText(html, "html"))
        qr_bytes = base64.b64decode(qr_b64)
        img_mime = MIMEImage(qr_bytes, _subtype="png")
        img_mime.add_header("Content-ID", "<qr_image>")
        img_mime.add_header("Content-Disposition", "inline")
        msg.attach(img_mime)

        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.ehlo(); s.starttls(); s.ehlo()
            s.login(cfg["EMAIL_REMITENTE"], cfg["EMAIL_APP_PASS"])
            s.sendmail(cfg["EMAIL_REMITENTE"], destinatario, msg.as_string())

        print(f"[CORREO] ✅ Enviado a {destinatario}")
    except Exception as e:
        print(f"[CORREO ERROR] {e}")


@tickets_bp.route("/comprar/<int:evento_id>", methods=["POST"])
@login_requerido
def comprar(evento_id):
    """Procesa la compra de un ticket."""
    zona_id = request.form.get("zona_id", "").strip()
    nombre  = request.form.get("nombre",  "").strip()
    correo  = request.form.get("correo",  "").strip()

    if not zona_id or not nombre or not correo:
        flash("Por favor completa todos los campos.", "danger")
        return redirect(url_for("public.evento", evento_id=evento_id))

    codigo    = str(uuid.uuid4())
    qr_base64 = generar_qr_base64(codigo)

    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        # Verificar que la zona existe y tiene disponibilidad
        cursor.execute("""
            SELECT zev.*, e.nombre AS evento_nombre, e.id AS eid
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

        # Insertar ticket
        cursor.execute("""
            INSERT INTO tickets (codigo, usuario_id, evento_id, zona_id, nombre, correo, estado)
            VALUES (%s, %s, %s, %s, %s, %s, 'activo')
        """, (codigo, session.get("usuario_id"), evento_id, zona_id, nombre, correo))

        # Actualizar contador de vendidos
        cursor.execute(
            "UPDATE zonas_evento SET vendidos = vendidos + 1 WHERE id = %s", (zona_id,)
        )
        conn.commit()

        # Enviar correo en hilo separado
        from flask import current_app
        app = current_app._get_current_object()
        threading.Thread(
            target=lambda: app.app_context().__enter__() or enviar_correo(
                correo, nombre, codigo,
                zona["evento_nombre"], zona["nombre"], zona["precio"], qr_base64
            ),
            daemon=True
        ).start()

        return render_template("tickets/confirmacion.html",
            nombre     = nombre,
            correo     = correo,
            zona       = zona["nombre"],
            precio     = zona["precio"],
            evento     = zona["evento_nombre"],
            codigo     = codigo,
            qr_base64  = qr_base64
        )

    except mysql.connector.Error as e:
        flash(f"Error al procesar la compra: {e}", "danger")
        return redirect(url_for("public.evento", evento_id=evento_id))
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()