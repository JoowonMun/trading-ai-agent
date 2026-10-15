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
