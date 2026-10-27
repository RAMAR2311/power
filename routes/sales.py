import os
import uuid
import time
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, flash, redirect, render_template, abort, url_for, current_app
from flask_login import login_required, current_user
from models import (
    db, Product, ProductVariant, Sale, SaleDetail, SalePayment, Expense,
    obtener_hora_bogota, ArqueoCaja, PriceApproval, Installer, InstallationService,
    InstallationJob, WorkOrder, Customer, User, Vehicle
)
from routes.vehiculos import sincronizar_vehiculo
from decorators import admin_required
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
import unicodedata
import re

def normalizar_texto(texto):
    """Normaliza texto eliminando acentos, tildes y diacríticos y convirtiendo a minúsculas."""
    if not texto:
        return ''
    return ''.join(
        c for c in unicodedata.normalize('NFD', str(texto))
        if unicodedata.category(c) != 'Mn'
    ).lower()

def comodin_vocales(texto):
    """Reemplaza vocales (con o sin tilde) por el comodín SQL '_' para coincidencia flexible en BD."""
    return re.sub(r'[aeiouáéíóúüÁÉÍÓÚÜ]', '_', str(texto))

sales_bp = Blueprint('sales_bp', __name__)

@sales_bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def procesar_venta():
    if request.method == 'GET':
        return render_template('sales/nueva.html')

    """
    Procesa la venta desde el POS flexible de POWER LED.
    Soporta:
    - 3 listas de precios (cliente_final, local, distribuidor)
    - Ítems de tipo PRODUCTO y SERVICIO (con creación automática de InstallationJob)
    - Datos de cliente opcionales o vinculación a Customer (obligatorio o auto-creado en CREDITO)
    - Datos de vehículo (placa_vehiculo, modelo_vehiculo), asesor_id, instalador_id
    - Orden de Trabajo vinculada (work_order_id -> cambia estado a COBRADO)
    """
    data = request.get_json() or {}
    items = data.get('items', [])
    pagos_data = data.get('pagos', [])
    metodo_pago_legacy = data.get('metodo_pago', 'efectivo')
    lista_precio = data.get('lista_precio', 'cliente_final')
    raw_wo_id = data.get('work_order_id')
    try:
        work_order_id = int(raw_wo_id) if raw_wo_id else None
    except (ValueError, TypeError):
        work_order_id = None

    if not items:
        return jsonify({'error': 'No se enviaron productos ni servicios para la venta'}), 400

    if not pagos_data:
        pagos_data = [{'metodo_pago': metodo_pago_legacy, 'monto': None}]

    try:
        if len(pagos_data) == 1:
            metodo_pago_principal = (pagos_data[0].get('metodo_pago') or 'efectivo').lower().strip()
        else:
            metodo_pago_principal = 'mixto'

        # Manejar Fecha de Venta para registros de fechas anteriores
        fecha_venta_str = data.get('fecha_venta')
        fecha_venta_obj = obtener_hora_bogota()
        if fecha_venta_str:
            try:
                fecha_seleccionada = datetime.strptime(fecha_venta_str, '%Y-%m-%d').date()
                if fecha_seleccionada != fecha_venta_obj.date():
                    fecha_venta_obj = datetime.combine(fecha_seleccionada, fecha_venta_obj.time())
            except ValueError:
                pass

        # Validar si la caja para la jornada seleccionada ya fue cerrada
        caja_cerrada = ArqueoCaja.query.filter_by(fecha_arqueo=fecha_venta_obj.date()).first()
        if caja_cerrada:
            return jsonify({
                'error': f'La caja del día {fecha_venta_obj.date().strftime("%Y-%m-%d")} ya se encuentra cerrada. No es posible registrar nuevas ventas.'
            }), 400

        # Datos de Cliente y Vehículo
        cliente_info = data.get('cliente') or {}
        cliente_id = data.get('cliente_id') or cliente_info.get('id')
        cliente_nombre = (data.get('cliente_nombre') or cliente_info.get('nombre') or '').strip()
        cliente_documento = (data.get('cliente_documento') or cliente_info.get('documento') or '').strip()
        cliente_telefono = (data.get('cliente_telefono') or cliente_info.get('telefono') or '').strip()
        placa_vehiculo = (data.get('placa_vehiculo') or cliente_info.get('placa') or '').strip().upper()
        modelo_vehiculo = (data.get('modelo_vehiculo') or cliente_info.get('modelo') or '').strip()

        asesor_id = data.get('asesor_id') or current_user.id
        instalador_id = data.get('instalador_id') or None
        if instalador_id:
            try:
                instalador_id = int(instalador_id)
            except (ValueError, TypeError):
                instalador_id = None

        # Verificar si algún pago es a CRÉDITO
        hay_credito = (metodo_pago_principal.upper() == 'CREDITO') or any(
            (p.get('metodo_pago') or '').upper() == 'CREDITO' for p in pagos_data
        )

        # Resolver o crear registro Customer si se enviaron datos o si es venta a crédito
        customer_obj = None
        if cliente_id:
            customer_obj = Customer.query.get(int(cliente_id))
        elif cliente_documento:
            customer_obj = Customer.query.filter_by(documento=cliente_documento).first()

        if not customer_obj and (cliente_nombre or hay_credito):
            if hay_credito and not cliente_nombre:
                raise ValueError("Para facturar a CRÉDITO debes seleccionar un cliente o activar 'Registrar Datos de Cliente' e ingresar al menos su Nombre y Cédula/NIT.")
            doc_final = cliente_documento if cliente_documento else f"CF-{int(time.time())}"
            customer_obj = Customer(
                nombre=cliente_nombre or 'Cliente Crédito',
                documento=doc_final,
                telefono=cliente_telefono or None,
                placa_frecuente=placa_vehiculo or None,
                lista_precio_default=lista_precio or 'cliente_final'
            )
            db.session.add(customer_obj)
            db.session.flush()

        if customer_obj:
            cliente_id = customer_obj.id
            if not cliente_nombre:
                cliente_nombre = customer_obj.nombre
            if not cliente_documento:
                cliente_documento = customer_obj.documento or ''
            if not cliente_telefono:
                cliente_telefono = customer_obj.telefono or ''
            if not placa_vehiculo and customer_obj.placa_frecuente:
                placa_vehiculo = customer_obj.placa_frecuente
            elif placa_vehiculo and not customer_obj.placa_frecuente:
                customer_obj.placa_frecuente = placa_vehiculo

        # Sincronizar el vehículo con el módulo de Historial de Vehículos si se indicó placa
        vehiculo_obj = None
        if placa_vehiculo:
            vehiculo_obj = sincronizar_vehiculo(
                placa=placa_vehiculo,
                modelo=modelo_vehiculo,
                cliente_id=cliente_id
            )
            if vehiculo_obj and not modelo_vehiculo and vehiculo_obj.modelo:
                modelo_vehiculo = vehiculo_obj.modelo

        nueva_venta = Sale(
            vendedor_id=current_user.id,
            asesor_id=int(asesor_id) if asesor_id else current_user.id,
            instalador_id=instalador_id,
            cliente_id=cliente_id,
            vehicle_id=vehiculo_obj.id if vehiculo_obj else None,
            work_order_id=work_order_id,
            monto_total=Decimal('0.00'),
            metodo_pago=metodo_pago_principal,
            lista_precio=lista_precio,
            placa_vehiculo=placa_vehiculo or None,
            modelo_vehiculo=modelo_vehiculo or None,
            cliente_nombre=cliente_nombre or None,
            cliente_documento=cliente_documento or None,
            cliente_telefono=cliente_telefono or None,
            fecha_venta=fecha_venta_obj
        )
        db.session.add(nueva_venta)
        db.session.flush()

        monto_total = Decimal('0.00')

        for item in items:
            tipo_item = (item.get('tipo_item') or 'PRODUCTO').upper().strip()
            product_id = item.get('product_id')
            variant_id = item.get('variant_id')
            service_id = item.get('service_id')
            item_installer_id = item.get('installer_id') or instalador_id
            cantidad_vendida = int(item.get('cantidad', 0))
            precio_venta_final = Decimal(str(item.get('precio_final', '0.00')))
            es_manual = item.get('es_manual', False)
            es_obsequio = item.get('es_obsequio', False)

            if cantidad_vendida <= 0:
                raise ValueError("La cantidad vendida debe ser mayor a 0.")

            # 1. Servicio de Instalación / Mano de Obra
            if tipo_item == 'SERVICIO' or service_id:
                servicio = InstallationService.query.get(service_id) if service_id else None
                nombre_servicio = item.get('nombre_manual') or (servicio.nombre if servicio else 'Servicio de Instalación')
                if item_installer_id:
                    try:
                        item_installer_id = int(item_installer_id)
                    except (ValueError, TypeError):
                        item_installer_id = instalador_id

                detalle = SaleDetail(
                    sale_id=nueva_venta.id,
                    product_id=None,
                    variant_id=None,
                    service_id=servicio.id if servicio else None,
                    installer_id=item_installer_id,
                    tipo_item='SERVICIO',
                    cantidad_vendida=cantidad_vendida,
                    precio_venta_final=precio_venta_final,
                    nombre_manual=nombre_servicio
                )
                db.session.add(detalle)
                monto_total += (precio_venta_final * cantidad_vendida)

                # Crear registro de comisión para liquidación de técnico si hay servicio e instalador
                tecnico_final_id = item_installer_id or nueva_venta.instalador_id
                if not tecnico_final_id:
                    primer_inst = Installer.query.filter_by(activo=True).first()
                    if primer_inst:
                        tecnico_final_id = primer_inst.id

                if servicio and tecnico_final_id:
                    if not nueva_venta.instalador_id:
                        nueva_venta.instalador_id = tecnico_final_id
                    for _ in range(cantidad_vendida):
                        job = InstallationJob(
                            sale_id=nueva_venta.id,
                            service_id=servicio.id,
                            installer_id=tecnico_final_id,
                            precio_cobrado=float(precio_venta_final),
                            costo_instalador=float(servicio.costo_instalador or 0),
                            fecha=fecha_venta_obj,
                            liquidado=False
                        )
                        db.session.add(job)

            # 2. Producto Manual / Externo
            elif es_manual:
                nombre_manual = item.get('nombre_manual', 'Producto Externo')
                precio_costo_manual = Decimal(str(item.get('precio_costo', '0.00')))

                detalle = SaleDetail(
                    sale_id=nueva_venta.id,
                    product_id=None,
                    variant_id=None,
                    tipo_item='PRODUCTO',
                    cantidad_vendida=cantidad_vendida,
                    precio_venta_final=precio_venta_final,
                    nombre_manual=nombre_manual,
                    precio_costo_manual=precio_costo_manual
                )
                db.session.add(detalle)
                monto_total += (precio_venta_final * cantidad_vendida)

                if precio_costo_manual > 0:
                    gasto_externo = Expense(
                        usuario_id=current_user.id,
                        tipo_gasto='Gasto Diario',
                        categoria='Pago Prod. Externo',
                        descripcion=f"Pago por producto manual prestado: {nombre_manual}",
                        monto=(precio_costo_manual * cantidad_vendida),
                        fecha_gasto=fecha_venta_obj
                    )
                    db.session.add(gasto_externo)

            # 3. Producto del Inventario Propio (Descuenta de stock_tienda)
            else:
                producto = Product.query.with_for_update().get(product_id)
                if not producto:
                    raise ValueError(f"El producto con ID {product_id} no existe.")

                if variant_id:
                    variante = ProductVariant.query.with_for_update().get(variant_id)
                    if not variante:
                        raise ValueError(f"La variante con ID {variant_id} no existe.")
                    if cantidad_vendida > variante.cantidad_stock:
                        raise ValueError(f"Stock insuficiente para '{variante.nombre_variante}' de '{producto.nombre}'. Solicitado: {cantidad_vendida}, Disponible: {variante.cantidad_stock}.")

                    stock_anterior = variante.cantidad_stock
                    variante.cantidad_stock -= cantidad_vendida
                    producto.stock_tienda = max(0, (producto.stock_tienda or 0) - cantidad_vendida)
                    producto.cantidad_stock = producto.stock_tienda
                    precio_limite_autorizado = Decimal(str(variante.precio_costo or producto.costo or 0)) if current_user.rol == 'admin' else Decimal(str(variante.precio_distribuidor or variante.precio_minimo or producto.precio_distribuidor or 0))

                    from models import StockAdjustment
                    ajuste = StockAdjustment(
                        product_id=producto.id,
                        admin_id=current_user.id,
                        tipo_movimiento=f"Venta Tienda (Subcat: {variante.nombre_variante})",
                        stock_anterior=stock_anterior,
                        stock_nuevo=variante.cantidad_stock
                    )
                    db.session.add(ajuste)
                else:
                    stock_disponible = producto.stock_tienda if producto.stock_tienda is not None else producto.cantidad_stock
                    if cantidad_vendida > stock_disponible:
                        raise ValueError(f"Stock insuficiente en Tienda para '{producto.nombre}'. Solicitado: {cantidad_vendida}, Disponible: {stock_disponible}.")

                    stock_anterior = stock_disponible
                    producto.stock_tienda = stock_disponible - cantidad_vendida
                    producto.cantidad_stock = producto.stock_tienda
                    precio_limite_autorizado = Decimal(str(producto.costo or producto.precio_costo or 0)) if current_user.rol == 'admin' else Decimal(str(producto.precio_distribuidor or producto.precio_minimo or 0))

                    from models import StockAdjustment
                    ajuste = StockAdjustment(
                        product_id=producto.id,
                        admin_id=current_user.id,
                        tipo_movimiento="Venta Tienda",
                        stock_anterior=stock_anterior,
                        stock_nuevo=producto.stock_tienda
                    )
                    db.session.add(ajuste)

                if not es_obsequio and precio_venta_final < precio_limite_autorizado:
                    if current_user.rol != 'admin':
                        aprobacion = PriceApproval.query.filter(
                            PriceApproval.vendedor_id == current_user.id,
                            PriceApproval.product_id == (producto.id if producto else None),
                            PriceApproval.variant_id == variant_id,
                            PriceApproval.estado == 'aprobado',
                            PriceApproval.precio_aprobado <= precio_venta_final
                        ).order_by(PriceApproval.id.desc()).first()

                        if not aprobacion:
                            raise ValueError(f"No autorizado: El precio (${precio_venta_final:,.0f}) del producto '{producto.nombre}' está por debajo del mínimo permitido (${precio_limite_autorizado:,.0f}) y no cuenta con autorización remota.")

                        aprobacion.estado = 'utilizada'
                        aprobacion.fecha_resolucion = obtener_hora_bogota()
                        aprobacion.sale_id = nueva_venta.id

                detalle = SaleDetail(
                    sale_id=nueva_venta.id,
                    product_id=producto.id,
                    variant_id=variant_id,
                    tipo_item='PRODUCTO',
                    cantidad_vendida=cantidad_vendida,
                    precio_venta_final=precio_venta_final
                )
                db.session.add(detalle)
                db.session.flush()

                ajuste.tipo_movimiento = f"{ajuste.tipo_movimiento} #{nueva_venta.id}"
                monto_total += (precio_venta_final * cantidad_vendida)

        nueva_venta.monto_total = monto_total

        # Si venía de una Hoja de Trabajo (Orden de Taller), marcarla como COBRADO
        if work_order_id:
            orden = WorkOrder.query.get(work_order_id)
            if orden:
                orden.estado = 'COBRADO'
                if not nueva_venta.placa_vehiculo and orden.placa_vehiculo:
                    nueva_venta.placa_vehiculo = orden.placa_vehiculo
                if not nueva_venta.modelo_vehiculo and orden.modelo_vehiculo:
                    nueva_venta.modelo_vehiculo = orden.modelo_vehiculo
                if not nueva_venta.instalador_id and orden.instalador_id:
                    nueva_venta.instalador_id = orden.instalador_id
                if not nueva_venta.asesor_id and orden.asesor_id:
                    nueva_venta.asesor_id = orden.asesor_id

        # Registrar los pagos mixtos en la tabla sale_payments
        total_pagos = Decimal('0.00')
        for pago_info in pagos_data:
            metodo = (pago_info.get('metodo_pago') or 'efectivo').lower().strip()
            monto_pago = pago_info.get('monto')

            if monto_pago is None:
                monto_pago = monto_total
            else:
                monto_pago = Decimal(str(monto_pago))

            if monto_pago <= 0 and monto_total > 0:
                raise ValueError(f"El monto del pago por '{metodo}' debe ser mayor a 0.")

            pago = SalePayment(
                sale_id=nueva_venta.id,
                metodo_pago=metodo,
                monto=monto_pago
            )
            db.session.add(pago)
            total_pagos += monto_pago

        diferencia = monto_total - total_pagos

        if len(pagos_data) == 1:
            if nueva_venta.pagos:
                nueva_venta.pagos[0].monto = monto_total
                total_pagos = monto_total
        elif abs(diferencia) <= Decimal('0.50'):
            if nueva_venta.pagos:
                nueva_venta.pagos[-1].monto += diferencia
                total_pagos = monto_total

        if total_pagos != monto_total:
            raise ValueError(f"La suma de los pagos (${total_pagos}) no coincide con el total de la venta (${monto_total}). Diferencia: ${monto_total - total_pagos}.")

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Venta registrada e inventario descontado con éxito.',
            'sale_id': nueva_venta.id,
            'total': str(monto_total)
        }), 201

    except ValueError as val_err:
        db.session.rollback()
        return jsonify({'error': str(val_err)}), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ocurrió un error interno al procesar la venta: {str(e)}'}), 500


