"""주간 리포트의 '지난주 대비'와 메일 종류 결정."""
from datetime import date

from agent.report.schema import Alert, Context, ReportType, WeeklyDiff, WeeklyHolding


def decide_report_type(today: date, prev: dict | None, alerts: list[Alert]) -> ReportType:
    if today.weekday() == 0:
        return "weekly"
    if prev is None or not alerts:
        return "none"
    return "alert"


def _pct(now, before):
    return (now / before - 1) * 100 if now is not None and before else None


def weekly_diff(prev: dict | None, ctx: Context, week_alerts: list[Alert]) -> WeeklyDiff | None:
    if prev is None:
        return None
    prev_by = {(p["market"], p["ticker"]): p for p in prev.get("holdings", [])}
    rows, seen = [], set()
    for h in ctx.holdings:
        key = (h.market, h.ticker)
        seen.add(key)
        p = prev_by.get(key)
        close = h.price.close if h.price else None
        rows.append(WeeklyHolding(
            ticker=h.ticker, name=h.name, market=h.market, status="held" if p else "new",
            close=close, prev_close=p.get("close") if p else None,
            return_pct=_pct(close, p.get("close")) if p else None,
            signal=h.signal, prev_signal=p.get("signal") if p else None,
            weight_pct=h.position.weight_pct, prev_weight_pct=p.get("weight_pct") if p else None))
    for key, p in prev_by.items():
        if key not in seen:
            rows.append(WeeklyHolding(ticker=p["ticker"], name=p["name"], market=p["market"], status="sold",
                                      prev_close=p.get("close"), prev_signal=p.get("signal"),
                                      prev_weight_pct=p.get("weight_pct")))
    prev_total = prev.get("portfolio", {}).get("total_krw")
    prev_classes = prev.get("portfolio", {}).get("by_class", {})
    prev_idx = prev.get("market", {}).get("indices", {})
    return WeeklyDiff(
        since=prev["date"], holdings=rows,
        total_krw=ctx.portfolio.total_krw, prev_total_krw=prev_total,
        total_change_pct=_pct(ctx.portfolio.total_krw, prev_total),
        class_changes={k: {"pct": w.pct, "prev_pct": prev_classes.get(k)} for k, w in ctx.portfolio.by_class.items()},
        index_changes={k: c for k, q in ctx.market.indices.items() if (c := _pct(q.close, prev_idx.get(k))) is not None},
        alerts=week_alerts)
