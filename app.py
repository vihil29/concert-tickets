# ============================================================
#  app.py — Sistema de Ticketing para Conciertos
#  Framework: Flask | DB: MySQL (XAMPP) | Correo: smtplib + QR
# ============================================================

import uuid                             # Genera códigos UUID únicos
import threading                        # Envío de correo sin bloquear la web
import smtplib                          # Envío de correos SMTP
import base64                           # Convierte el QR a texto Base64
import io                               # Buffer en memoria (sin guardar archivos)

import qrcode                           # pip install qrcode[pil]

from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.image     import MIMEImage

from flask import Flask, render_template, request, redirect, url_for, flash
import mysql.connector

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "clave_secreta_proyecto"

DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "",
    "database": "concert_tickets"
}

EMAIL_REMITENTE = "tazer3012@gmail.com"    # ← Tu Gmail
EMAIL_APP_PASS  = "ugty mbww zgfe cerl"  # ← App Password de 16 caracteres

# Zonas válidas del mapa del estadio
ZONAS_VALIDAS = [
    "General Norte", "General Sur", "Sombra Norte", "Sombra Sur",
    "Campo Izquierdo", "Campo Derecho", "General Centro",
    "Tribuna Norte", "Tribuna Sur", "Platea", "Nivel 12"
]


# ─────────────────────────────────────────────
#  FUNCIÓN: Conectar a MySQL
# ─────────────────────────────────────────────
def get_db_connection():
    """Retorna una conexión activa a la base de datos MySQL."""
    return mysql.connector.connect(**DB_CONFIG)


# ─────────────────────────────────────────────
#  FUNCIÓN: Generar QR en memoria → Base64
# ─────────────────────────────────────────────
def generar_qr_base64(codigo: str) -> str:
    """
    Recibe el UUID del ticket y devuelve una cadena Base64 del QR.
    NO se guarda ningún archivo en disco — todo ocurre en RAM.

    Flujo:
      uuid → qrcode.make() → BytesIO buffer → base64 → string
    """
    # 1. Crear imagen QR con corrección de errores alta
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8,
        border=3,
    )
    qr.add_data(codigo)
    qr.make(fit=True)

    # 2. Generar imagen con colores SoundPass (dorado sobre oscuro)
    img = qr.make_image(fill_color="#f0a500", back_color="#0d0d1a")

    # 3. Guardar imagen en buffer de memoria (sin tocar el disco)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    # 4. Convertir a Base64 y retornar como string
    return base64.b64encode(buffer.read()).decode("utf-8")


