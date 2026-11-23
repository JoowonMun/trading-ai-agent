"""업종 온도계 데이터: 국내는 KRX 업종 지수(PER·PBR 일별), 미국은 업종 ETF(현재 PER·가격)."""
import os
from datetime import date, timedelta

import pandas as pd

from agent.collectors.prices import MarketData, _krx, _quiet, _yyyymmdd

# (KRX 지수 코드, 이름, 가격 수준 방식) — 경기를 타는 업종·금융은 PBR
KR_SECTORS = [
    ("1013", "전기전자", "PER"), ("1008", "화학", "PBR"), ("1011", "금속", "PBR"), ("1018", "건설", "PBR"),
    ("1012", "기계·장비", "PBR"), ("1015", "운송장비·부품", "PBR"), ("1009", "제약", "PER"),
    ("1005", "음식료·담배", "PER"), ("1016", "유통", "PER"), ("1017", "전기·가스", "PER"), ("1020", "통신", "PER"),
    ("1021", "금융", "PBR"), ("1024", "증권", "PBR"), ("1025", "보험", "PBR"), ("1046", "IT 서비스", "PER"),
    ("1019", "운송·창고", "PBR"), ("1047", "오락·문화", "PER"),
]

US_SECTORS = [
    ("XLK", "기술"), ("SOXX", "반도체"), ("XLC", "커뮤니케이션"), ("XLY", "경기소비재"), ("XLP", "필수소비재"),
    ("XLE", "에너지"), ("XLF", "금융"), ("XLV", "헬스케어"), ("XLI", "산업재"), ("XLB", "소재"),
    ("XLU", "유틸리티"), ("XLRE", "부동산"),
]


class SectorData:
    def kr_fundamentals(self, code: str, start: date, end: date) -> pd.DataFrame:
        if not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
            raise RuntimeError("KRX 계정이 없어요")
        stock = _krx()

        df = _quiet(stock.get_index_fundamental, _yyyymmdd(start), _yyyymmdd(end), code)
        if df is None or df.empty or not {"종가", "PER", "PBR"} <= set(df.columns):
            raise RuntimeError("업종 지표를 가져오지 못했어요")
        out = df[["종가", "PER", "PBR"]].astype(float).rename(columns={"종가": "close", "PER": "per", "PBR": "pbr"})
        published = (out["close"] > 0) & ((out["per"] > 0) | (out["pbr"] > 0))  # 오늘 행은 지표가 0으로 온다
        return out[published].sort_index()

    def us_quote(self, ticker: str, today: date) -> tuple[float | None, pd.Series]:
        import yfinance as yf

        closes = MarketData().us_closes(ticker, today - timedelta(days=380), today)
        per = yf.Ticker(ticker).info.get("trailingPE")
        return (float(per) if per else None), closes

    def latest_trading_day(self, today: date) -> date:
        """오늘 이전 가장 최근 거래일 (KRX는 오늘 자료가 비어 있을 수 있다)."""
        stock = _krx()

        day = _quiet(stock.get_nearest_business_day_in_a_week, _yyyymmdd(today - timedelta(days=1)), True)
        return date(int(day[:4]), int(day[4:6]), int(day[6:]))

    def kr_constituents(self, code: str, day: date) -> list[str]:
        stock = _krx()

        return list(_quiet(stock.get_index_portfolio_deposit_file, code, _yyyymmdd(day)))

    def market_cap_top(self, day: date, n: int) -> list[str]:
        stock = _krx()

        df = _quiet(stock.get_market_cap, _yyyymmdd(day), "ALL")
        return list(df.sort_values("시가총액", ascending=False).index[:n])