@sales_bp.route('/api/search_products')
@login_required
def api_search_products():
    query = request.args.get('q', '').strip()

    if not query:
        return jsonify([])

    is_admin = (current_user.rol == 'admin')
    query_norm = normalizar_texto(query)

    exacto = Product.query.filter(
        Product.activo.is_(True),
        or_(Product.sku.ilike(query), Product.codigo_barras.ilike(query))
    ).first()

    tokens = [t for t in query.split() if len(t) > 0]
    tokens_norm = [normalizar_texto(t) for t in tokens]

    base_query = Product.query.filter(Product.activo.is_(True))
    for token in tokens:
        wildcard_v = comodin_vocales(token)
        base_query = base_query.filter(
            or_(
                Product.sku.ilike(f'%{token}%'),
                Product.codigo_barras.ilike(f'%{token}%'),
                Product.nombre.ilike(f'%{token}%'),
                Product.nombre.ilike(f'%{wildcard_v}%'),
                Product.variantes.any(ProductVariant.nombre_variante.ilike(f'%{token}%')),
                Product.variantes.any(ProductVariant.nombre_variante.ilike(f'%{wildcard_v}%'))
            )
        )

    candidatos = base_query.limit(40).all()

    if len(candidatos) < 5:
        todos_tienda = Product.query.filter_by(activo=True).all()
        for p in todos_tienda:
            if p not in candidatos:
                candidatos.append(p)

    productos_filtrados = []
    for p in candidatos:
        p_nombre_norm = normalizar_texto(p.nombre)
        p_sku_norm = normalizar_texto(p.sku or p.codigo_barras)
        variantes_norms = [normalizar_texto(v.nombre_variante) for v in p.variantes]

        coincide_todo = True
        for tn in tokens_norm:
            en_nombre = (tn in p_nombre_norm)
            en_sku = (tn in p_sku_norm)
            en_variante = any(tn in vn for vn in variantes_norms)
            if not (en_nombre or en_sku or en_variante):
                coincide_todo = False
                break

        if coincide_todo:
            productos_filtrados.append(p)

    if exacto:
        if exacto in productos_filtrados:
            productos_filtrados.remove(exacto)
        productos_filtrados.insert(0, exacto)

    results = []
    for p in productos_filtrados[:20]:
        variantes_data = []
        matched_variant_id = None
        if p.variantes:
            for v in p.variantes:
                v_norm = normalizar_texto(v.nombre_variante)
                if any(tn in v_norm for tn in tokens_norm):
                    if not matched_variant_id:
                        matched_variant_id = v.id

                v_costo = float(v.precio_costo) if v.precio_costo is not None else float(p.costo or p.precio_costo or 0)
                v_dist = float(v.precio_distribuidor or v.precio_minimo or p.precio_distribuidor or p.precio_minimo or 0)
                v_loc = float(v.precio_local or p.precio_local or v.precio_final or v.precio_sugerido or p.precio_final or 0)
                v_fin = float(v.precio_final or v.precio_sugerido or p.precio_final or p.precio_sugerido or 0)
                v_limite = v_costo if is_admin else v_dist

                variantes_data.append({
                    'id': v.id,
                    'nombre': v.nombre_variante,
                    'stock': v.cantidad_stock,
                    'precio_costo': v_costo,
                    'precio_distribuidor': v_dist,
                    'precio_local': v_loc,
                    'precio_final': v_fin,
                    'precio_minimo': v_dist,
                    'precio_sugerido': v_fin,
                    'precio_limite': v_limite
                })

        p_costo = float(p.costo or p.precio_costo or 0)
        p_dist = float(p.precio_distribuidor or p.precio_minimo or 0)
        p_loc = float(p.precio_local or p.precio_final or p.precio_sugerido or 0)
        p_fin = float(p.precio_final or p.precio_sugerido or 0)
        p_limite = p_costo if is_admin else p_dist

        results.append({
            'id': p.id,
            'nombre': p.nombre,
            'sku': p.codigo_barras or p.sku,
            'tipo_inventario': p.tipo_inventario,
            'cantidad_stock': p.total_stock,
            'stock_tienda': p.stock_tienda,
            'stock_bodega': p.stock_bodega,
            'precio_distribuidor': p_dist,
            'precio_local': p_loc,
            'precio_final': p_fin,
            'precio_minimo': p_dist,
            'precio_sugerido': p_fin,
            'precio_costo': p_costo,
            'precio_limite': p_limite,
            'variantes': variantes_data,
            'matched_variant_id': matched_variant_id
        })

    return jsonify(results)


