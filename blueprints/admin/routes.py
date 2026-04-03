"""blueprints/admin/routes.py"""


def format_hora(hora):
    """Convierte timedelta de MySQL TIME a string HH:MM."""
    if hora is None:
        return ''
    if hasattr(hora, 'strftime'):
        return hora.strftime('%H:%M')
    total = int(hora.total_seconds())
    return f"{total//3600:02d}:{(total%3600)//60:02d}"
import os
import uuid
from flask import render_template, request, redirect, url_for, flash, current_app, jsonify
from werkzeug.utils import secure_filename
import mysql.connector
from extensions import get_db
from decorators import admin_requerido
from . import admin_bp


def allowed_file(filename):
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]


# ─────────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────────
@admin_bp.route("/")
@admin_requerido
def dashboard():
    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) as total FROM eventos WHERE estado='proximo'")
        eventos_proximos = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM tickets WHERE estado='activo'")
        tickets_activos = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM tickets WHERE estado='ingresado'")
        tickets_ingresados = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM usuarios WHERE rol='cliente'")
        total_clientes = cursor.fetchone()["total"]

        # Últimos 5 tickets
        cursor.execute("""
            SELECT t.nombre, t.correo, e.nombre AS evento, zev.nombre AS zona,
                   t.fecha_compra, t.estado
            FROM tickets t
            JOIN eventos e ON t.evento_id = e.id
            JOIN zonas_evento zev ON t.zona_id = zev.id
            ORDER BY t.fecha_compra DESC LIMIT 5
        """)
        ultimos_tickets = cursor.fetchall()
        for t in ultimos_tickets:
            if t.get("fecha_compra"):
                t["fecha_compra"] = t["fecha_compra"].strftime("%d/%m/%Y %H:%M")

        return render_template("admin/dashboard.html",
            eventos_proximos   = eventos_proximos,
            tickets_activos    = tickets_activos,
            tickets_ingresados = tickets_ingresados,
            total_clientes     = total_clientes,
            ultimos_tickets    = ultimos_tickets
        )
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "danger")
        return render_template("admin/dashboard.html")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────
#  EVENTOS — lista
# ─────────────────────────────────────────────
@admin_bp.route("/eventos")
@admin_requerido
def eventos():
    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT e.*, c.nombre AS cat_nombre, c.icono AS cat_icono,
                   c.color AS cat_color,
                   (SELECT COUNT(*) FROM tickets t WHERE t.evento_id=e.id AND t.estado!='cancelado') AS vendidos,
                   (SELECT SUM(zev.capacidad) FROM zonas_evento zev WHERE zev.evento_id=e.id) AS capacidad
            FROM eventos e
            JOIN categorias c ON e.categoria_id = c.id
            ORDER BY e.fecha DESC
        """)
        eventos = cursor.fetchall()

        # Convertir hora (timedelta) y fecha a strings seguros
        for ev in eventos:
            ev['hora_str']  = format_hora(ev.get('hora'))
            ev['fecha_str'] = ev['fecha'].strftime('%d/%m/%Y') if ev.get('fecha') else '—'

        cursor.execute("SELECT * FROM categorias WHERE activa=1 ORDER BY nombre")
        categorias = cursor.fetchall()

        return render_template("admin/eventos.html", eventos=eventos, categorias=categorias)
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "danger")
        return render_template("admin/eventos.html", eventos=[], categorias=[])
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────
#  EVENTOS — crear
# ─────────────────────────────────────────────
@admin_bp.route("/eventos/crear", methods=["GET", "POST"])
@admin_requerido
def crear_evento():
    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM categorias WHERE activa=1 ORDER BY nombre")
        categorias = cursor.fetchall()

        if request.method == "POST":
            nombre       = request.form.get("nombre",       "").strip()
            descripcion  = request.form.get("descripcion",  "").strip()
            lugar        = request.form.get("lugar",        "").strip()
            fecha        = request.form.get("fecha",        "").strip()
            hora         = request.form.get("hora",         "").strip()
            categoria_id = request.form.get("categoria_id", "").strip()

            if not all([nombre, lugar, fecha, hora, categoria_id]):
                flash("Completa todos los campos obligatorios.", "danger")
                return render_template("admin/crear_evento.html", categorias=categorias)

            # Subida de imagen
            imagen_url = None
            if "imagen" in request.files:
                file = request.files["imagen"]
                if file and file.filename and allowed_file(file.filename):
                    ext      = file.filename.rsplit(".", 1)[1].lower()
                    filename = f"{uuid.uuid4()}.{ext}"
                    file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))
                    imagen_url = f"/static/uploads/{filename}"

            # Insertar evento
            cursor.execute("""
                INSERT INTO eventos (categoria_id, nombre, descripcion, lugar, fecha, hora, imagen_url, estado)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'proximo')
            """, (categoria_id, nombre, descripcion, lugar, fecha, hora, imagen_url))
            evento_id = cursor.lastrowid

            # Insertar zonas con sus precios
            # Zonas vienen como arrays del formulario
            zona_nombres    = request.form.getlist("zona_nombre[]")
            zona_precios    = request.form.getlist("zona_precio[]")
            zona_capacidades = request.form.getlist("zona_capacidad[]")
            zona_colores    = request.form.getlist("zona_color[]")
            zona_descs      = request.form.getlist("zona_desc[]")

            for i, zn in enumerate(zona_nombres):
                if zn.strip():
                    cursor.execute("""
                        INSERT INTO zonas_evento (evento_id, nombre, precio, capacidad, color, descripcion)
                        VALUES (%s,%s,%s,%s,%s,%s)
                    """, (
                        evento_id, zn.strip(),
                        float(zona_precios[i])    if i < len(zona_precios)     else 0,
                        int(zona_capacidades[i])  if i < len(zona_capacidades) else 100,
                        zona_colores[i]           if i < len(zona_colores)     else "#f0a500",
                        zona_descs[i]             if i < len(zona_descs)       else ""
                    ))

            conn.commit()
            flash(f"Evento '{nombre}' creado exitosamente.", "success")
            return redirect(url_for("admin.eventos"))

        return render_template("admin/crear_evento.html", categorias=categorias)

    except mysql.connector.Error as e:
        flash(f"Error: {e}", "danger")
        return redirect(url_for("admin.eventos"))
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────
#  EVENTOS — editar estado
# ─────────────────────────────────────────────
@admin_bp.route("/eventos/<int:evento_id>/estado", methods=["POST"])
@admin_requerido
def cambiar_estado_evento(evento_id):
    estado = request.form.get("estado")
    estados_validos = ["proximo", "en_curso", "finalizado", "cancelado", "agotado"]
    if estado not in estados_validos:
        flash("Estado no válido.", "danger")
        return redirect(url_for("admin.eventos"))

    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE eventos SET estado=%s WHERE id=%s", (estado, evento_id))
        conn.commit()
        flash("Estado actualizado.", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()

    return redirect(url_for("admin.eventos"))


# ─────────────────────────────────────────────
#  EVENTOS — eliminar
# ─────────────────────────────────────────────
@admin_bp.route("/eventos/<int:evento_id>/eliminar", methods=["POST"])
@admin_requerido
def eliminar_evento(evento_id):
    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM eventos WHERE id=%s", (evento_id,))
        conn.commit()
        flash("Evento eliminado.", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()
    return redirect(url_for("admin.eventos"))


# ─────────────────────────────────────────────
#  CATEGORÍAS
# ─────────────────────────────────────────────
@admin_bp.route("/categorias")
@admin_requerido
def categorias():
    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.*, COUNT(e.id) AS total_eventos
            FROM categorias c
            LEFT JOIN eventos e ON e.categoria_id = c.id
            GROUP BY c.id ORDER BY c.id
        """)
        cats = cursor.fetchall()
        return render_template("admin/categorias.html", categorias=cats)
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "danger")
        return render_template("admin/categorias.html", categorias=[])
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


