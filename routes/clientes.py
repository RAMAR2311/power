import os
import uuid
import time
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Customer, CustomerCreditPayment, Cliente, Maneo, Sale, get_bogota_time

clientes_bp = Blueprint('clientes_bp', __name__)

@clientes_bp.route('/', methods=['GET'])
@login_required
def index():
    q = request.args.get('q', '').strip()
    filtro = request.args.get('filtro', 'todos').strip()

    query = Customer.query
    if q:
        from sqlalchemy import or_
        query = query.filter(
            or_(
                Customer.nombre.ilike(f'%{q}%'),
                Customer.documento.ilike(f'%{q}%'),
                Customer.telefono.ilike(f'%{q}%'),
                Customer.placa_frecuente.ilike(f'%{q}%')
            )
        )

    todos = Customer.query.order_by(Customer.nombre.asc()).all()
    total_clientes = len(todos)
    total_cartera = sum(c.saldo_pendiente for c in todos)
    clientes_con_deuda_count = sum(1 for c in todos if c.saldo_pendiente > 0)

    lista_clientes = query.order_by(Customer.nombre.asc()).all()
    if filtro == 'con_deuda':
        lista_clientes = [c for c in lista_clientes if c.saldo_pendiente > 0]
    elif filtro == 'al_dia':
        lista_clientes = [c for c in lista_clientes if c.saldo_pendiente <= 0]

    return render_template(
        'clientes/index.html',
        clientes=lista_clientes,
        total_clientes=total_clientes,
        total_saldo_calle=total_cartera,
        clientes_con_deuda_count=clientes_con_deuda_count,
        q=q,
        filtro=filtro
    )

