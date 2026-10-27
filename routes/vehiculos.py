from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_
from models import (
    db, Vehicle, WorkOrder, Sale, Customer, Installer, User, get_bogota_time
)

vehiculos_bp = Blueprint('vehiculos_bp', __name__)


def sincronizar_vehiculo(placa, modelo=None, marca=None, color=None, anio=None, tipo=None, cliente_id=None, observaciones=None):
    """
    Crea o actualiza automáticamente el vehículo en el expediente histórico (Vehicle)
    cada vez que se registra una Hoja de Trabajo, una Venta en POS o un Cliente con placa.
    """
    placa_clean = (placa or '').strip().upper()
    if not placa_clean:
        return None

    vehiculo = Vehicle.query.filter_by(placa=placa_clean).first()
    ahora = get_bogota_time()

    if not vehiculo:
        vehiculo = Vehicle(
            placa=placa_clean,
            marca=(marca or '').strip() or None,
            modelo=(modelo or '').strip() or None,
            anio=(anio or '').strip() or None,
            color=(color or '').strip() or None,
            tipo=(tipo or 'AUTOMOVIL').strip().upper(),
            cliente_id=cliente_id,
            observaciones=(observaciones or '').strip() or None,
            fecha_registro=ahora,
            ultima_visita=ahora
        )
        db.session.add(vehiculo)
        db.session.flush()
    else:
        vehiculo.ultima_visita = ahora
        if modelo and not vehiculo.modelo:
            vehiculo.modelo = modelo.strip()
        elif modelo and modelo.strip() and modelo.strip() != vehiculo.modelo:
            vehiculo.modelo = modelo.strip()
        if marca and marca.strip():
            vehiculo.marca = marca.strip()
        if color and color.strip():
            vehiculo.color = color.strip()
        if anio and anio.strip():
            vehiculo.anio = anio.strip()
        if tipo and tipo.strip():
            vehiculo.tipo = tipo.strip().upper()
        if cliente_id and not vehiculo.cliente_id:
            vehiculo.cliente_id = cliente_id
        if observaciones and observaciones.strip():
            vehiculo.observaciones = observaciones.strip()

    # Sincronizar placa frecuente en el cliente propietario si aplica
    if cliente_id:
        cli = Customer.query.get(cliente_id)
        if cli and not cli.placa_frecuente:
            cli.placa_frecuente = placa_clean

    return vehiculo


def poblar_vehiculos_historicos():
    """
    Escanea WorkOrder, Sale y Customer existentes para garantizar que cualquier placa
    registrada previamente aparezca en el módulo de Vehículos y quede enlazada.
    """
    cambios = False
    for wo in WorkOrder.query.all():
        if wo.placa_vehiculo:
            v = sincronizar_vehiculo(
                placa=wo.placa_vehiculo,
                modelo=wo.modelo_vehiculo,
                cliente_id=wo.cliente_id
            )
            if v and wo.vehicle_id != v.id:
                wo.vehicle_id = v.id
                cambios = True

    for s in Sale.query.all():
        if s.placa_vehiculo:
            v = sincronizar_vehiculo(
                placa=s.placa_vehiculo,
                modelo=s.modelo_vehiculo,
                cliente_id=s.cliente_id
            )
            if v and s.vehicle_id != v.id:
                s.vehicle_id = v.id
                cambios = True

    for c in Customer.query.all():
        if c.placa_frecuente:
            sincronizar_vehiculo(
                placa=c.placa_frecuente,
                cliente_id=c.id
            )
            cambios = True

    if cambios:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


@vehiculos_bp.route('/', methods=['GET'])
@login_required
def index():
    poblar_vehiculos_historicos()

    q = request.args.get('q', '').strip()
    tipo_filtro = request.args.get('tipo', '').strip().upper()

    query = Vehicle.query
    if tipo_filtro:
        query = query.filter(Vehicle.tipo == tipo_filtro)
    if q:
        query = query.outerjoin(Customer, Vehicle.cliente_id == Customer.id).filter(
            or_(
                Vehicle.placa.ilike(f'%{q}%'),
                Vehicle.marca.ilike(f'%{q}%'),
                Vehicle.modelo.ilike(f'%{q}%'),
                Customer.nombre.ilike(f'%{q}%'),
                Customer.documento.ilike(f'%{q}%')
            )
        )

    vehiculos = query.order_by(Vehicle.ultima_visita.desc()).all()
    clientes = Customer.query.order_by(Customer.nombre.asc()).all()

    # Calcular métricas consolidadas para cada vehículo
    resumen_vehiculos = {}
    total_ordenes_global = 0
    total_facturado_global = 0.0

    for v in vehiculos:
        ordenes = WorkOrder.query.filter(
            or_(WorkOrder.vehicle_id == v.id, WorkOrder.placa_vehiculo == v.placa)
        ).all()
        ventas = Sale.query.filter(
            Sale.estado == 'ACTIVO',
            or_(Sale.vehicle_id == v.id, Sale.placa_vehiculo == v.placa)
        ).all()
        invertido = sum(float(s.monto_total or 0) for s in ventas)
        resumen_vehiculos[v.id] = {
            'ordenes_count': len(ordenes),
            'ventas_count': len(ventas),
            'total_invertido': invertido
        }
        total_ordenes_global += len(ordenes)
        total_facturado_global += invertido

    return render_template(
        'vehiculos/index.html',
        vehiculos=vehiculos,
        resumen_vehiculos=resumen_vehiculos,
        clientes=clientes,
        total_vehiculos=len(vehiculos),
        total_ordenes_global=total_ordenes_global,
        total_facturado_global=total_facturado_global,
        q=q,
        tipo_filtro=tipo_filtro
    )