# ─────────────────────────────────────────────
#  FUNCIÓN: Enviar correo HTML Pro con QR
# ─────────────────────────────────────────────
def enviar_correo(destinatario: str, nombre: str, codigo: str, zona: str, qr_base64: str):
    """
    Envía correo HTML con diseño SoundPass oscuro + QR embebido.
    Usa MIME multipart/related para incrustar la imagen QR con CID.
    Se ejecuta en threading para no bloquear Flask.
    """
    try:
        print(f"[CORREO] Preparando envío a: {destinatario}")

        # MIME related permite referenciar imágenes internas con cid:
        msg_root = MIMEMultipart("related")
        msg_root["Subject"] = "🎸 SoundPass — Tu Ticket de Concierto"
        msg_root["From"]    = EMAIL_REMITENTE
        msg_root["To"]      = destinatario

        msg_alt = MIMEMultipart("alternative")
        msg_root.attach(msg_alt)

        html_body = f"""
        <!DOCTYPE html><html lang="es">
        <body style="margin:0;padding:0;background:#080810;font-family:Arial,sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#080810;padding:32px 0;">
          <tr><td align="center">
            <table width="520" cellpadding="0" cellspacing="0"
                   style="background:#12121e;border-radius:20px;
                          border:1px solid rgba(240,165,0,0.25);max-width:520px;">

              <!-- HEADER -->
              <tr>
                <td style="background:linear-gradient(135deg,#1a1a2e,#0d0d1a);
                            padding:36px 32px 28px;text-align:center;
                            border-bottom:2px dashed rgba(255,255,255,0.06);">
                  <p style="margin:0 0 6px;font-size:12px;letter-spacing:3px;
                             text-transform:uppercase;color:rgba(240,165,0,0.5);">
                    🎸 FESTIVAL 2025 · ESTADIO NACIONAL
                  </p>
                  <h1 style="margin:0;font-size:30px;color:#f0a500;letter-spacing:2px;
                              font-family:Arial Black,sans-serif;">
                    ¡TICKET CONFIRMADO!
                  </h1>
                  <p style="margin:8px 0 0;color:#444;font-size:12px;">
                    Entrada válida para una persona · No transferible
                  </p>
                </td>
              </tr>

              <!-- BODY -->
              <tr>
                <td style="padding:28px 32px;">
                  <!-- Datos -->
                  <p style="margin:0 0 3px;font-size:10px;color:#444;letter-spacing:1.5px;text-transform:uppercase;">Asistente</p>
                  <p style="margin:0 0 20px;font-size:20px;color:#fff;font-weight:bold;">{nombre}</p>

                  <p style="margin:0 0 3px;font-size:10px;color:#444;letter-spacing:1.5px;text-transform:uppercase;">Zona</p>
                  <p style="margin:0 0 26px;">
                    <span style="background:rgba(240,165,0,0.12);color:#f0a500;
                                 border:1px solid rgba(240,165,0,0.3);border-radius:6px;
                                 padding:5px 16px;font-size:14px;font-weight:bold;letter-spacing:1px;">
                      {zona}
                    </span>
                  </p>

                  <!-- QR -->
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td align="center"
                          style="background:#0d0d1a;border:2px dashed rgba(240,165,0,0.3);
                                 border-radius:16px;padding:28px 20px;">
                        <p style="margin:0 0 16px;font-size:10px;color:#555;
                                   letter-spacing:2px;text-transform:uppercase;">
                          Código QR de Acceso
                        </p>
                        <!-- cid:qr_image es el Content-ID definido abajo -->
                        <img src="cid:qr_image" width="190" height="190"
                             alt="QR Ticket" style="display:block;margin:0 auto;border-radius:10px;" />
                        <p style="margin:18px 0 0;font-size:9px;color:#2a2a3a;
                                   font-family:Courier New,monospace;word-break:break-all;">
                          {codigo}
                        </p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>

              <!-- FOOTER -->
              <tr>
                <td style="background:rgba(0,0,0,0.35);padding:16px 32px;text-align:center;
                            border-top:1px solid rgba(255,255,255,0.04);border-radius:0 0 20px 20px;">
                  <p style="margin:0;font-size:11px;color:#2a2a3a;">
                    🔒 Presenta este QR en la entrada · Un solo uso · No compartas este código
                  </p>
                </td>
              </tr>

            </table>
          </td></tr>
        </table>
        </body></html>
        """

        msg_alt.attach(MIMEText(html_body, "html"))

        # Embeber QR como imagen CID (no aparece como adjunto, sino dentro del HTML)
        qr_bytes = base64.b64decode(qr_base64)
        img_mime = MIMEImage(qr_bytes, _subtype="png")
        img_mime.add_header("Content-ID", "<qr_image>")       # Referenciado en el HTML
        img_mime.add_header("Content-Disposition", "inline")
        msg_root.attach(img_mime)

        # Enviar con STARTTLS puerto 587 (compatible con Windows)
        print("[CORREO] Conectando smtp.gmail.com:587 ...")
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_REMITENTE, EMAIL_APP_PASS)
            server.sendmail(EMAIL_REMITENTE, destinatario, msg_root.as_string())

        print(f"[CORREO] ✅ Enviado a {destinatario}")

    except smtplib.SMTPAuthenticationError:
        print("[CORREO ERROR] ❌ App Password incorrecto o 2FA no activo.")
    except Exception as e:
        print(f"[CORREO ERROR] ❌ {e}")


