"""그날의 계산 결과 요약(스냅샷) — 알림 비교·주간 비교·성과 추적용. AI 해설·키·계좌번호는 넣지 않는다."""
from agent.report.schema import Context, HoldingContext

LEVEL_KEYS = [("sell2", "일부매도 2차"), ("sell1", "일부매도 1차"), ("buy1", "분할매수 1단계"),
              ("buy2", "분할매수 2단계"), ("buy3", "분할매수 3단계"), ("review", "재검토 기준가")]


def holding_levels(h: HoldingContext) -> dict[str, float]:
    v = h.valuation
    if v is None:
        return {}
    levels = {}
    if not v.insufficient:
        levels.update(buy1=v.buy[0], buy2=v.buy[1], buy3=v.buy[2], sell1=v.sell[0], sell2=v.sell[1])
    if v.review is not None:
        levels["review"] = v.review
    return levels


def make_snapshot(ctx: Context) -> dict:
    return {
        "version": 1,
        "date": ctx.date,
        "holdings": [{
            "ticker": h.ticker, "name": h.name, "market": h.market,
            "close": h.price.close if h.price else None,
            "signal": h.signal,
            "levels": holding_levels(h),
            "weight_pct": h.position.weight_pct,
            "nps_stake_pct": (h.nps or {}).get("stake_pct"),
            "nps_date": (h.nps or {}).get("date"),
            "disclosures": [d.url for d in h.disclosures],
            "next_earnings": h.next_earnings,
        } for h in ctx.holdings],
        "portfolio": {"total_krw": ctx.portfolio.total_krw, "cash_krw": ctx.portfolio.cash_krw,
                      "by_class": {k: w.pct for k, w in ctx.portfolio.by_class.items()}},
        "market": {"indices": {k: q.close for k, q in ctx.market.indices.items()},
                   "fx_usdkrw": ctx.market.fx_usdkrw},
        "alerts": [a.model_dump() for a in ctx.alerts],
    }
