"""테스트 데이터 생성기."""


def report_rows(rev, op, ni, equity_owners=None, equity_total=None, liabilities=None, *, add=None):
    """DART fnlttSinglAcntAll 응답의 list 항목 모양을 흉내낸다.

    rev/op/ni는 thstrm_amount(분기·반기 보고서는 3개월치, 사업보고서는 연간),
    add는 thstrm_add_amount(연초부터 누적) 3개 튜플 또는 None(필드 없음).
    """

    def flow(account_id, name, amount, cumulative):
        row = {"sj_div": "IS", "account_id": account_id, "account_nm": name, "thstrm_amount": f"{amount:,.0f}"}
        if cumulative is not None:
            row["thstrm_add_amount"] = f"{cumulative:,.0f}"
        return row

    adds = add or (None, None, None)
    rows = [
        flow("ifrs-full_Revenue", "매출액", rev, adds[0]),
        flow("dart_OperatingIncomeLoss", "영업이익", op, adds[1]),
        flow("ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 당기순이익", ni, adds[2]),
    ]
    for account_id, name, value in (
        ("ifrs-full_EquityAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 자본", equity_owners),
        ("ifrs-full_Equity", "자본총계", equity_total),
        ("ifrs-full_Liabilities", "부채총계", liabilities),
    ):
        if value is not None:
            rows.append({"sj_div": "BS", "account_id": account_id, "account_nm": name, "thstrm_amount": f"{value:,.0f}"})
    return rows


from datetime import date

import numpy as np
import pandas as pd

from agent.analysis.financials import quarter_end


class FakeMarket:
    def __init__(self, fail=()):
        self.fail = set(fail)

    def _series(self, ticker, end, low, high):
        if ticker in self.fail:
            raise RuntimeError(f"{ticker} 시세 실패")
        index = pd.bdate_range(end=pd.Timestamp(end), periods=1500)
        return pd.Series(np.linspace(low, high, len(index)), index=index)

    def kr_closes(self, ticker, start, end):
        return self._series(ticker, end, 40_000, 60_000)

    def us_closes(self, ticker, start, end):
        return self._series(ticker, end, 100, 200)

    def usdkrw(self, today):
        return 1300.0

    def indices(self, today):
        return {"KOSPI": {"close": 2500.0, "change_pct": 0.5}}

    def kr_flows(self, ticker, end):
        return None


class FakeDart:
    def __init__(self, today, fail=(), negative=()):
        self.today, self.fail, self.negative = today, set(fail), set(negative)

    def corp_code(self, ticker):
        if ticker in self.fail:
            from agent.collectors.dart import DartError
            raise DartError(f"{ticker} 없음")
        return f"C{ticker}"

    def company(self, corp_code):
        return {"induty_code": "264"}

    def quarterly_reports(self, corp_code, years):
        out = {}
        for y in range(self.today.year - years, self.today.year + 1):
            for q in range(1, 5):
                if quarter_end(y, q) > self.today:
                    continue
                bs = dict(equity_owners=200e9, equity_total=250e9, liabilities=100e9)
                if q < 4:
                    out[(y, q)] = report_rows(100e9, 10e9, 8e9, add=(q * 100e9, q * 10e9, q * 8e9), **bs)
                else:
                    out[(y, q)] = report_rows(400e9, 40e9, 32e9, **bs)
        return out

    def shares_outstanding(self, corp_code):
        return 1_000_000

    def dividend_per_share(self, corp_code):
        return 1000.0

    def disclosures(self, corp_code, start, end):
        if corp_code[1:] in self.negative:
            return [{"report_nm": "유상증자결정", "rcept_no": "20261014000001", "rcept_dt": "20261014"}]
        return []


