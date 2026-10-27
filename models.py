from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import pytz

db = SQLAlchemy()

BOGOTA_TZ = pytz.timezone('America/Bogota')

def obtener_hora_bogota():
    """Inyecta el uso de huso horario en Colombia (America/Bogota)."""
    return datetime.now(BOGOTA_TZ).replace(tzinfo=None)

def get_bogota_time():
    """Alias compatible con la especificación POWER LED."""
    return obtener_hora_bogota()

# --- USUARIOS ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    telefono = db.Column(db.String(20))
    password_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(50), nullable=False, default='vendedor')
    
    ventas = db.relationship('Sale', foreign_keys='Sale.vendedor_id', backref='vendedor', lazy=True)
    ajustes_stock = db.relationship('StockAdjustment', backref='admin', lazy=True)
    arqueos = db.relationship('ArqueoCaja', backref='cajero', lazy=True)

    def __init__(self, nombre=None, email=None, telefono=None, password_hash=None, rol=None, **kwargs):
        if nombre is not None: kwargs['nombre'] = nombre
        if email is not None: kwargs['email'] = email
        if telefono is not None: kwargs['telefono'] = telefono
        if password_hash is not None: kwargs['password_hash'] = password_hash
        if rol is not None: kwargs['rol'] = rol
        super(User, self).__init__(**kwargs)

# --- CATEGORÍAS Y SUBCATEGORÍAS ---
class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    stock_minimo_alerta = db.Column(db.Integer, default=5)
    subcategorias = db.relationship('Subcategory', backref='categoria', lazy=True, cascade="all, delete-orphan")
    productos = db.relationship('Product', backref='categoria', lazy=True)

class Subcategory(db.Model):
    __tablename__ = 'subcategories'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    stock_minimo_alerta = db.Column(db.Integer, nullable=True)  # Si es null, hereda de Category
    productos = db.relationship('Product', backref='subcategoria', lazy=True)

