# -*- coding: utf-8 -*-
"""
Generador de Iconos PWA y Favicons Oficiales POWER LED ("ILUMINA TU CAMINO")
Toma el logotipo oficial de alta resolución (static/img/logo-power-led.png),
invierte los trazos oscuros ("PW" y "POWER") a Blanco Puro (#FFFFFF) preservando
intactos los colores luz RGB de "LED" (L=#E31313, E=#40A435, D=#029CC2) sobre
fondo negro puro (#000000), y genera:
- Iconos PWA completos (72, 96, 128, 144, 152, 180, 192, 256, 384, 512)
- Iconos Maskable con Safe-Zone del 24% y barra inferior RGB LED
- Favicons (16x16, 32x32, 48x48, 64x64, favicon.ico multi-resolución y favicon-pw.png)
"""
import os
from PIL import Image, ImageDraw

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(BASE_DIR, 'static', 'img')
ICONS_DIR = os.path.join(IMG_DIR, 'icons')
os.makedirs(ICONS_DIR, exist_ok=True)


def build_dark_logo_from_master(master_path):
    """
    Convierte los píxeles negros/grises ('PW' y 'POWER') a blanco puro (#FFFFFF)
    manteniendo intactos los colores saturados de 'L' (#E31313), 'E' (#40A435) y 'D' (#029CC2).
    """
    src = Image.open(master_path).convert('RGBA')
    w, h = src.size
    pixels = src.load()

    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    out_px = out.load()

    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a < 15:
                continue
            # Si el fondo es blanco casi puro (cuando la imagen original no es transparente)
            if r > 240 and g > 240 and b > 240:
                continue

            max_c = max(r, g, b)
            min_c = min(r, g, b)
            sat = (max_c - min_c) / max_c if max_c > 0 else 0

            # Si tiene saturación cromática (letras L, E, D), preservar y realzar a colores oficiales
            if sat > 0.32 and max_c > 80:
                if r > g and r > b:
                    # L -> Rojo LED #E31313
                    out_px[x, y] = (227, 19, 19, a)
                elif g > r and g >= b:
                    # E -> Verde LED #40A435
                    out_px[x, y] = (64, 164, 53, a)
                else:
                    # D -> Azul/Cyan LED #029CC2
                    out_px[x, y] = (2, 156, 194, a)
            else:
                # Es parte de 'PW' o 'POWER' (trazo negro/gris oscuro sobre fondo claro)
                # Convertimos la oscuridad en opacidad blanca pura (#FFFFFF)
                darkness = 255 - int((r + g + b) / 3)
                alpha_val = min(255, int(a * (darkness / 220.0))) if darkness < 220 else a
                if alpha_val > 20:
                    out_px[x, y] = (255, 255, 255, alpha_val)

    # Recortar bordes vacíos
    bbox = out.getbbox()
    if bbox:
        out = out.crop(bbox)
    return out


def extract_pw_monogram(dark_logo):
    """Extrae únicamente el isotipo superior 'PW' para favicons pequeños (16x16, 32x32)."""
    w, h = dark_logo.size
    # En el logo oficial, el isotipo PW ocupa aproximadamente el 74% superior de la altura
    crop_h = int(h * 0.74)
    pw_part = dark_logo.crop((0, 0, w, crop_h))
    bbox = pw_part.getbbox()
    if bbox:
        pw_part = pw_part.crop(bbox)
    return pw_part


