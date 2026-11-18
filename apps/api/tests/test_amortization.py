from decimal import Decimal, localcontext

import pytest

from app.amortization import amortize, AmortizationRow

D = Decimal


def assert_rows(rows, reference):
    assert len(rows) == len(reference)
    for row, expected in zip(rows, reference, strict=True):
        actual = (row.principal, row.interest, row.amount, row.balance)
        assert all(abs(value - D(target)) < D('0.01') for value, target in zip(actual, expected, strict=True))


def test_french_reference_with_constant_payment_and_final_balance():
    # Con 10 % mensual y dos cuotas, 1000 = C/1.10 + C/1.10².
    # De ahí C = 576.190476… El primer interés es 100 y el segundo 52.38.
    rows = amortize(D('1000'), D('120'), 2, 'frances')
    assert_rows(rows, [
        ('476.19', '100.00', '576.19', '523.81'),
        ('523.81', '52.38', '576.19', '0.00'),
    ])


def test_german_reference_with_constant_principal_and_decreasing_interest():
    # Con 1 % mensual, se amortizan 1000 y el interés cae de 30 a 10.
    rows = amortize(D('3000'), D('12'), 3, 'aleman')
    assert_rows(rows, [
        ('1000.00', '30.00', '1030.00', '2000.00'),
        ('1000.00', '20.00', '1020.00', '1000.00'),
        ('1000.00', '10.00', '1010.00', '0.00'),
    ])


def test_french_differs_from_nominal_payment_only_at_rounding_close():
    rows = amortize(D('100000'), D('12'), 12, 'frances')
    assert all(row.amount == D('8884.88') for row in rows[:-1])
    assert rows[0] == AmortizationRow(1, D('7884.88'), D('1000.00'), D('8884.88'), D('92115.12'))
    assert rows[-1] == AmortizationRow(12, D('8796.88'), D('87.97'), D('8884.85'), D('0.00'))


@pytest.mark.parametrize('system', ['frances', 'aleman'])
def test_zero_rate_distributes_indivisible_cents(system):
    rows = amortize(D('100.00'), D(0), 3, system)
    assert [r.principal for r in rows] == [D('33.33'), D('33.34'), D('33.33')]
    assert all(r.amount == r.principal and r.interest == 0 for r in rows)
    assert rows[-1].balance == 0


@pytest.mark.parametrize('system', ['frances', 'aleman'])
def test_cent_accounting_reconciles_for_long_plan(system):
    capital = D('9876543.21')
    with localcontext(prec=8):
        rows = amortize(capital, D('13.5678'), 240, system)
    assert [row.number for row in rows] == list(range(1, 241))
    assert sum(row.principal for row in rows) == capital
    opening = capital
    for row in rows:
        assert row.principal > 0
        assert row.amount == row.principal + row.interest
        assert row.balance == opening - row.principal
        opening = row.balance
    assert opening == 0


@pytest.mark.parametrize('args', [
    (D('100.001'), D('12'), 12, 'frances'),
    (D('NaN'), D('12'), 12, 'frances'),
    (D('1000'), D('-0.5'), 12, 'frances'),
    (D('1000'), D('Infinity'), 12, 'frances'),
    (D('1000'), D('12'), 0, 'frances'),
    (D('1000'), D('12'), True, 'frances'),
    (D('1000'), D('12'), 601, 'frances'),
    (D('1000'), D('12'), 12, 'otro'),
    (D('0.01'), D('12'), 12, 'aleman'),
    (D('1.00'), D('1200'), 100, 'frances'),
    (D('999999999999.99'), D('12'), 1, 'aleman'),
    (D('1000'), D('1e10000'), 12, 'frances'),
])
def test_invalid_inputs_fail_before_returning_a_plan(args):
    with pytest.raises(ValueError):
        amortize(*args)
