from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from models import (
    db, WorkOrder, WorkOrderItem, Product, InstallationService,
    Installer, Customer, User, Vehicle, get_bogota_time
)
from routes.vehiculos import sincronizar_vehiculo

hojas_trabajo_bp = Blueprint('hojas_trabajo_bp', __name__)

def generar_numero_orden():
    ultimo = WorkOrder.query.order_by(WorkOrder.id.desc()).first()
    sig = (ultimo.id + 1) if ultimo else 1
    return f"OT-{sig:05d}"

@hojas_trabajo_bp.route('/', methods=['GET'])
@login_required
def index():
    estado_filtro = request.args.get('estado', '').strip()
    q = request.args.get('q', '').strip()

    query = WorkOrder.query
    if estado_filtro:
        query = query.filter(WorkOrder.estado == estado_filtro)
    if q:
        from sqlalchemy import or_
        query = query.filter(
            or_(
                WorkOrder.placa_vehiculo.ilike(f'%{q}%'),
                WorkOrder.numero_orden.ilike(f'%{q}%'),
                WorkOrder.modelo_vehiculo.ilike(f'%{q}%')
            )
        )

    ordenes = query.order_by(WorkOrder.fecha_creacion.desc()).all()

    en_proceso_count = WorkOrder.query.filter_by(estado='EN_PROCESO').count()
    listo_cobro_count = WorkOrder.query.filter_by(estado='LISTO_COBRO').count()
    cobradas_count = WorkOrder.query.filter_by(estado='COBRADO').count()

    productos = Product.query.filter(Product.activo.is_(True)).order_by(Product.nombre).all()
    servicios = InstallationService.query.filter(InstallationService.activo.is_(True)).order_by(InstallationService.nombre).all()
    instaladores = Installer.query.filter_by(activo=True).order_by(Installer.nombre).all()
    asesores = User.query.filter(User.rol != 'eliminado').order_by(User.nombre).all()
    clientes = Customer.query.order_by(Customer.nombre).all()

    return render_template(
        'hojas_trabajo/index.html',
        ordenes=ordenes,
        en_proceso_count=en_proceso_count,
        listo_cobro_count=listo_cobro_count,
        cobradas_count=cobradas_count,
        productos=productos,
        servicios=servicios,
        instaladores=instaladores,
        asesores=asesores,
        clientes=clientes,
        estado_filtro=estado_filtro,
        q=q
    )

@hojas_trabajo_bp.route('/nueva', methods=['POST'])
@login_required
def crear():
    placa = (request.form.get('placa_vehiculo') or '').strip().upper()
    modelo = (request.form.get('modelo_vehiculo') or '').strip()
    cliente_id = request.form.get('cliente_id', type=int) or None
    asesor_id = request.form.get('asesor_id', type=int) or current_user.id
    instalador_id = request.form.get('instalador_id', type=int) or None
    fecha_entrega_str = request.form.get('fecha_entrega', '').strip()
    observaciones = (request.form.get('observaciones') or '').strip()

    if not placa:
        flash('La placa del vehículo es obligatoria para abrir una Hoja de Trabajo.', 'danger')
        return redirect(url_for('hojas_trabajo_bp.index'))

    fecha_entrega = None
    if fecha_entrega_str:
        for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                fecha_entrega = datetime.strptime(fecha_entrega_str, fmt)
                break
            except ValueError:
                continue

    orden = WorkOrder(
        numero_orden=generar_numero_orden(),
        placa_vehiculo=placa,
        modelo_vehiculo=modelo,
        cliente_id=cliente_id,
        asesor_id=asesor_id,
        instalador_id=instalador_id,
        fecha_creacion=get_bogota_time(),
        fecha_entrega=fecha_entrega,
        estado='EN_PROCESO',
        observaciones=observaciones
    )

    try:
        vehiculo_obj = sincronizar_vehiculo(
            placa=placa,
            modelo=modelo,
            cliente_id=cliente_id,
            observaciones=observaciones
        )
        orden.vehicle_id = vehiculo_obj.id if vehiculo_obj else None
        db.session.add(orden)
        db.session.flush()

        # Recibir productos y servicios del formulario
        tipos = request.form.getlist('item_tipo[]')
        ref_ids = request.form.getlist('item_ref_id[]')
        cantidades = request.form.getlist('item_cantidad[]')
        precios = request.form.getlist('item_precio[]')

        for i in range(len(tipos)):
            if not ref_ids[i]:
                continue
            t = tipos[i].upper()
            rid = int(ref_ids[i])
            cant = max(1, int(cantidades[i] or 1))
            prec = float(precios[i] or 0.0)

            item = WorkOrderItem(
                order_id=orden.id,
                product_id=rid if t == 'PRODUCTO' else None,
                service_id=rid if t == 'SERVICIO' else None,
                tipo=t,
                cantidad=cant,
                precio_unitario=prec,
                subtotal=cant * prec
            )
            db.session.add(item)

        db.session.commit()
        flash(f'Hoja de Trabajo {orden.numero_orden} para placa {placa} registrada en taller.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear la Hoja de Trabajo: {str(e)}', 'danger')

    return redirect(url_for('hojas_trabajo_bp.index'))

