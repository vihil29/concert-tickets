"""
generate_icons.py — Genera los iconos de la PWA.
Ejecutar UNA SOLA VEZ en el VPS:
  python3 generate_icons.py
"""
from PIL import Image, ImageDraw
import os

def crear_icono(size, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img  = Image.new("RGB", (size, size), "#080810")
    draw = ImageDraw.Draw(img)

    margin = int(size * 0.12)
    draw.ellipse([margin, margin, size-margin, size-margin], fill="#f0a500")

    # Letra S centrada
    try:
        from PIL import ImageFont
        fsize = int(size * 0.45)
        font  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", fsize)
    except:
        font = None

    text = "S"
    if font:
        bbox = draw.textbbox((0,0), text, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text(((size-tw)/2, (size-th)/2-bbox[1]), text, fill="#080810", font=font)

    img.save(path)
    print(f"✅ Icono creado: {path}")

crear_icono(192, "static/icons/icon-192.png")
crear_icono(512, "static/icons/icon-512.png")
print("🎸 Iconos generados correctamente")