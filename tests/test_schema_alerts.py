from factories import sample_context

from agent.config import Settings
from agent.report.schema import Alert, Analysis, Context, WeeklyDiff


def test_context_defaults_keep_full_report_behaviour():
    ctx = sample_context()
    assert ctx.report_type == "weekly" and ctx.alerts == [] and ctx.weekly is None
    assert ctx.holdings[0].next_earnings is None


def test_alert_and_weekly_round_trip():
    ctx = sample_context()
    ctx.report_type = "alert"
    ctx.alerts = [Alert(kind="big_move", ticker="005930", name="삼성전자", market="KR",
                        message="삼성전자 -6.2% (2026-10-14 대비)", important=True)]
    ctx.weekly = WeeklyDiff(since="2026-10-13", holdings=[], alerts=ctx.alerts)
    assert Context.model_validate_json(ctx.model_dump_json()) == ctx


def test_analysis_alert_mode_allows_no_holdings():
    a = Analysis(date="2026-10-15", summary=["x"], alert_comments={"005930": "설명"})
    assert a.holdings == []


def test_alert_move_pct_default():
    assert Settings().alert_move_pct == 5.0
