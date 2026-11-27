"""Costo promedio móvil de los USD que todavía están en una cuenta."""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text

from app.usd_reference import effective_rate, local_today


ZERO = Decimal(0)


@dataclass
class Holding:
    quantity: Decimal = ZERO
    cost: Decimal | None = ZERO

    def receive(self, quantity: Decimal, cost: Decimal | None):
        remaining = quantity + min(self.quantity, ZERO)
        self.quantity += quantity
        if remaining > 0:
            if self.cost is None or cost is None:
                self.cost = None
            else:
                self.cost += cost * (remaining / quantity)

    def send(self, quantity: Decimal) -> Decimal | None:
        before = self.quantity
        self.quantity -= quantity
        if self.quantity <= 0:
            cost = self.cost if before == quantity else None
            self.cost = ZERO
            return cost
        if self.cost is None:
            return None
        cost = self.cost * (quantity / before)
        self.cost -= cost
        return cost


def usd_holding(session, space, account):
    today = local_today()
    # Cada transferencia USD lleva su costo a la cuenta de destino. El orden
    # de los cambios del mismo día usa la hora de registro cuando está disponible.
    events = session.execute(text("""
        SELECT * FROM (
            SELECT DATE '0001-01-01' AS fecha, 0 AS prioridad, NULL::timestamptz AS registrada,
                   id, NULL::uuid AS origen, id AS destino, saldo_inicial AS usd, NULL::numeric AS costo
            FROM public.cuentas WHERE espacio_id=:s AND moneda='USD' AND saldo_inicial<>0
            UNION ALL
            SELECT fecha,1,NULL,id,NULL,cuenta_id,importe,NULL FROM public.ingresos
            WHERE espacio_id=:s AND moneda='USD' AND anulado_en IS NULL
            UNION ALL
            SELECT fecha,2,registrada_en,id,
              CASE WHEN tipo='venta' THEN origen_id END,
              CASE WHEN tipo='compra' THEN destino_id END,
              usd,CASE WHEN tipo='compra' THEN ars END
            FROM public.ventas_usd WHERE espacio_id=:s AND anulado_en IS NULL
            UNION ALL
            SELECT fecha,3,NULL,id,origen_id,destino_id,importe,NULL FROM public.transferencias
            WHERE espacio_id=:s AND moneda='USD' AND anulado_en IS NULL
            UNION ALL
            SELECT fecha,4,NULL,id,cuenta_id,NULL,importe,NULL FROM public.gastos
            WHERE espacio_id=:s AND moneda='USD' AND anulado_en IS NULL
        ) movimientos
        WHERE fecha<=:day ORDER BY fecha, prioridad, registrada NULLS FIRST, id
    """), {'s': space, 'day': today})
    accounts = defaultdict(Holding)
    for event in events:
        cost = event.costo
        if event.origen is not None:
            cost = accounts[event.origen].send(event.usd)
        if event.destino is not None:
            accounts[event.destino].receive(event.usd, cost)

    holding = accounts[account]
    rate = effective_rate(session, space, today)['cotizacion'] if holding.quantity > 0 else None
    value = holding.quantity * Decimal(rate['tasa']) if rate else None
    average = holding.cost / holding.quantity if holding.quantity > 0 and holding.cost is not None else None
    gain = value - holding.cost if value is not None and average is not None else None
    return {
        'usd': format(holding.quantity, '.2f'),
        'costo_promedio': format(average, '.4f') if average is not None else None,
        'valor_ars': format(value, '.2f') if value is not None else None,
        'resultado_ars': format(gain, '.2f') if gain is not None else None,
        'resultado_pct': format(gain / holding.cost * 100, '.2f') if gain is not None and holding.cost else None,
        'fecha_referencia': rate['fecha'] if rate else None,
    }
