"""
Script de Migración Automática No Destructiva (v2) — POWER LED
Compatible con PostgreSQL y SQLite.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from models import (
    db, Category, Subcategory, Product, ProductVariant,
    Installer, InstallationService, Customer, Cliente
)

def add_column_if_missing(engine, table_name, col_name, col_type_sql):
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    existing_cols = [c['name'] for c in inspector.get_columns(table_name)]
    if col_name not in existing_cols:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type_sql}"))
        print(f"  [+] Columna agregada: {table_name}.{col_name} ({col_type_sql})")
        return True
    return False

def run_migration(app=None):
    if app is None:
        from app import create_app
        app = create_app()

    with app.app_context():
        engine = db.engine
        print(f"[MIGRATE v2] Ejecutando sobre motor: {engine.dialect.name}")

        # 1. Crear todas las tablas nuevas que aún no existan
        db.create_all()

        # 2. Asegurar nuevas columnas en tablas existentes (products, product_variants, sales, sale_details)
        add_column_if_missing(engine, 'products', 'codigo_barras', 'VARCHAR(50)')
        add_column_if_missing(engine, 'products', 'categoria_id', 'INTEGER')
        add_column_if_missing(engine, 'products', 'subcategory_id', 'INTEGER')
        add_column_if_missing(engine, 'products', 'costo', 'FLOAT DEFAULT 0.0')
        add_column_if_missing(engine, 'products', 'precio_distribuidor', 'FLOAT DEFAULT 0.0')
        add_column_if_missing(engine, 'products', 'precio_local', 'FLOAT DEFAULT 0.0')
        add_column_if_missing(engine, 'products', 'precio_final', 'FLOAT DEFAULT 0.0')
        add_column_if_missing(engine, 'products', 'stock_tienda', 'INTEGER DEFAULT 0')
        add_column_if_missing(engine, 'products', 'stock_bodega', 'INTEGER DEFAULT 0')
        add_column_if_missing(engine, 'products', 'stock_minimo', 'INTEGER DEFAULT 5')

        add_column_if_missing(engine, 'product_variants', 'stock_bodega', 'INTEGER DEFAULT 0')
        add_column_if_missing(engine, 'product_variants', 'precio_distribuidor', 'FLOAT')
        add_column_if_missing(engine, 'product_variants', 'precio_local', 'FLOAT')
        add_column_if_missing(engine, 'product_variants', 'precio_final', 'FLOAT')

        add_column_if_missing(engine, 'sales', 'asesor_id', 'INTEGER')
        add_column_if_missing(engine, 'sales', 'instalador_id', 'INTEGER')
        add_column_if_missing(engine, 'sales', 'cliente_id', 'INTEGER')
        add_column_if_missing(engine, 'sales', 'vehicle_id', 'INTEGER')
        add_column_if_missing(engine, 'sales', 'work_order_id', 'INTEGER')
        add_column_if_missing(engine, 'work_orders', 'vehicle_id', 'INTEGER')
        add_column_if_missing(engine, 'sales', 'lista_precio', "VARCHAR(30) DEFAULT 'cliente_final'")
        add_column_if_missing(engine, 'sales', 'estado', "VARCHAR(20) DEFAULT 'ACTIVO'")
        add_column_if_missing(engine, 'sales', 'placa_vehiculo', 'VARCHAR(20)')
        add_column_if_missing(engine, 'sales', 'modelo_vehiculo', 'VARCHAR(80)')
        add_column_if_missing(engine, 'sales', 'cliente_nombre', 'VARCHAR(120)')
        add_column_if_missing(engine, 'sales', 'cliente_documento', 'VARCHAR(30)')
        add_column_if_missing(engine, 'sales', 'cliente_telefono', 'VARCHAR(30)')

        add_column_if_missing(engine, 'sale_details', 'service_id', 'INTEGER')
        add_column_if_missing(engine, 'sale_details', 'installer_id', 'INTEGER')
        add_column_if_missing(engine, 'sale_details', 'tipo_item', "VARCHAR(20) DEFAULT 'PRODUCTO'")

        add_column_if_missing(engine, 'installation_services', 'activo', 'BOOLEAN DEFAULT 1')
        add_column_if_missing(engine, 'customers', 'fecha_registro', 'DATETIME')

        # 3. Sincronización de datos históricos de productos (sin perder registros previos)
        productos = Product.query.all()
        actualizados = 0
        for p in productos:
            mod = False
            if not p.codigo_barras and p.sku:
                p.codigo_barras = p.sku
                mod = True
            if (p.costo is None or p.costo == 0) and p.precio_costo:
                p.costo = float(p.precio_costo)
                mod = True
            if (p.precio_distribuidor is None or p.precio_distribuidor == 0) and p.precio_minimo:
                p.precio_distribuidor = float(p.precio_minimo)
                mod = True
            if (p.precio_final is None or p.precio_final == 0) and p.precio_sugerido:
                p.precio_final = float(p.precio_sugerido)
                mod = True
            if (p.precio_local is None or p.precio_local == 0) and (p.precio_final or p.precio_sugerido):
                # Precio local intermedio sugerido si no existía
                p_fin = float(p.precio_final or p.precio_sugerido or 0)
                p_dist = float(p.precio_distribuidor or p.precio_minimo or p_fin)
                p.precio_local = round((p_fin + p_dist) / 2.0, 0) if p_dist > 0 else p_fin
                mod = True
            if (p.stock_tienda == 0 and p.stock_bodega == 0) and (p.cantidad_stock and p.cantidad_stock > 0):
                if p.tipo_inventario == 'bodega':
                    p.stock_bodega = p.cantidad_stock
                else:
                    p.stock_tienda = p.cantidad_stock
                mod = True
            if p.stock_minimo is None:
                p.stock_minimo = 5
                mod = True
            if mod:
                actualizados += 1

        if actualizados:
            db.session.commit()
            print(f"  [+] {actualizados} productos migrados al esquema de 3 listas y stock dual.")

        # 4. Semillas iniciales de Categorías Automotrices POWER LED (si está vacío)
        if Category.query.count() == 0:
            catalogo_inicial = {
                'Iluminación LED Automotriz': ['Bombillería LED Principal (H4/H7/H11/9005)', 'Exploradoras y Barras LED', 'Cintas DRL y Ojos de Ángel', 'Stops y Direccionales LED'],
                'Polarizados y Películas': ['Nano-Cerámico', 'Ultra-Seguridad', 'Polarizado Convencional'],
                'Audio y Multimedia': ['Radios Pantallas Android / CarPlay', 'Parlantes, Bajos y Plantas', 'Cámaras de Reversa y Sensores'],
                'Seguridad y Alarmas': ['Alarmas Doble Vía / GPS', 'Bloqueo Central y Elevavidrios'],
                'Lujo y Accesorios Exteriores': ['Plumillas y Limpiabrisas', 'Pitos y Bocinas', 'Cromados y Defensa', 'Forros y Tapetes Termoformados']
            }
            for cat_nombre, subcats in catalogo_inicial.items():
                cat = Category(nombre=cat_nombre, stock_minimo_alerta=5)
                db.session.add(cat)
                db.session.flush()
                for sub_nombre in subcats:
                    db.session.add(Subcategory(nombre=sub_nombre, categoria_id=cat.id, stock_minimo_alerta=5))
            db.session.commit()
            print("  [+] Categorías y subcategorías automotrices iniciales creadas.")

        # 5. Semillas iniciales de Servicios de Instalación y Técnicos (si está vacío)
        if InstallationService.query.count() == 0:
            servicios_base = [
                ('Instalación Luces LED Principales', 25000.0, 12000.0),
                ('Instalación Exploradoras LED + Relay', 45000.0, 22000.0),
                ('Polarizado Nano-Cerámico Completo', 180000.0, 70000.0),
                ('Instalación Radio Pantalla Android + Cámara', 60000.0, 30000.0),
                ('Instalación Alarma y Bloqueo Central', 70000.0, 35000.0),
            ]
            for nom, precio, costo_tec in servicios_base:
                db.session.add(InstallationService(nombre=nom, precio_estandar=precio, costo_instalador=costo_tec, activo=True))
            db.session.commit()
            print("  [+] Catálogo inicial de servicios de instalación creado.")

        if Installer.query.count() == 0:
            db.session.add(Installer(nombre='Técnico Principal POWER LED', documento='10000001', telefono='3000000000', activo=True))
            db.session.commit()
            print("  [+] Técnico instalador inicial creado.")

        print("[MIGRATE v2] Migración completada exitosamente.")

if __name__ == '__main__':
    run_migration()
