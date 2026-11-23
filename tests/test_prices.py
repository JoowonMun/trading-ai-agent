from datetime import date

import pytest

from agent.collectors.prices import MarketData


def test_kr_flows_disabled_without_krx_account(monkeypatch):
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)
    assert MarketData().kr_flows("005930", date(2026, 10, 15)) is None


def test_indices_skip_failures(monkeypatch):
    import pandas as pd

    def fake_us_closes(self, ticker, start, end):
        if ticker == "^VIX":
            raise RuntimeError("down")
        return pd.Series([100.0, 101.0], index=pd.date_range("2026-10-13", periods=2))

    monkeypatch.setattr(MarketData, "us_closes", fake_us_closes)
    out = MarketData().indices(date(2026, 10, 15))
    assert "VIX" not in out
    assert out["KOSPI"]["close"] == 101.0
    assert out["KOSPI"]["change_pct"] == pytest.approx(1.0)


@pytest.mark.live
def test_live_kr_and_us_prices():
    md = MarketData()
    kr = md.kr_closes("005930", date(2026, 9, 1), date(2026, 10, 14))
    assert len(kr) > 10 and kr.iloc[-1] > 0
    etf = md.kr_closes("360750", date(2026, 9, 1), date(2026, 10, 14))
    assert etf.iloc[-1] > 0
    us = md.us_closes("AAPL", date(2026, 9, 1), date(2026, 10, 14))
    assert us.iloc[-1] > 0
    assert 800 < md.usdkrw(date(2026, 10, 14)) < 2500


def test_pykrx_login_messages_are_not_printed(monkeypatch, capsys):
    import pandas as pd
    from pykrx import stock

    monkeypatch.setenv("KRX_ID", "secret-id")
    monkeypatch.setenv("KRX_PW", "pw")

    def chatty(*args, **kwargs):
        print("KRX 로그인 시도... 로그인 ID: secret-id")
        return pd.DataFrame({"외국인합계": [1.0] * 5, "기관합계": [2.0] * 5})

    monkeypatch.setattr(stock, "get_market_trading_value_by_date", chatty)
    assert MarketData().kr_flows("005930", date(2026, 10, 15)) == {"foreign_5d_krw": 5.0, "institution_5d_krw": 10.0}
    out = capsys.readouterr()
    assert "secret-id" not in out.out + out.err


def test_us_closes_drop_missing_values(monkeypatch):
    import numpy as np
    import pandas as pd
    import yfinance as yf

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, **kwargs):
            idx = pd.date_range("2026-10-14", periods=3, tz="America/New_York")
            return pd.DataFrame({"Close": [100.0, 101.0, np.nan]}, index=idx)

    monkeypatch.setattr(yf, "Ticker", FakeTicker)
    closes = MarketData().us_closes("AAPL", date(2026, 10, 14), date(2026, 10, 16))
    assert closes.tolist() == [100.0, 101.0]


def test_quiet_is_safe_across_threads(capsys):
    import random
    import sys
    import time
    from concurrent.futures import ThreadPoolExecutor

    from agent.collectors.prices import _quiet

    def chatty(i):
        time.sleep(random.random() / 50)
        print(f"로그인 ID: secret-{i}")
        time.sleep(random.random() / 50)
        return i

    before = sys.stdout
    for _ in range(5):
        with ThreadPoolExecutor(6) as pool:
            assert list(pool.map(lambda i: _quiet(chatty, i), range(12))) == list(range(12))
    assert sys.stdout is before
    print("after")
    out = capsys.readouterr().out
    assert "secret" not in out and "after" in out


def test_pykrx_is_only_imported_through_quiet():
    """pykrx는 import하는 순간 로그인하며 아이디를 출력한다 — 반드시 _krx()로만 불러온다."""
    from pathlib import Path
    found = [(path.name, line.strip()) for path in Path("src/agent").rglob("*.py")
             for line in path.read_text(encoding="utf-8").splitlines() if line.strip().startswith(("from pykrx", "import pykrx"))]
    assert found == [("prices.py", "from pykrx import stock")]          # _import_stock 한 곳뿐


def test_krx_import_is_quiet(monkeypatch, capsys):
    import sys
    import types

    from agent.collectors import prices
    fake = types.ModuleType("pykrx")
    fake.__path__ = []
    stock = types.ModuleType("pykrx.stock")
    fake.stock = stock
    monkeypatch.setitem(sys.modules, "pykrx", fake)
    monkeypatch.setitem(sys.modules, "pykrx.stock", stock)
    monkeypatch.setattr(prices, "_import_stock", lambda: print("로그인 ID: secret") or stock)
    assert prices._krx() is stock
    assert "secret" not in capsys.readouterr().out
