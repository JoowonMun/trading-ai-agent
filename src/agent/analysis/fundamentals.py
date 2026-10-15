"""PER·PBR·ROE 등 재무 지표 계산."""
from agent.analysis.financials import QuarterFigures, ttm
from agent.report.schema import Fundamentals


def _pct(numer, denom):
    if numer is None or denom is None or denom <= 0:
        return None
    return numer / denom * 100


def _yoy(current, base):
    if current is None or base is None or base <= 0:
        return None
    return (current - base) / base * 100


def compute_fundamentals(quarters: list[QuarterFigures], market_cap: float, close: float,
                         dps: float | None) -> Fundamentals:
    if not quarters:
        return Fundamentals()
    index = len(quarters) - 1
    latest = quarters[index]
    t = ttm(quarters, index)
    ni = t["net_income"]
    base = next((x for x in quarters if (x.year, x.quarter) == (latest.year - 1, latest.quarter)), None)
    equity = latest.equity_owners
    return Fundamentals(
        per=market_cap / ni if ni is not None and ni > 0 else None,
        pbr=market_cap / equity if equity is not None and equity > 0 else None,
        roe=_pct(ni, equity),
        op_margin=_pct(t["op_income"], t["revenue"]),
        rev_yoy=_yoy(latest.revenue, base.revenue if base else None),
        op_yoy=_yoy(latest.op_income, base.op_income if base else None),
        debt_ratio=_pct(latest.liabilities, latest.equity_total),
        div_yield=dps / close * 100 if dps is not None and close > 0 else None,
        ttm_net_income=ni,
        latest_quarter=f"{latest.year}Q{latest.quarter}",
    )