def create_square_app_icon(logo_rgba, size, padding_ratio=0.14, add_rgb_bar=True):
    """
    Crea un icono cuadrado sobre fondo Negro Puro (#000000) con el logo centrado
    y una sutil línea inferior tricolor RGB (#E31313, #40A435, #029CC2).
    """
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 255))
    avail_w = int(size * (1.0 - 2 * padding_ratio))
    avail_h = int(size * (1.0 - 2 * padding_ratio))

    lw, lh = logo_rgba.size
    scale = min(avail_w / lw, avail_h / lh)
    new_w = max(1, int(lw * scale))
    new_h = max(1, int(lh * scale))

    resized = logo_rgba.resize((new_w, new_h), Image.Resampling.LANCZOS)
    pos_x = (size - new_w) // 2
    pos_y = (size - new_h) // 2 - (int(size * 0.02) if add_rgb_bar else 0)
    canvas.alpha_composite(resized, (pos_x, pos_y))

    if add_rgb_bar and size >= 64:
        draw = ImageDraw.Draw(canvas)
        bar_h = max(3, int(size * 0.022))
        bar_w = int(size * 0.68)
        start_x = (size - bar_w) // 2
        bar_y = pos_y + new_h + max(4, int(size * 0.045))
        if bar_y + bar_h < size - 4:
            seg = bar_w // 3
            # Rojo #E31313
            draw.rectangle([start_x, bar_y, start_x + seg, bar_y + bar_h], fill=(227, 19, 19, 255))
            # Verde #40A435
            draw.rectangle([start_x + seg, bar_y, start_x + 2 * seg, bar_y + bar_h], fill=(64, 164, 53, 255))
            # Azul #029CC2
            draw.rectangle([start_x + 2 * seg, bar_y, start_x + bar_w, bar_y + bar_h], fill=(2, 156, 194, 255))

    return canvas.convert('RGB')


def generate_all_icons():
    master_path = os.path.join(IMG_DIR, 'logo-power-led.png')
    dark_logo = build_dark_logo_from_master(master_path)
    pw_isotipo = extract_pw_monogram(dark_logo)

    # Guardar versiones transparentes actualizadas para cabeceras y login
    dark_logo.save(os.path.join(IMG_DIR, 'logo-power-led-dark.png'), 'PNG', optimize=True)
    pw_isotipo.save(os.path.join(IMG_DIR, 'pw-isotipo.png'), 'PNG', optimize=True)

    # Guardar cuadrado principal 512x512 en static/img/power-led-square.png
    square_512 = create_square_app_icon(dark_logo, 512, padding_ratio=0.13, add_rgb_bar=True)
    square_512.save(os.path.join(IMG_DIR, 'power-led-square.png'), 'PNG', optimize=True)

    # Tamaños estándar PWA ('any') con el logo completo PW + POWER LED
    pwa_sizes = [72, 96, 128, 144, 152, 180, 192, 256, 384, 512]
    for sz in pwa_sizes:
        icon_img = create_square_app_icon(dark_logo, sz, padding_ratio=0.13, add_rgb_bar=(sz >= 96))
        icon_img.save(os.path.join(ICONS_DIR, f'icon-{sz}x{sz}.png'), 'PNG', optimize=True)

    # Apple Touch Icon 180x180
    apple_icon = create_square_app_icon(dark_logo, 180, padding_ratio=0.14, add_rgb_bar=True)
    apple_icon.save(os.path.join(ICONS_DIR, 'apple-touch-icon.png'), 'PNG', optimize=True)

    # Iconos Maskable Android (Safe Zone del 22% para que los recortes circulares/squircle de Android no corten las letras)
    for sz in [192, 512]:
        maskable_img = create_square_app_icon(dark_logo, sz, padding_ratio=0.21, add_rgb_bar=True)
        maskable_img.save(os.path.join(ICONS_DIR, f'icon-maskable-{sz}x{sz}.png'), 'PNG', optimize=True)

    # Favicons (Usan el isotipo PW + barra RGB para máxima legibilidad en pestañas pequeñas 16px/32px)
    fav_512 = create_square_app_icon(pw_isotipo, 512, padding_ratio=0.15, add_rgb_bar=True)
    fav_512.save(os.path.join(IMG_DIR, 'favicon-pw.png'), 'PNG', optimize=True)

    fav_sizes = []
    for sz in [16, 32, 48, 64]:
        fav_img = create_square_app_icon(pw_isotipo, sz, padding_ratio=0.12, add_rgb_bar=(sz >= 32))
        fav_img.save(os.path.join(ICONS_DIR, f'favicon-{sz}x{sz}.png'), 'PNG', optimize=True)
        fav_sizes.append(fav_img)

    # Guardar static/favicon.ico multi-resolución (16, 32, 48)
    fav_sizes[2].save(
        os.path.join(BASE_DIR, 'static', 'favicon.ico'),
        format='ICO',
        sizes=[(16, 16), (32, 32), (48, 48)]
    )
    print("Iconos PWA, Maskable y Favicons POWER LED generados exitosamente.")


if __name__ == '__main__':
    generate_all_icons()
