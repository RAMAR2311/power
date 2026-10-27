import os
import uuid
import time
from werkzeug.utils import secure_filename
from flask import current_app, Blueprint, render_template, request, redirect, url_for, flash, abort, send_file, jsonify
from flask_login import login_required, current_user
from models import db, Product, StockAdjustment, ProductVariant, Category, Subcategory
from decorators import admin_required, admin_or_bodega_required
import pandas as pd
from io import BytesIO
from sqlalchemy import or_

inventory_bp = Blueprint('inventory_bp', __name__)

@inventory_bp.route('/', methods=['GET'])
@login_required
@admin_or_bodega_required
def index():
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '').strip()
    categoria_id = request.args.get('categoria_id', type=int)
    subcategory_id = request.args.get('subcategory_id', type=int)
    filtro_alerta = request.args.get('alerta', '').strip()
    per_page = 25

    base_query = Product.query.filter(Product.activo.is_(True))
    if q:
        base_query = base_query.filter(
            or_(
                Product.sku.ilike(f'%{q}%'),
                Product.codigo_barras.ilike(f'%{q}%'),
                Product.nombre.ilike(f'%{q}%'),
                Product.observacion.ilike(f'%{q}%'),
                Product.variantes.any(ProductVariant.nombre_variante.ilike(f'%{q}%'))
            )
        )

    if categoria_id:
        base_query = base_query.filter(Product.categoria_id == categoria_id)
    if subcategory_id:
        base_query = base_query.filter(Product.subcategory_id == subcategory_id)

    # Si se activa el filtro rápido de alertas de stock crítico
    if filtro_alerta == 'critico':
        todos_filtrados = [p for p in base_query.order_by(Product.nombre).all() if p.alerta_stock_activa]
        paginacion = None
        productos = todos_filtrados
    else:
        paginacion = base_query.order_by(Product.nombre).paginate(
            page=page, per_page=per_page, error_out=False
        )
        productos = paginacion.items

    # --- KPIs de Inventario ---
    todos = Product.query.filter(Product.activo.is_(True)).all()
    total_productos = len(todos)

    valor_costo = 0.0
    valor_sugerido = 0.0
    total_unidades_fisicas = 0
    total_unidades_bodega = 0
    productos_alerta_count = 0

    for p in todos:
        if p.alerta_stock_activa:
            productos_alerta_count += 1
        costo_u = float(p.costo or p.precio_costo or 0)
        final_u = float(p.precio_final or p.precio_sugerido or 0)
        st_tienda = int(p.stock_tienda if p.stock_tienda is not None else (p.cantidad_stock or 0))
        st_bodega = int(p.stock_bodega or 0)
        total_u = st_tienda + st_bodega
        valor_costo += costo_u * total_u
        valor_sugerido += final_u * total_u
        total_unidades_fisicas += st_tienda
        total_unidades_bodega += st_bodega

    categorias = Category.query.order_by(Category.nombre).all()
    subcategorias = Subcategory.query.filter_by(categoria_id=categoria_id).order_by(Subcategory.nombre).all() if categoria_id else Subcategory.query.order_by(Subcategory.nombre).all()

    return render_template(
        'inventory/index.html',
        productos=productos,
        paginacion=paginacion,
        total_productos=total_productos,
        valor_costo=valor_costo,
        valor_sugerido=valor_sugerido,
        total_unidades_fisicas=total_unidades_fisicas,
        total_unidades_bodega=total_unidades_bodega,
        productos_alerta_count=productos_alerta_count,
        categorias=categorias,
        subcategorias=subcategorias,
        categoria_id=categoria_id,
        subcategory_id=subcategory_id,
        filtro_alerta=filtro_alerta,
        q=q
    )

@inventory_bp.route('/api/subcategorias/<int:categoria_id>', methods=['GET'])
@login_required
def api_subcategorias(categoria_id):
    subs = Subcategory.query.filter_by(categoria_id=categoria_id).order_by(Subcategory.nombre).all()
    return jsonify([{
        'id': s.id,
        'nombre': s.nombre,
        'stock_minimo_alerta': s.stock_minimo_alerta
    } for s in subs])

