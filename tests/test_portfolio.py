import pytest

from agent.analysis.portfolio import aggregate_positions, summarize, value_positions
from agent.config import Account, Holdings, Position, Settings


def holdings():
    return Holdings(accounts=[
        Account(name="나무 국내", broker="nh", market="KR", asset_class="domestic",
                positions=[Position(ticker="A", name="에이", qty=100, avg_price=5000)]),
        Account(name="나무 미국", broker="nh", market="US", asset_class="us",
                positions=[Position(ticker="B", name="비", qty=1, avg_price=150)]),
        Account(name="ISA", broker="mirae", market="KR", asset_class="index", analyze=False,
                positions=[Position(ticker="C", name="씨", qty=10, avg_price=15000)]),
    ])


def run(closes, fx=1000.0, cash=0, h=None):
    positions = aggregate_positions(h or holdings())
    return summarize(value_positions(positions, closes, fx), cash, Settings())


def test_imbalanced_portfolio():
    p = run({"KR:A": 6000, "US:B": 200, "KR:C": 20000})
    assert p.total_krw == 1_000_000
    assert p.by_class["domestic"].pct == pytest.approx(60)
    assert [(r.asset_class, r.action, r.amount_krw) for r in p.rebalance] == [
        ("domestic", "줄이기", 300_000), ("us", "늘리기", 200_000), ("index", "늘리기", 100_000)]
    assert p.weights["KR:A"] == pytest.approx(60)
    assert any("에이" in w for w in p.warnings)
    assert not any("씨" in w for w in p.warnings)  # 지수 ETF는 단일 종목 경고 제외


def test_balanced_portfolio_has_no_rebalance():
    p = run({"KR:A": 3000, "US:B": 400, "KR:C": 30000})
    assert p.rebalance == []


def test_same_ticker_in_two_accounts_is_merged():
    h = holdings()
    h.accounts[2].positions.append(Position(ticker="A", qty=100, avg_price=7000))
    merged = {p.key: p for p in aggregate_positions(h)}
    assert merged["KR:A"].qty == 200
    assert merged["KR:A"].avg_price == 6000
    assert merged["KR:A"].analyze is True


def test_missing_price_is_excluded_and_rebalance_withheld():
    p = run({"KR:A": 6000, "KR:C": 20000})
    assert p.total_krw == 800_000
    assert any("비: 시세 없음" in w for w in p.warnings)
    assert p.rebalance == []
    assert any("리밸런싱 보류" in w for w in p.warnings)


def test_missing_fx_excludes_us_with_fx_reason():
    p = run({"KR:A": 6000, "US:B": 200, "KR:C": 20000}, fx=None)
    assert "US:B" not in p.weights
    assert any("비: 환율 없음" in w for w in p.warnings)
    assert p.rebalance == []


def test_nan_price_is_treated_as_missing():
    p = run({"KR:A": 6000, "US:B": float("nan"), "KR:C": 20000})
    assert "US:B" not in p.weights
    assert all(w == w for w in p.weights.values())  # NaN 없음
    assert any("비: 시세 없음" in w for w in p.warnings)
