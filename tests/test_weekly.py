from datetime import date

import pytest
from factories import sample_context

from agent.analysis.weekly import decide_report_type, weekly_diff
from agent.history.snapshot import make_snapshot
from agent.report.schema import Alert

ALERT = Alert(kind="big_move", ticker="005930", name="삼성전자", market="KR", message="m")


@pytest.mark.parametrize("today, prev, alerts, expected", [
    (date(2026, 10, 19), None, [], "weekly"),        # 월요일은 항상 주간
    (date(2026, 10, 19), {}, [ALERT], "weekly"),
    (date(2026, 10, 20), {}, [ALERT], "alert"),      # 화요일 + 알림
    (date(2026, 10, 20), {}, [], "none"),            # 화요일 + 알림 없음
    (date(2026, 10, 20), None, [], "none"),          # 첫 실행
])
def test_decide_report_type(today, prev, alerts, expected):
    assert decide_report_type(today, prev, alerts) == expected


def test_weekly_diff():
    ctx = sample_context()                                   # 삼성전자 65,000원, AAPL $230.50
    prev = make_snapshot(ctx)
    prev["date"] = "2026-10-08"
    prev["holdings"][0].update(close=60000, signal="add", weight_pct=7.0)
    prev["holdings"] = [prev["holdings"][0], {"ticker": "OLD", "name": "옛종목", "market": "US", "close": 10.0,
                                              "signal": None, "weight_pct": 1.0}]  # AAPL은 신규, OLD는 매도
    prev["portfolio"]["total_krw"] = 7_500_000
    prev["market"]["indices"]["KOSPI"] = 2400.0
    d = weekly_diff(prev, ctx, [ALERT])
    assert d.since == "2026-10-08"
    by = {h.ticker: h for h in d.holdings}
    assert by["005930"].status == "held" and by["005930"].return_pct == pytest.approx(65000 / 60000 * 100 - 100)
    assert (by["005930"].prev_signal, by["005930"].signal) == ("add", "hold")
    assert by["AAPL"].status == "new" and by["OLD"].status == "sold"
    assert d.total_change_pct == pytest.approx(8_000_000 / 7_500_000 * 100 - 100)
    assert d.index_changes["KOSPI"] == pytest.approx(2500 / 2400 * 100 - 100)
    assert d.alerts == [ALERT]


def test_weekly_diff_without_prev():
    assert weekly_diff(None, sample_context(), []) is None