# --- REFACTOR PRODUCTO (3 LISTAS DE PRECIOS Y STOCK POR UBICACIÓN) ---
class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    sku = db.Column(db.String(50), unique=True, nullable=True, index=True)
    codigo_barras = db.Column(db.String(50), unique=True, nullable=True, index=True)
    
    categoria_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    subcategory_id = db.Column(db.Integer, db.ForeignKey('subcategories.id'), nullable=True)

    # Costo y las 3 Listas de Precios Oficiales POWER LED
    costo = db.Column(db.Float, nullable=False, default=0.0)
    precio_distribuidor = db.Column(db.Float, nullable=False, default=0.0)
    precio_local = db.Column(db.Float, nullable=False, default=0.0)
    precio_final = db.Column(db.Float, nullable=False, default=0.0)

    # Inventarios separados por ubicación
    stock_tienda = db.Column(db.Integer, nullable=False, default=0)  # Disponible en mostrador / POS
    stock_bodega = db.Column(db.Integer, nullable=False, default=0)  # Almacén central
    stock_minimo = db.Column(db.Integer, nullable=False, default=5)  # Alerta individual (default 5)

    # Columnas heredadas para retrocompatibilidad con base de datos existente
    tipo_inventario = db.Column(db.String(50), nullable=False, default='tienda', server_default='tienda')
    cantidad_stock = db.Column(db.Integer, nullable=False, default=0)
    precio_costo = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    precio_minimo = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    precio_sugerido = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)

    imagen = db.Column(db.String(255), nullable=True)
    observacion = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, default=True, server_default='1', nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)
    
    detalles_venta = db.relationship('SaleDetail', backref='producto', lazy=True)
    ajustes_stock = db.relationship('StockAdjustment', backref='producto_rel', lazy=True)
    variantes = db.relationship('ProductVariant', backref='producto', lazy=True, cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        # Sincronizar SKU <-> codigo_barras
        if 'codigo_barras' in kwargs and not kwargs.get('sku'):
            kwargs['sku'] = kwargs['codigo_barras']
        elif 'sku' in kwargs and not kwargs.get('codigo_barras'):
            kwargs['codigo_barras'] = kwargs['sku']

        # Sincronizar precios nuevos y legacy
        if 'costo' in kwargs and 'precio_costo' not in kwargs:
            kwargs['precio_costo'] = kwargs['costo']
        elif 'precio_costo' in kwargs and 'costo' not in kwargs:
            kwargs['costo'] = float(kwargs['precio_costo'] or 0)

        if 'precio_final' in kwargs and 'precio_sugerido' not in kwargs:
            kwargs['precio_sugerido'] = kwargs['precio_final']
        elif 'precio_sugerido' in kwargs and 'precio_final' not in kwargs:
            kwargs['precio_final'] = float(kwargs['precio_sugerido'] or 0)

        if 'precio_distribuidor' in kwargs and 'precio_minimo' not in kwargs:
            kwargs['precio_minimo'] = kwargs['precio_distribuidor']
        elif 'precio_minimo' in kwargs and 'precio_distribuidor' not in kwargs:
            kwargs['precio_distribuidor'] = float(kwargs['precio_minimo'] or 0)

        if 'precio_local' not in kwargs:
            kwargs['precio_local'] = float(kwargs.get('precio_final') or kwargs.get('precio_sugerido') or 0)

        # Sincronizar stock_tienda / stock_bodega / cantidad_stock
        if 'stock_tienda' in kwargs and 'cantidad_stock' not in kwargs:
            kwargs['cantidad_stock'] = kwargs['stock_tienda']
        elif 'cantidad_stock' in kwargs and 'stock_tienda' not in kwargs:
            if kwargs.get('tipo_inventario') == 'bodega':
                kwargs.setdefault('stock_bodega', kwargs['cantidad_stock'])
                kwargs.setdefault('stock_tienda', 0)
            else:
                kwargs['stock_tienda'] = kwargs['cantidad_stock']

        super(Product, self).__init__(**kwargs)

    @property
    def umbral_alerta(self):
        if self.stock_minimo is not None and self.stock_minimo > 0:
            umbral = self.stock_minimo
        else:
            umbral = 5
        if self.subcategoria and self.subcategoria.stock_minimo_alerta is not None:
            umbral = self.subcategoria.stock_minimo_alerta
        elif self.categoria and self.categoria.stock_minimo_alerta is not None:
            umbral = self.categoria.stock_minimo_alerta
        return umbral

    @property
    def alerta_stock_activa(self):
        umbral = self.stock_minimo if self.stock_minimo is not None else 5
        if self.subcategoria and self.subcategoria.stock_minimo_alerta:
            umbral = self.subcategoria.stock_minimo_alerta
        elif self.categoria and self.categoria.stock_minimo_alerta:
            umbral = self.categoria.stock_minimo_alerta
        return (self.stock_tienda or 0) <= umbral

    @property
    def total_stock(self):
        if self.variantes:
            return sum(v.cantidad_stock for v in self.variantes)
        return self.stock_tienda if self.stock_tienda is not None else self.cantidad_stock

    @property
    def rango_precios(self):
        if not self.variantes:
            return None
        precios = [v.precio_final or v.precio_sugerido for v in self.variantes if (v.precio_final or v.precio_sugerido) is not None]
        if not precios:
            return None
        min_p = min(precios)
        max_p = max(precios)
        if min_p == max_p:
            return min_p
        return (min_p, max_p)

    @property
    def rango_costos(self):
        if not self.variantes:
            return None
        precios = [v.precio_costo for v in self.variantes if v.precio_costo is not None]
        if not precios:
            return None
        min_p = min(precios)
        max_p = max(precios)
        if min_p == max_p:
            return min_p
        return (min_p, max_p)

    @property
    def rango_minimos(self):
        if not self.variantes:
            return None
        precios = [v.precio_distribuidor or v.precio_minimo for v in self.variantes if (v.precio_distribuidor or v.precio_minimo) is not None]
        if not precios:
            return None
        min_p = min(precios)
        max_p = max(precios)
        if min_p == max_p:
            return min_p
        return (min_p, max_p)

    def obtener_precio_por_lista(self, lista='cliente_final'):
        lista_norm = (lista or 'cliente_final').lower().strip()
        if lista_norm in ('distribuidor', 'mayorista', 'precio_distribuidor'):
            return float(self.precio_distribuidor or self.precio_minimo or self.precio_final or 0)
        elif lista_norm in ('local', 'mostrador', 'precio_local'):
            return float(self.precio_local or self.precio_final or self.precio_sugerido or 0)
        return float(self.precio_final or self.precio_sugerido or 0)

class ProductVariant(db.Model):
    __tablename__ = 'product_variants'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    nombre_variante = db.Column(db.String(100), nullable=False)
    cantidad_stock = db.Column(db.Integer, nullable=False, default=0)
    stock_bodega = db.Column(db.Integer, nullable=False, default=0)
    
    # Precios específicos para variantes
    precio_costo = db.Column(db.Numeric(10, 2), nullable=True)
    precio_distribuidor = db.Column(db.Float, nullable=True)
    precio_local = db.Column(db.Float, nullable=True)
    precio_final = db.Column(db.Float, nullable=True)
    precio_minimo = db.Column(db.Numeric(10, 2), nullable=True)
    precio_sugerido = db.Column(db.Numeric(10, 2), nullable=True)

    def __init__(self, **kwargs):
        if 'precio_final' in kwargs and 'precio_sugerido' not in kwargs:
            kwargs['precio_sugerido'] = kwargs['precio_final']
        elif 'precio_sugerido' in kwargs and 'precio_final' not in kwargs and kwargs['precio_sugerido'] is not None:
            kwargs['precio_final'] = float(kwargs['precio_sugerido'])
        if 'precio_distribuidor' in kwargs and 'precio_minimo' not in kwargs:
            kwargs['precio_minimo'] = kwargs['precio_distribuidor']
        elif 'precio_minimo' in kwargs and 'precio_distribuidor' not in kwargs and kwargs['precio_minimo'] is not None:
            kwargs['precio_distribuidor'] = float(kwargs['precio_minimo'])
        super(ProductVariant, self).__init__(**kwargs)

# --- INGRESO Y RECEPCIÓN DE MERCANCÍA (TRAZABILIDAD + TICKET DE REVISIÓN) ---
class MerchandiseReceipt(db.Model):
    __tablename__ = 'merchandise_receipts'
    id = db.Column(db.Integer, primary_key=True)
    numero_ingreso = db.Column(db.String(30), unique=True, index=True, nullable=False)  # Ej: ING-00001
    numero_factura_proveedor = db.Column(db.String(60), nullable=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('providers.id'), nullable=True)
    provider_invoice_id = db.Column(db.Integer, db.ForeignKey('provider_invoices.id'), nullable=True)
    monto_factura_asignado = db.Column(db.Float, nullable=True)
    proveedor_nombre_manual = db.Column(db.String(120), nullable=True)
    destino = db.Column(db.String(20), nullable=False, default='BODEGA')  # 'BODEGA' o 'TIENDA'
    estado_revision = db.Column(db.String(30), nullable=False, default='VERIFICADO')  # 'PENDIENTE_REVISION', 'VERIFICADO', 'CON_NOVEDAD'
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    revisado_por = db.Column(db.String(100), nullable=True)
    fecha_ingreso = db.Column(db.DateTime, default=get_bogota_time)
    fecha_revision = db.Column(db.DateTime, nullable=True)
    observaciones = db.Column(db.Text, nullable=True)

    items = db.relationship('MerchandiseReceiptItem', backref='ingreso', cascade="all, delete-orphan", lazy=True)
    proveedor = db.relationship('Provider', foreign_keys=[provider_id], backref='ingresos_mercancia')
    factura_proveedor = db.relationship('ProviderInvoice', foreign_keys=[provider_invoice_id], backref='ingreso_mercancia_rel')
    usuario = db.relationship('User', foreign_keys=[usuario_id])

    @property
    def total_unidades(self):
        return sum(int(i.cantidad_recibida or 0) for i in self.items)

    @property
    def total_referencias(self):
        return len(self.items)

    @property
    def costo_total_ingreso(self):
        if self.monto_factura_asignado is not None and self.monto_factura_asignado > 0:
            return float(self.monto_factura_asignado)
        return sum(float(i.subtotal_costo or 0) for i in self.items)

    @property
    def costo_calculado_items(self):
        return sum(float(i.subtotal_costo or 0) for i in self.items)

    @property
    def nombre_proveedor_display(self):
        if self.proveedor:
            return f"{self.proveedor.nombre} ({self.proveedor.empresa})" if self.proveedor.empresa else self.proveedor.nombre
        return self.proveedor_nombre_manual or "Ingreso Directo / Sin Proveedor"

class MerchandiseReceiptItem(db.Model):
    __tablename__ = 'merchandise_receipt_items'
    id = db.Column(db.Integer, primary_key=True)
    receipt_id = db.Column(db.Integer, db.ForeignKey('merchandise_receipts.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    cantidad_esperada = db.Column(db.Integer, nullable=False, default=1)
    cantidad_recibida = db.Column(db.Integer, nullable=False, default=1)
    costo_unitario = db.Column(db.Float, nullable=False, default=0.0)
    subtotal_costo = db.Column(db.Float, nullable=False, default=0.0)
    stock_anterior = db.Column(db.Integer, nullable=False, default=0)
    stock_nuevo = db.Column(db.Integer, nullable=False, default=0)
    conformidad = db.Column(db.String(30), default='OK')  # 'OK', 'FALTANTE', 'AVERIA'
    nota_revision = db.Column(db.String(200), nullable=True)

    producto = db.relationship('Product', foreign_keys=[product_id])

# --- TRANSFERENCIAS BODEGA A TIENDA ---
class StockTransfer(db.Model):
    __tablename__ = 'stock_transfers'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=get_bogota_time)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    observaciones = db.Column(db.String(255))
    items = db.relationship('StockTransferItem', backref='transferencia', cascade="all, delete-orphan")
    usuario = db.relationship('User', foreign_keys=[usuario_id])

class StockTransferItem(db.Model):
    __tablename__ = 'stock_transfer_items'
    id = db.Column(db.Integer, primary_key=True)
    transfer_id = db.Column(db.Integer, db.ForeignKey('stock_transfers.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    producto = db.relationship('Product')

# --- MÓDULO DE INSTALADORES Y SERVICIOS ---
class Installer(db.Model):
    __tablename__ = 'installers'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    documento = db.Column(db.String(30), unique=True)
    telefono = db.Column(db.String(30))
    activo = db.Column(db.Boolean, default=True)
    instalaciones = db.relationship('InstallationJob', backref='tecnico', lazy=True)

class InstallationService(db.Model):
    __tablename__ = 'installation_services'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)  # Ej: "Luces LED Principales", "Polarizado", "Alarma"
    precio_estandar = db.Column(db.Float, default=0.0)   # Cobro al cliente
    costo_instalador = db.Column(db.Float, default=0.0)  # Mano de obra a liquidar al técnico
    activo = db.Column(db.Boolean, default=True)

# --- MÓDULO DE VEHÍCULOS (EXPEDIENTE / HISTORIAL AUTOMOTRIZ) ---
class Vehicle(db.Model):
    __tablename__ = 'vehicles'
    id = db.Column(db.Integer, primary_key=True)
    placa = db.Column(db.String(15), unique=True, nullable=False, index=True)
    marca = db.Column(db.String(60), nullable=True)       # Ej: Toyota, Mazda, Chevrolet, Yamaha
    modelo = db.Column(db.String(80), nullable=True)      # Ej: Hilux, Mazda 3, Tracker, NMAX
    anio = db.Column(db.String(10), nullable=True)        # Ej: 2024
    color = db.Column(db.String(40), nullable=True)       # Ej: Blanco Perlado, Negro, Gris
    tipo = db.Column(db.String(40), default='AUTOMOVIL')  # AUTOMOVIL, CAMIONETA, MOTO, PESADO
    cliente_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    observaciones = db.Column(db.Text, nullable=True)
    fecha_registro = db.Column(db.DateTime, default=get_bogota_time)
    ultima_visita = db.Column(db.DateTime, default=get_bogota_time)

    propietario = db.relationship('Customer', foreign_keys=[cliente_id], backref='vehiculos_registrados')
    ordenes_trabajo = db.relationship('WorkOrder', foreign_keys='WorkOrder.vehicle_id', backref='vehiculo_rel', lazy=True)
    ventas = db.relationship('Sale', foreign_keys='Sale.vehicle_id', backref='vehiculo_rel', lazy=True)

    @property
    def descripcion_completa(self):
        partes = [p for p in [self.marca, self.modelo, self.anio] if p]
        return " ".join(partes) if partes else (self.modelo or "Vehículo sin especificar")

# --- HOJAS DE TRABAJO (TALLER / ORDEN DE TRABAJO) ---
class WorkOrder(db.Model):
    __tablename__ = 'work_orders'
    id = db.Column(db.Integer, primary_key=True)
    numero_orden = db.Column(db.String(30), unique=True, index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=True)
    placa_vehiculo = db.Column(db.String(10), nullable=False)
    modelo_vehiculo = db.Column(db.String(80))
    cliente_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    asesor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    instalador_id = db.Column(db.Integer, db.ForeignKey('installers.id'), nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=get_bogota_time)
    fecha_entrega = db.Column(db.DateTime, nullable=True)
    estado = db.Column(db.String(30), default='EN_PROCESO')  # EN_PROCESO, LISTO_COBRO, COBRADO, CANCELADO
    observaciones = db.Column(db.Text)
    
    items = db.relationship('WorkOrderItem', backref='orden', cascade="all, delete-orphan")
    instalador = db.relationship('Installer')
    asesor = db.relationship('User', foreign_keys=[asesor_id])
    cliente = db.relationship('Customer', foreign_keys=[cliente_id], backref='ordenes_trabajo')

    @property
    def total_estimado(self):
        return sum(float(i.subtotal or 0) for i in self.items)

class WorkOrderItem(db.Model):
    __tablename__ = 'work_order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('work_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    service_id = db.Column(db.Integer, db.ForeignKey('installation_services.id'), nullable=True)
    tipo = db.Column(db.String(20), default='PRODUCTO')  # 'PRODUCTO' o 'SERVICIO'
    cantidad = db.Column(db.Integer, default=1)
    precio_unitario = db.Column(db.Float, default=0.0)
    subtotal = db.Column(db.Float, default=0.0)

    producto = db.relationship('Product', foreign_keys=[product_id])
    servicio = db.relationship('InstallationService', foreign_keys=[service_id])

# --- MÓDULO DE CLIENTES (CARTERA, CRÉDITOS Y ABONOS) ---
class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    documento = db.Column(db.String(30), unique=True, index=True)  # Cédula / NIT
    telefono = db.Column(db.String(30))
    direccion = db.Column(db.String(150))
    email = db.Column(db.String(100))
    placa_frecuente = db.Column(db.String(10))
    lista_precio_default = db.Column(db.String(20), default='cliente_final')  # 'distribuidor', 'local', 'cliente_final'
    limite_credito = db.Column(db.Float, default=0.0)
    fecha_registro = db.Column(db.DateTime, default=get_bogota_time)
    
    ventas = db.relationship('Sale', backref='cliente', lazy=True)
    abonos = db.relationship('CustomerCreditPayment', backref='cliente', lazy=True, cascade="all, delete-orphan")

    @property
    def total_creditos(self):
        total = 0.0
        for v in self.ventas:
            if (v.estado or 'ACTIVO') != 'ACTIVO':
                continue
            if (v.metodo_pago or '').upper() == 'CREDITO':
                total += float(v.total or 0)
            elif v.pagos:
                for p in v.pagos:
                    if (p.metodo_pago or '').upper() == 'CREDITO':
                        total += float(p.monto or 0)
        return total

    @property
    def total_abonos(self):
        return sum(float(a.monto or 0) for a in self.abonos if (a.estado or 'ACTIVO') == 'ACTIVO')

    @property
    def saldo_pendiente(self):
        return max(0.0, self.total_creditos - self.total_abonos)

class CustomerCreditPayment(db.Model):
    __tablename__ = 'customer_credit_payments'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime, default=get_bogota_time)
    metodo_pago = db.Column(db.String(30), default='EFECTIVO')  # Efectivo, Nequi, Daviplata, Bancolombia
    comprobante_url = db.Column(db.String(255))
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    estado = db.Column(db.String(20), default='ACTIVO')
    nota = db.Column(db.String(255))

    usuario = db.relationship('User', foreign_keys=[usuario_id])

# --- VENTAS Y CAJA POS ---
class Sale(db.Model):
    __tablename__ = 'sales'
    
    id = db.Column(db.Integer, primary_key=True)
    vendedor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    asesor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    instalador_id = db.Column(db.Integer, db.ForeignKey('installers.id'), nullable=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicles.id'), nullable=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_orders.id'), nullable=True)

    fecha_venta = db.Column(db.DateTime, default=obtener_hora_bogota)
    monto_total = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    metodo_pago = db.Column(db.String(50), nullable=False, default='efectivo')
    lista_precio = db.Column(db.String(30), nullable=True, default='cliente_final')
    estado = db.Column(db.String(20), nullable=False, default='ACTIVO', server_default='ACTIVO')

    # Datos de vehículo y cliente en mostrador
    placa_vehiculo = db.Column(db.String(20), nullable=True)
    modelo_vehiculo = db.Column(db.String(80), nullable=True)
    cliente_nombre = db.Column(db.String(120), nullable=True)
    cliente_documento = db.Column(db.String(30), nullable=True)
    cliente_telefono = db.Column(db.String(30), nullable=True)

    detalles = db.relationship('SaleDetail', backref='venta', lazy=True, cascade="all, delete-orphan")
    pagos = db.relationship('SalePayment', backref='venta', lazy=True, cascade="all, delete-orphan")
    instalaciones = db.relationship('InstallationJob', backref='venta', lazy=True, cascade="all, delete-orphan")
    asesor = db.relationship('User', foreign_keys=[asesor_id])
    instalador = db.relationship('Installer', foreign_keys=[instalador_id])
    orden_trabajo = db.relationship('WorkOrder', foreign_keys=[work_order_id])

    def __init__(self, **kwargs):
        if 'total' in kwargs and 'monto_total' not in kwargs:
            kwargs['monto_total'] = kwargs.pop('total')
        super(Sale, self).__init__(**kwargs)

    @property
    def total(self):
        return float(self.monto_total or 0)

    @total.setter
    def total(self, val):
        self.monto_total = val

    @property
    def metodo_pago_display(self):
        if not self.pagos:
            return self.metodo_pago.capitalize() if self.metodo_pago else 'Efectivo'
        if len(self.pagos) == 1:
            return self.pagos[0].metodo_pago.capitalize()
        return 'Pago Mixto'

class SalePayment(db.Model):
    __tablename__ = 'sale_payments'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    metodo_pago = db.Column(db.String(50), nullable=False)  # efectivo, nequi, bancolombia, daviplata, credito
    monto = db.Column(db.Numeric(10, 2), nullable=False)

    def __init__(self, **kwargs):
        super(SalePayment, self).__init__(**kwargs)

class SaleDetail(db.Model):
    __tablename__ = 'sale_details'
    
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True)
    service_id = db.Column(db.Integer, db.ForeignKey('installation_services.id'), nullable=True)
    installer_id = db.Column(db.Integer, db.ForeignKey('installers.id'), nullable=True)
    tipo_item = db.Column(db.String(20), nullable=False, default='PRODUCTO', server_default='PRODUCTO')  # 'PRODUCTO' o 'SERVICIO'
    cantidad_vendida = db.Column(db.Integer, nullable=False)
    precio_venta_final = db.Column(db.Numeric(10, 2), nullable=False)
    nombre_manual = db.Column(db.String(200), nullable=True)
    precio_costo_manual = db.Column(db.Numeric(10, 2), nullable=True)

    variante = db.relationship('ProductVariant', backref='ventas_rel', lazy=True)
    servicio = db.relationship('InstallationService', foreign_keys=[service_id])
    instalador = db.relationship('Installer', foreign_keys=[installer_id])

    def __init__(self, **kwargs):
        super(SaleDetail, self).__init__(**kwargs)