@sales_bp.route('/api/producto/<path:sku>', methods=['GET'])
@login_required
def api_buscar_producto(sku):
    sku_clean = sku.strip()
    is_admin = (current_user.rol == 'admin')

    producto = Product.query.filter(
        or_(Product.sku == sku_clean, Product.codigo_barras == sku_clean),
        Product.activo.is_(True)
    ).first()

    if not producto:
        producto = Product.query.filter(
            or_(Product.sku.ilike(sku_clean), Product.codigo_barras.ilike(sku_clean)),
            Product.activo.is_(True)
        ).first()

    if not producto:
        sku_norm = normalizar_texto(sku_clean)
        todos_tienda = Product.query.filter_by(activo=True).all()
        for p in todos_tienda:
            if normalizar_texto(p.sku or p.codigo_barras) == sku_norm or sku_norm in normalizar_texto(p.nombre):
                producto = p
                break

    if not producto:
        return jsonify({'error': f"Código o producto '{sku_clean}' no encontrado en la tienda"}), 404

    variantes_data = []
    for v in producto.variantes:
        v_costo = float(v.precio_costo) if v.precio_costo is not None else float(producto.costo or producto.precio_costo or 0)
        v_dist = float(v.precio_distribuidor or v.precio_minimo or producto.precio_distribuidor or 0)
        v_loc = float(v.precio_local or producto.precio_local or v.precio_final or v.precio_sugerido or producto.precio_final or 0)
        v_fin = float(v.precio_final or v.precio_sugerido or producto.precio_final or 0)
        v_limite = v_costo if is_admin else v_dist
        variantes_data.append({
            'id': v.id,
            'nombre': v.nombre_variante,
            'stock': v.cantidad_stock,
            'precio_distribuidor': v_dist,
            'precio_local': v_loc,
            'precio_final': v_fin,
            'precio_minimo': v_dist,
            'precio_limite': v_limite,
            'precio_sugerido': v_fin,
            'precio_costo': v_costo
        })

    p_costo = float(producto.costo or producto.precio_costo or 0)
    p_dist = float(producto.precio_distribuidor or producto.precio_minimo or 0)
    p_loc = float(producto.precio_local or producto.precio_final or producto.precio_sugerido or 0)
    p_fin = float(producto.precio_final or producto.precio_sugerido or 0)

    return jsonify({
        'id': producto.id,
        'nombre': producto.nombre,
        'sku': producto.codigo_barras or producto.sku,
        'tipo_inventario': producto.tipo_inventario,
        'cantidad_stock': producto.total_stock,
        'precio_distribuidor': p_dist,
        'precio_local': p_loc,
        'precio_final': p_fin,
        'precio_minimo': p_dist,
        'precio_limite': p_costo if is_admin else p_dist,
        'precio_sugerido': p_fin,
        'variantes': variantes_data,
        'auto_select_variant': None
    })


