from factories import sample_context

from agent.analysis.alerts import detect_alerts
from agent.config import Settings
from agent.history.snapshot import make_snapshot
from agent.report.schema import Disclosure


def prev_from(ctx, **changes):
    """sample_context를 어제 스냅샷으로 바꾸고 첫 종목 값을 덮어쓴다."""
    snap = make_snapshot(ctx)
    snap["date"] = "2026-10-14"
    snap["holdings"][0].update(changes)
    return snap


def kinds(alerts):
    return [a.kind for a in alerts]


def test_no_prev_snapshot_means_no_alerts():
    assert detect_alerts(None, sample_context(), Settings()) == []


def test_nothing_changed():
    ctx = sample_context()
    assert detect_alerts(prev_from(ctx), ctx, Settings()) == []


def test_signal_change():
    ctx = sample_context()
    alerts = detect_alerts(prev_from(ctx, signal="add"), ctx, Settings())
    assert kinds(alerts) == ["signal_change"] and "추가매수 → 보유" in alerts[0].message


def test_level_cross_down_and_big_move_with_base_date():
    ctx = sample_context()                       # 재검토 기준가 60,350원
    ctx.holdings[0].price.close = 59000
    alerts = detect_alerts(prev_from(ctx, close=66000), ctx, Settings())
    assert set(kinds(alerts)) == {"level_cross", "big_move"}
    cross = next(a for a in alerts if a.kind == "level_cross")
    assert "재검토 기준가(60,350원) 아래로" in cross.message and cross.important
    move = next(a for a in alerts if a.kind == "big_move")
    assert "-10.6%" in move.message and "2026-10-14" in move.message


def test_level_cross_up():
    ctx = sample_context()
    ctx.holdings[0].price.close = 85000             # 일부매도 1차 84,553원 위로
    alerts = detect_alerts(prev_from(ctx, close=84000), ctx, Settings())
    assert kinds(alerts) == ["level_cross"] and "일부매도 1차(84,553원) 위로" in alerts[0].message


def test_small_move_below_threshold_ignored():
    ctx = sample_context()
    assert detect_alerts(prev_from(ctx, close=63000), ctx, Settings()) == []   # +3.2%


def test_new_disclosure_only():
    ctx = sample_context()
    old = Disclosure(date="2026-10-13", title="옛 공시", category="other", negative=False, url="u1")
    new = Disclosure(date="2026-10-15", title="유상증자결정", category="rights_issue", negative=True, url="u2")
    ctx.holdings[0].disclosures = [old, new]
    alerts = detect_alerts(prev_from(ctx, disclosures=["u1"]), ctx, Settings())
    assert kinds(alerts) == ["disclosure"] and "유상증자결정" in alerts[0].message and alerts[0].important


def test_nps_new_filing():
    ctx = sample_context()
    ctx.holdings[0].nps = {"stake_pct": 7.5, "change_pct": -0.1, "date": "2026-10-15"}
    alerts = detect_alerts(prev_from(ctx, nps_date="2026-09-30"), ctx, Settings())
    assert kinds(alerts) == ["nps"] and "7.50%" in alerts[0].message and "-0.10%p" in alerts[0].message


def test_earnings_soon_only_once_per_date():
    ctx = sample_context()                     # 오늘 2026-10-15
    ctx.holdings[1].next_earnings = "2026-10-17"
    prev = prev_from(ctx)
    prev["holdings"][1]["next_earnings"] = None
    assert kinds(detect_alerts(prev, ctx, Settings())) == ["earnings_soon"]
    prev["holdings"][1]["next_earnings"] = "2026-10-17"    # 어제(10-14)도 D-3 안이었다
    assert detect_alerts(prev, ctx, Settings()) == []


def test_new_holding_has_no_comparison_alerts():
    ctx = sample_context()
    prev = prev_from(ctx)
    prev["holdings"] = prev["holdings"][1:]     # 어제는 첫 종목이 없었다
    assert detect_alerts(prev, ctx, Settings()) == []


def test_alerts_carry_numeric_values():
    ctx = sample_context()
    ctx.holdings[0].price.close = 59000
    alerts = detect_alerts(prev_from(ctx, close=66000), ctx, Settings())
    move = next(a for a in alerts if a.kind == "big_move")
    assert move.values == [round(59000 / 66000 * 100 - 100, 1), 66000, 59000]
    cross = next(a for a in alerts if a.kind == "level_cross")
    assert cross.values == [59000, 60350]