# --- REGISTRO DE INSTALACIONES COBRADAS (PARA LIQUIDACIÓN) ---
class InstallationJob(db.Model):
    __tablename__ = 'installation_jobs'
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('installation_services.id'), nullable=False)
    installer_id = db.Column(db.Integer, db.ForeignKey('installers.id'), nullable=False)
    precio_cobrado = db.Column(db.Float, default=0.0)
    costo_instalador = db.Column(db.Float, default=0.0)  # Lo que se le debe al instalador
    fecha = db.Column(db.DateTime, default=get_bogota_time)
    liquidado = db.Column(db.Boolean, default=False)

    servicio = db.relationship('InstallationService', foreign_keys=[service_id])

# --- KARDEX / AJUSTES DE STOCK ---
class StockAdjustment(db.Model):
    __tablename__ = 'stock_adjustments'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo_movimiento = db.Column(db.String(100), nullable=True)
    stock_anterior = db.Column(db.Integer, nullable=False)
    stock_nuevo = db.Column(db.Integer, nullable=False)
    fecha_ajuste = db.Column(db.DateTime, default=obtener_hora_bogota)

    def __init__(self, **kwargs):
        super(StockAdjustment, self).__init__(**kwargs)

# --- ARQUEO DE CAJA ---
class ArqueoCaja(db.Model):
    __tablename__ = 'arqueo_caja'
    
    id = db.Column(db.Integer, primary_key=True)
    vendedor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    fecha_arqueo = db.Column(db.Date, nullable=False, unique=True, index=True)

    base_inicial = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    gastos_del_dia = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    observaciones_gastos = db.Column(db.String(255), nullable=True)
    total_efectivo_sistema = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    total_transferencia_sistema = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    efectivo_fisico_contado = db.Column(db.Numeric(10, 2), nullable=True)
    diferencia = db.Column(db.Numeric(10, 2), nullable=True)
    observaciones = db.Column(db.Text, nullable=True)
    observaciones_diferencia = db.Column(db.Text, nullable=True)

    fecha_cierre = db.Column(db.DateTime, default=obtener_hora_bogota)
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)

    def __init__(self, **kwargs):
        if 'cajero_id' in kwargs and 'vendedor_id' not in kwargs:
            kwargs['vendedor_id'] = kwargs.pop('cajero_id')
        if 'observaciones' in kwargs and 'observaciones_diferencia' not in kwargs:
            kwargs['observaciones_diferencia'] = kwargs['observaciones']
        super(ArqueoCaja, self).__init__(**kwargs)

    @property
    def cajero_id(self):
        return self.vendedor_id

    @cajero_id.setter
    def cajero_id(self, val):
        self.vendedor_id = val

    @property
    def efectivo_esperado(self):
        base = float(self.base_inicial or 0)
        efectivo_sys = float(self.total_efectivo_sistema or 0)
        gastos = float(self.gastos_del_dia or 0)
        return (base + efectivo_sys) - gastos

    @property
    def total_recaudado_neto(self):
        efectivo_sys = float(self.total_efectivo_sistema or 0)
        digital_sys = float(self.total_transferencia_sistema or 0)
        gastos = float(self.gastos_del_dia or 0)
        return (efectivo_sys + digital_sys) - gastos

    @property
    def total_venta_bruta(self):
        return float(self.total_efectivo_sistema or 0) + float(self.total_transferencia_sistema or 0)