@sales_bp.route('/recibo/<int:sale_id>', methods=['GET'])
def imprimir_ticket(sale_id):
    venta = Sale.query.get_or_404(sale_id)
    return render_template('sales/ticket.html', venta=venta)


@sales_bp.route('/historial', methods=['GET'])
@login_required
@admin_required
def historial():
    hoy_bogota = obtener_hora_bogota().strftime('%Y-%m-%d')

    fecha_inicio = request.args.get('fecha_inicio', hoy_bogota)
    fecha_fin = request.args.get('fecha_fin', hoy_bogota)

    query = Sale.query.options(joinedload(Sale.vendedor))

    if fecha_inicio:
        inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
        query = query.filter(Sale.fecha_venta >= inicio_dt)

    if fecha_fin:
        fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
        query = query.filter(Sale.fecha_venta < fin_dt + timedelta(days=1))

    ventas = query.order_by(Sale.fecha_venta.desc()).all()

    total_efectivo = Decimal('0')
    total_nequi = Decimal('0')
    total_bancolombia = Decimal('0')
    total_daviplata = Decimal('0')
    total_bolt = Decimal('0')
    total_transferencia_legacy = Decimal('0')
    total_mixto = 0

    for v in ventas:
        if v.pagos:
            for pago in v.pagos:
                metodo = (pago.metodo_pago or '').lower().strip()
                if metodo == 'efectivo':
                    total_efectivo += pago.monto
                elif metodo == 'nequi':
                    total_nequi += pago.monto
                elif metodo == 'bancolombia':
                    total_bancolombia += pago.monto
                elif metodo == 'daviplata':
                    total_daviplata += pago.monto
                elif metodo in ['bolt', 'bold']:
                    total_bolt += pago.monto
                elif metodo == 'transferencia':
                    total_transferencia_legacy += pago.monto
                else:
                    total_transferencia_legacy += pago.monto
            if len(v.pagos) > 1:
                total_mixto += 1
        else:
            metodo_v = (v.metodo_pago or '').lower().strip()
            if metodo_v == 'efectivo':
                total_efectivo += v.monto_total
            elif metodo_v == 'nequi':
                total_nequi += v.monto_total
            elif metodo_v == 'bancolombia':
                total_bancolombia += v.monto_total
            elif metodo_v == 'daviplata':
                total_daviplata += v.monto_total
            elif metodo_v in ['bolt', 'bold']:
                total_bolt += v.monto_total
            elif metodo_v == 'transferencia':
                total_transferencia_legacy += v.monto_total
            else:
                total_transferencia_legacy += v.monto_total

    total_general = total_efectivo + total_nequi + total_bancolombia + total_daviplata + total_bolt + total_transferencia_legacy
    total_digital = total_nequi + total_bancolombia + total_daviplata + total_bolt + total_transferencia_legacy
    total_operaciones = len(ventas)
    ticket_promedio = (total_general / Decimal(total_operaciones)) if total_operaciones > 0 else Decimal('0')

    return render_template('sales/historial.html',
                           ventas=ventas,
                           total_general=total_general,
                           total_digital=total_digital,
                           total_operaciones=total_operaciones,
                           ticket_promedio=ticket_promedio,
                           total_efectivo=total_efectivo,
                           total_nequi=total_nequi,
                           total_bancolombia=total_bancolombia,
                           total_daviplata=total_daviplata,
                           total_bolt=total_bolt,
                           total_transferencia_legacy=total_transferencia_legacy,
                           total_mixto=total_mixto,
                           fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin)


