# -*- coding: utf-8 -*-
from app import create_app
from models import db, Category, Subcategory, Product

app = create_app()
with app.app_context():
    estructura = {
        'Iluminación LED Automotriz': (5, [
            ('Bombillos Turbo LED (H4/H7/H11/9005)', 5),
            ('Exploradoras & Barras LED Off-Road', 5),
            ('Cintas DRL & Ojos de Ángel RGB', 4),
            ('Stops, Cucuyos & Direccionales LED', 6),
        ]),
        'Audio & Multimedia CarPlay': (3, [
            ('Pantallas Android & CarPlay Inalámbrico', 3),
            ('Parlantes, Subwoofers & Bajos Activos', 3),
            ('Plantas, Amplificadores & Procesadores DSP', 2),
        ]),
        'Seguridad, Alarmas & Cámaras': (4, [
            ('Alarmas Doble Vía & GPS Tracker', 4),
            ('Cámaras de Reversa AHD & 360°', 5),
            ('Sensores de Parqueo & Bloqueo Central', 4),
        ]),
        'Polarizados & Estética Automotriz': (4, [
            ('Película Nanocerámica HD Termocontraíble', 4),
            ('Película Ultra-Seguridad Antiatraco', 3),
            ('Cintas Decorativas, Plumillas & Lujos', 5),
        ]),
    }

    for p in Product.query.all():
        p.categoria_id = None
        p.subcategory_id = None
    db.session.flush()
    Subcategory.query.delete()
    Category.query.delete()
    db.session.commit()

    cat_objs = {}
    sub_objs = {}
    for cat_nom, (cat_min, subs) in estructura.items():
        c = Category(nombre=cat_nom, stock_minimo_alerta=cat_min)
        db.session.add(c)
        db.session.flush()
        cat_objs[cat_nom] = c
        for sub_nom, sub_min in subs:
            s = Subcategory(nombre=sub_nom, categoria_id=c.id, stock_minimo_alerta=sub_min)
            db.session.add(s)
            db.session.flush()
            sub_objs[sub_nom] = (c, s)
    db.session.commit()

    catalogo_completo = [
        ('LED-H4-20K', 'Bombillo LED H4 Turbo 20.000 LM Ventilador Silencioso', 'Bombillos Turbo LED (H4/H7/H11/9005)', 45000, 65000, 80000, 110000, 32, 32),
        ('PW-LED-H4-24K', 'Kit Bombillos Turbo LED H4 24.000 LM Canbus Pro', 'Bombillos Turbo LED (H4/H7/H11/9005)', 55000, 78000, 95000, 135000, 14, 40),
        ('PW-LED-H7-30K', 'Kit Bombillos LED H7 30.000 LM CSP Tubo de Cobre', 'Bombillos Turbo LED (H4/H7/H11/9005)', 68000, 95000, 115000, 160000, 12, 35),
        ('PW-EXP-DUAL', 'Par Exploradoras Mini Driving LED Bicolor (Blanco/Ámbar)', 'Exploradoras & Barras LED Off-Road', 42000, 62000, 75000, 110000, 18, 50),
        ('PW-BAR-22P', 'Barra LED Curva 22 Pulgadas 4D Off-Road 180W', 'Exploradoras & Barras LED Off-Road', 95000, 135000, 160000, 220000, 6, 15),
        ('PW-DRL-60CM', 'Par Cintas DRL Secuenciales 60cm Blanco Hielo + Direccional Ámbar', 'Cintas DRL & Ojos de Ángel RGB', 22000, 35000, 45000, 75000, 15, 40),
        ('PW-STOP-T20', 'Par Bombillos LED T20 / 1157 Strobo Freno + Direccional Canbus', 'Stops, Cucuyos & Direccionales LED', 12000, 20000, 28000, 45000, 25, 80),
        ('PW-RAD-9P', 'Pantalla Android 9" QLED 4GB/64GB CarPlay Inalámbrico', 'Pantallas Android & CarPlay Inalámbrico', 280000, 360000, 410000, 520000, 5, 12),
        ('PW-SUB-10P', 'Subwoofer Slim Bajo Silla 10" Activo 800W', 'Parlantes, Subwoofers & Bajos Activos', 210000, 275000, 310000, 390000, 4, 10),
        ('PW-AMP-4CH', 'Planta Amplificador Digital 4 Canales 1600W Clase D Compacta', 'Plantas, Amplificadores & Procesadores DSP', 155000, 210000, 245000, 320000, 5, 14),
        ('PW-ALA-PRO', 'Alarma Automotriz Ultra Pro con Módulo Elevavidrios', 'Alarmas Doble Vía & GPS Tracker', 85000, 118000, 135000, 185000, 9, 25),
        ('PW-CAM-AHD', 'Cámara de Reversa AHD 1080p Visión Nocturna Ojo de Pez', 'Cámaras de Reversa AHD & 360°', 25000, 38000, 48000, 75000, 20, 60),
        ('PW-SEN-4P', 'Kit 4 Sensores de Reversa con Display LED Acústico', 'Sensores de Parqueo & Bloqueo Central', 32000, 48000, 60000, 95000, 11, 30),
        ('PW-POL-NANO', 'Kit Rollo Polarizado Nanocerámico Termocontraíble 20%', 'Película Nanocerámica HD Termocontraíble', 140000, 190000, 220000, 290000, 7, 18),
        ('PW-POL-SEG8', 'Kit Película de Seguridad 8 Micras Antiatraco UV400', 'Película Ultra-Seguridad Antiatraco', 110000, 155000, 185000, 250000, 3, 12),
        ('PW-PLU-SIL', 'Par Plumillas Aerodinámicas Siliconadas Grafito Universal', 'Cintas Decorativas, Plumillas & Lujos', 18000, 28000, 36000, 55000, 16, 45),
    ]

    for sku, nombre, sub_nom, costo, p_dist, p_loc, p_fin, s_tda, s_bod in catalogo_completo:
        cat_obj, sub_obj = sub_objs[sub_nom]
        prod = Product.query.filter_by(codigo_barras=sku).first()
        if not prod:
            prod = Product(
                codigo_barras=sku, sku=sku, nombre=nombre,
                categoria_id=cat_obj.id, subcategory_id=sub_obj.id,
                costo=costo, precio_distribuidor=p_dist, precio_local=p_loc, precio_final=p_fin,
                stock_tienda=s_tda, stock_bodega=s_bod, stock_minimo=sub_obj.stock_minimo_alerta or 5
            )
            db.session.add(prod)
        else:
            prod.nombre = nombre
            prod.categoria_id = cat_obj.id
            prod.subcategory_id = sub_obj.id
            prod.costo = costo
            prod.precio_distribuidor = p_dist
            prod.precio_local = p_loc
            prod.precio_final = p_fin
    db.session.commit()

    print('=== RESUMEN DE CATEGORIAS Y SUBCATEGORIAS ===')
    for c in Category.query.all():
        print(f'[{c.nombre}] ({len(c.subcategorias)} subcategorias, {len(c.productos)} productos):')
        for s in c.subcategorias:
            print(f'   - {s.nombre}: {len(s.productos)} productos (Alerta <= {s.stock_minimo_alerta})')
