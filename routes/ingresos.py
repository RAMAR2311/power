from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_
from models import (
    db, MerchandiseReceipt, MerchandiseReceiptItem, Product, Provider,
    ProviderInvoice, StockAdjustment, Category, Subcategory, get_bogota_time
)

ingresos_bp = Blueprint('ingresos_bp', __name__)


def generar_numero_ingreso():
    ultimo = MerchandiseReceipt.query.order_by(MerchandiseReceipt.id.desc()).first()
    sig = (ultimo.id + 1) if ultimo else 1
    return f"ING-{sig:05d}"


@ingresos_bp.route('/', methods=['GET'])
@login_required
def index():
    q = request.args.get('q', '').strip()
    destino_filtro = request.args.get('destino', '').strip().upper()
    estado_filtro = request.args.get('estado', '').strip().upper()

    query = MerchandiseReceipt.query
    if destino_filtro in ('BODEGA', 'TIENDA'):
        query = query.filter(MerchandiseReceipt.destino == destino_filtro)
    if estado_filtro:
        query = query.filter(MerchandiseReceipt.estado_revision == estado_filtro)
    if q:
        query = query.outerjoin(Provider, MerchandiseReceipt.provider_id == Provider.id).filter(
            or_(
                MerchandiseReceipt.numero_ingreso.ilike(f'%{q}%'),
                MerchandiseReceipt.numero_factura_proveedor.ilike(f'%{q}%'),
                MerchandiseReceipt.proveedor_nombre_manual.ilike(f'%{q}%'),
                Provider.nombre.ilike(f'%{q}%'),
                Provider.empresa.ilike(f'%{q}%')
            )
        )

    ingresos = query.order_by(MerchandiseReceipt.fecha_ingreso.desc()).all()

    productos = Product.query.filter_by(activo=True).order_by(Product.nombre.asc()).all()
    proveedores = Provider.query.order_by(Provider.nombre.asc()).all()
    categorias = Category.query.order_by(Category.nombre.asc()).all()

    # KPIs de trazabilidad
    total_actas = len(ingresos)
    total_unidades_ingresadas = sum(i.total_unidades for i in ingresos)
    total_costo_ingresos = sum(i.costo_total_ingreso for i in ingresos)
    pendientes_revision = MerchandiseReceipt.query.filter_by(estado_revision='PENDIENTE_REVISION').count()

    return render_template(
        'ingresos/index.html',
        ingresos=ingresos,
        productos=productos,
        proveedores=proveedores,
        categorias=categorias,
        total_actas=total_actas,
        total_unidades_ingresadas=total_unidades_ingresadas,
        total_costo_ingresos=total_costo_ingresos,
        pendientes_revision=pendientes_revision,
        q=q,
        destino_filtro=destino_filtro,
        estado_filtro=estado_filtro
    )