@sales_bp.route('/ventas_hoy', methods=['GET'])
@login_required
def ventas_hoy():
    hoy_bogota = obtener_hora_bogota().date()
    inicio_dt = datetime.combine(hoy_bogota, datetime.min.time())
    fin_dt = datetime.combine(hoy_bogota, datetime.max.time())

    ventas = Sale.query.options(joinedload(Sale.vendedor)).filter(
        Sale.fecha_venta >= inicio_dt,
        Sale.fecha_venta <= fin_dt
    ).order_by(Sale.fecha_venta.desc()).all()

    total_efectivo = Decimal('0')
    total_transferencias = Decimal('0')
    total_mixto = 0

    for v in ventas:
        if v.pagos:
            for pago in v.pagos:
                if pago.metodo_pago == 'efectivo':
                    total_efectivo += pago.monto
                else:
                    total_transferencias += pago.monto
            if len(v.pagos) > 1:
                total_mixto += 1
        else:
            if v.metodo_pago == 'efectivo':
                total_efectivo += v.monto_total
            else:
                total_transferencias += v.monto_total

    return render_template('sales/ventas_hoy.html',
                           ventas=ventas,
                           total_efectivo=total_efectivo,
                           total_transferencias=total_transferencias,
                           total_mixto=total_mixto,
                           hoy=hoy_bogota.strftime('%Y-%m-%d'))


