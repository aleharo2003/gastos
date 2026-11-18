"""Valida generación, ajuste en cadena y pagos sobre PostgreSQL con los roles reales."""
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.accounts import AccountInput, create_account
from app.adjustment_indices import IndexValueInput, import_index_values, save_index_value
from app.commitments import (
    CommitmentInput, PaymentInput, create_commitment, due_overview, list_installments, monthly_due, pay_installment,
)
from app.db.connection import create_migration_engine, create_runtime_engine
from app.db.unit_of_work import runtime_transaction


def check_indexed_commitments(runtime_url, migration_url, jobs_url):
    runtime = create_runtime_engine(runtime_url)
    migrator = create_migration_engine(migration_url)
    jobs = create_engine(jobs_url, hide_parameters=True)
    owner, other, account, foreign, plan, foreign_plan = (uuid4() for _ in range(6))
    today = datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()
    current = today.replace(day=1)
    previous, older, future = (monthly_due(current, offset) for offset in (-1, -2, 1))

    def run(operation, space=owner):
        with runtime_transaction(runtime, usuario_id=space, espacio_id=space) as session:
            return operation(session, space, space)

    def set_rate(period, rate, space=owner):
        value = IndexValueInput(indice='CAC', periodo=period.strftime('%Y-%m'), variacion=rate)
        return run(lambda s, u, w: save_index_value(s, u, w, value), space)

    def create(identifier, wallet, first, space=owner):
        body = CommitmentInput(id=identifier, cuenta_id=wallet, nombre='Terreno', importe='100.00',
                               moneda='ARS', primer_vencimiento=first.isoformat(), total_cuotas=3, indice_ajuste='CAC')
        return run(lambda s, u, w: create_commitment(s, u, w, body), space)

    def installments(identifier=plan, space=owner):
        return run(lambda s, u, w: list_installments(s, u, w, identifier), space)['items']

    def amounts(rows):
        return [(row['importe'], row.get('pendiente_ajuste', False)) for row in rows]

    try:
        for user, wallet in ((owner, account), (other, foreign)):
            with runtime_transaction(runtime, usuario_id=user) as session:
                session.execute(text('SELECT public.crear_espacio_personal()'))
            run(lambda s, u, w: create_account(s, u, w, AccountInput(id=wallet, nombre='Caja')), user)

        set_rate(older, '10')
        set_rate(current, '90', other)
        response = create(plan, account, older)
        assert response['indice_ajuste'] == 'CAC'
        assert response['total'] == '364.10'
        assert amounts(installments()) == [('110.00', False), ('121.00', True), ('133.10', True)]
        assert create(plan, account, older) == response

        def due_items():
            groups = run(lambda s, u, w: due_overview(s, u, w, today))['grupos']
            return {row['numero']: row for group in groups.values() for row in group['items']}

        assert due_items()[2]['pendiente_ajuste']
        pending = installments()[1]
        payment = PaymentInput(id=uuid4(), cuenta_id=account, fecha=today.isoformat(), importe='110.00')
        try:
            run(lambda s, u, w: pay_installment(s, u, w, pending['id'], payment))
        except HTTPException as error:
            assert error.status_code == 409
        else:
            raise AssertionError('La API aceptó un pago sobre una cuota a ajustar')
        first = installments()[0]
        run(lambda s, u, w: pay_installment(s, u, w, first['id'], payment))
        paid = installments()[0]

        set_rate(current, '-5')
        assert amounts(installments()) == [('110.00', False), ('121.00', True), ('114.95', True)]
        csv = f'indice,periodo,variacion\nCAC,{previous:%Y-%m},20\n'
        assert run(lambda s, u, w: import_index_values(s, u, w, csv)) == {'importadas': 1, 'existentes': 0}
        revised = installments()
        assert revised[0] == paid and revised[0]['estado'] == 'pagada'
        assert amounts(revised) == [('110.00', False), ('132.00', False), ('125.40', False)]
        assert 'pendiente_ajuste' not in due_items()[2]
        assert revised[1]['id'] == pending['id'] and revised[1]['version'] > pending['version']

        create(foreign_plan, foreign, future, other)
        assert amounts(installments(foreign_plan, other)) == [('190.00', True)]
        set_rate(future, '6')
        assert amounts(installments(foreign_plan, other)) == [('190.00', True)]

        # Simula una cuota mensual omitida y prueba la entrada real del job.
        with migrator.begin() as connection:
            connection.execute(text('DELETE FROM public.cuotas WHERE espacio_id=:s AND compromiso_id=:c AND numero=3'),
                               {'s': owner, 'c': plan})
        with jobs.begin() as connection:
            assert connection.execute(text('SELECT public.generar_cuotas_mes()')).scalar_one() >= 1
            assert connection.execute(text('SELECT public.generar_cuotas_mes()')).scalar_one() == 0
        assert amounts(installments()) == amounts(revised)
    finally:
        runtime.dispose()
        migrator.dispose()
        jobs.dispose()
