"""blueprints/staff/routes.py"""
from flask import render_template, request, jsonify, make_response
import mysql.connector
from extensions import get_db
from decorators import staff_requerido
from . import staff_bp


@staff_bp.route("/")
@staff_requerido
def pwa():
    """PWA del staff — panel de validación instalable."""
    resp = make_response(render_template("staff/pwa.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


@staff_bp.route("/api/validar", methods=["POST"])
@staff_requerido
def api_validar():
    """
    Valida un código QR.
    Ahora incluye nombre del evento en la respuesta.
    """
    data   = request.get_json()
    codigo = data.get("codigo", "").strip() if data else ""

    if not codigo:
        return jsonify({"estado": "error", "mensaje": "Código vacío"}), 400

    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        # Buscar ticket con info de evento y zona
        cursor.execute("""
            SELECT t.*,
                   e.nombre  AS evento_nombre,
                   e.fecha   AS evento_fecha,
                   c.nombre  AS categoria,
                   c.icono   AS cat_icono,
                   zev.nombre AS zona_nombre,
                   zev.precio AS zona_precio
            FROM tickets t
            JOIN eventos       e   ON t.evento_id = e.id
            JOIN categorias    c   ON e.categoria_id = c.id
            JOIN zonas_evento  zev ON t.zona_id = zev.id
            WHERE t.codigo = %s
        """, (codigo,))
        ticket = cursor.fetchone()

        if not ticket:
            return jsonify({"estado": "invalido", "mensaje": "Código no encontrado"})

        # Formatear fechas para JSON
        if ticket.get("fecha_compra"):
            ticket["fecha_compra"] = ticket["fecha_compra"].strftime("%d/%m/%Y %H:%M")
        if ticket.get("evento_fecha"):
            ticket["evento_fecha"] = str(ticket["evento_fecha"])

        if ticket["estado"] == "ingresado":
            return jsonify({"estado": "usado", "mensaje": "Ticket ya utilizado", "ticket": ticket})

        # Marcar como ingresado
        cursor.execute("UPDATE tickets SET estado='ingresado' WHERE codigo=%s", (codigo,))
        conn.commit()
        ticket["estado"] = "ingresado"

        return jsonify({"estado": "valido", "mensaje": "Acceso permitido", "ticket": ticket})

    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


@staff_bp.route("/api/stats")
@staff_requerido
def api_stats():
    """Estadísticas generales para el dashboard de la PWA."""
    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) as total FROM tickets WHERE estado != 'cancelado'")
        total = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM tickets WHERE estado = 'ingresado'")
        ingresados = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM tickets WHERE estado = 'activo'")
        activos = cursor.fetchone()["total"]

        # Por evento
        cursor.execute("""
            SELECT e.nombre AS evento, c.icono, COUNT(*) AS cantidad,
                   SUM(CASE WHEN t.estado='ingresado' THEN 1 ELSE 0 END) AS ingresados
            FROM tickets t
            JOIN eventos e ON t.evento_id = e.id
            JOIN categorias c ON e.categoria_id = c.id
            WHERE t.estado != 'cancelado'
            GROUP BY e.id ORDER BY cantidad DESC LIMIT 10
        """)
        por_evento = cursor.fetchall()

        return jsonify({"total": total, "ingresados": ingresados,
                        "activos": activos, "por_evento": por_evento})

    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


@staff_bp.route("/api/tickets")
@staff_requerido
def api_tickets():
    """Lista de tickets paginada con info de evento."""
    page   = int(request.args.get("page", 1))
    limit  = int(request.args.get("limit", 20))
    offset = (page - 1) * limit

    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT t.*, e.nombre AS evento_nombre, c.icono AS cat_icono,
                   zev.nombre AS zona_nombre
            FROM tickets t
            JOIN eventos e ON t.evento_id = e.id
            JOIN categorias c ON e.categoria_id = c.id
            JOIN zonas_evento zev ON t.zona_id = zev.id
            ORDER BY t.fecha_compra DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))
        tickets = cursor.fetchall()

        for t in tickets:
            if t.get("fecha_compra"):
                t["fecha_compra"] = t["fecha_compra"].strftime("%d/%m/%Y %H:%M")

        cursor.execute("SELECT COUNT(*) as total FROM tickets WHERE estado != 'cancelado'")
        total = cursor.fetchone()["total"]

        return jsonify({"tickets": tickets, "total": total, "page": page})

    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


@staff_bp.route("/api/buscar")
@staff_requerido
def api_buscar():
    """Busca tickets por nombre, correo o evento."""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"tickets": []})

    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT t.*, e.nombre AS evento_nombre, c.icono AS cat_icono,
                   zev.nombre AS zona_nombre
            FROM tickets t
            JOIN eventos e ON t.evento_id = e.id
            JOIN categorias c ON e.categoria_id = c.id
            JOIN zonas_evento zev ON t.zona_id = zev.id
            WHERE t.nombre LIKE %s OR t.correo LIKE %s OR e.nombre LIKE %s
            ORDER BY t.fecha_compra DESC LIMIT 30
        """, (f"%{q}%", f"%{q}%", f"%{q}%"))
        tickets = cursor.fetchall()

        for t in tickets:
            if t.get("fecha_compra"):
                t["fecha_compra"] = t["fecha_compra"].strftime("%d/%m/%Y %H:%M")

        return jsonify({"tickets": tickets})

    except mysql.connector.Error as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()