# ═══════════════════════════════════════════════════════════
#  RUTAS DE USUARIO
# ═══════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/comprar", methods=["POST"])
def comprar():
    """
    Flujo de compra:
      1. Validar campos
      2. Generar UUID
      3. Generar QR en memoria (Base64)
      4. Guardar en MySQL
      5. Enviar correo con QR en hilo separado
      6. Mostrar confirmación con QR
    """
    nombre = request.form.get("nombre", "").strip()
    correo = request.form.get("correo", "").strip()
    zona   = request.form.get("zona",   "").strip()

    if not nombre or not correo or zona not in ZONAS_VALIDAS:
        flash("Por favor completa todos los campos correctamente.", "danger")
        return redirect(url_for("index"))

    # Paso 1: UUID único
    codigo = str(uuid.uuid4())

    # Paso 2: QR en memoria — sin tocar el disco
    qr_base64 = generar_qr_base64(codigo)

    # Paso 3: Guardar en base de datos
    try:
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tickets (codigo, nombre, correo, zona, estado) VALUES (%s,%s,%s,%s,'Activo')",
            (codigo, nombre, correo, zona)
        )
        conn.commit()
    except mysql.connector.Error as e:
        flash(f"Error al guardar el ticket: {e}", "danger")
        return redirect(url_for("index"))
    finally:
        cursor.close()
        conn.close()

    # Paso 4: Correo en hilo separado (no bloquea la página web)
    threading.Thread(
        target=enviar_correo,
        args=(correo, nombre, codigo, zona, qr_base64),
        daemon=True
    ).start()

    # Paso 5: Mostrar confirmación con QR
    return render_template(
        "confirmacion.html",
        nombre=nombre, correo=correo, zona=zona,
        codigo=codigo, qr_base64=qr_base64
    )


# ═══════════════════════════════════════════════════════════
#  RUTAS DE ADMIN
# ═══════════════════════════════════════════════════════════

@app.route("/admin")
def admin():
    return render_template("admin.html")


@app.route("/validar", methods=["POST"])
def validar():
    """
    Valida el código del ticket (ingresado a mano o escaneado por QR).
    Lógica:
      → No existe  → inválido
      → Ingresado  → ya usado, acceso denegado
      → Activo     → válido, marca como 'Ingresado'
    """
    codigo = request.form.get("codigo", "").strip()

    if not codigo:
        flash("Debes ingresar un código.", "warning")
        return redirect(url_for("admin"))

    try:
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tickets WHERE codigo = %s", (codigo,))
        ticket = cursor.fetchone()

        if not ticket:
            resultado = {"estado": "invalido",
                         "mensaje": "❌ Código no encontrado. Ticket inválido.", "ticket": None}
        elif ticket["estado"] == "Ingresado":
            resultado = {"estado": "usado",
                         "mensaje": "⚠️ Este ticket ya fue utilizado. Acceso denegado.", "ticket": ticket}
        else:
            cursor.execute("UPDATE tickets SET estado='Ingresado' WHERE codigo=%s", (codigo,))
            conn.commit()
            resultado = {"estado": "valido",
                         "mensaje": "✅ Ticket válido. ¡Acceso permitido!", "ticket": ticket}

    except mysql.connector.Error as e:
        flash(f"Error de base de datos: {e}", "danger")
        return redirect(url_for("admin"))
    finally:
        cursor.close()
        conn.close()

    return render_template("admin.html", resultado=resultado, codigo_buscado=codigo)


if __name__ == "__main__":
    # DESPUÉS — acepta conexiones desde cualquier dispositivo en la red
    app.run(debug=True, host="0.0.0.0", port=5000)