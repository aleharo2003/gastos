"""Cuotas elegibles por fecha argentina, configuración, saldo y espacio."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Barrier
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, text

from app.accounts import AccountInput, create_account
from app.commitments import CommitmentInput, PaymentInput, create_commitment, list_installments, pay_installment
from app.db.connection import create_migration_engine, create_runtime_engine
from app.db.unit_of_work import runtime_transaction
from app.reminder_preferences import DEFAULTS, ReminderPreferences, save_preferences


def check_reminder_candidates(runtime_url, migration_url, jobs_url):
    runtime = create_runtime_engine(runtime_url)
    migrator = create_migration_engine(migration_url)
    jobs = create_engine(jobs_url, hide_parameters=True)
    owner, other, spectator, wallet, other_wallet = (uuid4() for _ in range(5))

    def run(operation, actor=owner):
        with runtime_transaction(runtime, usuario_id=actor, espacio_id=actor) as session:
            return operation(session, actor, actor)

    def preferences(actor, **overrides):
        body = ReminderPreferences(**(DEFAULTS | overrides))
        run(lambda s, u, w: save_preferences(s, u, w, body), actor)

    def make_quota(day, name, actor=owner, account=wallet, currency='ARS'):
        body = CommitmentInput(id=uuid4(), cuenta_id=account, nombre=name, moneda=currency,
                               importe='100', primer_vencimiento=day, total_cuotas=1)

        def create(session, user, space):
            create_commitment(session, user, space, body)
            return list_installments(session, user, space, body.id)['items'][0]['id']

        return run(create, actor)

    def candidates(hour=12, minute=0):
        instant = datetime(2026, 2, 11, hour, minute, tzinfo=UTC)
        with migrator.connect() as connection:
            rows = connection.execute(text('SELECT * FROM public.candidatos_avisos_email(:instant)'),
                                      {'instant': instant}).mappings().all()
        return {row['nombre']: row for row in rows if row['usuario_id'] in (owner, other, spectator)}

    def ready(instant):
        with migrator.connect() as connection:
            rows = connection.execute(text('SELECT * FROM public.avisos_email_para_preparar(:instant)'),
                                      {'instant': instant}).mappings().all()
            return {str(row['cuota_id']): row for row in rows if row['usuario_id'] == owner}

    def enqueue(instant):
        with migrator.begin() as connection:
            return connection.execute(text('SELECT public.encolar_avisos_email(:instant)'),
                                      {'instant': instant}).scalar_one()

    try:
        for actor in (owner, other, spectator):
            with runtime_transaction(runtime, usuario_id=actor) as session:
                session.execute(text('SELECT public.crear_espacio_personal()'))
        for actor, account in ((owner, wallet), (other, other_wallet)):
            run(lambda s, u, w: create_account(s, u, w, AccountInput(id=account, nombre='Caja')), actor)
        with migrator.begin() as connection:
            connection.execute(text("""
                INSERT INTO public.miembros_espacio (usuario_id, espacio_id, rol)
                VALUES (:spectator, :owner, 'lector')
            """), {'spectator': spectator, 'owner': owner})

        upcoming = make_quota('2026-02-13', 'En el límite', currency='USD')
        make_quota('2026-02-14', 'Fuera del plazo')
        make_quota('2026-02-10', 'Vencida')
        make_quota('2026-02-11', 'Vence hoy')
        skip = make_quota('2026-02-12', 'No aplica')
        draft = make_quota('2026-02-12', 'Borrador')
        indexed = make_quota('2026-02-12', 'Índice provisorio')
        paid = make_quota('2026-02-11', 'Pagada')
        make_quota('2026-02-11', 'Otro espacio', other, other_wallet)

        for quota, amount in ((upcoming, '30'), (paid, '100')):
            payment = PaymentInput(id=uuid4(), cuenta_id=wallet, fecha='2026-02-10', importe=amount)
            run(lambda s, u, w: pay_installment(s, u, w, quota, payment))
        with migrator.begin() as connection:
            for field, quota in (('no_aplica', skip), ('estimado', draft), ('pendiente_ajuste', indexed)):
                connection.execute(text(f'UPDATE public.cuotas SET {field} = true WHERE id = :id'), {'id': quota})
        assert candidates() == {}

        preferences(owner, canal='email', dias_anticipacion=2, vencidas=True)
        preferences(other, canal='push', vencidas=True)
        assert candidates(11, 59) == {}
        selected = candidates()
        assert set(selected) == {'En el límite', 'Vence hoy', 'Vencida', 'Borrador', 'Índice provisorio'}
        assert all(row['espacio_id'] == owner and row['fecha_aviso'] == date(2026, 2, 11)
                   for row in selected.values())
        assert selected['En el límite']['pendiente'] == Decimal('70.00')
        assert selected['En el límite']['moneda'] == 'USD'
        assert selected['Vencida']['evento'] == 'vencida'
        assert selected['Vence hoy']['evento'] == 'vencimiento'
        assert selected['Borrador']['estimado']
        assert selected['Índice provisorio']['pendiente_ajuste']

        preferences(owner, canal='email', dias_anticipacion=0)
        assert set(candidates()) == {'Vence hoy'}
        preferences(owner, canal='email', dias_anticipacion=0, hora_local='00:00')
        assert set(candidates(2, 59)) == {'Vencida'}
        assert candidates(2, 59)['Vencida']['fecha_aviso'] == date(2026, 2, 10)
        assert set(candidates(3, 0)) == {'Vence hoy'}
        preferences(owner, canal='ninguno')
        assert candidates() == {}

        preferences(owner, canal='email', dias_anticipacion=3)
        # La misma cuota puede quedar en la ventana en fechas distintas.
        first = datetime(2026, 2, 11, 12, 0, tzinfo=UTC)
        next_day = datetime(2026, 2, 12, 12, 0, tzinfo=UTC)
        assert ready(first) == {}
        barrier = Barrier(2, timeout=10)

        def concurrent_enqueue(_):
            barrier.wait()
            return enqueue(first)

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(concurrent_enqueue, range(2))) == [0, 5]
        assert enqueue(first) == 0
        assert enqueue(next_day) == 4
        assert enqueue(next_day) == 0
        with migrator.connect() as connection:
            assert connection.execute(text("""
                SELECT fecha_aviso FROM public.avisos_email
                WHERE usuario_id = :owner AND espacio_id = :owner AND cuota_id = :quota
                ORDER BY fecha_aviso
            """), {'owner': owner, 'quota': upcoming}).scalars().all() == [
                date(2026, 2, 11), date(2026, 2, 12),
            ]

        assert ready(first)[upcoming]['pendiente'] == Decimal('70.00')
        for amount, expected in (('10', Decimal('60.00')), ('60', None)):
            payment = PaymentInput(id=uuid4(), cuenta_id=wallet, fecha='2026-02-11', importe=amount)
            run(lambda s, u, w: pay_installment(s, u, w, upcoming, payment))
            refreshed = ready(first).get(upcoming)
            assert (refreshed['pendiente'] if refreshed else None) == expected
        preferences(owner, canal='ninguno')
        assert ready(first) == {}
        assert ready(next_day) == {}

        for engine in (runtime, jobs):
            with engine.connect() as connection:
                assert not connection.execute(text("""
                    SELECT has_function_privilege(current_user,
                        'public.candidatos_avisos_email(timestamptz)', 'EXECUTE')
                """)).scalar_one()
                assert not connection.execute(text("""
                    SELECT has_function_privilege(current_user,
                        'public.encolar_avisos_email(timestamptz)', 'EXECUTE')
                    OR has_table_privilege(current_user, 'public.avisos_email', 'SELECT')
                    OR has_function_privilege(current_user,
                        'public.avisos_email_para_preparar(timestamptz)', 'EXECUTE')
                """)).scalar_one()
    finally:
        runtime.dispose()
        migrator.dispose()
        jobs.dispose()
