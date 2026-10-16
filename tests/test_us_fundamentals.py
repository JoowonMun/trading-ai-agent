from datetime import date

import numpy as np
import pandas as pd
import pytest

from agent.collectors.common import NotACompany
from agent.collectors.us_fundamentals import YahooFundamentals

TODAY = date(2026, 10, 16)
Q_ENDS = pd.to_datetime(["2026-07-31", "2026-04-30", "2026-01-31", "2025-10-31", "2025-07-31"])  # 최신순 (yfinance 순서)
A_ENDS = pd.to_datetime(["2026-01-31", "2025-01-31", "2024-01-31", "2023-01-31", "2022-01-31"])


def frame(rows: dict, columns) -> pd.DataFrame:
    return pd.DataFrame(rows, index=columns).T


class FakeTicker:
    def __init__(self, info=None, quarterly_income=None, dividends=None):
        self.info = info if info is not None else {"quoteType": "EQUITY", "sector": "Technology"}
        self.quarterly_income_stmt = quarterly_income if quarterly_income is not None else frame({
            "Total Revenue": [50, 45, 40, 35, 30],
            "Operating Income": [30, 27, 24, 21, 18],
            "Net Income Common Stockholders": [25, 22, 20, 18, 15],
        }, Q_ENDS)
        self.quarterly_balance_sheet = frame({
            "Stockholders Equity": [200, 190, 180, 170, 160],
            "Total Equity Gross Minority Interest": [205, 195, 185, 175, 165],
            "Total Liabilities Net Minority Interest": [100, 95, 90, 85, 80],
            "Ordinary Shares Number": [1000, 1000, 1000, 1000, 1000],
        }, Q_ENDS)
        self.income_stmt = frame({"Net Income Common Stockholders": [78, 60, 30, 4, 9]}, A_ENDS)
        self.balance_sheet = frame({"Stockholders Equity": [180, 150, 120, 100, 90]}, A_ENDS)
        idx = pd.to_datetime(["2025-06-01", "2026-03-01", "2026-09-01"]).tz_localize("America/New_York")
        self.dividends = dividends if dividends is not None else pd.Series([0.5, 0.01, 0.01], index=idx)


def load(ticker=None):
    return YahooFundamentals(ticker_factory=lambda symbol: ticker or FakeTicker()).load("NVDA", TODAY)


def test_quarters_mapped_oldest_first_by_calendar_quarter():
    data = load()
    assert [(q.year, q.quarter) for q in data.quarters] == [(2025, 3), (2025, 4), (2026, 1), (2026, 2), (2026, 3)]
    latest = data.quarters[-1]
    assert (latest.revenue, latest.op_income, latest.net_income) == (50, 30, 25)
    assert (latest.equity_owners, latest.equity_total, latest.liabilities) == (200, 205, 100)


def test_shares_dividends_and_sector():
    data = load()
    assert data.shares == 1000
    assert data.dps == pytest.approx(0.02)  # 최근 1년 배당만 합산
    assert data.financial is False


def test_per_points_combine_annual_and_quarterly_ttm():
    data = load()
    per = dict((d.strftime("%Y-%m-%d"), v) for d, v in data.points["PER"])
    assert per["2022-05-01"] == 9           # 연간 결산(1/31) + 90일
    assert per["2026-05-01"] == 78
    assert per["2026-09-14"] == 25 + 22 + 20 + 18  # 최근 4분기 합, 분기 종료(7/31) + 45일
    pbr = dict((d.strftime("%Y-%m-%d"), v) for d, v in data.points["PBR"])
    assert pbr["2026-09-14"] == 200


def test_financial_sector_detected():
    ticker = FakeTicker(info={"quoteType": "EQUITY", "sector": "Financial Services"})
    assert load(ticker).financial is True


def test_etf_is_not_a_company():
    with pytest.raises(NotACompany):
        load(FakeTicker(info={"quoteType": "ETF"}))


def test_missing_values_become_none():
    q = frame({"Total Revenue": [50, np.nan, 40, 35, 30],
               "Operating Income": [30, 27, 24, 21, 18],
               "Net Income Common Stockholders": [25, 22, 20, 18, 15]}, Q_ENDS)
    data = load(FakeTicker(quarterly_income=q))
    assert data.quarters[-2].revenue is None


def test_no_financial_statements_raises():
    with pytest.raises(RuntimeError, match="재무"):
        load(FakeTicker(quarterly_income=pd.DataFrame()))


@pytest.mark.live
def test_live_nvda():
    data = YahooFundamentals().load("NVDA", TODAY)
    assert len(data.quarters) >= 4 and data.shares > 1e9
    assert sum(1 for _, v in data.points["PER"] if v) >= 5