@sales_bp.route('/eliminar/<int:sale_id>', methods=['POST'])
@login_required
@admin_required
def eliminar_venta(sale_id):
    venta = Sale.query.get_or_404(sale_id)

    caja_cerrada = ArqueoCaja.query.filter_by(fecha_arqueo=venta.fecha_venta.date()).first()
    if caja_cerrada:
        flash(f'No se puede anular la venta #{venta.id} porque la caja del día {venta.fecha_venta.date().strftime("%Y-%m-%d")} ya fue cerrada.', 'danger')
        return redirect(url_for('sales_bp.historial'))

    try:
        from models import StockAdjustment
        for detalle in venta.detalles:
            if detalle.variant_id:
                variante = ProductVariant.query.with_for_update().get(detalle.variant_id)
                if variante:
                    stock_anterior = variante.cantidad_stock
                    variante.cantidad_stock += detalle.cantidad_vendida

                    ajuste = StockAdjustment(
                        product_id=detalle.product_id,
                        admin_id=current_user.id,
                        tipo_movimiento=f"Anulación Venta #{venta.id} (Subcat: {variante.nombre_variante})",
                        stock_anterior=stock_anterior,
                        stock_nuevo=variante.cantidad_stock
                    )
                    db.session.add(ajuste)

                producto = Product.query.with_for_update().get(detalle.product_id)
                if producto:
                    producto.stock_tienda = (producto.stock_tienda or 0) + detalle.cantidad_vendida
                    producto.cantidad_stock = producto.stock_tienda
            elif detalle.product_id:
                producto = Product.query.with_for_update().get(detalle.product_id)
                if producto:
                    stock_anterior = producto.stock_tienda or producto.cantidad_stock
                    producto.stock_tienda = stock_anterior + detalle.cantidad_vendida
                    producto.cantidad_stock = producto.stock_tienda

                    ajuste = StockAdjustment(
                        product_id=producto.id,
                        admin_id=current_user.id,
                        tipo_movimiento=f"Anulación Venta #{venta.id}",
                        stock_anterior=stock_anterior,
                        stock_nuevo=producto.stock_tienda
                    )
                    db.session.add(ajuste)

        PriceApproval.query.filter_by(sale_id=venta.id).update({'sale_id': None, 'estado': 'cancelada'})

        db.session.delete(venta)
        db.session.commit()
        flash('Venta anulada y stock devuelto exitosamente.', 'success')

    except Exception as e:
        db.session.rollback()
        import logging
        logging.error(f"Error al anular venta #{sale_id}: {str(e)}", exc_info=True)
        flash('Ocurrió un error al anular la venta.', 'danger')

    fecha_inicio = request.form.get('fecha_inicio')
    fecha_fin = request.form.get('fecha_fin')
    if fecha_inicio or fecha_fin:
        return redirect(url_for('sales_bp.historial', fecha_inicio=fecha_inicio, fecha_fin=fecha_fin))
    return redirect(url_for('sales_bp.historial'))


