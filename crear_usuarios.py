"""
crear_usuarios.py
Crea los usuarios por defecto con contraseñas hasheadas reales.
Correr UNA SOLA VEZ en el VPS:
  python3 /var/www/concert_tickets/crear_usuarios.py
"""
import mysql.connector
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "user":     os.getenv("DB_USER", "soundpass"),
    "password": os.getenv("DB_PASSWORD"),
    "database": "concert_tickets"
}

usuarios = [
    {
        "nombre":  "Administrador",
        "correo":  "admin@soundpass.shop",
        "password": "Admin2025!",
        "rol":     "admin"
    },
    {
        "nombre":  "Staff SoundPass",
        "correo":  "staff@soundpass.shop",
        "password": "Staff2025!",
        "rol":     "staff"
    }
]

conn   = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

for u in usuarios:
    hashed = generate_password_hash(u["password"])
    cursor.execute("""
        INSERT INTO usuarios (nombre, correo, password, rol)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE password = VALUES(password), rol = VALUES(rol)
    """, (u["nombre"], u["correo"], hashed, u["rol"]))
    print(f"✅ Usuario creado: {u['correo']} ({u['rol']})")

conn.commit()
cursor.close()
conn.close()
print("\n🎸 Usuarios listos. Puedes hacer login en https://soundpass.shop/login")