@inventory_bp.route('/categorias/crear', methods=['POST'])
@login_required
@admin_or_bodega_required
def crear_categoria():
    nombre = (request.form.get('nombre') or '').strip()
    stock_min = int(request.form.get('stock_minimo_alerta') or 5)
    if not nombre:
        flash('El nombre de la categoría es obligatorio.', 'warning')
        return redirect(url_for('inventory_bp.index'))

    if Category.query.filter(Category.nombre.ilike(nombre)).first():
        flash(f'La categoría "{nombre}" ya existe.', 'warning')
        return redirect(url_for('inventory_bp.index'))

    cat = Category(nombre=nombre, stock_minimo_alerta=stock_min)
    db.session.add(cat)
    db.session.commit()
    flash(f'Categoría "{nombre}" creada exitosamente.', 'success')
    return redirect(request.referrer or url_for('inventory_bp.index'))

@inventory_bp.route('/subcategorias/crear', methods=['POST'])
@login_required
@admin_or_bodega_required
def crear_subcategoria():
    categoria_id = request.form.get('categoria_id', type=int)
    nombre = (request.form.get('nombre') or '').strip()
    stock_min_raw = request.form.get('stock_minimo_alerta', '').strip()
    stock_min = int(stock_min_raw) if stock_min_raw else None

    if not categoria_id or not nombre:
        flash('Debes seleccionar una categoría padre y escribir el nombre de la subcategoría.', 'warning')
        return redirect(url_for('inventory_bp.index'))

    sub = Subcategory(nombre=nombre, categoria_id=categoria_id, stock_minimo_alerta=stock_min)
    db.session.add(sub)
    db.session.commit()
    flash(f'Subcategoría "{nombre}" creada correctamente.', 'success')
    return redirect(request.referrer or url_for('inventory_bp.index'))

@inventory_bp.route('/categorias/<int:id>/eliminar', methods=['POST'])
@login_required
@admin_or_bodega_required
def eliminar_categoria(id):
    cat = Category.query.get_or_404(id)
    for p in cat.productos:
        p.categoria_id = None
        p.subcategory_id = None
    db.session.delete(cat)
    db.session.commit()
    flash(f'Categoría "{cat.nombre}" eliminada.', 'info')
    return redirect(request.referrer or url_for('inventory_bp.index'))

@inventory_bp.route('/subcategorias/<int:id>/eliminar', methods=['POST'])
@login_required
@admin_or_bodega_required
def eliminar_subcategoria(id):
    sub = Subcategory.query.get_or_404(id)
    for p in sub.productos:
        p.subcategory_id = None
    db.session.delete(sub)
    db.session.commit()
    flash(f'Subcategoría "{sub.nombre}" eliminada.', 'info')
    return redirect(request.referrer or url_for('inventory_bp.index'))

