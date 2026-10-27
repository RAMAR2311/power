import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

from flask import Flask, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect

# Importar la instancia de db desde models
from models import db, User

def create_app():
    app = Flask(__name__)
    
    # Configuración mediante variables de entorno
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-super-secreta')
    app.config['VALOR_MENSUALIDAD_SERVIDOR'] = os.environ.get('VALOR_MENSUALIDAD_SERVIDOR', '80.000')
    app.config['PIN_CONFIRMACION_SERVIDOR'] = os.environ.get('PIN_CONFIRMACION_SERVIDOR', '9876')
    
    # Detección inteligente de Base de Datos (PostgreSQL con Fallback automático a SQLite local)
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', 5432))
            sock.close()
            if result == 0:
                db_url = 'postgresql://postgres:admin123@localhost:5432/mariposacel'
            else:
                instance_path = os.path.join(app.root_path, 'instance')
                os.makedirs(instance_path, exist_ok=True)
                db_url = f"sqlite:///{os.path.join(instance_path, 'crm_inventory.db')}"
        except Exception:
            instance_path = os.path.join(app.root_path, 'instance')
            os.makedirs(instance_path, exist_ok=True)
            db_url = f"sqlite:///{os.path.join(instance_path, 'crm_inventory.db')}"

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')


    # Inicializar Extensiones
    db.init_app(app)
    Migrate(app, db)
    csrf = CSRFProtect(app)
    
    login_manager = LoginManager()
    login_manager.login_view = 'auth_bp.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Importar y Registrar Blueprints
    from routes.sales import sales_bp
    from routes.inventory import inventory_bp
    from routes.auth import auth_bp
    from routes.arqueo import arqueo_bp
    from routes.gastos import gastos_bp
    from routes.servidor import servidor_bp
    
    app.register_blueprint(sales_bp, url_prefix='/sales')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(arqueo_bp, url_prefix='/arqueo')
    app.register_blueprint(gastos_bp, url_prefix='/gastos')
    app.register_blueprint(servidor_bp, url_prefix='/servidor')
    
    # Registro de Blueprint Admin
    from routes.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Registro de Blueprint Proveedores
    from routes.proveedores import providers_bp
    app.register_blueprint(providers_bp, url_prefix='/proveedores')

    # Registro de Blueprints Bodega, Clientes y Maneos
    from routes.bodega import bodega_bp
    from routes.clientes import clientes_bp
    from routes.maneos import maneos_bp
    app.register_blueprint(bodega_bp, url_prefix='/bodega')
    app.register_blueprint(clientes_bp, url_prefix='/clientes')
    app.register_blueprint(maneos_bp, url_prefix='/maneos')

    # Registro de Nuevos Módulos Automotrices POWER LED (Hojas de Trabajo, Instalaciones, Vehículos e Ingresos de Mercancía)
    from routes.hojas_trabajo import hojas_trabajo_bp
    from routes.instalaciones import instalaciones_bp
    from routes.vehiculos import vehiculos_bp
    from routes.ingresos import ingresos_bp
    app.register_blueprint(hojas_trabajo_bp, url_prefix='/hojas-trabajo')
    app.register_blueprint(instalaciones_bp, url_prefix='/instalaciones')
    app.register_blueprint(vehiculos_bp, url_prefix='/vehiculos')
    app.register_blueprint(ingresos_bp, url_prefix='/ingresos')

    # Registro de Blueprint Aprobaciones de Precios en Tiempo Real
    from routes.aprobaciones import aprobaciones_bp
    app.register_blueprint(aprobaciones_bp, url_prefix='/api')
    csrf.exempt(aprobaciones_bp)

    # Context Processor Global: Estado de Pago del Servidor
    @app.context_processor
    def inject_pago_servidor():
        import urllib.parse
        from datetime import datetime
        from itsdangerous import URLSafeTimedSerializer
        from models import ServerPayment, obtener_hora_bogota

        MESES_ESPANOL = [
            'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
        ]

        try:
            ahora = obtener_hora_bogota()
            anio_actual = ahora.year
            mes_actual = ahora.month
            dia_actual = ahora.day

            monto = app.config.get('VALOR_MENSUALIDAD_SERVIDOR', '80.000')
            dia_vencimiento = 15
            dia_preventivo = 8

            if anio_actual < 2026 or (anio_actual == 2026 and mes_actual < 11):
                mes_cobro = 11
                anio_cobro = 2026
                pago_existente = ServerPayment.query.filter_by(
                    anio=anio_cobro,
                    mes=mes_cobro,
                    estado='pagado'
                ).first()
                estado = 'pagado' if pago_existente else 'al_dia'
                dias_restantes = (datetime(2026, 11, 15) - datetime(anio_actual, mes_actual, dia_actual)).days
                dias_gabela = 0
            else:
                pago_mes_actual = ServerPayment.query.filter_by(
                    anio=anio_actual,
                    mes=mes_actual,
                    estado='pagado'
                ).first()

                if pago_mes_actual and dia_actual > dia_vencimiento:
                    if mes_actual == 12:
                        mes_cobro = 1
                        anio_cobro = anio_actual + 1
                    else:
                        mes_cobro = mes_actual + 1
                        anio_cobro = anio_actual

                    pago_existente = ServerPayment.query.filter_by(
                        anio=anio_cobro,
                        mes=mes_cobro,
                        estado='pagado'
                    ).first()
                    estado = 'pagado' if pago_existente else 'al_dia'
                    dias_restantes = 0
                    dias_gabela = 0
                else:
                    mes_cobro = mes_actual
                    anio_cobro = anio_actual
                    pago_existente = pago_mes_actual

                    if pago_existente:
                        estado = 'pagado'
                        dias_restantes = 0
                        dias_gabela = 0
                    elif 1 <= dia_actual < dia_preventivo:
                        estado = 'al_dia'
                        dias_restantes = dia_vencimiento - dia_actual
                        dias_gabela = 0
                    elif dia_preventivo <= dia_actual < dia_vencimiento:
                        estado = 'preventivo'
                        dias_restantes = dia_vencimiento - dia_actual
                        dias_gabela = 0
                    elif dia_actual == dia_vencimiento:
                        estado = 'hoy'
                        dias_restantes = 0
                        dias_gabela = 0
                    elif dia_vencimiento < dia_actual <= (dia_vencimiento + 5):
                        estado = 'gabela'
                        dias_restantes = 0
                        dias_gabela = (dia_vencimiento + 5) - dia_actual + 1
                    else:
                        estado = 'vencido'
                        dias_restantes = 0
                        dias_gabela = 0

            mes_nombre = MESES_ESPANOL[mes_cobro - 1]

            serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
            token = serializer.dumps({'anio': anio_cobro, 'mes': mes_cobro}, salt='server-payment-salt')

            try:
                url_confirmacion = url_for('servidor_bp.confirmar_pago', token=token, _external=True)
            except Exception:
                base_url = request.host_url.rstrip('/') if request else 'http://localhost:5000'
                url_confirmacion = f"{base_url}/servidor/confirmar-pago?token={token}"

            mensaje_wa = (
                f"Hola, adjunto el comprobante de pago de la mensualidad del servidor Zenic (${monto} COP) para {mes_nombre} {anio_cobro}.\n\n"
                f"Para confirmar mi pago en el sistema con 1 solo clic, toca aquí:\n"
                f"{url_confirmacion}"
            )

            whatsapp_url = f"https://wa.me/573115643557?text={urllib.parse.quote(mensaje_wa)}"

            pago_servidor = {
                'estado': estado,
                'mes_nombre': mes_nombre,
                'anio': anio_cobro,
                'dia_vencimiento': dia_vencimiento,
                'monto': monto,
                'dias_restantes': dias_restantes,
                'dias_gabela': dias_gabela,
                'whatsapp_url': whatsapp_url,
                'nu_llave': '@QEI910',
                'nequi_num': '3505422186'
            }
        except Exception:
            ahora_fallback = obtener_hora_bogota()
            dia_venc_fallback = 15 if (ahora_fallback.year > 2026 or (ahora_fallback.year == 2026 and ahora_fallback.month >= 10)) else 30
            pago_servidor = {
                'estado': 'al_dia',
                'mes_nombre': 'Actual',
                'anio': ahora_fallback.year,
                'dia_vencimiento': dia_venc_fallback,
                'monto': '80.000',
                'dias_restantes': 0,
                'dias_gabela': 0,
                'whatsapp_url': '#',
                'nu_llave': '@QEI910',
                'nequi_num': '3505422186'
            }

        return dict(pago_servidor=pago_servidor)


    @app.template_filter('cop')
    def cop_filter(value):
        if value is None:
            return "0"
        try:
            return "{:,.0f}".format(float(value))
        except (ValueError, TypeError):
            return value

    @app.route('/')
    def index():
        if not current_user.is_authenticated:
            return redirect(url_for('auth_bp.login'))
        if current_user.rol == 'admin':
            return redirect(url_for('admin_bp.dashboard'))
        return redirect(url_for('sales_bp.caja_visual'))

    @app.route('/pos')
    def pos_alias():
        if not current_user.is_authenticated:
            return redirect(url_for('auth_bp.login'))
        hoja_id = request.args.get('hoja_id', type=int)
        if hoja_id:
            return redirect(url_for('sales_bp.caja_visual', hoja_id=hoja_id))
        return redirect(url_for('sales_bp.caja_visual'))

    @app.route('/sw.js')
    def sw():
        from flask import send_from_directory, make_response
        resp = make_response(send_from_directory('static', 'sw.js', mimetype='application/javascript'))
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp

    @app.route('/manifest.json')
    def manifest():
        from flask import send_from_directory, make_response
        resp = make_response(send_from_directory('static', 'manifest.json', mimetype='application/manifest+json'))
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp

    @app.route('/offline')
    def offline():
        from flask import render_template
        return render_template('offline.html')

    @app.route('/favicon.ico')
    def favicon():
        from flask import send_from_directory, make_response
        resp = make_response(send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon'))
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp

    @app.route('/apple-touch-icon.png')
    @app.route('/apple-touch-icon-precomposed.png')
    def apple_touch_icon():
        from flask import send_from_directory, make_response
        resp = make_response(send_from_directory(os.path.join('static', 'img', 'icons'), 'apple-touch-icon.png', mimetype='image/png'))
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        return resp

    return app

if __name__ == '__main__':
    app = create_app()
    
    # ---------------- LÓGICA DE INICIALIZACIÓN ----------------
    with app.app_context():
        from models import db, User
        from werkzeug.security import generate_password_hash
        
        # Ejecutar migración automática no destructiva (v2 POWER LED)
        try:
            from scripts.migrate_v2 import run_migration
            run_migration(app)
        except Exception as mig_err:
            print(f"[WARN] Nota al ejecutar migrate_v2: {mig_err}")
            db.create_all()
        
        # Crear la carpeta de imágenes si no existe
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        if not User.query.filter(User.email.in_(['admin@powerled.com', 'admin@maripocell.com', 'admin@mariposacel.com'])).first():
            master_admin = User(
                nombre='Administrador Principal',
                email='admin@powerled.com',
                password_hash=generate_password_hash('Admin123'),
                rol='admin'
            )
            db.session.add(master_admin)
            db.session.commit()
            print("[INFO] Usuario maestro 'admin@powerled.com' fue creado automaticamente.")
            
    # Permite acceder desde la red local / celular (host='0.0.0.0')
    app.run(host='0.0.0.0', port=5000, debug=True)
