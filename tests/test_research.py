from factories import sample_context

from agent.analysis.research import pick_research_targets
from agent.config import Settings
from agent.report.schema import Alert, WeeklyDiff, WeeklyHolding


def big(t, change):
    return Alert(kind="big_move", ticker=t, name=t, market="KR", message="m", values=[change, 1.0, 1.0])


def test_alert_targets_sorted_and_capped():
    ctx = sample_context()
    ctx.report_type = "alert"
    ctx.alerts = [big("A", -5.5), big("B", 9.0), Alert(kind="disclosure", ticker="C", name="C", market="KR", message="m"),
                  big("D", -7.0), big("E", 6.0)]
    assert pick_research_targets(ctx, Settings()) == ["B", "D", "E"]


def test_weekly_targets_use_weekly_returns():
    ctx = sample_context()
    ctx.report_type = "weekly"
    ctx.weekly = WeeklyDiff(since="2026-10-08", holdings=[
        WeeklyHolding(ticker="X", name="X", market="US", status="held", return_pct=-8.0),
        WeeklyHolding(ticker="Y", name="Y", market="US", status="held", return_pct=3.0),
        WeeklyHolding(ticker="Z", name="Z", market="US", status="new")])
    assert pick_research_targets(ctx, Settings()) == ["X"]


def test_no_targets_without_history_or_on_quiet_day():
    ctx = sample_context()               # weekly, weekly=None
    assert pick_research_targets(ctx, Settings()) == []
    ctx.report_type = "none"
    assert pick_research_targets(ctx, Settings()) == []
