"""blueprints/public/routes.py"""
from flask import render_template, request, redirect, url_for, session, flash, jsonify, current_app
from extensions import get_db
import threading
import mysql.connector
import io, base64, qrcode
from decorators import login_requerido
from . import public_bp


@public_bp.route("/")
def index():
    """
    Página principal — catálogo de eventos agrupados por categoría.
    Accesible sin login.
    """
    categoria_slug = request.args.get("cat", None)  # filtro opcional por categoría

    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        # Cargar categorías activas para el menú
        cursor.execute(
            "SELECT * FROM categorias WHERE activa = 1 ORDER BY id"
        )
        categorias = cursor.fetchall()

        # Cargar eventos próximos (con info de categoría)
        query = """
            SELECT e.*, c.nombre AS cat_nombre, c.slug AS cat_slug,
                   c.icono AS cat_icono, c.color AS cat_color,
                   c.mapa_tipo,
                   (SELECT COUNT(*) FROM tickets t WHERE t.evento_id = e.id AND t.estado != 'cancelado') AS vendidos,
                   (SELECT SUM(zev.capacidad) FROM zonas_evento zev WHERE zev.evento_id = e.id) AS capacidad_total,
                   (SELECT MIN(zev.precio) FROM zonas_evento zev WHERE zev.evento_id = e.id) AS precio_min
            FROM eventos e
            JOIN categorias c ON e.categoria_id = c.id
            WHERE e.estado IN ('proximo', 'en_curso')
        """
        params = []
        if categoria_slug:
            query += " AND c.slug = %s"
            params.append(categoria_slug)

        query += " ORDER BY e.fecha ASC, e.hora ASC"
        cursor.execute(query, params)
        eventos = cursor.fetchall()

        # Agrupar eventos por categoría
        eventos_por_cat = {}
        for e in eventos:
            slug = e["cat_slug"]
            if slug not in eventos_por_cat:
                eventos_por_cat[slug] = {
                    "info":    {"nombre": e["cat_nombre"], "icono": e["cat_icono"], "color": e["cat_color"], "slug": slug},
                    "eventos": []
                }
            eventos_por_cat[slug]["eventos"].append(e)

        return render_template("public/index.html",
            categorias       = categorias,
            eventos_por_cat  = eventos_por_cat,
            cat_activa       = categoria_slug
        )

    except mysql.connector.Error as e:
        flash(f"Error al cargar eventos: {e}", "danger")
        return render_template("public/index.html", categorias=[], eventos_por_cat={}, cat_activa=None)
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


@public_bp.route("/evento/<int:evento_id>")
def evento(evento_id):
    """
    Detalle de un evento con mapa de zonas.
    Accesible sin login para VER, pero requiere login para COMPRAR.
    """
    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        # Cargar evento con info de categoría
        cursor.execute("""
            SELECT e.*, c.nombre AS cat_nombre, c.slug AS cat_slug,
                   c.icono AS cat_icono, c.color AS cat_color, c.mapa_tipo
            FROM eventos e
            JOIN categorias c ON e.categoria_id = c.id
            WHERE e.id = %s
        """, (evento_id,))
        evento = cursor.fetchone()

        if not evento:
            flash("Evento no encontrado.", "warning")
            return redirect(url_for("public.index"))

        # Cargar zonas con disponibilidad
        cursor.execute("""
            SELECT zev.*,
                   (zev.capacidad - zev.vendidos) AS disponibles
            FROM zonas_evento zev
            WHERE zev.evento_id = %s
            ORDER BY zev.precio DESC
        """, (evento_id,))
        zonas = cursor.fetchall()

        return render_template("public/evento.html",
            evento = evento,
            zonas  = zonas
        )

    except mysql.connector.Error as e:
        flash(f"Error: {e}", "danger")
        return redirect(url_for("public.index"))
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def _qr_base64(codigo: str) -> str:
    """Genera QR en memoria y devuelve Base64."""
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=7, border=3)
    qr.add_data(codigo)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#000000", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


