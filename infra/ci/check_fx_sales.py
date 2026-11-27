"""Prueba el saldo, la referencia histórica y los reintentos en la base desechable."""
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text

from app.db.connection import create_migration_engine, create_runtime_engine
from app.db.unit_of_work import runtime_transaction
from app.incomes import account_balance
from app.movements import list_movements, parse_cursor
from app.usd_holdings import usd_holding
from app.usd_reference import ManualRate, save_rate
from app.usd_offers import AcceptOffer, OfferInput, accept_offer, save_offer
from app.usd_sales import SaleInput, list_sales, local_today, sale_analysis, save_sale


def check_fx_sales(runtime_url, migration_url):
    runtime = create_runtime_engine(runtime_url)
    migrator = create_migration_engine(migration_url)
    owner, origin, destination = (uuid4() for _ in range(3))
    day = local_today()
    try:
        with runtime_transaction(runtime, usuario_id=owner) as s:
            s.execute(text('SELECT public.crear_espacio_personal()'))
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as s:
            s.execute(text("""INSERT INTO public.cuentas(id,espacio_id,nombre,tipo,moneda,saldo_inicial)
                VALUES (:a,:s,'USD','efectivo','USD',100),(:b,:s,'ARS','efectivo','ARS',0)"""),
                {'a': origin, 'b': destination, 's': owner})
            save_rate(s, owner, owner, ManualRate(fecha=day.isoformat(), tasa='1600'), day)
            sale = SaleInput(id=uuid4(), origen_id=origin, destino_id=destination,
                             fecha=day.isoformat(), contraparte='Comprador', usd='25.00', ars='42500.10')
            first = save_sale(s, owner, owner, sale)
            assert first['tasa'] == '1700.0040' and first['referencia'] == '1600.0000'
            assert first['diferencia_pct'] == '6.25'
            save_rate(s, owner, owner, ManualRate(fecha=day.isoformat(), tasa='1750'), day)
            assert save_sale(s, owner, owner, sale) == first
            assert list_sales(s, owner, owner, 0)['items'] == [first]
            totals = {row['moneda']: row for row in account_balance(s, owner, owner)['totales']}
            assert totals['USD']['saldo'] == '75.00' and totals['USD']['gastos'] == '0.00'
            assert totals['ARS']['saldo'] == '42500.10' and totals['ARS']['ingresos'] == '0.00'
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as s:
            wrong = sale.model_copy(update={'id': uuid4(), 'origen_id': destination, 'destino_id': origin})
            try:
                save_sale(s, owner, owner, wrong)
            except HTTPException as error:
                assert error.status_code == 422
            else:
                raise AssertionError('La venta aceptó cuentas con monedas incompatibles')
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as s:
            round_id = uuid4()
            low = OfferInput(id=uuid4(), ronda=round_id, tasa='1700', contraparte='Ana')
            high = OfferInput(id=uuid4(), ronda=round_id, tasa='1800', contraparte='Luis')
            assert save_offer(s, owner, owner, low)['oferta']['referencia'] == '1750.0000'
            save_offer(s, owner, owner, high)
            acceptance = AcceptOffer(oferta_id=low.id, origen_id=origin, destino_id=destination,
                                     usd='5.00', fecha=day.isoformat())
            try:
                accept_offer(s, owner, owner, acceptance)
            except HTTPException as error:
                assert error.status_code == 409
            else:
                raise AssertionError('La aceptación omitió el aviso de la mejor oferta')
            accepted = acceptance.model_copy(update={'confirmar_mejor': True})
            result = accept_offer(s, owner, owner, accepted)
            assert result['venta']['ars'] == '8500.00'
            assert accept_offer(s, owner, owner, accepted) == result
            states = dict(s.execute(text('SELECT id,estado FROM public.ofertas_usd WHERE ronda=:r'),
                                    {'r': round_id}).tuples().all())
            assert states == {low.id: 'aceptada', high.id: 'rechazada'}
            report = sale_analysis(s, owner, owner)
            assert report['rondas'][0]['diferencia_ars'] == '500.00'
            assert report['rondas'][0]['mejor_contraparte'] == 'Luis'
            ranks = {row['contraparte']: row for row in report['contrapartes']}
            assert ranks['Luis']['operaciones'] == 0 and ranks['Luis']['diferencia'] is None
            assert ranks['Ana']['operaciones'] == 1 and ranks['Ana']['comparadas'] == 1
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as s:
            unusual = sale.model_copy(update={'id': uuid4(), 'ars': sale.ars * 2})
            try:
                save_sale(s, owner, owner, unusual)
            except HTTPException as error:
                assert error.status_code == 409 and error.detail['codigo'] == 'cotizacion_atipica'
            else:
                raise AssertionError('Venta atípica aceptada sin confirmar')
            assert save_sale(s, owner, owner, unusual.model_copy(update={'confirmar_atipico': True}))['usd'] == '25.00'
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as s:
            purchased, receiving = uuid4(), uuid4()
            s.execute(text("""INSERT INTO public.cuentas(id,espacio_id,nombre,tipo,moneda,saldo_inicial)
                VALUES (:a,:s,'Compras USD','efectivo','USD',0),(:b,:s,'Destino USD','efectivo','USD',0)"""),
                {'a': purchased, 'b': receiving, 's': owner})
            buy = SaleInput(id=uuid4(), origen_id=destination, destino_id=purchased, tipo='compra',
                            fecha=day.isoformat(), contraparte='Compra prueba', usd='100.00', ars='160000.00')
            saved = save_sale(s, owner, owner, buy)
            assert saved['tipo'] == 'compra' and save_sale(s, owner, owner, buy) == saved
            assert usd_holding(s, owner, purchased)['costo_promedio'] == '1600.0000'
            save_sale(s, owner, owner, buy.model_copy(update={'id': uuid4(), 'usd': buy.usd / 2, 'ars': buy.ars * 9 / 16}))
            holding = usd_holding(s, owner, purchased)
            assert holding == {
                'usd': '150.00', 'costo_promedio': '1666.6667', 'valor_ars': '262500.00',
                'resultado_ars': '12500.00', 'resultado_pct': '5.00', 'fecha_referencia': day.isoformat(),
            }
            sell = sale.model_copy(update={'id': uuid4(), 'origen_id': purchased})
            save_sale(s, owner, owner, sell)
            usd = account_balance(s, owner, owner, purchased)['totales'][1]
            assert usd['saldo'] == '125.00' and usd['transferencias_entrada'] == '150.00'
            assert account_balance(s, owner, owner, destination)['totales'][0]['transferencias_salida'] == '250000.00'
            s.execute(text("""INSERT INTO public.transferencias
                (id,espacio_id,usuario_id,origen_id,destino_id,fecha,descripcion,moneda,importe)
                VALUES (:id,:s,:s,:a,:b,:day,'Mover USD','USD',25)"""),
                {'id': uuid4(), 's': owner, 'a': purchased, 'b': receiving, 'day': day})
            assert usd_holding(s, owner, purchased)['usd'] == '100.00'
            assert usd_holding(s, owner, receiving)['costo_promedio'] == '1666.6667'
            assert usd_holding(s, owner, origin)['resultado_ars'] is None
            filters = {'desde': day, 'hasta': day, 'tipo': 'cambio', 'moneda': None,
                       'cuenta': purchased, 'texto': ''}
            exchange = list_movements(s, owner, owner, filters, None)
            assert len(exchange['items']) == 3
            by_id = {row['id']: row for row in exchange['items']}
            assert (by_id[str(buy.id)]['moneda'], by_id[str(buy.id)]['importe'],
                    by_id[str(buy.id)]['moneda_destino'], by_id[str(buy.id)]['importe_destino']) == (
                        'ARS', '160000.00', 'USD', '100.00')
            assert exchange['totales'] == [{
                'moneda': 'USD', 'ingresos': '0.00', 'gastos': '0.00', 'transferencias': '0.00',
                'cambio_entrada': '150.00', 'cambio_salida': '25.00', 'variacion_cuenta': '125.00',
            }]
            pesos = filters | {'cuenta': destination, 'moneda': 'ARS', 'texto': 'compra prueba'}
            result = list_movements(s, owner, owner, pesos, None)
            assert len(result['items']) == 2 and result['totales'][0]['variacion_cuenta'] == '-250000.00'
            assert list_movements(s, owner, owner, pesos | {'moneda': 'USD'}, None)['items'] == []
            assert list_movements(s, owner, owner, filters | {'anulados': True}, None)['items'] == []
            assert parse_cursor(f'{day.isoformat()}/cambio/{buy.id}') == (day, 'cambio', buy.id)
            print('OK: cambios en historial, filtros por cuenta y moneda y variación de saldo.', flush=True)
            assert 'Compra prueba' not in {row['contraparte'] for row in sale_analysis(s, owner, owner)['contrapartes']}
        print('OK: cambios USD, saldos por moneda, referencia congelada, reintentos y costo promedio.', flush=True)
    finally:
        with migrator.begin() as c:
            for table,column in (('ofertas_usd','espacio_id'), ('ventas_usd','espacio_id'), ('transferencias','espacio_id'), ('cuentas','espacio_id'), ('miembros_espacio','espacio_id'),
                                 ('espacios','id'), ('perfiles','usuario_id')):
                c.execute(text(f'DELETE FROM public.{table} WHERE {column}=:u'), {'u': owner})
        runtime.dispose()
        migrator.dispose()
