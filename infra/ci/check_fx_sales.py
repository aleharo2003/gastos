"""Prueba el saldo, la referencia histórica y los reintentos en la base desechable."""
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text

from app.db.connection import create_migration_engine, create_runtime_engine
from app.db.unit_of_work import runtime_transaction
from app.incomes import account_balance
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
        print('OK: venta USD, saldos por moneda, referencia congelada y reintento.', flush=True)
    finally:
        with migrator.begin() as c:
            for table,column in (('ofertas_usd','espacio_id'), ('ventas_usd','espacio_id'), ('cuentas','espacio_id'), ('miembros_espacio','espacio_id'),
                                 ('espacios','id'), ('perfiles','usuario_id')):
                c.execute(text(f'DELETE FROM public.{table} WHERE {column}=:u'), {'u': owner})
        runtime.dispose()
        migrator.dispose()
