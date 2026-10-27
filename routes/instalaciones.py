from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from models import db, Installer, InstallationService, InstallationJob, Sale, get_bogota_time
from decorators import admin_required

instalaciones_bp = Blueprint('instalaciones_bp', __name__)

@instalaciones_bp.route('/', methods=['GET'])
@login_required
def index():
    hoy = get_bogota_time().strftime('%Y-%m-%d')
    fecha_inicio = request.args.get('fecha_inicio', hoy)
    fecha_fin = request.args.get('fecha_fin', hoy)
    installer_id = request.args.get('installer_id', type=int)
    estado_liq = request.args.get('estado_liq', 'todos')

    instaladores = Installer.query.order_by(Installer.nombre).all()
    servicios = InstallationService.query.filter_by(activo=True).order_by(InstallationService.nombre).all()

    query_jobs = InstallationJob.query
    if fecha_inicio:
        try:
            dt_ini = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            query_jobs = query_jobs.filter(InstallationJob.fecha >= dt_ini)
        except ValueError:
            pass
    if fecha_fin:
        try:
            dt_fin = datetime.strptime(fecha_fin, '%Y-%m-%d') + timedelta(days=1)
            query_jobs = query_jobs.filter(InstallationJob.fecha < dt_fin)
        except ValueError:
            pass

    if installer_id:
        query_jobs = query_jobs.filter(InstallationJob.installer_id == installer_id)
    if estado_liq == 'pendientes':
        query_jobs = query_jobs.filter(InstallationJob.liquidado.is_(False))
    elif estado_liq == 'liquidados':
        query_jobs = query_jobs.filter(InstallationJob.liquidado.is_(True))

    jobs = query_jobs.order_by(InstallationJob.fecha.desc()).all()

    total_facturado_servicios = sum(float(j.precio_cobrado or 0) for j in jobs)
    total_mano_obra = sum(float(j.costo_instalador or 0) for j in jobs)
    total_pendiente_pagar = sum(float(j.costo_instalador or 0) for j in jobs if not j.liquidado)
    vehiculos_atendidos = len(set(j.sale_id for j in jobs))

    return render_template(
        'instalaciones/index.html',
        instaladores=instaladores,
        servicios=servicios,
        jobs=jobs,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        installer_id=installer_id,
        estado_liq=estado_liq,
        total_facturado_servicios=total_facturado_servicios,
        total_mano_obra=total_mano_obra,
        total_pendiente_pagar=total_pendiente_pagar,
        vehiculos_atendidos=vehiculos_atendidos
    )

@instalaciones_bp.route('/servicios/crear', methods=['POST'])
@login_required
def crear_servicio():
    nombre = (request.form.get('nombre') or '').strip()
    precio_estandar = float(request.form.get('precio_estandar') or 0.0)
    costo_instalador = float(request.form.get('costo_instalador') or 0.0)

    if not nombre:
        flash('El nombre del servicio es obligatorio.', 'warning')
        return redirect(url_for('instalaciones_bp.index'))

    srv = InstallationService(
        nombre=nombre,
        precio_estandar=precio_estandar,
        costo_instalador=costo_instalador,
        activo=True
    )
    db.session.add(srv)
    db.session.commit()
    flash(f'Servicio de instalación "{nombre}" creado exitosamente.', 'success')
    return redirect(url_for('instalaciones_bp.index'))

@instalaciones_bp.route('/servicios/<int:id>/editar', methods=['POST'])
@login_required
def editar_servicio(id):
    srv = InstallationService.query.get_or_404(id)
    srv.nombre = (request.form.get('nombre') or srv.nombre).strip()
    srv.precio_estandar = float(request.form.get('precio_estandar') or 0.0)
    srv.costo_instalador = float(request.form.get('costo_instalador') or 0.0)
    db.session.commit()
    flash(f'Servicio "{srv.nombre}" actualizado.', 'success')
    return redirect(url_for('instalaciones_bp.index'))

@instalaciones_bp.route('/servicios/<int:id>/eliminar', methods=['POST'])
@login_required
def eliminar_servicio(id):
    srv = InstallationService.query.get_or_404(id)
    srv.activo = False
    db.session.commit()
    flash(f'Servicio "{srv.nombre}" desactivado del catálogo.', 'info')
    return redirect(url_for('instalaciones_bp.index'))

@instalaciones_bp.route('/instaladores/crear', methods=['POST'])
@login_required
def crear_instalador():
    nombre = (request.form.get('nombre') or '').strip()
    documento = (request.form.get('documento') or '').strip() or None
    telefono = (request.form.get('telefono') or '').strip() or None

    if not nombre:
        flash('El nombre del técnico instalador es obligatorio.', 'warning')
        return redirect(url_for('instalaciones_bp.index'))

    if documento and Installer.query.filter_by(documento=documento).first():
        flash(f'Ya existe un instalador con el documento "{documento}".', 'warning')
        return redirect(url_for('instalaciones_bp.index'))

    ins = Installer(nombre=nombre, documento=documento, telefono=telefono, activo=True)
    db.session.add(ins)
    db.session.commit()
    flash(f'Instalador "{nombre}" registrado exitosamente.', 'success')
    return redirect(url_for('instalaciones_bp.index'))

@instalaciones_bp.route('/instaladores/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_instalador(id):
    ins = Installer.query.get_or_404(id)
    ins.activo = not ins.activo
    db.session.commit()
    estado_str = 'Activo' if ins.activo else 'Inactivo'
    flash(f'Estado del técnico "{ins.nombre}" cambiado a {estado_str}.', 'info')
    return redirect(url_for('instalaciones_bp.index'))

@instalaciones_bp.route('/liquidar', methods=['POST'])
@login_required
def liquidar_trabajos():
    job_ids = request.form.getlist('job_ids[]')
    installer_id = request.form.get('installer_id', type=int)
    fecha_inicio = request.form.get('fecha_inicio', '')
    fecha_fin = request.form.get('fecha_fin', '')

    if job_ids:
        ids_int = [int(jid) for jid in job_ids if str(jid).isdigit()]
        InstallationJob.query.filter(InstallationJob.id.in_(ids_int)).update({'liquidado': True}, synchronize_session=False)
        db.session.commit()
        flash(f'{len(ids_int)} servicio(s) marcados como liquidados al instalador.', 'success')
    elif installer_id:
        q = InstallationJob.query.filter_by(installer_id=installer_id, liquidado=False)
        if fecha_inicio:
            q = q.filter(InstallationJob.fecha >= datetime.strptime(fecha_inicio, '%Y-%m-%d'))
        if fecha_fin:
            q = q.filter(InstallationJob.fecha < datetime.strptime(fecha_fin, '%Y-%m-%d') + timedelta(days=1))
        count = q.update({'liquidado': True}, synchronize_session=False)
        db.session.commit()
        flash(f'Se liquidaron {count} servicio(s) pendientes del técnico.', 'success')
    else:
        flash('Selecciona al menos un trabajo o un técnico para liquidar.', 'warning')

    return redirect(url_for('instalaciones_bp.index', installer_id=installer_id, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin))