# --- MANEOS / PRÉSTAMOS ENTRE LOCALES ---
class Maneo(db.Model):
    __tablename__ = 'maneos'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    local_vecino = db.Column(db.String(150), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    valor_fijo = db.Column(db.Numeric(10, 2), nullable=True)
    estado = db.Column(db.String(50), nullable=False, default='PENDIENTE')
    fecha_prestamo = db.Column(db.DateTime, default=obtener_hora_bogota)
    fecha_resolucion = db.Column(db.DateTime, nullable=True)

    producto = db.relationship('Product', backref='maneos', lazy=True)
    variante = db.relationship('ProductVariant', backref='maneos_rel', lazy=True)
    cliente = db.relationship('Cliente', backref='maneos', lazy=True)

    def __init__(self, **kwargs):
        super(Maneo, self).__init__(**kwargs)

    @property
    def nombre_cliente_o_local(self):
        if self.cliente:
            return self.cliente.nombre_o_razon_social
        return self.local_vecino or "Sin especificar"

    @property
    def valor_unitario_calculado(self):
        if self.valor_fijo is not None:
            return float(self.valor_fijo)
        if self.variante and (self.variante.precio_final or self.variante.precio_sugerido):
            return float(self.variante.precio_final or self.variante.precio_sugerido)
        return float(self.producto.precio_final or self.producto.precio_sugerido or 0)

    @property
    def subtotal_calculado(self):
        return self.cantidad * self.valor_unitario_calculado

# --- GASTOS OPERATIVOS ---
class Expense(db.Model):
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo_gasto = db.Column(db.String(50), nullable=False)
    categoria = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(255), nullable=True)
    monto = db.Column(db.Numeric(10, 2), nullable=False)
    metodo_pago = db.Column(db.String(50), nullable=False, default='efectivo')
    fecha_gasto = db.Column(db.DateTime, default=obtener_hora_bogota)

    usuario = db.relationship('User', backref='gastos', lazy=True)

    def __init__(self, **kwargs):
        super(Expense, self).__init__(**kwargs)

