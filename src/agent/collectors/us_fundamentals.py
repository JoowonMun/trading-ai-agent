"""미국 종목 재무 데이터 (yfinance).

SEC EDGAR가 한국 IP를 차단해(403) yfinance를 쓴다. 연간 실적 약 5년 + 최근 5개 분기를 받아
- 최근 분기들 → QuarterFigures (지표·성장률 계산용)
- 연간 실적 + 분기 TTM → 밴드용 실적 시점 목록 (결산 후 연간 90일 / 분기 45일 뒤부터 사용)
으로 바꾼다. 결산월이 회사마다 달라 분기는 실제 종료일이 속한 달력 분기로 매긴다.
"""
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from agent.analysis.financials import QuarterFigures, ttm
from agent.analysis.valuation import EarningsPoint
from agent.collectors.common import NotACompany

ANNUAL_LAG = pd.Timedelta(days=90)
QUARTER_LAG = pd.Timedelta(days=45)
ROWS = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "op_income": ["Operating Income", "Total Operating Income As Reported"],
    "net_income": ["Net Income Common Stockholders", "Net Income"],
    "equity_owners": ["Stockholders Equity", "Common Stock Equity"],
    "equity_total": ["Total Equity Gross Minority Interest", "Stockholders Equity"],
    "liabilities": ["Total Liabilities Net Minority Interest"],
    "shares": ["Ordinary Shares Number", "Share Issued"],
}


@dataclass
class UsFundamentalData:
    quarters: list[QuarterFigures]
    points: dict[str, list[EarningsPoint]]  # {"PER": [...], "PBR": [...]}
    shares: float | None
    dps: float | None
    financial: bool


def _value(df: pd.DataFrame, key: str, column) -> float | None:
    if df is None or df.empty or column not in df.columns:
        return None
    for row in ROWS[key]:
        if row in df.index:
            v = df.at[row, column]
            if pd.notna(v):
                return float(v)
    return None


def _columns_oldest_first(df: pd.DataFrame) -> list[pd.Timestamp]:
    return [] if df is None or df.empty else sorted(pd.Timestamp(c) for c in df.columns)


class YahooFundamentals:
    def __init__(self, ticker_factory=None):
        if ticker_factory is None:
            import yfinance as yf
            ticker_factory = yf.Ticker
        self.ticker_factory = ticker_factory

    def load(self, symbol: str, today: date) -> UsFundamentalData:
        t = self.ticker_factory(symbol)
        info = t.info or {}
        if info.get("quoteType") in ("ETF", "MUTUALFUND"):
            raise NotACompany(f"{symbol}는 ETF입니다")

        qi, qb = t.quarterly_income_stmt, t.quarterly_balance_sheet
        q_cols = _columns_oldest_first(qi)
        if not q_cols:
            raise RuntimeError(f"{symbol} 재무제표를 가져오지 못했습니다")
        quarters = [QuarterFigures(
            year=c.year, quarter=(c.month - 1) // 3 + 1,
            revenue=_value(qi, "revenue", c), op_income=_value(qi, "op_income", c),
            net_income=_value(qi, "net_income", c), equity_owners=_value(qb, "equity_owners", c),
            equity_total=_value(qb, "equity_total", c), liabilities=_value(qb, "liabilities", c),
        ) for c in q_cols]

        ai, ab = t.income_stmt, t.balance_sheet
        per = [(c + ANNUAL_LAG, _value(ai, "net_income", c)) for c in _columns_oldest_first(ai)]
        pbr = [(c + ANNUAL_LAG, _value(ab, "equity_owners", c)) for c in _columns_oldest_first(ab)]
        for i, c in enumerate(q_cols):
            ni = ttm(quarters, i)["net_income"]
            if ni is not None:
                per.append((c + QUARTER_LAG, ni))
            pbr.append((c + QUARTER_LAG, quarters[i].equity_owners))

        shares = next((v for c in reversed(_columns_oldest_first(qb)) if (v := _value(qb, "shares", c))), None)
        shares = shares or info.get("sharesOutstanding")

        return UsFundamentalData(quarters=quarters, points={"PER": per, "PBR": pbr}, shares=shares,
                                 dps=_trailing_dividends(t.dividends, today),
                                 financial=info.get("sector") == "Financial Services")


def _trailing_dividends(dividends: pd.Series, today: date) -> float | None:
    if dividends is None or dividends.empty:
        return None
    index = dividends.index.tz_localize(None) if dividends.index.tz is not None else dividends.index
    recent = dividends[index > pd.Timestamp(today - timedelta(days=365))]
    return float(recent.sum())
