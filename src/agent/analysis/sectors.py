"""업종 온도계: 업종의 가격 수준(과거 대비 위치) · 이익 방향 · 주가 위치를 계산한다."""
from datetime import date, timedelta

import pandas as pd

from agent.report.schema import SectorRow

MIN_DAYS = 240        # 가격 수준을 매기려면 유효한 날이 1년치는 있어야 한다
DAYS_3M, DAYS_1Y = 63, 252


def level_of(pct: float | None) -> str | None:
    if pct is None:
        return None
    if pct <= 30:
        return "싸요"
    if pct >= 70:
        return "비싸요"
    return "보통"


def percentile_of(values: pd.Series, current: float) -> float:
    return round(float((values <= current).mean()) * 100, 1)


def _change(now: float, before: float | None) -> float | None:
    if before is None or before <= 0:
        return None
    return round((now / before - 1) * 100, 1)


def price_position(closes: pd.Series) -> tuple[float | None, float | None]:
    closes = closes.dropna()
    if closes.empty:
        return None, None
    now = float(closes.iloc[-1])
    high = float(closes.tail(DAYS_1Y).max())
    before = float(closes.iloc[-1 - DAYS_3M]) if len(closes) > DAYS_3M else None
    return _change(now, high), _change(now, before)


def kr_row(code: str, name: str, method: str, df: pd.DataFrame) -> SectorRow:
    row = SectorRow(key=f"KR:{code}", name=name, market="KR", method=method, close=float(df["close"].iloc[-1]))
    col = df[method.lower()].round(2)
    current = float(col.iloc[-1])
    valid = col[col > 0]
    if current > 0:
        row.value = current
    if current > 0 and len(valid) >= MIN_DAYS:
        row.percentile = percentile_of(valid, current)
        row.level = level_of(row.percentile)
    else:
        row.note = "자료 부족"

    eps = (df["close"] / df["per"]).where(df["per"] > 0)
    if pd.notna(eps.iloc[-1]):
        now = float(eps.iloc[-1])
        for days, field in ((DAYS_3M, "earnings_3m_pct"), (DAYS_1Y, "earnings_1y_pct")):
            if len(eps) > days and pd.notna(eps.iloc[-1 - days]):
                setattr(row, field, _change(now, float(eps.iloc[-1 - days])))
    row.drawdown_52w_pct, row.return_3m_pct = price_position(df["close"])
    return row


def us_row(ticker: str, name: str, per: float | None, closes: pd.Series) -> SectorRow:
    row = SectorRow(key=f"US:{ticker}", name=name, market="US", method="PER",
                    value=per if per and per > 0 else None,
                    close=float(closes.iloc[-1]) if not closes.empty else None)
    row.drawdown_52w_pct, row.return_3m_pct = price_position(closes)
    return row


def sort_rows(rows: list[SectorRow]) -> list[SectorRow]:
    return sorted(rows, key=lambda r: (r.percentile is None, r.percentile or 0))


US_PERCENTILE_WEEKS, US_EARNINGS_WEEKS = 26, 13


def enrich_us_from_history(rows: list[SectorRow], past: list[dict], today: date) -> None:
    """미국 업종은 과거 PER을 무료로 구할 수 없어, 매주 저장한 기록으로 과거 대비 위치·이익 방향을 채운다."""
    cutoff = (today - timedelta(days=91)).isoformat()
    for row in rows:
        if row.market != "US":
            continue
        hist = sorted(((s["date"], s["sectors"][row.key]) for s in past if row.key in (s.get("sectors") or {})),
                      key=lambda x: x[0])
        row.history_weeks = len(hist) + 1
        values = [h["value"] for _, h in hist if h.get("value")]
        if row.value and row.history_weeks >= US_PERCENTILE_WEEKS:
            row.percentile = percentile_of(pd.Series(values + [row.value]), row.value)
            row.level = level_of(row.percentile)
            row.note = ""
        else:
            row.note = f"기록 {row.history_weeks}주 — {US_PERCENTILE_WEEKS}주부터 과거와 비교"
        old = [h for d, h in hist if d <= cutoff]
        if row.value and row.close and old and old[-1].get("eps") and row.history_weeks >= US_EARNINGS_WEEKS:
            row.earnings_3m_pct = _change(row.close / row.value, old[-1]["eps"])
