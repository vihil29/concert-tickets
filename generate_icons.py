"""
Genera los iconos de la PWA (192x192 y 512x512).
Corre esto UNA SOLA VEZ en el VPS:
  python3 generate_icons.py
"""
from PIL import Image, ImageDraw, ImageFont
import os

def crear_icono(size, path):
    img  = Image.new("RGB", (size, size), "#080810")
    draw = ImageDraw.Draw(img)

    # Fondo con gradiente simulado (círculo dorado)
    margin = int(size * 0.15)
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill="#f0a500"
    )

    # Letra S en el centro
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                                   int(size * 0.45))
    except:
        font = ImageFont.load_default()

    text = "S"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2, (size - th) / 2 - bbox[1]),
        text, fill="#080810", font=font
    )

    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    print(f"Icono creado: {path}")

crear_icono(192, "static/icons/icon-192.png")
crear_icono(512, "static/icons/icon-512.png")
print("✅ Iconos generados correctamente")