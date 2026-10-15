from datetime import date

import pytest
from factories import FakeDart, FakeMarket

from agent.config import Account, Holdings, Position, Settings
from agent.report.context import ContextError, build_context

TODAY = date(2026, 10, 15)


def holdings():
    return Holdings(accounts=[
        Account(name="나무 국내", broker="nh", market="KR", asset_class="domestic", positions=[
            Position(ticker="005930", name="삼성전자", qty=10, avg_price=50000),
            Position(ticker="000660", name="SK하이닉스", qty=5, avg_price=50000),
        ]),
        Account(name="나무 미국", broker="nh", market="US", asset_class="us",
                positions=[Position(ticker="AAPL", name="Apple", qty=5, avg_price=150)]),
        Account(name="ISA", broker="mirae", market="KR", asset_class="index", analyze=False,
                positions=[Position(ticker="360750", name="TIGER 미국S&P500", qty=30, avg_price=18000)]),
    ])


def build(market=None, dart=None, h=None):
    return build_context(Settings(), h or holdings(), market or FakeMarket(),
                         dart or FakeDart(TODAY, negative={"000660"}), TODAY)


def by_ticker(ctx):
    return {h.ticker: h for h in ctx.holdings}


def test_happy_path():
    ctx = build()
    h = by_ticker(ctx)
    assert ctx.date == "2026-10-15"
    assert ctx.market.fx_usdkrw == 1300.0
    samsung = h["005930"]
    assert samsung.price.close == 60_000
    assert samsung.fundamentals.per > 0
    assert samsung.valuation.method == "PER" and not samsung.valuation.insufficient
    assert samsung.signal in {"add", "hold", "trim", "review"}
    assert samsung.position.weight_pct > 0
    assert samsung.assessments["roe"] in {"good", "neutral", "caution"}
    assert h["000660"].signal == "review"
    assert h["000660"].disclosures[0].negative
    assert h["AAPL"].signal is None and any("2단계" in m for m in h["AAPL"].missing)
    assert h["360750"].signal is None and h["360750"].price is not None and h["360750"].valuation is None
    assert ctx.portfolio.total_krw > 0
    assert "PER" in ctx.glossary_terms


def test_one_price_failure_does_not_stop_others():
    ctx = build(market=FakeMarket(fail={"005930"}))
    h = by_ticker(ctx)
    assert h["005930"].price is None and any("시세" in m for m in h["005930"].missing)
    assert h["000660"].signal == "review"
    assert any("삼성전자" in w for w in ctx.portfolio.warnings)


def test_dart_failure_marks_holding_missing():
    ctx = build(dart=FakeDart(TODAY, fail={"005930"}))
    samsung = by_ticker(ctx)["005930"]
    assert samsung.signal is None
    assert any("분석" in m for m in samsung.missing)
    assert samsung.price is not None


def test_all_prices_failed_raises():
    h = Holdings(accounts=[Account(name="a", broker="nh", market="KR", asset_class="domestic",
                                   positions=[Position(ticker="005930", qty=1, avg_price=1)])])
    with pytest.raises(ContextError):
        build(market=FakeMarket(fail={"005930"}), h=h)


def test_context_round_trips_as_json():
    from agent.report.schema import Context
    ctx = build()
    assert Context.model_validate_json(ctx.model_dump_json()) == ctx


def test_ticker_not_in_dart_is_noted_not_failed():
    from agent.collectors.dart import NotInDart

    class EtfDart(FakeDart):
        def corp_code(self, ticker):
            if ticker == "0189B0":
                raise NotInDart("없음")
            return super().corp_code(ticker)

    h = Holdings(accounts=[Account(name="a", broker="nh", market="KR", asset_class="domestic",
                                   positions=[Position(ticker="0189B0", name="TIGER 은액티브", qty=1, avg_price=1)])])
    etf = build(dart=EtfDart(TODAY), h=h).holdings[0]
    assert etf.signal is None and etf.price is not None
    assert etf.missing == ["ETF·펀드 등 개별 기업이 아니라 재무 분석 대상이 아닙니다"]