# --- CLIENTES BODEGA MAYORISTA / MANEOS LEGACY ---
class Cliente(db.Model):
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    nombre_o_razon_social = db.Column(db.String(150), nullable=False)
    documento_o_nit = db.Column(db.String(50), unique=True, nullable=True, index=True)
    telefono = db.Column(db.String(50), nullable=True)
    contacto_persona = db.Column(db.String(100), nullable=True)
    local_numero = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    direccion = db.Column(db.String(255), nullable=True)
    zona = db.Column(db.String(100), nullable=True)
    notas = db.Column(db.Text, nullable=True)
    creado_por_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    fecha_registro = db.Column(db.DateTime, default=obtener_hora_bogota)

    facturas = db.relationship('FacturaBodega', backref='cliente', lazy=True)
    abonos = db.relationship('AbonoBodega', backref='cliente', lazy=True)

    def __init__(self, **kwargs):
        super(Cliente, self).__init__(**kwargs)

    @property
    def maneos_activos(self):
        return [m for m in self.maneos if m.estado == 'PENDIENTE']

    @property
    def saldo_maneos_pendiente(self):
        return sum(m.subtotal_calculado for m in self.maneos if m.estado == 'PENDIENTE')

    @property
    def unidades_maneos_pendientes(self):
        return sum(m.cantidad for m in self.maneos if m.estado == 'PENDIENTE')

    @property
    def total_historico_prestado(self):
        return sum(m.subtotal_calculado for m in self.maneos)

    @property
    def total_historico_cobrado(self):
        return sum(m.subtotal_calculado for m in self.maneos if m.estado == 'FACTURADO')

    @property
    def total_historico_devuelto(self):
        return sum(m.subtotal_calculado for m in self.maneos if m.estado == 'DEVUELTO')

    @property
    def total_contado(self):
        return sum(f.monto_total for f in self.facturas if f.modalidad == 'contado')

    @property
    def total_credito(self):
        return sum(f.monto_total for f in self.facturas if f.modalidad == 'credito')

    @property
    def total_abonado(self):
        return sum(a.monto for a in self.abonos if not (a.factura and a.factura.modalidad == 'contado'))

    @property
    def deuda_total(self):
        return self.total_credito - self.total_abonado

    @property
    def estado_global(self):
        return "Con Deuda" if (self.deuda_total > 0 or self.saldo_maneos_pendiente > 0) else "Al Día"

