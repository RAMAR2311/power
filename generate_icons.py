import os
from PIL import Image
import numpy as np

def generate_all_icons(source_path="static/img/logo-power-led.png"):
    if not os.path.exists(source_path):
        print(f"No se encontró imagen fuente: {source_path}")
        return

    img = Image.open(source_path).convert('RGBA')
    arr = np.array(img, dtype=np.float32)

    # Detectar fondo blanco/claro y hacerlo transparente
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]
    
    # Luminancia (0 = negro, 255 = blanco)
    lum = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    max_c = np.max(rgb, axis=2)
    min_c = np.min(rgb, axis=2)
    sat = max_c - min_c  # Diferencia cromática (alta para rojo, verde, azul)

    # 1. Crear versión con fondo transparente y texto negro -> blanco (Dark Theme)
    dark_arr = arr.copy()
    
    # Píxeles que son fondo blanco puro (lum > 240 y baja saturación) -> transparentes
    is_bg = (lum > 235) & (sat < 30)
    dark_arr[is_bg, 3] = 0

    # Píxeles oscuros acromáticos (PW y POWER en negro/gris oscuro: sat < 45 y lum <= 235)
    # Los convertimos a blanco puro manteniendo antialiasing mediante el canal alpha
    is_dark_ink = (~is_bg) & (sat < 45) & (alpha > 10)
    # Mientras más oscuro era originalmente, más opaco será en blanco
    ink_opacity = np.clip((245.0 - lum[is_dark_ink]) / 200.0, 0.0, 1.0) * 255.0
    dark_arr[is_dark_ink, 0] = 255
    dark_arr[is_dark_ink, 1] = 255
    dark_arr[is_dark_ink, 2] = 255
    dark_arr[is_dark_ink, 3] = ink_opacity

    # Píxeles de color ("LED": sat >= 45) conservan su RGB vibrante original y ajustan bordes blancos
    is_color = (~is_bg) & (sat >= 45) & (alpha > 10)
    # Suavizar halo blanco en bordes de letras de color
    light_color_edge = is_color & (lum > 200) & (sat < 80)
    dark_arr[light_color_edge, 3] = np.clip((250.0 - lum[light_color_edge]) * 4.0, 0, 255)

    dark_logo_full = Image.fromarray(dark_arr.astype(np.uint8))

    # Recortar bordes transparentes sobrantes con un pequeño margen (zona segura)
    bbox = dark_logo_full.getbbox()
    if bbox:
        dark_logo_full = dark_logo_full.crop(bbox)

    os.makedirs("static/img/icons", exist_ok=True)
    os.makedirs("static/css", exist_ok=True)

    # Guardar logo completo para tema oscuro
    dark_logo_full.save("static/img/logo-power-led-dark.png")

    # 2. Extraer únicamente el isotipo superior "PW" (aprox. el 68% superior de la imagen)
    w_full, h_full = dark_logo_full.size
    # Buscar la fila intermedia vacía entre "PW" y "POWER LED"
    alpha_proj = np.max(np.array(dark_logo_full)[:, :, 3], axis=1)
    # Buscar entre el 55% y 80% de la altura donde alpha_proj sea mínimo
    start_search = int(h_full * 0.55)
    end_search = int(h_full * 0.82)
    split_y = start_search + np.argmin(alpha_proj[start_search:end_search])

    pw_isotipo = dark_logo_full.crop((0, 0, w_full, split_y))
    pw_bbox = pw_isotipo.getbbox()
    if pw_bbox:
        pw_isotipo = pw_isotipo.crop(pw_bbox)
    pw_isotipo.save("static/img/pw-isotipo.png")

    # 3. Crear cuadrado de icono/favicon con fondo negro #000000 y el logo / monograma PW centrado
    # Para favicon e iconos PWA usamos el logo completo sobre #000000 y un borde/respiración limpio
    w_pw, h_pw = pw_isotipo.size
    max_pw = max(w_pw, h_pw)
    target_pw_dim = int(max_pw / 0.76)
    square_pw_dark = Image.new('RGBA', (target_pw_dim, target_pw_dim), (0, 0, 0, 255))
    ox = (target_pw_dim - w_pw) // 2
    oy = (target_pw_dim - h_pw) // 2
    square_pw_dark.paste(pw_isotipo, (ox, oy), pw_isotipo)
    square_pw_dark.save("static/img/favicon-pw.png")

    # También cuadrado con el imagotipo completo (PW + POWER LED) sobre fondo #000000
    w_f, h_f = dark_logo_full.size
    max_f = max(w_f, h_f)
    target_f_dim = int(max_f / 0.82)
    square_full_dark = Image.new('RGBA', (target_f_dim, target_f_dim), (0, 0, 0, 255))
    ox_f = (target_f_dim - w_f) // 2
    oy_f = (target_f_dim - h_f) // 2
    square_full_dark.paste(dark_logo_full, (ox_f, oy_f), dark_logo_full)
    square_full_dark.save("static/img/power-led-square.png")

    # Reemplazar archivos legacy por compatibilidad si alguna ruta los invoca
    square_full_dark.save("static/img/Maripocell.png")
    square_full_dark.save("static/img/Maripocel.png")
    square_full_dark.save("static/img/Mariposacel.png")
    dark_logo_full.save("static/img/Maripocell_wide.png")
    dark_logo_full.save("static/img/Maripocel_wide.png")

    # Iconos PWA y Favicons
    square_full_dark.resize((512, 512), Image.Resampling.LANCZOS).save("static/img/icons/icon-512x512.png")
    square_full_dark.resize((192, 192), Image.Resampling.LANCZOS).save("static/img/icons/icon-192x192.png")
    square_full_dark.resize((180, 180), Image.Resampling.LANCZOS).save("static/img/icons/apple-touch-icon.png")
    square_pw_dark.resize((48, 48), Image.Resampling.LANCZOS).save("static/img/icons/favicon-48x48.png")
    square_pw_dark.resize((32, 32), Image.Resampling.LANCZOS).save("static/img/icons/favicon-32x32.png")
    square_pw_dark.resize((16, 16), Image.Resampling.LANCZOS).save("static/img/icons/favicon-16x16.png")

    square_pw_dark.save("static/favicon.ico", format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print("Iconos PWA, Favicon PW e Imagotipos POWER LED generados con éxito.")

if __name__ == "__main__":
    generate_all_icons()