@hojas_trabajo_bp.route('/<int:id>/cobrar', methods=['POST', 'GET'])
@login_required
def cobrar_en_caja(id):
    orden = WorkOrder.query.get_or_404(id)
    if orden.estado == 'COBRADO':
        flash(f'La orden {orden.numero_orden} ya fue cobrada anteriormente.', 'info')
        return redirect(url_for('hojas_trabajo_bp.index'))

    orden.estado = 'LISTO_COBRO'
    db.session.commit()
    return redirect(url_for('sales_bp.caja_visual', hoja_id=orden.id))

@hojas_trabajo_bp.route('/<int:id>/estado', methods=['POST'])
@login_required
def cambiar_estado(id):
    orden = WorkOrder.query.get_or_404(id)
    nuevo_estado = (request.form.get('estado') or '').strip().upper()
    if nuevo_estado in ('EN_PROCESO', 'LISTO_COBRO', 'COBRADO', 'CANCELADO'):
        orden.estado = nuevo_estado
        db.session.commit()
        flash(f'Estado de la orden {orden.numero_orden} actualizado a {nuevo_estado}.', 'success')
    return redirect(url_for('hojas_trabajo_bp.index'))

@hojas_trabajo_bp.route('/api/<int:id>', methods=['GET'])
@login_required
def api_detalle(id):
    orden = WorkOrder.query.get_or_404(id)
    items_data = []
    for it in orden.items:
        if it.tipo == 'SERVICIO' and it.servicio:
            items_data.append({
                'tipo': 'SERVICIO',
                'service_id': it.service_id,
                'product_id': None,
                'nombre': f"[INSTALACIÓN] {it.servicio.nombre}",
                'sku': f"SRV-{it.service_id}",
                'cantidad': it.cantidad,
                'precio_final': float(it.precio_unitario or it.servicio.precio_estandar or 0),
                'precio_distribuidor': float(it.precio_unitario or 0),
                'precio_local': float(it.precio_unitario or 0),
                'precio_cliente_final': float(it.precio_unitario or 0),
                'costo_instalador': float(it.servicio.costo_instalador or 0),
                'installer_id': orden.instalador_id,
                'max_stock': 999
            })
        elif it.producto:
            p = it.producto
            items_data.append({
                'tipo': 'PRODUCTO',
                'product_id': p.id,
                'service_id': None,
                'nombre': p.nombre,
                'sku': p.codigo_barras or p.sku,
                'cantidad': it.cantidad,
                'precio_final': float(it.precio_unitario or p.precio_final or p.precio_sugerido or 0),
                'precio_distribuidor': float(p.precio_distribuidor or p.precio_minimo or 0),
                'precio_local': float(p.precio_local or p.precio_final or 0),
                'precio_cliente_final': float(p.precio_final or p.precio_sugerido or 0),
                'max_stock': max(it.cantidad, p.stock_tienda or 0)
            })

    return jsonify({
        'id': orden.id,
        'numero_orden': orden.numero_orden,
        'placa_vehiculo': orden.placa_vehiculo,
        'modelo_vehiculo': orden.modelo_vehiculo or '',
        'asesor_id': orden.asesor_id,
        'instalador_id': orden.instalador_id,
        'cliente_id': orden.cliente_id,
        'cliente_nombre': orden.cliente.nombre if orden.cliente else '',
        'cliente_documento': orden.cliente.documento if orden.cliente else '',
        'cliente_telefono': orden.cliente.telefono if orden.cliente else '',
        'items': items_data
    })