@sales_bp.route('/editar_pago/<int:sale_id>', methods=['POST'])
@login_required
@admin_required
def editar_pago(sale_id):
    venta = Sale.query.get_or_404(sale_id)

    fecha_inicio = request.form.get('fecha_inicio', '')
    fecha_fin = request.form.get('fecha_fin', '')

    caja_cerrada = ArqueoCaja.query.filter_by(fecha_arqueo=venta.fecha_venta.date()).first()
    if caja_cerrada:
        flash(f'No se puede modificar el pago de la venta #{venta.id} porque la caja del día {venta.fecha_venta.date().strftime("%Y-%m-%d")} ya fue cerrada.', 'danger')
        return redirect(url_for('sales_bp.historial', fecha_inicio=fecha_inicio, fecha_fin=fecha_fin))

    try:
        tipo_pago = request.form.get('tipo_pago', 'unico')

        if tipo_pago == 'unico':
            metodo = request.form.get('metodo_pago_unico', 'efectivo').lower().strip()
            if metodo not in ['efectivo', 'nequi', 'bancolombia', 'daviplata', 'bolt', 'credito']:
                metodo = 'efectivo'

            SalePayment.query.filter_by(sale_id=venta.id).delete()

            nuevo_pago = SalePayment(
                sale_id=venta.id,
                metodo_pago=metodo,
                monto=venta.monto_total
            )
            db.session.add(nuevo_pago)
            venta.metodo_pago = metodo

        elif tipo_pago == 'mixto':
            metodos_posibles = ['efectivo', 'nequi', 'bancolombia', 'daviplata', 'bolt', 'credito']
            nuevos_pagos = []
            suma_montos = Decimal('0.00')

            for m in metodos_posibles:
                raw_val = request.form.get(f'monto_{m}', '0').replace(',', '').replace('$', '').strip()
                if raw_val:
                    try:
                        monto_decimal = Decimal(raw_val)
                        if monto_decimal > Decimal('0'):
                            nuevos_pagos.append((m, monto_decimal))
                            suma_montos += monto_decimal
                    except Exception:
                        pass

            if not nuevos_pagos:
                flash('Debe especificar al menos un método con monto mayor a $0 en pago mixto.', 'warning')
                return redirect(url_for('sales_bp.historial', fecha_inicio=fecha_inicio, fecha_fin=fecha_fin))

            if abs(suma_montos - venta.monto_total) > Decimal('0.01'):
                flash(f'La suma de los pagos (${suma_montos:,.0f}) no coincide con el total de la factura (${venta.monto_total:,.0f}).', 'danger')
                return redirect(url_for('sales_bp.historial', fecha_inicio=fecha_inicio, fecha_fin=fecha_fin))

            SalePayment.query.filter_by(sale_id=venta.id).delete()

            for m, monto_val in nuevos_pagos:
                p = SalePayment(
                    sale_id=venta.id,
                    metodo_pago=m,
                    monto=monto_val
                )
                db.session.add(p)

            if len(nuevos_pagos) == 1:
                venta.metodo_pago = nuevos_pagos[0][0]
            else:
                venta.metodo_pago = 'mixto'

        db.session.commit()
        flash(f'¡Método de pago de la venta #{venta.id} actualizado exitosamente!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error al actualizar el pago: {str(e)}', 'danger')

    return redirect(url_for('sales_bp.historial', fecha_inicio=fecha_inicio, fecha_fin=fecha_fin))


@sales_bp.route('/catalogo', methods=['GET'])
@login_required
def catalogo():
    query_str = request.args.get('q', '').strip()
    filtro_foto = request.args.get('foto', 'todos').strip()

    base_query = Product.query.filter(Product.activo.is_(True))

    total_tienda = base_query.count()
    total_con_foto = base_query.filter(Product.imagen.isnot(None), Product.imagen != '').count()
    total_sin_foto = total_tienda - total_con_foto

    if query_str:
        search_term = f"%{query_str}%"
        base_query = base_query.filter(
            or_(
                Product.sku.ilike(search_term),
                Product.codigo_barras.ilike(search_term),
                Product.nombre.ilike(search_term)
            )
        )

    if filtro_foto == 'con_foto':
        base_query = base_query.filter(Product.imagen.isnot(None), Product.imagen != '')
    elif filtro_foto == 'sin_foto':
        base_query = base_query.filter(or_(Product.imagen.is_(None), Product.imagen == ''))

    productos = base_query.order_by(Product.nombre.asc()).all()

    return render_template(
        'sales/catalogo.html',
        productos=productos,
        q=query_str,
        filtro_foto=filtro_foto,
        total_tienda=total_tienda,
        total_con_foto=total_con_foto,
        total_sin_foto=total_sin_foto
    )