@clientes_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    if request.method == 'POST':
        nombre = (request.form.get('nombre') or '').strip()
        documento = (request.form.get('documento') or request.form.get('documento_o_nit') or '').strip() or None
        telefono = (request.form.get('telefono') or '').strip()
        direccion = (request.form.get('direccion') or '').strip()
        email = (request.form.get('email') or '').strip()
        placa_frecuente = (request.form.get('placa_frecuente') or '').strip().upper()
        lista_precio_default = (request.form.get('lista_precio_default') or 'cliente_final').strip()
        limite_credito = float(request.form.get('limite_credito') or 0.0)

        if not nombre:
            flash('El nombre del cliente es obligatorio.', 'danger')
            return render_template('clientes/form.html', cliente=None)

        if documento and Customer.query.filter_by(documento=documento).first():
            flash(f'Ya existe un cliente registrado con el documento/NIT "{documento}".', 'warning')
            return render_template('clientes/form.html', cliente=None)

        nuevo_c = Customer(
            nombre=nombre,
            documento=documento,
            telefono=telefono,
            direccion=direccion,
            email=email,
            placa_frecuente=placa_frecuente,
            lista_precio_default=lista_precio_default,
            limite_credito=limite_credito
        )
        try:
            db.session.add(nuevo_c)
            db.session.flush()
            if placa_frecuente:
                from routes.vehiculos import sincronizar_vehiculo
                sincronizar_vehiculo(placa=placa_frecuente, cliente_id=nuevo_c.id)
            db.session.commit()
            flash(f'Cliente "{nombre}" registrado exitosamente.', 'success')
            return redirect(url_for('clientes_bp.estado_cuenta', id=nuevo_c.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar el cliente: {str(e)}', 'danger')

    return render_template('clientes/form.html', cliente=None)

@clientes_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    cliente = Customer.query.get_or_404(id)
    if request.method == 'POST':
        nombre = (request.form.get('nombre') or '').strip()
        documento = (request.form.get('documento') or request.form.get('documento_o_nit') or '').strip() or None
        telefono = (request.form.get('telefono') or '').strip()
        direccion = (request.form.get('direccion') or '').strip()
        email = (request.form.get('email') or '').strip()
        placa_frecuente = (request.form.get('placa_frecuente') or '').strip().upper()
        lista_precio_default = (request.form.get('lista_precio_default') or 'cliente_final').strip()
        limite_credito = float(request.form.get('limite_credito') or 0.0)

        if not nombre:
            flash('El nombre del cliente es obligatorio.', 'danger')
            return render_template('clientes/form.html', cliente=cliente)

        if documento and documento != cliente.documento:
            if Customer.query.filter_by(documento=documento).first():
                flash(f'Ya existe otro cliente con el documento "{documento}".', 'warning')
                return render_template('clientes/form.html', cliente=cliente)

        cliente.nombre = nombre
        cliente.documento = documento
        cliente.telefono = telefono
        cliente.direccion = direccion
        cliente.email = email
        cliente.placa_frecuente = placa_frecuente
        cliente.lista_precio_default = lista_precio_default
        cliente.limite_credito = limite_credito

        try:
            if placa_frecuente:
                from routes.vehiculos import sincronizar_vehiculo
                sincronizar_vehiculo(placa=placa_frecuente, cliente_id=cliente.id)
            db.session.commit()
            flash(f'Datos de "{nombre}" actualizados correctamente.', 'success')
            return redirect(url_for('clientes_bp.estado_cuenta', id=cliente.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el cliente: {str(e)}', 'danger')

    return render_template('clientes/form.html', cliente=cliente)

@clientes_bp.route('/<int:id>/estado_cuenta', methods=['GET'])
@clientes_bp.route('/<int:id>/estado-cuenta', methods=['GET'])
@login_required
def estado_cuenta(id):
    cliente = Customer.query.get_or_404(id)
    ventas_credito = [
        v for v in sorted(cliente.ventas, key=lambda x: x.fecha_venta or get_bogota_time(), reverse=True)
        if (v.estado or 'ACTIVO') == 'ACTIVO' and (
            (v.metodo_pago or '').upper() == 'CREDITO' or
            any((p.metodo_pago or '').upper() == 'CREDITO' for p in v.pagos)
        )
    ]
    abonos = sorted([a for a in cliente.abonos if (a.estado or 'ACTIVO') == 'ACTIVO'], key=lambda x: x.fecha or get_bogota_time(), reverse=True)

    return render_template(
        'clientes/estado_cuenta.html',
        cliente=cliente,
        ventas_credito=ventas_credito,
        abonos=abonos,
        saldo_pendiente=cliente.saldo_pendiente,
        total_creditos=cliente.total_creditos,
        total_abonos=cliente.total_abonos
    )

@clientes_bp.route('/<int:id>/abonar', methods=['POST'])
@login_required
def registrar_abono(id):
    cliente = Customer.query.get_or_404(id)
    monto_raw = (request.form.get('monto') or '0').replace('.', '').replace(',', '').strip()
    metodo_pago = (request.form.get('metodo_pago') or 'EFECTIVO').strip().upper()
    nota = (request.form.get('nota') or '').strip()

    try:
        monto = float(monto_raw)
    except ValueError:
        monto = 0.0

    if monto <= 0:
        flash('El monto del abono debe ser mayor a $0.', 'danger')
        return redirect(url_for('clientes_bp.estado_cuenta', id=cliente.id))

    comprobante_url = None
    if 'comprobante' in request.files:
        file = request.files['comprobante']
        if file and file.filename != '':
            sec_name = secure_filename(file.filename)
            ext = sec_name.rsplit('.', 1)[-1].lower() if '.' in sec_name else 'jpg'
            filename = f"abono_cli_{cliente.id}_{uuid.uuid4().hex[:6]}_{int(time.time())}.{ext}"
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'abonos')
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, filename))
            comprobante_url = f"uploads/abonos/{filename}"

    abono = CustomerCreditPayment(
        cliente_id=cliente.id,
        monto=monto,
        fecha=get_bogota_time(),
        metodo_pago=metodo_pago,
        comprobante_url=comprobante_url,
        usuario_id=current_user.id,
        estado='ACTIVO',
        nota=nota
    )
    try:
        db.session.add(abono)
        db.session.commit()
        flash(f'Abono por ${monto:,.0f} COP registrado exitosamente para {cliente.nombre}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al registrar el abono: {str(e)}', 'danger')

    return redirect(url_for('clientes_bp.estado_cuenta', id=cliente.id))

@clientes_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar(id):
    cliente = Customer.query.get_or_404(id)
    if cliente.saldo_pendiente > 0:
        flash(f'No se puede eliminar a "{cliente.nombre}" porque tiene un saldo pendiente de ${cliente.saldo_pendiente:,.0f}.', 'danger')
        return redirect(url_for('clientes_bp.index'))

    try:
        db.session.delete(cliente)
        db.session.commit()
        flash('Cliente eliminado del directorio.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar cliente: {str(e)}', 'danger')
    return redirect(url_for('clientes_bp.index'))

@clientes_bp.route('/api/crear_rapido', methods=['POST'])
@login_required
def api_crear_rapido():
    """Endpoint AJAX compatible con Maneos y Caja POS."""
    data = request.get_json(silent=True) or request.form
    nombre = (data.get('nombre') or '').strip()
    documento = (data.get('documento') or '').strip() or None
    telefono = (data.get('telefono') or '').strip()
    placa = (data.get('placa_frecuente') or data.get('placa') or '').strip().upper()
    local_numero = (data.get('local_numero') or '').strip()

    if not nombre:
        return jsonify({'success': False, 'message': 'El nombre es obligatorio.'}), 400

    # Crear también en Customer y Cliente legacy si aplica
    cust = None
    if documento:
        cust = Customer.query.filter_by(documento=documento).first()
    if not cust:
        cust = Customer.query.filter(Customer.nombre.ilike(nombre)).first()
    if not cust:
        cust = Customer(
            nombre=nombre,
            documento=documento,
            telefono=telefono,
            placa_frecuente=placa,
            lista_precio_default='cliente_final'
        )
        db.session.add(cust)

    cli_legacy = Cliente.query.filter(Cliente.nombre_o_razon_social.ilike(nombre)).first()
    if not cli_legacy:
        cli_legacy = Cliente(
            nombre_o_razon_social=nombre,
            documento_o_nit=documento,
            local_numero=local_numero,
            telefono=telefono,
            creado_por_id=current_user.id
        )
        db.session.add(cli_legacy)

    db.session.commit()
    return jsonify({
        'success': True,
        'customer_id': cust.id,
        'cliente': {
            'id': cli_legacy.id,
            'customer_id': cust.id,
            'nombre': cust.nombre,
            'documento': cust.documento or '',
            'telefono': cust.telefono or '',
            'placa': cust.placa_frecuente or '',
            'lista_precio': cust.lista_precio_default,
            'local': local_numero,
            'saldo': cust.saldo_pendiente
        }
    })
