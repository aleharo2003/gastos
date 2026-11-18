"""Planes mensuales de amortización, sin acceso a la API ni a la base."""
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from typing import Literal

AmortizationSystem = Literal['frances', 'aleman']
CENT = Decimal('0.01')
MONEY_LIMIT = Decimal('1000000000000')
MAX_INSTALLMENTS = 600


@dataclass(frozen=True, slots=True)
class AmortizationRow:
    number: int
    principal: Decimal
    interest: Decimal
    amount: Decimal
    balance: Decimal


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _french_payment(principal: Decimal, rate: Decimal, installments: int) -> Decimal:
    # El capital es la suma de las cuotas descontadas a su valor presente.
    discount = Decimal(1)
    factor = Decimal(0)
    for _ in range(installments):
        discount /= 1 + rate
        factor += discount
    return _money(principal / factor)


def amortize(
    principal: Decimal, annual_rate_percent: Decimal, installments: int, system: AmortizationSystem,
) -> tuple[AmortizationRow, ...]:
    """Calcula cuotas mensuales con interés sobre saldo y TNA expresada en porcentaje.

    Por ejemplo, una TNA de Decimal('12') equivale a 1 % mensual. Los importes
    se redondean al centavo más próximo. Si el último decimal es cinco,
    se redondea hacia arriba. La última cuota cancela el saldo exacto.
    """
    if system not in ('frances', 'aleman'):
        raise ValueError('Sistema de amortización inválido')
    if type(installments) is not int or not 1 <= installments <= MAX_INSTALLMENTS:
        raise ValueError('La cantidad de cuotas debe estar entre 1 y 600')
    if not isinstance(principal, Decimal) or not principal.is_finite() or not 0 < principal < MONEY_LIMIT:
        raise ValueError('Capital fuera del rango admitido')
    if not isinstance(annual_rate_percent, Decimal) or not annual_rate_percent.is_finite() or annual_rate_percent < 0:
        raise ValueError('La tasa nominal anual debe ser un porcentaje no negativo')

    with localcontext(Context(prec=50, rounding=ROUND_HALF_UP)):
        if _money(principal) != principal or principal < CENT * installments:
            raise ValueError('El capital debe tener hasta dos decimales y alcanzar un centavo por cuota')
        if annual_rate_percent >= MONEY_LIMIT * 1200 / principal:
            raise ValueError('El interés supera el importe máximo admitido')

        rate = annual_rate_percent / 1200
        fixed_payment = _french_payment(principal, rate, installments) if system == 'frances' and rate else None
        balance = _money(principal)
        rows = []
        for number in range(1, installments + 1):
            interest = _money(balance * rate)
            if number == installments:
                principal_part = balance
            elif fixed_payment is not None:
                principal_part = fixed_payment - interest
                # El redondeo puede impedir una amortización positiva o agotar el saldo antes del plazo.
                if not 0 < principal_part < balance:
                    raise ValueError('No se puede mantener la cuota francesa en centavos para ese capital, tasa y plazo')
            else:
                expected_balance = _money(principal * (installments - number) / installments)
                principal_part = balance - expected_balance
            amount = principal_part + interest
            if amount >= MONEY_LIMIT:
                raise ValueError('La cuota supera el importe máximo admitido')

            balance -= principal_part
            rows.append(AmortizationRow(number, principal_part, interest, amount, balance))
        return tuple(rows)