def sample_context():
    from agent.config import Profile
    from agent.report.schema import (Band, ClassWeight, Context, Fundamentals, HoldingContext, IndexQuote, Market,
                                     Portfolio, PositionInfo, PriceSnapshot, Rebalance, Valuation)

    return Context(
        date="2026-10-15",
        profile=Profile(),
        market=Market(indices={"KOSPI": IndexQuote(close=2500.0, change_pct=0.52)}, fx_usdkrw=1350.0),
        holdings=[
            HoldingContext(
                ticker="005930", name="삼성전자", market="KR", asset_class="domestic",
                position=PositionInfo(qty=10, avg_price=71000, weight_pct=8.2),
                price=PriceSnapshot(close=65000, price_date="2026-10-14", ma20=66000, ma60=68000, ma120=70000,
                                    rsi14=38.5, pos_52w_pct=22.0),
                fundamentals=Fundamentals(per=12.3, pbr=1.1, roe=9.5, op_margin=12.0, rev_yoy=5.0, op_yoy=10.0,
                                          debt_ratio=35.0, div_yield=2.2, ttm_net_income=3.2e13,
                                          latest_quarter="2026Q2"),
                valuation=Valuation(method="PER", insufficient=False, current_multiple=12.3,
                                    band=Band(p10=8.0, p25=10.0, p50=13.0, p75=16.0, p90=19.0),
                                    fair=68699, buy=[52846, 47561, 42276], sell=[84553, 100406], review=60350),
                assessments={"per": "good", "roe": "neutral", "debt_ratio": "good", "op_yoy": "caution"},
                signal="hold",
            ),
            HoldingContext(
                ticker="AAPL", name="Apple", market="US", asset_class="us",
                position=PositionInfo(qty=5, avg_price=185.2, weight_pct=12.0),
                price=PriceSnapshot(close=230.5, price_date="2026-10-14"),
                missing=["미국 종목 분석은 2단계에서 추가됩니다"],
            ),
        ],
        portfolio=Portfolio(
            total_krw=8_000_000, cash_krw=0,
            by_class={"domestic": ClassWeight(label="국내", value_krw=650_000, pct=8.2, target_pct=30, diff_pct=-21.8)},
            rebalance=[Rebalance(asset_class="domestic", label="국내", action="늘리기", amount_krw=1_740_000)],
            weights={"KR:005930": 8.2, "US:AAPL": 12.0},
        ),
        glossary_terms=["PER", "ROE"],
    )


class FakeUs:
    """YahooFundamentals 대역: 5개 분기 + 6년치 연간 실적 시점."""

    def __init__(self, today, etf=(), fail=()):
        self.today, self.etf, self.fail = today, set(etf), set(fail)

    def load(self, symbol, today):
        from agent.analysis.financials import QuarterFigures
        from agent.collectors.common import NotACompany
        from agent.collectors.us_fundamentals import UsFundamentalData
        if symbol in self.etf:
            raise NotACompany(f"{symbol}는 ETF입니다")
        if symbol in self.fail:
            raise RuntimeError("yfinance 오류")
        quarters = [QuarterFigures(2025 + (q > 4), (q - 1) % 4 + 1, 100e6, 30e6, 25e6, 500e6, 500e6, 200e6)
                    for q in range(3, 8)]
        months = pd.date_range(end=pd.Timestamp(today), periods=80, freq="MS")
        points = {"PER": [(m, 100e6) for m in months], "PBR": [(m, 500e6) for m in months]}
        return UsFundamentalData(quarters=quarters, points=points, shares=1e6, dps=1.0, financial=False)


class FakeNps:
    def __init__(self, fail=False):
        self.fail = fail

    def annual_holdings(self):
        return {"as_of": "2025-12-31", "rows": [
            {"rank": 1, "name": "삼성전자", "value_eok": 551095.0, "weight_pct": 21.06, "stake_pct": 7.76},
            {"rank": 2, "name": "SK하이닉스", "value_eok": 374316.0, "weight_pct": 14.31, "stake_pct": 7.9}]}

    def recent_changes(self, days):
        if self.fail:
            raise RuntimeError("DART 지연")
        return [{"name": "SK하이닉스", "ticker": "000660", "corp_code": "C000660", "stake_pct": 8.1,
                 "change_pct": 0.2, "date": "2026-10-14"},
                {"name": "대한항공", "ticker": "003490", "corp_code": "C003490", "stake_pct": 9.97,
                 "change_pct": -0.03, "date": "2026-10-15"}]

    def stake(self, corp_code):
        return {"C005930": {"stake_pct": 7.5, "change_pct": -0.1, "date": "2026-09-30"}}.get(corp_code)
