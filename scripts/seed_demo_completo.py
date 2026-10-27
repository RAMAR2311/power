# -*- coding: utf-8 -*-
"""
Script de Semilla y Auditoría Integral de Módulos (Demo Comercial POWER LED)
Puebla ejemplos realistas en TODOS los módulos del sistema y verifica HTTP 200 en todas las rutas.
"""
from datetime import timedelta
from werkzeug.security import generate_password_hash
from app import create_app
from models import (
    db, User, Category, Subcategory, Product, StockTransfer, StockTransferItem,
    MerchandiseReceipt, MerchandiseReceiptItem, StockAdjustment,
    Provider, ProviderInvoice, ProviderPayment,
    Customer, CustomerCreditPayment,
    Vehicle, Installer, InstallationService, WorkOrder, WorkOrderItem,
    Sale, SaleDetail, SalePayment, InstallationJob,
    Cliente, FacturaBodega, FacturaBodegaDetalle, AbonoBodega,
    Maneo, Expense, ArqueoCaja, PriceApproval, get_bogota_time
)


def seed_all_demo_data():
    app = create_app()
    with app.app_context():
        db.create_all()
        ahora = get_bogota_time()

        # 1. USUARIOS (Admin, Bodega, Vendedor/Asesor)
        admin = User.query.filter_by(email='admin@powerled.com').first()
        if not admin:
            admin = User(
                nombre='Administrador General POWER LED',
                email='admin@powerled.com',
                telefono='3001112233',
                password_hash=generate_password_hash('Admin123'),
                rol='admin'
            )
            db.session.add(admin)

        bodega_user = User.query.filter_by(email='bodega@powerled.com').first()
        if not bodega_user:
            bodega_user = User(
                nombre='Jefe de Bodega Central',
                email='bodega@powerled.com',
                telefono='3004445566',
                password_hash=generate_password_hash('Bodega123'),
                rol='bodega'
            )
            db.session.add(bodega_user)

        vendedor = User.query.filter_by(email='asesor@powerled.com').first()
        if not vendedor:
            vendedor = User(
                nombre='Carlos Andrés (Asesor Mostrador)',
                email='asesor@powerled.com',
                telefono='3109998877',
                password_hash=generate_password_hash('Ventas123'),
                rol='vendedor'
            )
            db.session.add(vendedor)
        db.session.commit()

        # 2. CATEGORÍAS Y SUBCATEGORÍAS AUTOMOTRICES POWER LED
        cats_spec = [
            ('ILUMINACIÓN LED AUTOMOTRIZ', 5, ['Bombillos Turbo LED', 'Exploradoras & Barras LED', 'Ojos de Ángel & DRL']),
            ('AUDIO & MULTIMEDIA CARPLAY', 3, ['Radios Android / CarPlay', 'Parlantes & Subwoofers', 'Plantas & Amplificadores']),
            ('SEGURIDAD & ALARMAS', 4, ['Alarmas Doble Vía & GPS', 'Cámaras de Reversa & 360', 'Sensores de Parqueo']),
            ('POLARIZADOS & ESTÉTICA', 4, ['Nanocerámico HD', 'Cintas & Accesorios Exterior'])
        ]
        cat_map = {}
        sub_map = {}
        for cat_nombre, min_stock, sub_list in cats_spec:
            cat = Category.query.filter_by(nombre=cat_nombre).first()
            if not cat:
                cat = Category(nombre=cat_nombre, stock_minimo_alerta=min_stock)
                db.session.add(cat)
                db.session.flush()
            cat_map[cat_nombre] = cat
            for sub_nombre in sub_list:
                sub = Subcategory.query.filter_by(nombre=sub_nombre, categoria_id=cat.id).first()
                if not sub:
                    sub = Subcategory(nombre=sub_nombre, categoria_id=cat.id, stock_minimo_alerta=min_stock)
                    db.session.add(sub)
                    db.session.flush()
                sub_map[sub_nombre] = sub
        db.session.commit()

        # 3. CATÁLOGO DE PRODUCTOS (Con 3 listas de precios y stock en Tienda y Bodega)
        productos_spec = [
            ('PW-LED-H4-24K', 'Kit Bombillos Turbo LED H4 24.000 LM Canbus Pro', 'ILUMINACIÓN LED AUTOMOTRIZ', 'Bombillos Turbo LED', 55000, 78000, 95000, 135000, 14, 40),
            ('PW-LED-H7-30K', 'Kit Bombillos LED H7 30.000 LM CSP Tubo de Cobre', 'ILUMINACIÓN LED AUTOMOTRIZ', 'Bombillos Turbo LED', 68000, 95000, 115000, 160000, 12, 35),
            ('PW-EXP-DUAL', 'Par Exploradoras Mini Driving LED Bicolor (Blanco/Ámbar)', 'ILUMINACIÓN LED AUTOMOTRIZ', 'Exploradoras & Barras LED', 42000, 62000, 75000, 110000, 18, 50),
            ('PW-BAR-22P', 'Barra LED Curva 22 Pulgadas 4D Off-Road 180W', 'ILUMINACIÓN LED AUTOMOTRIZ', 'Exploradoras & Barras LED', 95000, 135000, 160000, 220000, 6, 15),
            ('PW-RAD-9P', 'Pantalla Android 9" QLED 4GB/64GB CarPlay Inalámbrico', 'AUDIO & MULTIMEDIA CARPLAY', 'Radios Android / CarPlay', 280000, 360000, 410000, 520000, 5, 12),
            ('PW-SUB-10P', 'Subwoofer Slim Bajo Silla 10" Activo 800W', 'AUDIO & MULTIMEDIA CARPLAY', 'Parlantes & Subwoofers', 210000, 275000, 310000, 390000, 4, 10),
            ('PW-ALA-PRO', 'Alarma Automotriz Ultra Pro con Módulo Elevavidrios', 'SEGURIDAD & ALARMAS', 'Alarmas Doble Vía & GPS', 85000, 118000, 135000, 185000, 9, 25),
            ('PW-CAM-AHD', 'Cámara de Reversa AHD 1080p Visión Nocturna Ojo de Pez', 'SEGURIDAD & ALARMAS', 'Cámaras de Reversa & 360', 25000, 38000, 48000, 75000, 20, 60),
            ('PW-POL-NANO', 'Kit Rollo Polarizado Nanocerámico Termocontraíble 20%', 'POLARIZADOS & ESTÉTICA', 'Nanocerámico HD', 140000, 190000, 220000, 290000, 7, 18),
        ]
        prod_objs = []
        for sku, nombre, cat_n, sub_n, costo, p_dist, p_loc, p_fin, s_tienda, s_bodega in productos_spec:
            p = Product.query.filter_by(codigo_barras=sku).first()
            if not p:
                p = Product(
                    codigo_barras=sku,
                    sku=sku,
                    nombre=nombre,
                    categoria_id=cat_map[cat_n].id,
                    subcategory_id=sub_map[sub_n].id,
                    costo=costo,
                    precio_distribuidor=p_dist,
                    precio_local=p_loc,
                    precio_final=p_fin,
                    stock_tienda=s_tienda,
                    stock_bodega=s_bodega,
                    stock_minimo=5
                )
                db.session.add(p)
                db.session.flush()
            prod_objs.append(p)
        db.session.commit()

        # 4. PROVEEDORES, FACTURAS DE PROVEEDORES Y ABONOS
        proveedores_spec = [
            ('Importadora LuminaTech Asia', 'LuminaTech Group SAS', '3157894561'),
            ('Distribuidora Nacional CarAudio Pro', 'CarAudio Pro Colombia Ltda', '3106549872'),
            ('Seguridad Automotriz Global', 'Global Alarmas & GPS SAS', '3012223344'),
        ]
        prov_objs = []
        for nom, emp, tel in proveedores_spec:
            pr = Provider.query.filter_by(nombre=nom).first()
            if not pr:
                pr = Provider(nombre=nom, empresa=emp, telefono=tel)
                db.session.add(pr)
                db.session.flush()
            prov_objs.append(pr)
        db.session.commit()

        # 5. ACTAS DE INGRESO DE MERCANCÍA (Con Factura Asignada a Proveedor y Ticket de Revisión)
        if MerchandiseReceipt.query.count() < 3:
            # Ingreso 1: Verificado en Bodega con factura cargada a Importadora LuminaTech
            ing1 = MerchandiseReceipt(
                numero_ingreso='ING-00101',
                numero_factura_proveedor='FAC-LUM-2026-88',
                provider_id=prov_objs[0].id,
                destino='BODEGA',
                estado_revision='VERIFICADO',
                usuario_id=admin.id,
                revisado_por='Jefe de Bodega Central',
                fecha_ingreso=ahora - timedelta(days=2),
                fecha_revision=ahora - timedelta(days=2, hours=-1),
                observaciones='Importación contenedor luces LED H4 y H7 verificada al 100%',
                monto_factura_asignado=2460000
            )
            db.session.add(ing1)
            db.session.flush()

            inv_p1 = ProviderInvoice(
                provider_id=prov_objs[0].id,
                monto_total=2460000,
                numero_factura='FAC-LUM-2026-88',
                descripcion=f'Ingreso de Mercancía {ing1.numero_ingreso} (40 uds a BODEGA)',
                fecha_factura=ahora - timedelta(days=2)
            )
            db.session.add(inv_p1)
            db.session.flush()
            ing1.provider_invoice_id = inv_p1.id

            # Abono parcial a ese proveedor
            ab_prov = ProviderPayment(
                provider_id=prov_objs[0].id,
                monto_abonado=1000000,
                observacion='Transferencia Bancolombia Abono Inicial FAC-LUM-2026-88',
                fecha_pago=ahora - timedelta(days=1)
            )
            db.session.add(ab_prov)

            db.session.add(MerchandiseReceiptItem(
                receipt_id=ing1.id, product_id=prod_objs[0].id,
                cantidad_esperada=20, cantidad_recibida=20,
                costo_unitario=55000, subtotal_costo=1100000,
                stock_anterior=20, stock_nuevo=40, conformidad='OK', nota_revision='Cajas selladas OK'
            ))
            db.session.add(MerchandiseReceiptItem(
                receipt_id=ing1.id, product_id=prod_objs[1].id,
                cantidad_esperada=20, cantidad_recibida=20,
                costo_unitario=68000, subtotal_costo=1360000,
                stock_anterior=15, stock_nuevo=35, conformidad='OK', nota_revision='Lote 2026 verificado'
            ))

            # Ingreso 2: Pendiente de Revisión en Tienda POS con CarAudio Pro
            ing2 = MerchandiseReceipt(
                numero_ingreso='ING-00102',
                numero_factura_proveedor='REM-AUDIO-554',
                provider_id=prov_objs[1].id,
                destino='TIENDA',
                estado_revision='PENDIENTE_REVISION',
                usuario_id=bodega_user.id,
                revisado_por='Carlos Andrés (Asesor Mostrador)',
                fecha_ingreso=ahora - timedelta(hours=3),
                observaciones='Recepción en mostrador pendiente de conteo de pantallas CarPlay',
                monto_factura_asignado=1400000
            )
            db.session.add(ing2)
            db.session.flush()

            inv_p2 = ProviderInvoice(
                provider_id=prov_objs[1].id,
                monto_total=1400000,
                numero_factura='REM-AUDIO-554',
                descripcion=f'Ingreso de Mercancía {ing2.numero_ingreso} (5 uds a TIENDA)',
                fecha_factura=ahora - timedelta(hours=3)
            )
            db.session.add(inv_p2)
            db.session.flush()
            ing2.provider_invoice_id = inv_p2.id

            db.session.add(MerchandiseReceiptItem(
                receipt_id=ing2.id, product_id=prod_objs[4].id,
                cantidad_esperada=5, cantidad_recibida=5,
                costo_unitario=280000, subtotal_costo=1400000,
                stock_anterior=0, stock_nuevo=5, conformidad='OK', nota_revision='Revisar arneses Canbus'
            ))
            db.session.commit()

        # 6. TRASLADOS INTERNOS BODEGA -> TIENDA
        if StockTransfer.query.count() == 0:
            tr1 = StockTransfer(
                fecha=ahora - timedelta(days=1),
                usuario_id=bodega_user.id,
                observaciones='Surtido de vitrina principal LED e iluminación para fin de semana'
            )
            db.session.add(tr1)
            db.session.flush()
            db.session.add(StockTransferItem(transfer_id=tr1.id, product_id=prod_objs[0].id, cantidad=6))
            db.session.add(StockTransferItem(transfer_id=tr1.id, product_id=prod_objs[2].id, cantidad=8))
            db.session.commit()

        # 7. TÉCNICOS INSTALADORES Y CATÁLOGO DE SERVICIOS DE MANO DE OBRA
        instaladores_spec = [
            ('Jhonatan Ramírez (Especialista Eléctrico & LED)', '1098765432', '3112223344'),
            ('Mauricio Gómez (Técnico CarAudio & Alarmas)', '1095123456', '3125556677'),
            ('Andrés Felipe Vega (Maestro Polarizado HD)', '1094888999', '3147778899'),
        ]
        inst_objs = []
        for nom, doc, tel in instaladores_spec:
            inst = Installer.query.filter_by(documento=doc).first()
            if not inst:
                inst = Installer(nombre=nom, documento=doc, telefono=tel, activo=True)
                db.session.add(inst)
                db.session.flush()
            inst_objs.append(inst)

        servicios_spec = [
            ('Instalación Kit Luces LED Principales + Alineación', 35000, 20000),
            ('Instalación Exploradoras LED con Relay y Switch Original', 55000, 32000),
            ('Instalación Pantalla Android / CarPlay + Cámara Reversa', 90000, 50000),
            ('Instalación Alarma Doble Vía + Módulo Elevavidrios', 110000, 65000),
            ('Aplicación Polarizado Nanocerámico Completo', 140000, 80000),
        ]
        serv_objs = []
        for nom, precio, comision in servicios_spec:
            sv = InstallationService.query.filter_by(nombre=nom).first()
            if not sv:
                sv = InstallationService(nombre=nom, precio_estandar=precio, costo_instalador=comision, activo=True)
                db.session.add(sv)
                db.session.flush()
            serv_objs.append(sv)
        db.session.commit()

        # 8. CLIENTES MOSTRADOR / TALLER / CARTERA CRÉDITO (Customer)
        clientes_spec = [
            ('Juan Sebastián Mendoza', '1098445566', '3168889900', 'Calle 45 #18-22 Cabecera', 'jmendoza@gmail.com', 'KLM842', 'cliente_final', 1500000),
            ('Lubricentro & Lujos El Volante', '900456123-1', '3174445522', 'Av. Quebradaseca #24-10', 'compras@elvolante.co', 'RJT911', 'local', 3000000),
            ('Importaciones & Flotas Santander SAS', '901222888-9', '3183331100', 'Zona Industrial Chimita Bg 12', 'logistica@flotassantander.com', 'WXY505', 'distribuidor', 5000000),
        ]
        cust_objs = []
        for nom, doc, tel, dir_c, email, placa, lista, cupo in clientes_spec:
            c = Customer.query.filter_by(documento=doc).first()
            if not c:
                c = Customer(
                    nombre=nom, documento=doc, telefono=tel, direccion=dir_c,
                    email=email, placa_frecuente=placa, lista_precio_default=lista, limite_credito=cupo
                )
                db.session.add(c)
                db.session.flush()
            cust_objs.append(c)
        db.session.commit()

        # 9. VEHÍCULOS CON EXPEDIENTE E HISTORIAL AUTOMOTRIZ (Vehicle)
        vehiculos_spec = [
            ('KLM842', 'TOYOTA', 'HILUX SRX 4X4', '2024', 'Blanco Perlado', 'CAMIONETA', cust_objs[0].id, 'Sistema eléctrico 12V Canbus sensible, luces principales H4 y exploradoras'),
            ('RJT911', 'MAZDA', 'MAZDA 3 TOURING', '2023', 'Rojo Diamante', 'AUTOMOVIL', cust_objs[1].id, 'Cliente solicita línea premium en audio y polarizado nanocerámico'),
            ('WXY505', 'CHEVROLET', 'NHR REWARD TURBO', '2025', 'Blanco', 'PESADO', cust_objs[2].id, 'Camión de flota corporativa, barra LED 22 pulgadas y cámara reversa'),
            ('MTR77G', 'YAMAHA', 'NMAX CONNECTED 155', '2025', 'Gris Mate', 'MOTO', cust_objs[0].id, 'Exploradoras Mini Driving bicolor con soporte de barras'),
        ]
        veh_objs = []
        for placa, marca, modelo, anio, color, tipo, cid, obs in vehiculos_spec:
            v = Vehicle.query.filter_by(placa=placa).first()
            if not v:
                v = Vehicle(
                    placa=placa, marca=marca, modelo=modelo, anio=anio,
                    color=color, tipo=tipo, cliente_id=cid, observaciones=obs,
                    fecha_registro=ahora - timedelta(days=5), ultima_visita=ahora
                )
                db.session.add(v)
                db.session.flush()
            veh_objs.append(v)
        db.session.commit()

        # 10. HOJAS DE TRABAJO DE TALLER (WorkOrder: EN_PROCESO, LISTO_COBRO, COBRADO)
        if WorkOrder.query.count() < 3:
            # Orden 1: EN_PROCESO
            ot1 = WorkOrder(
                numero_orden='OT-0001',
                vehicle_id=veh_objs[0].id,
                placa_vehiculo=veh_objs[0].placa,
                modelo_vehiculo=veh_objs[0].descripcion_completa,
                cliente_id=cust_objs[0].id,
                asesor_id=vendedor.id,
                instalador_id=inst_objs[0].id,
                estado='EN_PROCESO',
                observaciones='Instalar Kit Turbo LED H4 y Exploradoras Mini Driving sin cortar cableado original'
            )
            db.session.add(ot1)
            db.session.flush()
            db.session.add(WorkOrderItem(order_id=ot1.id, product_id=prod_objs[0].id, tipo='PRODUCTO', cantidad=1, precio_unitario=135000, subtotal=135000))
            db.session.add(WorkOrderItem(order_id=ot1.id, product_id=prod_objs[2].id, tipo='PRODUCTO', cantidad=1, precio_unitario=110000, subtotal=110000))
            db.session.add(WorkOrderItem(order_id=ot1.id, service_id=serv_objs[0].id, tipo='SERVICIO', cantidad=1, precio_unitario=35000, subtotal=35000))
            db.session.add(WorkOrderItem(order_id=ot1.id, service_id=serv_objs[1].id, tipo='SERVICIO', cantidad=1, precio_unitario=55000, subtotal=55000))

            # Orden 2: LISTO_COBRO (Para probar en vivo el paso a Caja POS con 1 clic)
            ot2 = WorkOrder(
                numero_orden='OT-0002',
                vehicle_id=veh_objs[1].id,
                placa_vehiculo=veh_objs[1].placa,
                modelo_vehiculo=veh_objs[1].descripcion_completa,
                cliente_id=cust_objs[1].id,
                asesor_id=vendedor.id,
                instalador_id=inst_objs[1].id,
                estado='LISTO_COBRO',
                observaciones='Pantalla Android 9" CarPlay + Cámara AHD instalada y probada. Lista para facturar en POS.'
            )
            db.session.add(ot2)
            db.session.flush()
            db.session.add(WorkOrderItem(order_id=ot2.id, product_id=prod_objs[4].id, tipo='PRODUCTO', cantidad=1, precio_unitario=410000, subtotal=410000))
            db.session.add(WorkOrderItem(order_id=ot2.id, product_id=prod_objs[7].id, tipo='PRODUCTO', cantidad=1, precio_unitario=48000, subtotal=48000))
            db.session.add(WorkOrderItem(order_id=ot2.id, service_id=serv_objs[2].id, tipo='SERVICIO', cantidad=1, precio_unitario=90000, subtotal=90000))

            # Orden 3: COBRADO
            ot3 = WorkOrder(
                numero_orden='OT-0003',
                vehicle_id=veh_objs[2].id,
                placa_vehiculo=veh_objs[2].placa,
                modelo_vehiculo=veh_objs[2].descripcion_completa,
                cliente_id=cust_objs[2].id,
                asesor_id=admin.id,
                instalador_id=inst_objs[2].id,
                estado='COBRADO',
                fecha_entrega=ahora - timedelta(hours=2),
                observaciones='Polarizado Nanocerámico + Barra LED 22 Pulgadas entregada a satisfacción.'
            )
            db.session.add(ot3)
            db.session.flush()
            db.session.add(WorkOrderItem(order_id=ot3.id, product_id=prod_objs[3].id, tipo='PRODUCTO', cantidad=1, precio_unitario=220000, subtotal=220000))
            db.session.add(WorkOrderItem(order_id=ot3.id, service_id=serv_objs[4].id, tipo='SERVICIO', cantidad=1, precio_unitario=140000, subtotal=140000))
            db.session.commit()

        # 11. VENTAS POS (Contado, Pago Mixto y Crédito con Liquidación de Técnicos)
        if Sale.query.count() < 2:
            ot_cobrada = WorkOrder.query.filter_by(estado='COBRADO').first()
            # Venta 1: Contado / Mixto (Efectivo + Nequi) vinculada a vehículo y técnico
            v1 = Sale(
                vendedor_id=admin.id,
                asesor_id=vendedor.id,
                instalador_id=inst_objs[0].id,
                cliente_id=cust_objs[0].id,
                vehicle_id=veh_objs[0].id,
                work_order_id=ot_cobrada.id if ot_cobrada else None,
                fecha_venta=ahora - timedelta(hours=2),
                monto_total=335000,
                metodo_pago='efectivo',
                lista_precio='cliente_final',
                estado='ACTIVO',
                placa_vehiculo=veh_objs[0].placa,
                modelo_vehiculo=veh_objs[0].descripcion_completa,
                cliente_nombre=cust_objs[0].nombre,
                cliente_documento=cust_objs[0].documento,
                cliente_telefono=cust_objs[0].telefono
            )
            db.session.add(v1)
            db.session.flush()
            db.session.add(SaleDetail(sale_id=v1.id, product_id=prod_objs[0].id, tipo_item='PRODUCTO', cantidad_vendida=1, precio_venta_final=135000))
            db.session.add(SaleDetail(sale_id=v1.id, product_id=prod_objs[2].id, tipo_item='PRODUCTO', cantidad_vendida=1, precio_venta_final=110000))
            db.session.add(SaleDetail(sale_id=v1.id, service_id=serv_objs[0].id, installer_id=inst_objs[0].id, tipo_item='SERVICIO', cantidad_vendida=1, precio_venta_final=35000, nombre_manual=serv_objs[0].nombre))
            db.session.add(SaleDetail(sale_id=v1.id, service_id=serv_objs[1].id, installer_id=inst_objs[0].id, tipo_item='SERVICIO', cantidad_vendida=1, precio_venta_final=55000, nombre_manual=serv_objs[1].nombre))
            db.session.add(SalePayment(sale_id=v1.id, metodo_pago='efectivo', monto=200000))
            db.session.add(SalePayment(sale_id=v1.id, metodo_pago='nequi', monto=135000))

            # Registrar comisiones del técnico en InstallationJob
            db.session.add(InstallationJob(
                sale_id=v1.id, installer_id=inst_objs[0].id, service_id=serv_objs[0].id,
                precio_cobrado=35000, costo_instalador=20000, liquidado=False, fecha=ahora - timedelta(hours=2)
            ))
            db.session.add(InstallationJob(
                sale_id=v1.id, installer_id=inst_objs[0].id, service_id=serv_objs[1].id,
                precio_cobrado=55000, costo_instalador=32000, liquidado=False, fecha=ahora - timedelta(hours=2)
            ))

            # Venta 2: A Crédito para ver Cartera de Clientes y Abonos
            v2 = Sale(
                vendedor_id=admin.id,
                asesor_id=vendedor.id,
                instalador_id=inst_objs[1].id,
                cliente_id=cust_objs[1].id,
                vehicle_id=veh_objs[1].id,
                fecha_venta=ahora - timedelta(days=1),
                monto_total=500000,
                metodo_pago='CREDITO',
                lista_precio='local',
                estado='ACTIVO',
                placa_vehiculo=veh_objs[1].placa,
                modelo_vehiculo=veh_objs[1].descripcion_completa,
                cliente_nombre=cust_objs[1].nombre,
                cliente_documento=cust_objs[1].documento,
                cliente_telefono=cust_objs[1].telefono
            )
            db.session.add(v2)
            db.session.flush()
            db.session.add(SaleDetail(sale_id=v2.id, product_id=prod_objs[4].id, tipo_item='PRODUCTO', cantidad_vendida=1, precio_venta_final=410000))
            db.session.add(SaleDetail(sale_id=v2.id, service_id=serv_objs[2].id, installer_id=inst_objs[1].id, tipo_item='SERVICIO', cantidad_vendida=1, precio_venta_final=90000, nombre_manual=serv_objs[2].nombre))
            db.session.add(SalePayment(sale_id=v2.id, metodo_pago='CREDITO', monto=500000))
            db.session.add(InstallationJob(
                sale_id=v2.id, installer_id=inst_objs[1].id, service_id=serv_objs[2].id,
                precio_cobrado=90000, costo_instalador=50000, liquidado=True, fecha=ahora - timedelta(days=1)
            ))

            # Abono a la cartera del cliente
            db.session.add(CustomerCreditPayment(
                cliente_id=cust_objs[1].id,
                monto=200000,
                metodo_pago='NEQUI',
                usuario_id=admin.id,
                estado='ACTIVO',
                nota='Abono inicial Nequi a factura de Pantalla CarPlay'
            ))
            db.session.commit()

        # 12. MÓDULO BODEGA MAYORISTA (Clientes Mayoristas, Facturas Bodega y Abonos)
        if Cliente.query.count() == 0:
            cl_bod1 = Cliente(
                nombre_o_razon_social='Autolujos & Polarizados Del Oriente',
                documento_o_nit='900777666-4',
                telefono='3154448899',
                contacto_persona='Hernán Darío Gómez',
                local_numero='Local 104 Centro Comercial del Automóvil',
                email='autolujosoriente@gmail.com',
                direccion='Carrera 15 #21-40',
                zona='Bucaramanga Centro',
                notas='Cliente mayorista VIP de iluminación LED',
                creado_por_id=bodega_user.id
            )
            cl_bod2 = Cliente(
                nombre_o_razon_social='Distribuciones Eléctricas El Faro',
                documento_o_nit='800112233-5',
                telefono='3189990011',
                contacto_persona='Martha Lucía Cala',
                local_numero='Bodega 8 La Rosita',
                email='elfarodistribuciones@hotmail.com',
                direccion='Calle 36 #14-18',
                zona='La Rosita',
                notas='Despachos semanales a crédito 15 días',
                creado_por_id=bodega_user.id
            )
            db.session.add_all([cl_bod1, cl_bod2])
            db.session.flush()

            fb1 = FacturaBodega(
                cliente_id=cl_bod1.id,
                usuario_id=bodega_user.id,
                numero_factura='BOD-2026-001',
                monto_total=780000,
                modalidad='credito',
                estado='Pendiente',
                fecha_subida=ahora - timedelta(days=2)
            )
            db.session.add(fb1)
            db.session.flush()
            db.session.add(FacturaBodegaDetalle(factura_id=fb1.id, producto_id=prod_objs[0].id, cantidad=10, precio_venta=78000))
            db.session.add(AbonoBodega(
                cliente_id=cl_bod1.id, factura_id=fb1.id, usuario_id=bodega_user.id,
                monto=300000, metodo_pago='bancolombia', observacion='Abono parcial transferencia Bancolombia'
            ))

            fb2 = FacturaBodega(
                cliente_id=cl_bod2.id,
                usuario_id=bodega_user.id,
                numero_factura='BOD-2026-002',
                monto_total=620000,
                modalidad='contado',
                estado='Pagada',
                fecha_subida=ahora - timedelta(days=1)
            )
            db.session.add(fb2)
            db.session.flush()
            db.session.add(FacturaBodegaDetalle(factura_id=fb2.id, producto_id=prod_objs[2].id, cantidad=10, precio_venta=62000))
            db.session.commit()

        # 13. MANEOS / PRÉSTAMOS ENTRE LOCALES VECINOS
        cl_maneo = Cliente.query.first()
        if Maneo.query.count() == 0 and cl_maneo:
            m1 = Maneo(
                product_id=prod_objs[1].id,
                cliente_id=cl_maneo.id,
                local_vecino=cl_maneo.nombre_o_razon_social,
                cantidad=2,
                valor_fijo=95000,
                estado='PENDIENTE',
                fecha_prestamo=ahora - timedelta(hours=5)
            )
            m2 = Maneo(
                product_id=prod_objs[7].id,
                cliente_id=cl_maneo.id,
                local_vecino=cl_maneo.nombre_o_razon_social,
                cantidad=3,
                valor_fijo=38000,
                estado='FACTURADO',
                fecha_prestamo=ahora - timedelta(days=2),
                fecha_resolucion=ahora - timedelta(days=1)
            )
            db.session.add_all([m1, m2])
            db.session.commit()

        # 14. GASTOS OPERATIVOS (Expense)
        if Expense.query.count() == 0:
            g1 = Expense(
                usuario_id=admin.id,
                tipo_gasto='Operativo',
                categoria='Insumos de Taller (Cinta, Termoencogible, Relays)',
                descripcion='Compra de rollos de cinta Tesa original, conectores y amarras plásticas para bahía de instalación',
                monto=45000,
                metodo_pago='efectivo',
                fecha_gasto=ahora - timedelta(hours=4)
            )
            g2 = Expense(
                usuario_id=admin.id,
                tipo_gasto='Logística',
                categoria='Fletes y Transportadoras',
                descripcion='Pago flete Envía caja de exploradoras y pantallas',
                monto=32000,
                metodo_pago='nequi',
                fecha_gasto=ahora - timedelta(days=1)
            )
            db.session.add_all([g1, g2])
            db.session.commit()

        # 15. APROBACIONES REMOTAS DE PRECIO EN TIEMPO REAL (PriceApproval)
        if PriceApproval.query.count() == 0:
            pa1 = PriceApproval(
                vendedor_id=vendedor.id,
                product_id=prod_objs[4].id,
                nombre_producto=prod_objs[4].nombre,
                precio_original=520000,
                precio_solicitado=475000,
                estado='pendiente',
                motivo='Cliente lleva combo de Pantalla Android + Luces LED H4 de contado en efectivo',
                fecha_solicitud=ahora - timedelta(minutes=25)
            )
            db.session.add(pa1)
            db.session.commit()

        print("=== SEMILLA DEMO COMERCIAL POWER LED COMPLETADA CON ÉXITO ===")


if __name__ == '__main__':
    seed_all_demo_data()
