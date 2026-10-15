"""PER/PBR 밴드 기반 적정가·분할매수가·매도목표가·재검토가."""
from typing import Literal

import pandas as pd

from agent.analysis.financials import QuarterFigures, ttm
from agent.config import Profile
from agent.report.schema import Band, Valuation

FINANCIAL_KSIC_PREFIXES = ("64", "65", "66")


def is_financial(induty_code: str | None) -> bool:
    return bool(induty_code) and induty_code.startswith(FINANCIAL_KSIC_PREFIXES)


def choose_method(financial: bool, ttm_net_income: float | None) -> Literal["PER", "PBR"]:
    if financial or ttm_net_income is None or ttm_net_income <= 0:
        return "PBR"
    return "PER"


def monthly_multiples(monthly_close: pd.Series, quarters: list[QuarterFigures], shares: float,
                      method: str, lag_days: int = 60) -> pd.Series:
    denominators = []
    for i, q in enumerate(quarters):
        value = ttm(quarters, i)["net_income"] if method == "PER" else q.equity_owners
        available_from = pd.Timestamp(q.period_end) + pd.Timedelta(days=lag_days)
        denominators.append((available_from, value))

    out = {}
    for month_end, close in monthly_close.items():
        available = [value for available_from, value in denominators if available_from <= month_end]
        if not available:
            continue
        denom = available[-1]
        if denom is None or denom <= 0:
            continue
        out[month_end] = float(close) * shares / denom
    return pd.Series(out, dtype=float)


def band_valuation(multiples: pd.Series, method: str, current_multiple: float | None, close: float,
                   avg_price: float | None, profile: Profile, band_years: int, min_points: int,
                   decimals: int = 0) -> Valuation:
    def rnd(x):
        return round(x, decimals) if decimals else round(x)

    review = rnd(avg_price * (1 - profile.review_drawdown_pct / 100)) if avg_price else None
    recent = multiples.iloc[-band_years * 12:]
    if current_multiple is None or current_multiple <= 0 or len(recent) < min_points:
        return Valuation(method=method, insufficient=True, review=review,
                         note=f"{method} 밴드 계산에 필요한 데이터 부족 ({len(recent)}개월, 최소 {min_points}개월)")

    p10, p25, p50, p75, p90 = (float(recent.quantile(x)) for x in (0.10, 0.25, 0.50, 0.75, 0.90))

    def price(multiple):
        return rnd(close * multiple / current_multiple)

    return Valuation(
        method=method,
        insufficient=False,
        current_multiple=round(current_multiple, 2),
        band=Band(p10=round(p10, 2), p25=round(p25, 2), p50=round(p50, 2), p75=round(p75, 2), p90=round(p90, 2)),
        fair=price(p50),
        buy=[price(p25), price((p10 + p25) / 2), price(p10)],
        sell=[price(p75), price(p90)],
        review=review,
    )
