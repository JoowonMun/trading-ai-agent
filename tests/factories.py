"""테스트 데이터 생성기."""


def report_rows(rev_cum, op_cum, ni_cum, equity_owners=None, equity_total=None, liabilities=None, *, with_add=True):
    """DART fnlttSinglAcntAll 응답의 list 항목 모양을 흉내낸다."""

    def flow(account_id, name, cum):
        row = {"sj_div": "IS", "account_id": account_id, "account_nm": name}
        if with_add:
            row["thstrm_amount"] = "999"  # 3개월치 값 — 누적값이 있으면 쓰이면 안 된다
            row["thstrm_add_amount"] = f"{cum:,.0f}"
        else:
            row["thstrm_amount"] = f"{cum:,.0f}"
        return row

    rows = [
        flow("ifrs-full_Revenue", "매출액", rev_cum),
        flow("dart_OperatingIncomeLoss", "영업이익", op_cum),
        flow("ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 당기순이익", ni_cum),
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
                if quarter_end(y, q) <= self.today:
                    out[(y, q)] = report_rows(q * 100e9, q * 10e9, q * 8e9, equity_owners=200e9,
                                              equity_total=250e9, liabilities=100e9, with_add=q < 4)
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
