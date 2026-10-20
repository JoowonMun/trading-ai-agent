"""시세: 국내는 pykrx 일봉, 미국·환율·지수는 yfinance."""
import contextlib
import io
import os
from datetime import date, timedelta

import pandas as pd

INDEX_TICKERS = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11", "S&P500": "^GSPC", "NASDAQ": "^IXIC", "VIX": "^VIX"}


def _yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _quiet(fn, *args):
    """pykrx는 KRX 로그인 시 아이디를 print한다 — 실행 로그에 남지 않게 출력을 버린다."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*args)


class MarketData:
    def kr_closes(self, ticker: str, start: date, end: date) -> pd.Series:
        from pykrx import stock

        df = _quiet(stock.get_market_ohlcv, _yyyymmdd(start), _yyyymmdd(end), ticker)
        if df is None or df.empty or "종가" not in df.columns:
            raise RuntimeError(f"{ticker} 국내 시세를 가져오지 못했습니다")
        closes = df["종가"].astype(float).dropna()
        return closes[closes > 0]

    def us_closes(self, ticker: str, start: date, end: date) -> pd.Series:
        import yfinance as yf

        df = yf.Ticker(ticker).history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                                       auto_adjust=True)
        if df is None or df.empty:
            raise RuntimeError(f"{ticker} 시세를 가져오지 못했습니다")
        closes = df["Close"].astype(float).dropna()  # yfinance가 최근 종가를 비워 줄 때가 있다
        if closes.empty:
            raise RuntimeError(f"{ticker} 시세를 가져오지 못했습니다")
        closes.index = closes.index.tz_localize(None)
        return closes

    def usdkrw(self, today: date) -> float:
        return float(self.us_closes("KRW=X", today - timedelta(days=10), today).iloc[-1])

    def indices(self, today: date) -> dict[str, dict]:
        out = {}
        for name, ticker in INDEX_TICKERS.items():
            try:
                closes = self.us_closes(ticker, today - timedelta(days=10), today)
            except Exception:
                continue
            change = (closes.iloc[-1] / closes.iloc[-2] - 1) * 100 if len(closes) >= 2 else None
            out[name] = {"close": float(closes.iloc[-1]), "change_pct": None if change is None else float(change)}
        return out

    def kr_flows(self, ticker: str, end: date) -> dict | None:
        if not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
            return None
        from pykrx import stock

        df = _quiet(stock.get_market_trading_value_by_date, _yyyymmdd(end - timedelta(days=14)), _yyyymmdd(end),
                    ticker)
        if df is None or df.empty:
            return None
        last5 = df.tail(5)
        return {"foreign_5d_krw": float(last5["외국인합계"].sum()),
                "institution_5d_krw": float(last5["기관합계"].sum())}
