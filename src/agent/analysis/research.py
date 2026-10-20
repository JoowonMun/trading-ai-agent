"""'왜 움직였나' 조사 대상 선정 — 크게 움직인 종목을 변동폭 순으로 몇 개만 고른다."""
from agent.config import Settings
from agent.report.schema import Context


def pick_research_targets(ctx: Context, settings: Settings) -> list[str]:
    if ctx.report_type == "alert":
        moves = {a.ticker: abs(a.values[0]) for a in ctx.alerts if a.kind == "big_move" and a.values}
    elif ctx.report_type == "weekly" and ctx.weekly:
        moves = {h.ticker: abs(h.return_pct) for h in ctx.weekly.holdings
                 if h.status == "held" and h.return_pct is not None
                 and abs(h.return_pct) >= settings.research_weekly_move_pct}
    else:
        moves = {}
    return sorted(moves, key=moves.get, reverse=True)[:settings.research_max]