class FacturaBodega(db.Model):
    __tablename__ = 'facturas_bodega'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    numero_factura = db.Column(db.String(100), nullable=False)
    archivo_ruta = db.Column(db.String(255), nullable=True)
    monto_total = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    modalidad = db.Column(db.String(50), nullable=False, default='credito')
    estado = db.Column(db.String(50), nullable=False, default='Pendiente')
    fecha_subida = db.Column(db.DateTime, default=obtener_hora_bogota)

    usuario = db.relationship('User', backref='facturas_subidas', lazy=True)
    abonos = db.relationship('AbonoBodega', backref='factura', lazy=True, cascade="all, delete-orphan")
    detalles = db.relationship('FacturaBodegaDetalle', backref='factura', lazy=True, cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        super(FacturaBodega, self).__init__(**kwargs)

    @property
    def saldo_pendiente(self):
        total_abonado_factura = sum(abono.monto for abono in self.abonos) or 0
        return self.monto_total - total_abonado_factura

class FacturaBodegaDetalle(db.Model):
    __tablename__ = 'facturas_bodega_detalles'

    id = db.Column(db.Integer, primary_key=True)
    factura_id = db.Column(db.Integer, db.ForeignKey('facturas_bodega.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_venta = db.Column(db.Numeric(10, 2), nullable=True)

    producto = db.relationship('Product', backref='detalles_factura_bodega', lazy=True)
    variante = db.relationship('ProductVariant', backref='detalles_factura_bodega_rel', lazy=True)

    def __init__(self, **kwargs):
        super(FacturaBodegaDetalle, self).__init__(**kwargs)

class AbonoBodega(db.Model):
    __tablename__ = 'abonos_bodega'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    factura_id = db.Column(db.Integer, db.ForeignKey('facturas_bodega.id'), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    monto = db.Column(db.Numeric(10, 2), nullable=False)
    metodo_pago = db.Column(db.String(50), nullable=False, default='efectivo')
    observacion = db.Column(db.String(255), nullable=True)
    fecha_abono = db.Column(db.DateTime, default=obtener_hora_bogota)

    usuario = db.relationship('User', backref='abonos_registrados', lazy=True)

    def __init__(self, **kwargs):
        super(AbonoBodega, self).__init__(**kwargs)

# --- PROVEEDORES ---
class Provider(db.Model):
    __tablename__ = 'providers'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    empresa = db.Column(db.String(150), nullable=True)
    telefono = db.Column(db.String(50), nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=obtener_hora_bogota)
    
    facturas = db.relationship('ProviderInvoice', backref='provider', cascade='all, delete-orphan', lazy=True)
    pagos = db.relationship('ProviderPayment', backref='provider', cascade='all, delete-orphan', lazy=True)

class ProviderInvoice(db.Model):
    __tablename__ = 'provider_invoices'
    
    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('providers.id'), nullable=False)
    monto_total = db.Column(db.Numeric(10, 2), nullable=False)
    numero_factura = db.Column(db.String(100), nullable=True)
    descripcion = db.Column(db.String(255), nullable=True)
    comprobante = db.Column(db.String(255), nullable=True)
    fecha_factura = db.Column(db.DateTime, default=obtener_hora_bogota)

class ProviderPayment(db.Model):
    __tablename__ = 'provider_payments'
    
    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('providers.id'), nullable=False)
    monto_abonado = db.Column(db.Numeric(10, 2), nullable=False)
    observacion = db.Column(db.String(255), nullable=True)
    fecha_pago = db.Column(db.DateTime, default=obtener_hora_bogota)

class ServerPayment(db.Model):
    __tablename__ = 'server_payments'

    id = db.Column(db.Integer, primary_key=True)
    anio = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)
    estado = db.Column(db.String(20), nullable=False, default='pagado')
    fecha_pago = db.Column(db.DateTime, default=obtener_hora_bogota)
    observacion = db.Column(db.String(255), nullable=True)

    def __init__(self, **kwargs):
        super(ServerPayment, self).__init__(**kwargs)

class PriceApproval(db.Model):
    """Modelo para solicitudes y aprobaciones remotas de precios en tiempo real."""
    __tablename__ = 'price_approvals'

    id = db.Column(db.Integer, primary_key=True)
    vendedor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True, index=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True)
    nombre_producto = db.Column(db.String(200), nullable=False)
    precio_original = db.Column(db.Numeric(10, 2), nullable=False)
    precio_solicitado = db.Column(db.Numeric(10, 2), nullable=False)
    precio_aprobado = db.Column(db.Numeric(10, 2), nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='pendiente', index=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    motivo = db.Column(db.String(255), nullable=True)
    motivo_rechazo = db.Column(db.Text, nullable=True)
    fecha_solicitud = db.Column(db.DateTime, default=obtener_hora_bogota, index=True)
    fecha_resolucion = db.Column(db.DateTime, nullable=True)

    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=True, index=True)

    vendedor = db.relationship('User', foreign_keys=[vendedor_id], backref='solicitudes_precio')
    admin = db.relationship('User', foreign_keys=[admin_id], backref='aprobaciones_resueltas')
    producto = db.relationship('Product', foreign_keys=[product_id], backref='aprobaciones_precio')
    variante = db.relationship('ProductVariant', foreign_keys=[variant_id], backref='aprobaciones_precio')
    sale = db.relationship('Sale', foreign_keys=[sale_id], backref='aprobaciones_precio')

    def __init__(self, **kwargs):
        super(PriceApproval, self).__init__(**kwargs)
