"""Prepara y envía el resumen de la última semana cerrada."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4

from psycopg.pq import TransactionStatus

from deliver_reminder_email import mailbox
from reminder_email import ReminderEmail, format_amount, reminder_link


def budget_line(report):
    limit = report['limite']
    if not limit:
        return 'Presupuesto semanal sin límite configurado.'
    currency = limit['moneda']
    cap = Decimal(limit['importe'])
    totals = {row['moneda']: Decimal(row['total']) for row in report['gastos']}
    if any(amount for code, amount in totals.items() if code not in ('ARS', 'USD')):
        return f'Límite semanal: {currency} {format_amount(cap)}. Conversión pendiente.'
    native = totals.get(currency, Decimal(0))
    other = totals.get('USD' if currency == 'ARS' else 'ARS', Decimal(0))
    if currency == 'ARS':
        fixed_usd, fixed_ars = map(Decimal, report['gastos_fijados'])
        native += fixed_ars
        other -= fixed_usd
    if other:
        if not report['tasa']:
            return f'Límite semanal: {currency} {format_amount(cap)}. Conversión pendiente.'
        rate = Decimal(report['tasa'])
        native += other * rate if currency == 'ARS' else other / rate
    spent = native.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    difference = cap - spent
    status = 'Disponible' if difference >= 0 else 'Exceso'
    return (f'Gastado: {currency} {format_amount(spent)} de {format_amount(cap)}. '
            f'{status}: {currency} {format_amount(abs(difference))}.')


def render_weekly_summary(report, scope: tuple[UUID, UUID], app_url):
    reminder_link(app_url)
    start = date.fromisoformat(report['desde'])
    finish = date.fromisoformat(report['hasta'])
    upcoming = date.fromisoformat(report['proximos_desde'])
    lines = [f'Tu semana del {start:%d/%m} al {finish:%d/%m}.', '', 'Gastos registrados']
    lines.extend(f"- {row['moneda']} {format_amount(Decimal(row['total']))}" for row in report['gastos'])
    if not report['gastos']:
        lines.append('Sin gastos registrados.')
    lines.extend(['', 'Estado del presupuesto', budget_line(report), '', 'Próximos siete días'])
    for row in report['proximos']:
        due = date.fromisoformat(row['vencimiento'])
        label = 'Estimado' if row['estimado'] else 'Saldo'
        name = ' '.join(row['nombre'].split())
        lines.append(f"- {due:%d/%m} · {name} · {label} {row['moneda']} {format_amount(Decimal(row['saldo']))}")
    extra = report['cantidad_proximos'] - len(report['proximos'])
    if extra == 1:
        lines.append('Hay un vencimiento más en Piggo.')
    elif extra > 1:
        lines.append(f'Hay {extra} vencimientos más en Piggo.')
    if not report['proximos']:
        lines.append('Sin vencimientos pendientes en ese período.')
    lines.extend(['', 'Ver en Piggo: ' + app_url])
    return ReminderEmail(*scope, upcoming, f'Piggo · Resumen semanal al {finish:%d/%m/%Y}', '\n'.join(lines))


def read_weekly_summary(connection, instant, scope):
    if instant.utcoffset() is None:
        raise ValueError('El instante debe incluir zona horaria')
    return connection.execute('SELECT public.resumen_semanal_piloto(%s, %s, %s)', (*scope, instant)).fetchone()[0]


def send_weekly_summary(connection, instant, scope, recipient, app_url, sender):
    if not connection.autocommit or connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError('La entrega requiere autocommit y una conexión sin transacción abierta')
    recipient = mailbox(recipient)
    report = read_weekly_summary(connection, instant, scope)
    if report is None:
        return None
    message = render_weekly_summary(report, scope, app_url)
    attempt = uuid4()
    reserved = connection.execute('SELECT public.reservar_resumen_semanal_piloto(%s, %s, %s, %s)',
                                  (*scope, instant, attempt)).fetchone()[0]
    if not reserved:
        return None

    outcome = sender.send(attempt, recipient, message)
    recorded = connection.execute('SELECT public.resolver_resumen_semanal_piloto(%s, %s)',
                                  (attempt, outcome.estado)).fetchone()[0]
    if not recorded:
        raise RuntimeError('No se pudo registrar el resultado del resumen')
    return outcome
