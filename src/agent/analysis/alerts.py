"""직전 스냅샷 대비 의미 있는 변화 → 알림. 문구와 숫자는 여기서 만든다(AI는 해설만)."""
from datetime import date

from agent.config import Settings
from agent.history.snapshot import LEVEL_KEYS, holding_levels
from agent.report.schema import Alert, Context

SIGNAL_LABELS = {"add": "추가매수", "hold": "보유", "trim": "일부매도", "review": "재검토"}
IMPORTANT_LEVELS = {"review", "buy1", "sell1"}
EARNINGS_WINDOW_DAYS = 3


def _money(value: float, market: str) -> str:
    return f"${value:,.2f}" if market == "US" else f"{value:,.0f}원"


def _crossed(before: float, after: float, level: float) -> bool:
    return before > level >= after or before < level <= after


def _days_until(target: str | None, today: date) -> int | None:
    return None if not target else (date.fromisoformat(target) - today).days


def detect_alerts(prev: dict | None, ctx: Context, settings: Settings) -> list[Alert]:
    if prev is None:
        return []
    today = date.fromisoformat(ctx.date)
    prev_date = prev["date"]
    prev_by = {(p["market"], p["ticker"]): p for p in prev.get("holdings", [])}
    alerts: list[Alert] = []

    for h in ctx.holdings:
        def add(kind, message, important=False, values=()):
            alerts.append(Alert(kind=kind, ticker=h.ticker, name=h.name, market=h.market, message=message,
                                important=important, values=list(values)))

        p = prev_by.get((h.market, h.ticker))
        close = h.price.close if h.price else None
        if p is not None:
            if h.signal and p.get("signal") and h.signal != p["signal"]:
                add("signal_change", f"{h.name}: {SIGNAL_LABELS[p['signal']]} → {SIGNAL_LABELS[h.signal]}",
                    important=h.signal != "hold")
            before = p.get("close")
            if close and before:
                levels = holding_levels(h)
                for key, label in LEVEL_KEYS:
                    level = levels.get(key)
                    if level and _crossed(before, close, level):
                        direction = "아래로 내려왔어요" if close < level else "위로 올라섰어요"
                        add("level_cross", f"{h.name} 현재가 {_money(close, h.market)} — "
                                           f"{label}({_money(level, h.market)}) {direction}",
                            important=key in IMPORTANT_LEVELS, values=(close, level))
                change = (close / before - 1) * 100
                if abs(change) >= settings.alert_move_pct:
                    add("big_move", f"{h.name} {change:+.1f}% ({prev_date} 대비, {_money(before, h.market)} → "
                                    f"{_money(close, h.market)})", important=True,
                    values=(round(change, 1), before, close))
            known = set(p.get("disclosures", []))
            for d in h.disclosures:
                if d.url not in known:
                    add("disclosure", f"{h.name} 공시: {d.title} ({d.date})", important=d.negative)
            nps_date = (h.nps or {}).get("date")
            if h.nps and nps_date and nps_date > (p.get("nps_date") or ""):
                change_txt = f" ({h.nps['change_pct']:+.2f}%p)" if h.nps.get("change_pct") is not None else ""
                add("nps", f"국민연금 {h.name} 지분 {h.nps['stake_pct']:.2f}%{change_txt} · {nps_date} 신고",
                    values=[v for v in (h.nps["stake_pct"], h.nps.get("change_pct")) if v is not None])

        days = _days_until(h.next_earnings, today)
        if days is not None and 0 <= days <= EARNINGS_WINDOW_DAYS:
            prev_days = _days_until(p.get("next_earnings"), date.fromisoformat(prev_date)) if p else None
            already = (p is not None and p.get("next_earnings") == h.next_earnings
                       and prev_days is not None and 0 <= prev_days <= EARNINGS_WINDOW_DAYS)
            if not already:
                when = "오늘" if days == 0 else f"D-{days}"
                add("earnings_soon", f"{h.name} 실적 발표 {when} ({h.next_earnings})")
    return alerts