@ingresos_bp.route('/nuevo', methods=['POST'])
@login_required
def crear():
    destino = (request.form.get('destino') or 'BODEGA').strip().upper()
    if destino not in ('BODEGA', 'TIENDA'):
        destino = 'BODEGA'

    provider_id = request.form.get('provider_id', type=int) or None
    proveedor_manual = (request.form.get('proveedor_nombre_manual') or '').strip() or None
    numero_factura = (request.form.get('numero_factura_proveedor') or '').strip() or None
    raw_monto_factura = (request.form.get('monto_factura_proveedor') or '').replace(',', '').strip()
    monto_factura_manual = float(raw_monto_factura) if raw_monto_factura else 0.0
    cargar_cuenta_proveedor = request.form.get('cargar_cuenta_proveedor', '1') == '1'
    estado_revision = (request.form.get('estado_revision') or 'PENDIENTE_REVISION').strip().upper()
    revisado_por = (request.form.get('revisado_por') or current_user.nombre or '').strip()
    observaciones = (request.form.get('observaciones') or '').strip()

    # Si no escogieron un proveedor de la lista pero escribieron un nombre manual y pidieron cargar factura,
    # buscamos o creamos automáticamente el Proveedor para poder asignarle el valor de la factura
    if not provider_id and proveedor_manual and cargar_cuenta_proveedor:
        prov_existente = Provider.query.filter(Provider.nombre.ilike(proveedor_manual)).first()
        if prov_existente:
            provider_id = prov_existente.id
        else:
            nuevo_prov = Provider(nombre=proveedor_manual, empresa=proveedor_manual)
            db.session.add(nuevo_prov)
            db.session.flush()
            provider_id = nuevo_prov.id

    product_ids = request.form.getlist('product_id[]')
    cantidades_esperadas = request.form.getlist('cantidad_esperada[]')
    cantidades_recibidas = request.form.getlist('cantidad_recibida[]')
    costos_unitarios = request.form.getlist('costo_unitario[]')
    precios_dist = request.form.getlist('precio_distribuidor[]')
    precios_loc = request.form.getlist('precio_local[]')
    precios_fin = request.form.getlist('precio_final[]')
    notas_items = request.form.getlist('nota_revision[]')

    if not product_ids:
        flash('Debes agregar al menos un producto al acta de ingreso de mercancía.', 'danger')
        return redirect(url_for('ingresos_bp.index'))

    ahora = get_bogota_time()
    ingreso = MerchandiseReceipt(
        numero_ingreso=generar_numero_ingreso(),
        numero_factura_proveedor=numero_factura,
        provider_id=provider_id,
        proveedor_nombre_manual=proveedor_manual,
        destino=destino,
        estado_revision=estado_revision,
        usuario_id=current_user.id,
        revisado_por=revisado_por,
        fecha_ingreso=ahora,
        fecha_revision=ahora if estado_revision == 'VERIFICADO' else None,
        observaciones=observaciones
    )

    try:
        db.session.add(ingreso)
        db.session.flush()

        items_validos = 0
        hay_novedad = False

        for i in range(len(product_ids)):
            if not product_ids[i]:
                continue
            pid = int(product_ids[i])
            cant_rec = int(cantidades_recibidas[i] or 0)
            cant_esp = int(cantidades_esperadas[i] or cant_rec) if i < len(cantidades_esperadas) and cantidades_esperadas[i] else cant_rec
            if cant_rec <= 0:
                continue

            producto = Product.query.with_for_update().get(pid)
            if not producto:
                continue

            costo_u = float(costos_unitarios[i] or producto.costo or producto.precio_costo or 0)
            nota_it = (notas_items[i] if i < len(notas_items) else '').strip()

            # Actualizar costo y precios si se especificaron en el ingreso
            if costo_u > 0:
                producto.costo = costo_u
                producto.precio_costo = costo_u
            if i < len(precios_dist) and precios_dist[i]:
                val_d = float(precios_dist[i] or 0)
                if val_d > 0:
                    producto.precio_distribuidor = val_d
                    producto.precio_minimo = val_d
            if i < len(precios_loc) and precios_loc[i]:
                val_l = float(precios_loc[i] or 0)
                if val_l > 0:
                    producto.precio_local = val_l
            if i < len(precios_fin) and precios_fin[i]:
                val_f = float(precios_fin[i] or 0)
                if val_f > 0:
                    producto.precio_final = val_f
                    producto.precio_sugerido = val_f

            # Sumar stock según el destino seleccionado (BODEGA o TIENDA) y guardar trazabilidad exacta
            if destino == 'BODEGA':
                stock_ant = int(producto.stock_bodega or 0)
                producto.stock_bodega = stock_ant + cant_rec
                stock_nvo = producto.stock_bodega
                tipo_mov = f"Ingreso Mercancía Bodega ({ingreso.numero_ingreso})"
            else:
                stock_ant = int(producto.stock_tienda or 0)
                producto.stock_tienda = stock_ant + cant_rec
                producto.cantidad_stock = producto.stock_tienda
                stock_nvo = producto.stock_tienda
                tipo_mov = f"Ingreso Mercancía Tienda ({ingreso.numero_ingreso})"

            conformidad = 'OK'
            if cant_rec < cant_esp:
                conformidad = 'FALTANTE'
                hay_novedad = True

            item = MerchandiseReceiptItem(
                receipt_id=ingreso.id,
                product_id=producto.id,
                cantidad_esperada=cant_esp,
                cantidad_recibida=cant_rec,
                costo_unitario=costo_u,
                subtotal_costo=cant_rec * costo_u,
                stock_anterior=stock_ant,
                stock_nuevo=stock_nvo,
                conformidad=conformidad,
                nota_revision=nota_it or None
            )
            db.session.add(item)

            # Registrar en el Kardex Global (StockAdjustment) para trazabilidad cruzada
            kardex = StockAdjustment(
                product_id=producto.id,
                admin_id=current_user.id,
                tipo_movimiento=tipo_mov,
                stock_anterior=stock_ant,
                stock_nuevo=stock_nvo,
                fecha_ajuste=ahora
            )
            db.session.add(kardex)
            items_validos += 1

        if items_validos == 0:
            db.session.rollback()
            flash('No se ingresaron cantidades mayores a 0.', 'warning')
            return redirect(url_for('ingresos_bp.index'))

        if hay_novedad and ingreso.estado_revision == 'VERIFICADO':
            ingreso.estado_revision = 'CON_NOVEDAD'

        # Determinar el valor final de la factura del ingreso (el digitado o la suma de costos de los productos)
        costo_calculado = sum(float(it.subtotal_costo or 0) for it in ingreso.items)
        valor_factura_final = monto_factura_manual if monto_factura_manual > 0 else costo_calculado
        ingreso.monto_factura_asignado = valor_factura_final

        # Si hay un proveedor seleccionado y se solicitó asignarle la factura a su estado de cuenta
        factura_msg = ""
        if provider_id and cargar_cuenta_proveedor and valor_factura_final > 0:
            folio_factura = numero_factura or ingreso.numero_ingreso
            desc_factura = f"Ingreso de Mercancía {ingreso.numero_ingreso} ({ingreso.total_unidades} uds a {destino})"
            if observaciones:
                desc_factura += f" - {observaciones[:120]}"
            nueva_factura_prov = ProviderInvoice(
                provider_id=provider_id,
                monto_total=valor_factura_final,
                numero_factura=folio_factura,
                descripcion=desc_factura,
                fecha_factura=ahora
            )
            db.session.add(nueva_factura_prov)
            db.session.flush()
            ingreso.provider_invoice_id = nueva_factura_prov.id
            prov_obj = Provider.query.get(provider_id)
            prov_nom = prov_obj.nombre if prov_obj else "Proveedor"
            factura_msg = f" Se cargó la factura {folio_factura} por ${valor_factura_final:,.0f} al proveedor {prov_nom}."

        db.session.commit()
        flash(f'Acta de Ingreso {ingreso.numero_ingreso} registrada ({ingreso.total_unidades} uds enviadas a {destino}).{factura_msg}', 'success')
        return redirect(url_for('ingresos_bp.ticket_revision', id=ingreso.id))

    except Exception as e:
        db.session.rollback()
        flash(f'Error al procesar el ingreso de mercancía: {str(e)}', 'danger')
        return redirect(url_for('ingresos_bp.index'))