@sales_bp.route('/catalogo/cambiar_foto/<int:id>', methods=['POST'])
@login_required
def cambiar_foto_catalogo(id):
    producto = Product.query.get_or_404(id)
    q = request.form.get('q', '')
    foto = request.form.get('foto', 'todos')

    if 'imagen' not in request.files:
        flash('No se seleccionó ningún archivo de imagen.', 'warning')
        return redirect(url_for('sales_bp.catalogo', q=q, foto=foto))

    file = request.files['imagen']
    if not file or file.filename == '':
        flash('Por favor selecciona una foto para subir.', 'warning')
        return redirect(url_for('sales_bp.catalogo', q=q, foto=foto))

    sec_name = secure_filename(file.filename)
    ext = sec_name.rsplit('.', 1)[-1].lower() if '.' in sec_name else ''
    allowed_exts = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
    if ext not in allowed_exts:
        flash('Formato no permitido. Formatos válidos: PNG, JPG, JPEG, WEBP.', 'danger')
        return redirect(url_for('sales_bp.catalogo', q=q, foto=foto))

    try:
        os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
        unique_name = f"prod_{producto.id}_{uuid.uuid4().hex[:8]}_{int(time.time())}.{ext}"
        file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name))
        producto.imagen = unique_name
        db.session.commit()
        flash(f'¡Foto de "{producto.nombre}" actualizada con éxito!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al guardar la imagen: {str(e)}', 'danger')

    return redirect(url_for('sales_bp.catalogo', q=q, foto=foto))


@sales_bp.route('/catalogo/eliminar_foto/<int:id>', methods=['POST'])
@login_required
def eliminar_foto_catalogo(id):
    producto = Product.query.get_or_404(id)
    q = request.form.get('q', '')
    foto = request.form.get('foto', 'todos')

    try:
        producto.imagen = None
        db.session.commit()
        flash(f'Foto de "{producto.nombre}" eliminada correctamente.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar la foto: {str(e)}', 'danger')

    return redirect(url_for('sales_bp.catalogo', q=q, foto=foto))


@sales_bp.route('/caja_visual', methods=['GET'])
@login_required
def caja_visual():
    hoy_bogota = obtener_hora_bogota()
    productos = Product.query.filter(Product.activo.is_(True)).order_by(Product.nombre.asc()).all()
    servicios = InstallationService.query.filter_by(activo=True).order_by(InstallationService.nombre.asc()).all()
    instaladores = Installer.query.filter_by(activo=True).order_by(Installer.nombre.asc()).all()
    asesores = User.query.order_by(User.nombre.asc()).all()
    clientes = Customer.query.order_by(Customer.nombre.asc()).all()

    hoja_id = request.args.get('hoja_id', type=int)
    orden_trabajo = None
    orden_preload = None
    if hoja_id:
        orden_trabajo = WorkOrder.query.get(hoja_id)
        if orden_trabajo:
            items_preload = []
            for it in orden_trabajo.items:
                if it.tipo == 'SERVICIO' and it.servicio:
                    items_preload.append({
                        'tipo_item': 'SERVICIO',
                        'service_id': it.servicio.id,
                        'installer_id': orden_trabajo.instalador_id,
                        'product_id': None,
                        'variant_id': None,
                        'nombre': f"🔧 {it.servicio.nombre}",
                        'sku': 'SERVICIO',
                        'precio_final': float(it.precio_unitario or it.servicio.precio_estandar or 0),
                        'precio_cliente_final': float(it.precio_unitario or it.servicio.precio_estandar or 0),
                        'precio_local': float(it.precio_unitario or it.servicio.precio_estandar or 0),
                        'precio_distribuidor': float(it.precio_unitario or it.servicio.precio_estandar or 0),
                        'precio_minimo': 0,
                        'cantidad': int(it.cantidad or 1),
                        'max_stock': 999
                    })
                elif it.producto:
                    p = it.producto
                    items_preload.append({
                        'tipo_item': 'PRODUCTO',
                        'service_id': None,
                        'installer_id': None,
                        'product_id': p.id,
                        'variant_id': None,
                        'nombre': p.nombre,
                        'sku': p.codigo_barras or p.sku or '',
                        'precio_final': float(it.precio_unitario or p.precio_final or p.precio_sugerido or 0),
                        'precio_cliente_final': float(p.precio_final or p.precio_sugerido or 0),
                        'precio_local': float(p.precio_local or p.precio_final or p.precio_sugerido or 0),
                        'precio_distribuidor': float(p.precio_distribuidor or p.precio_minimo or 0),
                        'precio_minimo': float(p.precio_distribuidor or p.precio_minimo or 0),
                        'cantidad': int(it.cantidad or 1),
                        'max_stock': max(int(it.cantidad or 1), int(p.stock_tienda or p.cantidad_stock or 1))
                    })
            orden_preload = {
                'id': orden_trabajo.id,
                'numero_orden': orden_trabajo.numero_orden,
                'placa_vehiculo': orden_trabajo.placa_vehiculo or '',
                'modelo_vehiculo': orden_trabajo.modelo_vehiculo or '',
                'cliente_id': orden_trabajo.cliente_id,
                'cliente_nombre': orden_trabajo.cliente.nombre if orden_trabajo.cliente else '',
                'cliente_documento': orden_trabajo.cliente.documento if orden_trabajo.cliente else '',
                'cliente_telefono': orden_trabajo.cliente.telefono if orden_trabajo.cliente else '',
                'asesor_id': orden_trabajo.asesor_id,
                'instalador_id': orden_trabajo.instalador_id,
                'items': items_preload
            }

    return render_template(
        'sales/caja_visual.html',
        productos=productos,
        servicios=servicios,
        instaladores=instaladores,
        asesores=asesores,
        clientes=clientes,
        orden_trabajo=orden_trabajo,
        orden_preload=orden_preload,
        hoy=hoy_bogota.strftime('%Y-%m-%d')
    )
