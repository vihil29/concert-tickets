"""blueprints/tickets/routes.py"""
import uuid
import threading
import smtplib
import base64
import io

import qrcode
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.image     import MIMEImage

from flask import render_template, request, redirect, url_for, flash, session
import mysql.connector

from extensions import get_db
from decorators import login_requerido
from . import tickets_bp


# ─────────────────────────────────────────────
#  GENERAR QR EN MEMORIA
# ─────────────────────────────────────────────
def generar_qr_base64(codigo: str) -> str:
    """
    Genera el QR del UUID en memoria (sin tocar disco).
    Negro sobre blanco para máxima compatibilidad con lectores.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8,
        border=3
    )
    qr.add_data(codigo)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#000000", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


# ─────────────────────────────────────────────
#  ENVIAR CORREO PRO
# ─────────────────────────────────────────────
def _enviar_correo_worker(cfg: dict, destinatario: str, nombre: str,
                           codigo: str, evento_nombre: str, evento_fecha: str,
                           evento_hora: str, zona_nombre: str, precio,
                           imagen_url: str, qr_b64: str):
    """
    Worker que corre en un hilo separado.
    Recibe todos los datos como argumentos simples (sin depender del contexto Flask).
    Envía un correo HTML profesional con:
      - Imagen del evento (si tiene URL pública)
      - Nombre, fecha, hora del evento
      - Nombre del asistente y zona
      - QR embebido como imagen CID
    """
    try:
        import logging
        logging.basicConfig(filename='/tmp/soundpass_mail.log', level=logging.DEBUG,
                            format='%(asctime)s %(message)s')
        log = logging.getLogger(__name__)
        
        log.info(f"[CORREO] Enviando a {destinatario}...")

        remitente   = cfg["EMAIL_REMITENTE"]
        app_pass    = cfg["EMAIL_APP_PASS"]

        # Estructura MIME: related permite embeber imágenes con CID
        msg_root = MIMEMultipart("related")
        msg_root["Subject"] = f"🎟️ Tu Ticket — {evento_nombre}"
        msg_root["From"]    = f"SoundPass <{remitente}>"
        msg_root["To"]      = destinatario

        msg_alt = MIMEMultipart("alternative")
        msg_root.attach(msg_alt)

        # ── Imagen del evento ──
        evento_img_html = ""
        if imagen_url:
            try:
                import os
                
                # 1. Limpiamos la ruta y le decimos dónde está en el VPS
                ruta_limpia = imagen_url.lstrip("/")
                ruta_absoluta = os.path.join("/var/www/concert_tickets", ruta_limpia)
                
                # 2. Abrimos la imagen física desde el disco duro
                with open(ruta_absoluta, "rb") as f:
                    img_data = f.read()

                # 3. Extraemos la extensión (.webp, .jpg) para evitar errores en el correo
                ext = os.path.splitext(ruta_absoluta)[1].lower().replace(".", "")
                if ext == "jpg": 
                    ext = "jpeg"  # El formato interno oficial para jpg es 'jpeg'
                if not ext:
                    ext = "png"   # Por si acaso viene sin extensión

                # 4. Embebemos la imagen en el correo
                if img_data:
                    img_mime2 = MIMEImage(img_data, _subtype=ext)
                    img_mime2.add_header("Content-ID", "<evento_img>")
                    img_mime2.add_header("Content-Disposition", "inline")
                    msg_root.attach(img_mime2)
                    
                    evento_img_html = '<img src="cid:evento_img" width="100%" style="display:block;border-radius:12px 12px 0 0;max-height:220px;object-fit:cover;"/>'
            
            except Exception as img_err:
                print(f"[CORREO] No se pudo cargar imagen local del evento: {img_err}")
                evento_img_html = '<div style="height:100px;background:linear-gradient(135deg,#1a1a2e,#0d0d1a);display:flex;align-items:center;justify-content:center;font-size:3rem;border-radius:12px 12px 0 0;">🎸</div>'

        # ── HTML del correo ──
        # He rediseñado esto para que parezca un ticket premium con un contenedor limpio
        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <body style="margin:0;padding:0;background-color:#ffffff;font-family:Arial,sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#ffffff;padding:40px 0;">
          <tr><td align="center">
            
            <table width="520" cellpadding="0" cellspacing="0" 
                   style="max-width:520px;background-color:#12121e;border-radius:20px;
                          box-shadow: 0 10px 25px rgba(0,0,0,0.25);
                          border:1px solid rgba(240,165,0,0.1);overflow:hidden;">

              <tr><td style="padding: 24px 24px 0 24px;">
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr><td align="center" style="background-color: #080810; border-radius: 12px; overflow: hidden; padding: 12px 0;">
                    {evento_img_html if imagen_url else '<div style="height:140px;display:flex;align-items:center;justify-content:center;font-size:3rem;color:#f0a500;">🎸</div>'}
                  </td></tr>
                </table>
              </td></tr>

              <tr><td style="padding:22px 32px;text-align:center;">
                <img src="https://soundpass.shop/static/logo.png" alt="SoundPass Logo" height="30" style="display:block;margin:0 auto 12px auto; filter: drop-shadow(0 0 4px #f0a500);">
                
                <p style="margin:0;font-size:11px;letter-spacing:3px;
                           text-transform:uppercase;color:rgba(240,165,0,0.6);">
                  🎟️ SOUNDPASS · TICKET CONFIRMADO
                </p>
                <h1 style="margin:6px 0 0 0;font-size:28px;color:#f0a500;letter-spacing:1px;
                            font-family:Arial Black,sans-serif; text-shadow: 0 0 10px rgba(240,165,0,0.1);">
                  {evento_nombre}
                </h1>
              </td></tr>

              <tr><td style="padding:0 32px;"><table width="100%" style="border-top:1px dashed rgba(240,165,0,0.15);"><tr><td></td></tr></table></td></tr>

              <tr><td style="padding:24px 32px 0;">
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="padding:0 8px 20px 0;width:50%;vertical-align:top;text-align:center;">
                      <p style="margin:0 0 4px;font-size:10px;color:rgba(255,255,255,0.4);
                                 text-transform:uppercase;letter-spacing:1px;">Fecha</p>
                      <p style="margin:0;font-size:16px;color:#fff;font-weight:bold;">
                        {evento_fecha}
                      </p>
                    </td>
                    <td style="padding:0 0 20px 8px;width:50%;vertical-align:top;text-align:center;">
                      <p style="margin:0 0 4px;font-size:10px;color:rgba(255,255,255,0.4);
                                 text-transform:uppercase;letter-spacing:1px;">Hora</p>
                      <p style="margin:0;font-size:16px;color:#fff;font-weight:bold;">
                        {evento_hora} hrs
                      </p>
                    </td>
                  </td></tr>
                  <tr><td colspan="2" style="padding:0 0 24px;text-align:center;">
                      <p style="margin:0 0 4px;font-size:10px;color:rgba(255,255,255,0.4);
                                 text-transform:uppercase;letter-spacing:1px;">Asistente</p>
                      <p style="margin:0;font-size:20px;color:#fff;font-weight:bold;">
                        {nombre}
                      </p>
                  </td></tr>
                  <tr><td colspan="2" style="padding:0 0 30px;text-align:center;">
                      <p style="margin:0 0 4px;font-size:10px;color:rgba(255,255,255,0.4);
                                 text-transform:uppercase;letter-spacing:1px;">Zona</p>
                      <span style="background:rgba(240,165,0,0.1);color:#f0a500;
                                   border:1px solid rgba(240,165,0,0.25);border-radius:6px;
                                   padding:8px 20px;font-size:15px;font-weight:bold;">
                        {zona_nombre} — ${precio}
                      </span>
                  </td></tr>
                </table>
              </td></tr>

              <tr><td style="padding:0 32px;"><table width="100%" style="border-top:2px dashed rgba(240,165,0,0.15);"><tr><td></td></tr></table></td></tr>

              <tr><td style="padding:28px 32px;">
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr><td align="center" style="background-color: #ffffff; border-radius: 14px; padding: 24px; box-shadow: inset 0 0 10px rgba(0,0,0,0.05);">
                    <p style="margin:0 0 18px;font-size:10px;color:#0d0d1a;
                               text-transform:uppercase;letter-spacing:2px;font-weight:bold;">
                      Código QR de Acceso
                    </p>
                    <img src="cid:qr_image" width="180" height="180"
                         style="display:block;margin:0 auto;border-radius:8px;
                                background:#fff;padding:4px;"/>
                    <p style="margin:18px 0 0;font-size:9px;color:rgba(0,0,0,0.3);
                               font-family:Courier New,monospace;word-break:break-all;">
                      {codigo}
                    </p>
                  </td></tr>
                </table>
              </td></tr>

              <tr><td style="background-color: rgba(0,0,0,0.2);padding:14px 32px;
                             text-align:center;border-top:1px solid rgba(255,255,255,0.04);">
                <p style="margin:0;font-size:11px;color:rgba(255,255,255,0.25);">
                  🔒 Presenta el QR en la entrada · Un solo uso · No compartas
                </p>
              </td></tr>

            </table>

            <p style="font-size:12px;color:#555555;margin-top:20px;">
              Este es tu ticket electrónico oficial para el evento. ¡Disfrútalo!
            </p>

          </td></tr>
        </table>
        </body></html>
        """

        msg_alt.attach(MIMEText(html, "html"))

        # Embeber QR como imagen CID
        qr_bytes  = base64.b64decode(qr_b64)
        img_mime  = MIMEImage(qr_bytes, _subtype="png")
        img_mime.add_header("Content-ID", "<qr_image>")
        img_mime.add_header("Content-Disposition", "inline")
        msg_root.attach(img_mime)

        # Enviar con Brevo SMTP
        # Enviar con Brevo SMTP
        smtp_host = cfg.get("EMAIL_SMTP_HOST", "smtp-relay.brevo.com")
        smtp_user = cfg.get("EMAIL_SMTP_USER")  # ✅ Ahora sí lee tu usuario a72087001...
        
        with smtplib.SMTP(smtp_host, 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, app_pass)
            # Usamos send_message que es más moderno y lee el 'From' y 'To' automáticamente
            server.send_message(msg_root)

        print(f"[CORREO] ✅ Enviado correctamente a {destinatario}")

    except smtplib.SMTPAuthenticationError:
        print("[CORREO ERROR] ❌ App Password incorrecto o 2FA no activo")
    except Exception as e:
        print(f"[CORREO ERROR] ❌ {type(e).__name__}: {e}")