@ingresos_bp.route('/<int:id>/ticket', methods=['GET'])
@login_required
def ticket_revision(id):
    """
    Renderiza el Ticket Térmico 80mm / Acta de Revisión Física de Mercancía
    con casillas de chequeo (Checklist), stock anterior -> stock nuevo,
    cantidades esperadas vs recibidas y firmas de recibido/revisado.
    """
    ingreso = MerchandiseReceipt.query.get_or_404(id)
    return render_template('ingresos/ticket_revision.html', ingreso=ingreso)


@ingresos_bp.route('/<int:id>/aprobar-revision', methods=['POST'])
@login_required
def aprobar_revision(id):
    ingreso = MerchandiseReceipt.query.get_or_404(id)
    estado = (request.form.get('estado_revision') or 'VERIFICADO').strip().upper()
    revisado_por = (request.form.get('revisado_por') or current_user.nombre).strip()
    observaciones = (request.form.get('observaciones') or '').strip()

    ingreso.estado_revision = estado
    ingreso.revisado_por = revisado_por
    ingreso.fecha_revision = get_bogota_time()
    if observaciones:
        ingreso.observaciones = (f"{ingreso.observaciones} | Revisión: {observaciones}" if ingreso.observaciones else f"Revisión: {observaciones}")

    db.session.commit()
    flash(f'Estado de revisión del ingreso {ingreso.numero_ingreso} actualizado a {estado}.', 'success')
    return redirect(url_for('ingresos_bp.ticket_revision', id=ingreso.id))


