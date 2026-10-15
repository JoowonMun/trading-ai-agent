import pytest

from agent.analysis.financials import QuarterFigures
from agent.analysis.fundamentals import compute_fundamentals


def q(year, quarter, rev, op, ni, eq=None, eq_total=None, liab=None):
    return QuarterFigures(year, quarter, rev, op, ni, eq, eq_total, liab)


QUARTERS = [
    q(2025, 1, 100, 10, 8),
    q(2025, 2, 100, 10, 8),
    q(2025, 3, 100, 10, 8),
    q(2025, 4, 100, 10, 8),
    q(2026, 1, 110, 12, 10),
    q(2026, 2, 120, 15, 12, eq=200, eq_total=250, liab=100),
]


def test_compute_fundamentals():
    f = compute_fundamentals(QUARTERS, market_cap=760, close=25000, dps=500)
    assert f.ttm_net_income == 38
    assert f.per == pytest.approx(20.0)
    assert f.pbr == pytest.approx(3.8)
    assert f.roe == pytest.approx(19.0)
    assert f.op_margin == pytest.approx(47 / 430 * 100)
    assert f.rev_yoy == pytest.approx(20.0)
    assert f.op_yoy == pytest.approx(50.0)
    assert f.debt_ratio == pytest.approx(40.0)
    assert f.div_yield == pytest.approx(2.0)
    assert f.latest_quarter == "2026Q2"


def test_loss_making_company_has_no_per():
    losing = QUARTERS[:-1] + [q(2026, 2, 120, -50, -60, eq=200, eq_total=250, liab=100)]
    f = compute_fundamentals(losing, market_cap=760, close=25000, dps=None)
    assert f.ttm_net_income < 0
    assert f.per is None
    assert f.pbr == pytest.approx(3.8)
    assert f.op_yoy == pytest.approx(-600.0)
    assert f.div_yield is None


def test_yoy_none_when_base_negative():
    base_negative = [q(2025, 2, 100, -5, -1)] + [q(2025, 3, 1, 1, 1), q(2025, 4, 1, 1, 1),
                                                   q(2026, 1, 1, 1, 1), q(2026, 2, 120, 15, 12)]
    assert compute_fundamentals(base_negative, 1, 1, None).op_yoy is None


def test_empty_quarters():
    assert compute_fundamentals([], 100, 100, None).per is None