@vehiculos_bp.route('/nuevo', methods=['POST'])
@login_required
def crear():
    placa = (request.form.get('placa') or '').strip().upper()
    marca = (request.form.get('marca') or '').strip()
    modelo = (request.form.get('modelo') or '').strip()
    anio = (request.form.get('anio') or '').strip()
    color = (request.form.get('color') or '').strip()
    tipo = (request.form.get('tipo') or 'AUTOMOVIL').strip().upper()
    cliente_id = request.form.get('cliente_id', type=int) or None
    observaciones = (request.form.get('observaciones') or '').strip()

    if not placa:
        flash('La placa del vehículo es obligatoria.', 'danger')
        return redirect(url_for('vehiculos_bp.index'))

    try:
        v = sincronizar_vehiculo(
            placa=placa,
            marca=marca,
            modelo=modelo,
            anio=anio,
            color=color,
            tipo=tipo,
            cliente_id=cliente_id,
            observaciones=observaciones
        )
        db.session.commit()
        flash(f'Vehículo [{v.placa}] guardado y vinculado exitosamente.', 'success')
        return redirect(url_for('vehiculos_bp.historial', id=v.id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al registrar el vehículo: {str(e)}', 'danger')
        return redirect(url_for('vehiculos_bp.index'))


@vehiculos_bp.route('/<int:id>', methods=['GET'])
@vehiculos_bp.route('/<int:id>/historial', methods=['GET'])
@login_required
def historial(id):
    vehiculo = Vehicle.query.get_or_404(id)

    # Todas las Hojas de Trabajo asociadas por vehicle_id o placa
    ordenes = WorkOrder.query.filter(
        or_(WorkOrder.vehicle_id == vehiculo.id, WorkOrder.placa_vehiculo == vehiculo.placa)
    ).order_by(WorkOrder.fecha_creacion.desc()).all()

    # Todas las Ventas / Facturas POS asociadas por vehicle_id o placa
    ventas = Sale.query.filter(
        or_(Sale.vehicle_id == vehiculo.id, Sale.placa_vehiculo == vehiculo.placa)
    ).order_by(Sale.fecha_venta.desc()).all()

    total_invertido = sum(float(v.monto_total or 0) for v in ventas if (v.estado or 'ACTIVO') == 'ACTIVO')

    # Consolidar historial cronológico de repuestos/accesorios e instalaciones realizadas al vehículo
    repuestos_instalados = []
    servicios_realizados = []
    for venta in ventas:
        if (venta.estado or 'ACTIVO') != 'ACTIVO':
            continue
        for det in venta.detalles:
            if det.tipo_item == 'SERVICIO' or det.service_id:
                servicios_realizados.append({
                    'fecha': venta.fecha_venta,
                    'sale_id': venta.id,
                    'concepto': det.nombre_manual or (det.servicio.nombre if det.servicio else 'Servicio de Instalación'),
                    'tecnico': det.instalador.nombre if det.instalador else (venta.instalador.nombre if venta.instalador else 'Taller POWER LED'),
                    'asesor': venta.asesor.nombre if venta.asesor else venta.vendedor.nombre,
                    'cantidad': det.cantidad_vendida,
                    'valor': float(det.precio_venta_final or 0) * int(det.cantidad_vendida or 1)
                })
            else:
                repuestos_instalados.append({
                    'fecha': venta.fecha_venta,
                    'sale_id': venta.id,
                    'producto': det.nombre_manual or (det.producto.nombre if det.producto else 'Accesorio'),
                    'sku': det.producto.codigo_barras or det.producto.sku if det.producto else 'MANUAL',
                    'asesor': venta.asesor.nombre if venta.asesor else venta.vendedor.nombre,
                    'cantidad': det.cantidad_vendida,
                    'valor': float(det.precio_venta_final or 0) * int(det.cantidad_vendida or 1)
                })

    clientes = Customer.query.order_by(Customer.nombre.asc()).all()

    return render_template(
        'vehiculos/detalle.html',
        vehiculo=vehiculo,
        ordenes=ordenes,
        ventas=ventas,
        repuestos_instalados=repuestos_instalados,
        servicios_realizados=servicios_realizados,
        total_invertido=total_invertido,
        clientes=clientes
    )


@vehiculos_bp.route('/placa/<string:placa>', methods=['GET'])
@login_required
def ver_por_placa(placa):
    placa_clean = (placa or '').strip().upper()
    vehiculo = Vehicle.query.filter_by(placa=placa_clean).first()
    if not vehiculo:
        vehiculo = sincronizar_vehiculo(placa=placa_clean)
        db.session.commit()
    return redirect(url_for('vehiculos_bp.historial', id=vehiculo.id))


@vehiculos_bp.route('/<int:id>/editar', methods=['POST'])
@login_required
def editar(id):
    vehiculo = Vehicle.query.get_or_404(id)
    vehiculo.marca = (request.form.get('marca') or '').strip() or None
    vehiculo.modelo = (request.form.get('modelo') or '').strip() or None
    vehiculo.anio = (request.form.get('anio') or '').strip() or None
    vehiculo.color = (request.form.get('color') or '').strip() or None
    vehiculo.tipo = (request.form.get('tipo') or 'AUTOMOVIL').strip().upper()
    vehiculo.cliente_id = request.form.get('cliente_id', type=int) or None
    vehiculo.observaciones = (request.form.get('observaciones') or '').strip() or None

    try:
        db.session.commit()
        flash(f'Ficha técnica del vehículo [{vehiculo.placa}] actualizada.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar vehículo: {str(e)}', 'danger')

    return redirect(url_for('vehiculos_bp.historial', id=vehiculo.id))


@vehiculos_bp.route('/api/buscar/<string:placa>', methods=['GET'])
@login_required
def api_buscar_por_placa(placa):
    """
    Endpoint AJAX para autocompletar datos del vehículo y su propietario en:
    - Hojas de Trabajo (/hojas-trabajo)
    - Caja Registradora POS (/sales/caja_visual)
    """
    placa_clean = (placa or '').strip().upper()
    if not placa_clean:
        return jsonify({'found': False})

    vehiculo = Vehicle.query.filter_by(placa=placa_clean).first()
    if not vehiculo:
        # Buscar en órdenes previas o clientes por si aún no se había sincronizado
        orden_previa = WorkOrder.query.filter_by(placa_vehiculo=placa_clean).order_by(WorkOrder.id.desc()).first()
        cliente_previo = Customer.query.filter_by(placa_frecuente=placa_clean).first()
        if not orden_previa and not cliente_previo:
            return jsonify({'found': False, 'placa': placa_clean})

        vehiculo = sincronizar_vehiculo(
            placa=placa_clean,
            modelo=orden_previa.modelo_vehiculo if orden_previa else None,
            cliente_id=orden_previa.cliente_id if orden_previa else (cliente_previo.id if cliente_previo else None)
        )
        db.session.commit()

    propietario = vehiculo.propietario
    ordenes_count = WorkOrder.query.filter(
        or_(WorkOrder.vehicle_id == vehiculo.id, WorkOrder.placa_vehiculo == vehiculo.placa)
    ).count()
    ventas_count = Sale.query.filter(
        or_(Sale.vehicle_id == vehiculo.id, Sale.placa_vehiculo == vehiculo.placa)
    ).count()

    return jsonify({
        'found': True,
        'id': vehiculo.id,
        'placa': vehiculo.placa,
        'marca': vehiculo.marca or '',
        'modelo': vehiculo.modelo or '',
        'descripcion_completa': vehiculo.descripcion_completa,
        'anio': vehiculo.anio or '',
        'color': vehiculo.color or '',
        'tipo': vehiculo.tipo or 'AUTOMOVIL',
        'cliente_id': vehiculo.cliente_id,
        'cliente_nombre': propietario.nombre if propietario else '',
        'cliente_documento': propietario.documento if propietario else '',
        'cliente_telefono': propietario.telefono if propietario else '',
        'lista_precio_default': propietario.lista_precio_default if propietario else 'cliente_final',
        'ordenes_count': ordenes_count,
        'ventas_count': ventas_count,
        'historial_url': url_for('vehiculos_bp.historial', id=vehiculo.id)
    })
