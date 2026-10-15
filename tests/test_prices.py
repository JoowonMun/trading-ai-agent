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
