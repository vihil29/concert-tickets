"""
app.py — Punto de entrada de SoundPass
Registra todos los blueprints y configura la aplicación.
"""
import os
from flask import Flask
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Crear carpeta de uploads si no existe
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ── Registrar blueprints ──
    from blueprints.auth   import auth_bp
    from blueprints.public import public_bp
    from blueprints.tickets import tickets_bp
    from blueprints.staff  import staff_bp
    from blueprints.admin  import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(tickets_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(admin_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)