@inventory_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@admin_or_bodega_required
def nuevo():
    categorias = Category.query.order_by(Category.nombre).all()
    subcategorias = Subcategory.query.order_by(Subcategory.nombre).all()

    if request.method == 'POST':
        imagen_filename = None
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                sec_name = secure_filename(file.filename)
                ext = sec_name.rsplit('.', 1)[-1].lower() if '.' in sec_name else 'jpg'
                filename = f"prod_{uuid.uuid4().hex[:8]}_{int(time.time())}.{ext}"
                try:
                    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
                    file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                    imagen_filename = filename
                except OSError as e:
                    flash(f'Error al guardar la imagen: {str(e)}', 'danger')
                    return redirect(url_for('inventory_bp.nuevo'))

        sku_candidato = (request.form.get('codigo_barras') or request.form.get('sku') or '').strip()
        if not sku_candidato:
            flash('Debes ingresar un Código de Barras / SKU para el producto.', 'warning')
            return render_template('inventory/form.html', categorias=categorias, subcategorias=subcategorias)

        prod_existente = Product.query.filter(
            or_(Product.sku == sku_candidato, Product.codigo_barras == sku_candidato),
            Product.activo.is_(True)
        ).first()
        if prod_existente:
            flash(f'El código "{sku_candidato}" ya existe en el inventario (pertenece a "{prod_existente.nombre}").', 'warning')
            return render_template('inventory/form.html', categorias=categorias, subcategorias=subcategorias)

        costo_val = float(request.form.get('costo') or request.form.get('precio_costo') or 0.0)
        p_distribuidor = float(request.form.get('precio_distribuidor') or request.form.get('precio_minimo') or 0.0)
        p_local = float(request.form.get('precio_local') or 0.0)
        p_final = float(request.form.get('precio_final') or request.form.get('precio_sugerido') or 0.0)
        if p_local <= 0 and p_final > 0:
            p_local = p_final

        stock_tienda_val = int(request.form.get('stock_tienda') if request.form.get('stock_tienda') is not None else (request.form.get('cantidad_stock') or 0))
        stock_bodega_val = int(request.form.get('stock_bodega') or 0)
        stock_minimo_val = int(request.form.get('stock_minimo') or 5)

        categoria_id = request.form.get('categoria_id', type=int) or None
        subcategory_id = request.form.get('subcategory_id', type=int) or None

        nuevo_prod = Product(
            sku=sku_candidato,
            codigo_barras=sku_candidato,
            nombre=request.form.get('nombre', '').strip(),
            categoria_id=categoria_id,
            subcategory_id=subcategory_id,
            costo=costo_val,
            precio_distribuidor=p_distribuidor,
            precio_local=p_local,
            precio_final=p_final,
            precio_costo=costo_val,
            precio_minimo=p_distribuidor,
            precio_sugerido=p_final,
            stock_tienda=stock_tienda_val,
            stock_bodega=stock_bodega_val,
            stock_minimo=stock_minimo_val,
            cantidad_stock=stock_tienda_val,
            tipo_inventario='tienda',
            imagen=imagen_filename,
            observacion=request.form.get('observacion')
        )

        try:
            db.session.add(nuevo_prod)
            db.session.flush()

            ajuste_inicial = StockAdjustment(
                product_id=nuevo_prod.id,
                admin_id=current_user.id,
                tipo_movimiento=f'Creación Inicial (Tienda: {stock_tienda_val} / Bodega: {stock_bodega_val})',
                stock_anterior=0,
                stock_nuevo=stock_tienda_val
            )
            db.session.add(ajuste_inicial)
            db.session.commit()

            flash('Producto registrado exitosamente con sus 3 listas de precios y stock dual.', 'success')
            return redirect(url_for('inventory_bp.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar el producto: {str(e)}', 'danger')

    return render_template('inventory/form.html', producto=None, categorias=categorias, subcategorias=subcategorias)

@inventory_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_or_bodega_required
def editar_producto(id):
    producto = Product.query.get_or_404(id)
    categorias = Category.query.order_by(Category.nombre).all()
    subcategorias = Subcategory.query.order_by(Subcategory.nombre).all()

    if request.method == 'POST':
        stock_anterior = producto.stock_tienda or 0

        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                sec_name = secure_filename(file.filename)
                ext = sec_name.rsplit('.', 1)[-1].lower() if '.' in sec_name else 'jpg'
                filename = f"prod_{producto.id}_{uuid.uuid4().hex[:8]}_{int(time.time())}.{ext}"
                try:
                    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
                    file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                    producto.imagen = filename
                except OSError as e:
                    flash(f'Error al guardar la imagen: {str(e)}', 'danger')
                    return redirect(url_for('inventory_bp.editar_producto', id=id))

        nuevo_sku = (request.form.get('codigo_barras') or request.form.get('sku') or '').strip()
        if not nuevo_sku:
            flash('El Código de Barras / SKU no puede estar vacío.', 'warning')
            return redirect(url_for('inventory_bp.editar_producto', id=id))

        otro_con_sku = Product.query.filter(
            or_(Product.sku == nuevo_sku, Product.codigo_barras == nuevo_sku),
            Product.id != id
        ).first()
        if otro_con_sku:
            flash(f'El código "{nuevo_sku}" ya pertenece a "{otro_con_sku.nombre}".', 'warning')
            return redirect(url_for('inventory_bp.editar_producto', id=id))

        costo_val = float(request.form.get('costo') or request.form.get('precio_costo') or 0.0)
        p_distribuidor = float(request.form.get('precio_distribuidor') or request.form.get('precio_minimo') or 0.0)
        p_local = float(request.form.get('precio_local') or 0.0)
        p_final = float(request.form.get('precio_final') or request.form.get('precio_sugerido') or 0.0)
        if p_local <= 0 and p_final > 0:
            p_local = p_final

        stock_tienda_val = int(request.form.get('stock_tienda') if request.form.get('stock_tienda') is not None else (request.form.get('cantidad_stock') or 0))
        stock_bodega_val = int(request.form.get('stock_bodega') or 0)
        stock_minimo_val = int(request.form.get('stock_minimo') or 5)

        producto.sku = nuevo_sku
        producto.codigo_barras = nuevo_sku
        producto.nombre = request.form.get('nombre', '').strip()
        producto.categoria_id = request.form.get('categoria_id', type=int) or None
        producto.subcategory_id = request.form.get('subcategory_id', type=int) or None
        producto.costo = costo_val
        producto.precio_distribuidor = p_distribuidor
        producto.precio_local = p_local
        producto.precio_final = p_final
        producto.precio_costo = costo_val
        producto.precio_minimo = p_distribuidor
        producto.precio_sugerido = p_final
        producto.stock_tienda = stock_tienda_val
        producto.stock_bodega = stock_bodega_val
        producto.stock_minimo = stock_minimo_val
        producto.cantidad_stock = stock_tienda_val
        producto.observacion = request.form.get('observacion')

        try:
            db.session.commit()
            if stock_anterior != stock_tienda_val:
                ajuste = StockAdjustment(
                    product_id=producto.id,
                    admin_id=current_user.id,
                    tipo_movimiento='Ajuste de Inventario en Edición',
                    stock_anterior=stock_anterior,
                    stock_nuevo=stock_tienda_val
                )
                db.session.add(ajuste)
                db.session.commit()

            flash('Producto actualizado correctamente.', 'success')
            return redirect(url_for('inventory_bp.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el producto: {str(e)}', 'danger')

    return render_template('inventory/form.html', producto=producto, categorias=categorias, subcategorias=subcategorias)

@inventory_bp.route('/historial-ajustes')
@login_required
@admin_or_bodega_required
def historial_ajustes():
    ajustes = StockAdjustment.query.order_by(StockAdjustment.fecha_ajuste.desc()).limit(250).all()
    return render_template('inventory/historial_ajustes.html', ajustes=ajustes)

@inventory_bp.route('/ver/<int:id>', methods=['GET'])
@login_required
@admin_or_bodega_required
def ver_producto(id):
    producto = Product.query.get_or_404(id)
    ajustes = StockAdjustment.query.filter_by(product_id=id).order_by(StockAdjustment.fecha_ajuste.desc()).all()
    return render_template('inventory/ver.html', producto=producto, ajustes=ajustes)

@inventory_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_or_bodega_required
def eliminar_producto(id):
    producto = Product.query.get_or_404(id)
    nombre = producto.nombre
    try:
        if producto.sku and not producto.sku.endswith(f"_arch_{producto.id}"):
            producto.sku = f"{producto.sku}_arch_{producto.id}"
        if producto.codigo_barras and not producto.codigo_barras.endswith(f"_arch_{producto.id}"):
            producto.codigo_barras = f"{producto.codigo_barras}_arch_{producto.id}"
        producto.activo = False
        db.session.commit()
        flash(f'Producto "{nombre}" fue retirado del catálogo activo.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al eliminar el producto: {str(e)}', 'danger')
    return redirect(url_for('inventory_bp.index'))

@inventory_bp.route('/plantilla-importacion')
@login_required
@admin_or_bodega_required
def descargar_plantilla():
    df = pd.DataFrame(columns=[
        'codigo_barras', 'nombre', 'categoria', 'subcategoria',
        'stock_tienda', 'stock_bodega', 'stock_minimo',
        'costo', 'precio_distribuidor', 'precio_local', 'precio_final', 'observacion'
    ])
    df.loc[0] = ['LED-H4-PRO', 'Kit Bombillos LED H4 Turbo 24000LM', 'Iluminación LED Automotriz', 'Bombillería LED Principal (H4/H7/H11/9005)', 15, 40, 5, 45000, 65000, 75000, 90000, 'Luz blanca 6500K Canbus']
    df.loc[1] = ['EXP-MINI-3P', 'Exploradoras LED Lupa Mini Driving Bicolor', 'Iluminación LED Automotriz', 'Exploradoras y Barras LED', 10, 25, 5, 38000, 55000, 65000, 80000, 'Blanco + Ámbar']

    output = BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    output.seek(0)
    return send_file(output, download_name="plantilla_importacion_power_led.xlsx", as_attachment=True)

@inventory_bp.route('/importar', methods=['POST'])
@login_required
@admin_or_bodega_required
def importar_inventario():
    if 'archivo' not in request.files:
        flash('No se seleccionó ningún archivo.', 'danger')
        return redirect(url_for('inventory_bp.index'))

    archivo = request.files['archivo']
    if archivo.filename == '':
        flash('Ningún archivo seleccionado.', 'danger')
        return redirect(url_for('inventory_bp.index'))

    if not (archivo.filename.endswith('.xlsx') or archivo.filename.endswith('.csv')):
        flash('Formato no válido. Solo debes subir archivos .xlsx o .csv', 'warning')
        return redirect(url_for('inventory_bp.index'))

    try:
        df = pd.read_csv(archivo) if archivo.filename.endswith('.csv') else pd.read_excel(archivo)
        df.columns = [str(c).strip().lower() for c in df.columns]

        creados = 0
        actualizados = 0

        for _, row in df.iterrows():
            sku_raw = str(row.get('codigo_barras', row.get('sku', ''))).strip()
            if not sku_raw or sku_raw.lower() == 'nan':
                continue

            nombre_val = str(row.get('nombre', 'Producto Sin Nombre')).strip()
            st_tienda = int(row['stock_tienda']) if 'stock_tienda' in row and pd.notna(row['stock_tienda']) else (int(row['cantidad_stock']) if 'cantidad_stock' in row and pd.notna(row['cantidad_stock']) else 0)
            st_bodega = int(row['stock_bodega']) if 'stock_bodega' in row and pd.notna(row['stock_bodega']) else 0
            st_min = int(row['stock_minimo']) if 'stock_minimo' in row and pd.notna(row['stock_minimo']) else 5

            costo_v = float(row['costo']) if 'costo' in row and pd.notna(row['costo']) else (float(row['precio_costo']) if 'precio_costo' in row and pd.notna(row['precio_costo']) else 0.0)
            p_dist = float(row['precio_distribuidor']) if 'precio_distribuidor' in row and pd.notna(row['precio_distribuidor']) else (float(row['precio_minimo']) if 'precio_minimo' in row and pd.notna(row['precio_minimo']) else 0.0)
            p_fin = float(row['precio_final']) if 'precio_final' in row and pd.notna(row['precio_final']) else (float(row['precio_sugerido']) if 'precio_sugerido' in row and pd.notna(row['precio_sugerido']) else 0.0)
            p_loc = float(row['precio_local']) if 'precio_local' in row and pd.notna(row['precio_local']) else p_fin

            cat_name = str(row.get('categoria', '')).strip() if 'categoria' in row and pd.notna(row.get('categoria')) else ''
            sub_name = str(row.get('subcategoria', '')).strip() if 'subcategoria' in row and pd.notna(row.get('subcategoria')) else ''

            cat_obj = None
            sub_obj = None
            if cat_name and cat_name.lower() != 'nan':
                cat_obj = Category.query.filter(Category.nombre.ilike(cat_name)).first()
                if not cat_obj:
                    cat_obj = Category(nombre=cat_name, stock_minimo_alerta=5)
                    db.session.add(cat_obj)
                    db.session.flush()
            if sub_name and sub_name.lower() != 'nan' and cat_obj:
                sub_obj = Subcategory.query.filter(Subcategory.categoria_id == cat_obj.id, Subcategory.nombre.ilike(sub_name)).first()
                if not sub_obj:
                    sub_obj = Subcategory(nombre=sub_name, categoria_id=cat_obj.id, stock_minimo_alerta=5)
                    db.session.add(sub_obj)
                    db.session.flush()

            obs_val = str(row.get('observacion', '')).strip() if 'observacion' in row and pd.notna(row.get('observacion')) else ''
            if obs_val.lower() == 'nan':
                obs_val = ''

            prod = Product.query.filter(or_(Product.sku == sku_raw, Product.codigo_barras == sku_raw)).first()
            if prod:
                prod.stock_tienda = (prod.stock_tienda or 0) + st_tienda
                prod.stock_bodega = (prod.stock_bodega or 0) + st_bodega
                prod.cantidad_stock = prod.stock_tienda
                prod.costo = costo_v
                prod.precio_costo = costo_v
                prod.precio_distribuidor = p_dist
                prod.precio_minimo = p_dist
                prod.precio_local = p_loc
                prod.precio_final = p_fin
                prod.precio_sugerido = p_fin
                prod.nombre = nombre_val
                if cat_obj: prod.categoria_id = cat_obj.id
                if sub_obj: prod.subcategory_id = sub_obj.id
                if obs_val: prod.observacion = obs_val
                actualizados += 1
            else:
                nuevo_p = Product(
                    sku=sku_raw,
                    codigo_barras=sku_raw,
                    nombre=nombre_val,
                    categoria_id=cat_obj.id if cat_obj else None,
                    subcategory_id=sub_obj.id if sub_obj else None,
                    stock_tienda=st_tienda,
                    stock_bodega=st_bodega,
                    stock_minimo=st_min,
                    cantidad_stock=st_tienda,
                    costo=costo_v,
                    precio_distribuidor=p_dist,
                    precio_local=p_loc,
                    precio_final=p_fin,
                    precio_costo=costo_v,
                    precio_minimo=p_dist,
                    precio_sugerido=p_fin,
                    observacion=obs_val
                )
                db.session.add(nuevo_p)
                creados += 1

        db.session.commit()
        flash(f'Importación completada. Creados: {creados} | Actualizados: {actualizados}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al importar el archivo: {str(e)}', 'danger')

    return redirect(url_for('inventory_bp.index'))

@inventory_bp.route('/api/search')
@login_required
def api_search():
    query = request.args.get('q', '').strip()
    if len(query) < 1:
        return jsonify([])

    productos = Product.query.filter(Product.activo.is_(True)).filter(
        or_(
            Product.sku.ilike(f'%{query}%'),
            Product.codigo_barras.ilike(f'%{query}%'),
            Product.nombre.ilike(f'%{query}%'),
            Product.observacion.ilike(f'%{query}%')
        )
    ).limit(15).all()

    results = []
    for p in productos:
        results.append({
            'id': p.id,
            'sku': p.codigo_barras or p.sku,
            'nombre': p.nombre,
            'categoria': p.categoria.nombre if p.categoria else 'General',
            'subcategoria': p.subcategoria.nombre if p.subcategoria else '',
            'stock': p.stock_tienda,
            'stock_bodega': p.stock_bodega,
            'alerta_stock': p.alerta_stock_activa,
            'precio_distribuidor': float(p.precio_distribuidor or 0),
            'precio_local': float(p.precio_local or 0),
            'precio_final': float(p.precio_final or p.precio_sugerido or 0),
            'precio_sugerido': float(p.precio_final or p.precio_sugerido or 0),
            'variantes': [],
            'url_ver': url_for('inventory_bp.ver_producto', id=p.id),
            'url_editar': url_for('inventory_bp.editar_producto', id=p.id)
        })

    return jsonify(results)
