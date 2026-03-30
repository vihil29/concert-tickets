"""blueprints/public/routes.py"""
from flask import render_template, request, redirect, url_for, session, flash
from extensions import get_db
import mysql.connector
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