@public_bp.route("/mis-entradas")
@login_requerido
def mis_entradas():
    """
    Muestra todos los tickets del usuario logueado.
    JOIN con eventos, categorías y zonas para mostrar
    imagen, nombre, fecha, zona, precio y estado.
    Genera el QR de cada ticket en memoria para el modal.
    """
    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                t.id, t.codigo, t.nombre, t.correo, t.estado,
                t.fecha_compra,
                e.nombre       AS evento_nombre,
                e.imagen_url   AS evento_imagen,
                e.fecha        AS evento_fecha,
                e.hora         AS evento_hora,
                e.lugar        AS evento_lugar,
                e.id           AS evento_id,
                c.nombre       AS cat_nombre,
                c.icono        AS cat_icono,
                c.color        AS cat_color,
                zev.nombre     AS zona_nombre,
                zev.precio     AS zona_precio
            FROM tickets t
            JOIN eventos       e   ON t.evento_id = e.id
            JOIN categorias    c   ON e.categoria_id = c.id
            JOIN zonas_evento  zev ON t.zona_id = zev.id
            WHERE t.usuario_id = %s
            ORDER BY t.fecha_compra DESC
        """, (session["usuario_id"],))

        tickets = cursor.fetchall()

        # Formatear fechas y generar QR para cada ticket
        for t in tickets:
            # Hora (timedelta → HH:MM)
            h = t.get("evento_hora")
            if h and hasattr(h, "total_seconds"):
                s2 = int(h.total_seconds())
                t["hora_str"] = f"{s2//3600:02d}:{(s2%3600)//60:02d}"
            elif h and hasattr(h, "strftime"):
                t["hora_str"] = h.strftime("%H:%M")
            else:
                t["hora_str"] = "—"

            t["fecha_str"]   = t["evento_fecha"].strftime("%d %b %Y") if t.get("evento_fecha") else "—"
            t["compra_str"]  = t["fecha_compra"].strftime("%d/%m/%Y %H:%M") if t.get("fecha_compra") else "—"
            t["qr_base64"]   = _qr_base64(t["codigo"])

        return render_template("public/mis_entradas.html", tickets=tickets)

    except mysql.connector.Error as e:
        flash(f"Error al cargar tus entradas: {e}", "danger")
        return render_template("public/mis_entradas.html", tickets=[])
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()

@public_bp.route("/reenviar-ticket/<codigo>", methods=["POST"])
@login_requerido
def reenviar_ticket(codigo):
    """
    Ruta para reenviar el correo de confirmación de un ticket existente.
    """
    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        # 1. Buscar el ticket (y verificar que pertenece al usuario logueado)
        cursor.execute("""
            SELECT t.codigo, t.nombre, t.correo,
                   e.nombre AS evento_nombre, e.imagen_url, e.fecha, e.hora,
                   zev.nombre AS zona_nombre, zev.precio
            FROM tickets t
            JOIN eventos e ON t.evento_id = e.id
            JOIN zonas_evento zev ON t.zona_id = zev.id
            WHERE t.codigo = %s AND t.usuario_id = %s
        """, (codigo, session["usuario_id"]))
        info = cursor.fetchone()

        if not info:
            return jsonify({"status": "error", "message": "Ticket no encontrado"}), 404

        # 2. Formatear fechas y hora (igual que en el checkout)
        hora_obj = info.get("hora")
        if hora_obj and hasattr(hora_obj, 'total_seconds'):
            t_sec = int(hora_obj.total_seconds())
            hora_str = f"{t_sec//3600:02d}:{(t_sec%3600)//60:02d}"
        elif hora_obj and hasattr(hora_obj, 'strftime'):
            hora_str = hora_obj.strftime('%H:%M')
        else:
            hora_str = "—"

        fecha_obj = info.get("fecha")
        fecha_str = fecha_obj.strftime('%d de %B de %Y') if fecha_obj else "—"

        # 3. Generar el QR de nuevo
        from blueprints.tickets.routes import generar_qr_base64, _enviar_correo_worker
        qr_base64 = generar_qr_base64(codigo)

        # 4. Configuración del correo
        cfg = {
            "EMAIL_REMITENTE": current_app.config.get("EMAIL_REMITENTE", ""),
            "EMAIL_APP_PASS":  current_app.config.get("EMAIL_APP_PASS",  ""),
            "EMAIL_SMTP_HOST": current_app.config.get("EMAIL_SMTP_HOST", "smtp-relay.brevo.com"),
            "EMAIL_SMTP_USER": current_app.config.get("EMAIL_SMTP_USER", ""),
        }

        # 5. Disparar el hilo del correo
        threading.Thread(
            target=_enviar_correo_worker,
            args=(cfg, info["correo"], info["nombre"], codigo,
                  info["evento_nombre"], fecha_str, hora_str,
                  info["zona_nombre"], info["precio"],
                  info.get("imagen_url") or "", qr_base64),
            daemon=True
        ).start()

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"[RE-ENVIO ERROR] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()