@ingresos_bp.route('/api/crear-proveedor-rapido', methods=['POST'])
@login_required
def api_crear_proveedor_rapido():
    """Permite crear un proveedor nuevo sobre la marcha mientras se recibe mercancía."""
    data = request.get_json(silent=True) or request.form
    nombre = (data.get('nombre') or '').strip()
    empresa = (data.get('empresa') or '').strip()
    telefono = (data.get('telefono') or '').strip()

    if not nombre:
        return jsonify({'success': False, 'message': 'El nombre del proveedor es obligatorio.'}), 400

    prov = Provider(
        nombre=nombre,
        empresa=empresa or None,
        telefono=telefono or None
    )
    db.session.add(prov)
    db.session.commit()

    return jsonify({
        'success': True,
        'proveedor': {
            'id': prov.id,
            'nombre': prov.nombre,
            'empresa': prov.empresa or '',
            'display': f"{prov.nombre} ({prov.empresa})" if prov.empresa else prov.nombre
        }
    })


@ingresos_bp.route('/api/crear-producto-rapido', methods=['POST'])
@login_required
def api_crear_producto_rapido():
    """Permite crear un producto nuevo sobre la marcha mientras se recibe mercancía."""
    data = request.get_json(silent=True) or request.form
    nombre = (data.get('nombre') or '').strip()
    codigo_barras = (data.get('codigo_barras') or '').strip().upper()
    raw_cat = data.get('categoria_id')
    categoria_id = int(raw_cat) if raw_cat and str(raw_cat).isdigit() else None
    costo = float(data.get('costo') or 0)
    precio_dist = float(data.get('precio_distribuidor') or costo)
    precio_loc = float(data.get('precio_local') or precio_dist)
    precio_fin = float(data.get('precio_final') or precio_loc)

    if not nombre:
        return jsonify({'success': False, 'message': 'El nombre del producto es obligatorio.'}), 400

    if not codigo_barras:
        import time
        codigo_barras = f"PW-{int(time.time()) % 1000000}"

    if Product.query.filter(or_(Product.codigo_barras == codigo_barras, Product.sku == codigo_barras)).first():
        return jsonify({'success': False, 'message': f'El código {codigo_barras} ya existe.'}), 400

    prod = Product(
        nombre=nombre,
        codigo_barras=codigo_barras,
        sku=codigo_barras,
        categoria_id=categoria_id,
        costo=costo,
        precio_distribuidor=precio_dist,
        precio_local=precio_loc,
        precio_final=precio_fin,
        stock_tienda=0,
        stock_bodega=0,
        stock_minimo=5
    )
    db.session.add(prod)
    db.session.commit()

    return jsonify({
        'success': True,
        'producto': {
            'id': prod.id,
            'nombre': prod.nombre,
            'sku': prod.codigo_barras,
            'costo': prod.costo,
            'precio_distribuidor': prod.precio_distribuidor,
            'precio_local': prod.precio_local,
            'precio_final': prod.precio_final,
            'stock_bodega': prod.stock_bodega,
            'stock_tienda': prod.stock_tienda
        }
    })