# ─────────────────────────────────────────────
#  RUTA: Comprar ticket
# ─────────────────────────────────────────────
@tickets_bp.route("/comprar/<int:evento_id>", methods=["POST"])
@login_requerido
def comprar(evento_id):
    """
    Flujo de compra:
    1. Validar zona y disponibilidad
    2. Generar UUID + QR en memoria
    3. Guardar ticket en DB
    4. Lanzar hilo de correo (sin depender del contexto Flask)
    5. Mostrar confirmación con QR
    """
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

        # Verificar zona y disponibilidad (incluye imagen del evento)
        cursor.execute("""
            SELECT zev.*,
                   e.nombre      AS evento_nombre,
                   e.imagen_url  AS evento_imagen,
                   e.fecha       AS evento_fecha,
                   e.hora        AS evento_hora,
                   e.id          AS eid
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

        # Incrementar vendidos
        cursor.execute(
            "UPDATE zonas_evento SET vendidos = vendidos + 1 WHERE id = %s", (zona_id,)
        )
        conn.commit()

        # ── Preparar datos para el correo ──
        # Convertir hora (timedelta) a string seguro
        hora_obj = zona.get("evento_hora")
        if hora_obj and hasattr(hora_obj, 'total_seconds'):
            total = int(hora_obj.total_seconds())
            hora_str = f"{total//3600:02d}:{(total%3600)//60:02d}"
        elif hora_obj and hasattr(hora_obj, 'strftime'):
            hora_str = hora_obj.strftime('%H:%M')
        else:
            hora_str = "—"

        fecha_obj = zona.get("evento_fecha")
        fecha_str = fecha_obj.strftime('%d de %B de %Y') if fecha_obj else "—"

        from flask import current_app
        cfg = {
            "EMAIL_REMITENTE": current_app.config.get("EMAIL_REMITENTE", ""),
            "EMAIL_APP_PASS":  current_app.config.get("EMAIL_APP_PASS",  ""),
            "EMAIL_SMTP_HOST": current_app.config.get("EMAIL_SMTP_HOST", "smtp-relay.brevo.com"),
            "EMAIL_SMTP_USER": current_app.config.get("EMAIL_SMTP_USER", ""),
        }

        # ── Lanzar hilo de correo ──
        # Pasamos TODOS los datos como argumentos simples (strings, no objetos Flask)
        # Así el hilo no depende del contexto de Flask y no falla
        hilo = threading.Thread(
            target=_enviar_correo_worker,
            args=(
                cfg,
                correo,
                nombre,
                codigo,
                zona["evento_nombre"],
                fecha_str,
                hora_str,
                zona["nombre"],
                zona["precio"],
                zona.get("evento_imagen") or "",
                qr_base64
            ),
            daemon=True
        )
        hilo.start()

        return render_template("tickets/confirmacion.html",
            nombre    = nombre,
            correo    = correo,
            zona      = zona["nombre"],
            precio    = zona["precio"],
            evento    = zona["evento_nombre"],
            codigo    = codigo,
            qr_base64 = qr_base64
        )

    except mysql.connector.Error as e:
        flash(f"Error al procesar la compra: {e}", "danger")
        return redirect(url_for("public.evento", evento_id=evento_id))
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()