@admin_bp.route("/categorias/crear", methods=["POST"])
@admin_requerido
def crear_categoria():
    nombre     = request.form.get("nombre",     "").strip()
    slug       = request.form.get("slug",       "").strip().lower().replace(" ", "-")
    icono      = request.form.get("icono",      "🎫")
    color      = request.form.get("color",      "#f0a500")
    mapa_tipo  = request.form.get("mapa_tipo",  "concierto")

    if not nombre or not slug:
        flash("Nombre y slug son obligatorios.", "danger")
        return redirect(url_for("admin.categorias"))

    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO categorias (nombre, slug, icono, color, mapa_tipo)
            VALUES (%s,%s,%s,%s,%s)
        """, (nombre, slug, icono, color, mapa_tipo))
        conn.commit()
        flash(f"Categoría '{nombre}' creada.", "success")
    except mysql.connector.IntegrityError:
        flash("Ya existe una categoría con ese nombre o slug.", "warning")
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()

    return redirect(url_for("admin.categorias"))


# ─────────────────────────────────────────────
#  USUARIOS
# ─────────────────────────────────────────────
@admin_bp.route("/usuarios")
@admin_requerido
def usuarios():
    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.*,
                   COUNT(t.id) AS total_tickets
            FROM usuarios u
            LEFT JOIN tickets t ON t.usuario_id = u.id
            GROUP BY u.id ORDER BY u.fecha_registro DESC
        """)
        users = cursor.fetchall()
        for u in users:
            if u.get("fecha_registro"):
                u["fecha_registro"] = u["fecha_registro"].strftime("%d/%m/%Y")
        return render_template("admin/usuarios.html", usuarios=users)
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "danger")
        return render_template("admin/usuarios.html", usuarios=[])
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


@admin_bp.route("/usuarios/<int:usuario_id>/rol", methods=["POST"])
@admin_requerido
def cambiar_rol(usuario_id):
    """Permite al admin cambiar el rol de un usuario."""
    rol = request.form.get("rol")
    if rol not in ("admin", "staff", "cliente"):
        flash("Rol no válido.", "danger")
        return redirect(url_for("admin.usuarios"))

    conn = cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE usuarios SET rol=%s WHERE id=%s", (rol, usuario_id))
        conn.commit()
        flash("Rol actualizado.", "success")
    except mysql.connector.Error as e:
        flash(f"Error: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()

    return redirect(url_for("admin.usuarios"))