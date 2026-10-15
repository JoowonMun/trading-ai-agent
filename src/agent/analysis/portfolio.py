"""보유 합산, 원화 평가액, 비중, 리밸런싱 제안."""
from dataclasses import dataclass

from agent.config import Holdings, Settings
from agent.report.schema import ClassWeight, Portfolio, Rebalance

CLASS_LABELS = {"domestic": "국내", "us": "미국", "index": "지수"}


def position_key(market: str, ticker: str) -> str:
    return f"{market}:{ticker}"


@dataclass
class AggregatedPosition:
    key: str
    ticker: str
    name: str
    market: str
    asset_class: str
    qty: float
    avg_price: float
    analyze: bool


@dataclass
class PositionValue:
    position: AggregatedPosition
    close: float | None
    value_krw: float | None


def aggregate_positions(holdings: Holdings) -> list[AggregatedPosition]:
    merged: dict[str, AggregatedPosition] = {}
    for account in holdings.accounts:
        for p in account.positions:
            key = position_key(account.market, p.ticker)
            if key not in merged:
                merged[key] = AggregatedPosition(key, p.ticker, p.name or p.ticker, account.market,
                                                 account.asset_class, p.qty, p.avg_price, account.analyze)
                continue
            m = merged[key]
            total_qty = m.qty + p.qty
            m.avg_price = (m.avg_price * m.qty + p.avg_price * p.qty) / total_qty if total_qty else 0
            m.qty = total_qty
            m.analyze = m.analyze or account.analyze
    return list(merged.values())


def value_positions(positions: list[AggregatedPosition], closes: dict[str, float],
                    usdkrw: float | None) -> list[PositionValue]:
    out = []
    for p in positions:
        close = closes.get(p.key)
        fx = 1.0 if p.market == "KR" else usdkrw
        value = p.qty * close * fx if close is not None and fx else None
        out.append(PositionValue(p, close, value))
    return out


def summarize(values: list[PositionValue], cash_krw: float, settings: Settings) -> Portfolio:
    warnings = [f"{v.position.name}: {'시세' if v.close is None else '환율'} 없음 — 비중 계산에서 제외"
                for v in values if v.value_krw is None]
    incomplete = bool(warnings)
    priced = [v for v in values if v.value_krw is not None]
    total = sum(v.value_krw for v in priced) + cash_krw
    if total <= 0:
        return Portfolio(total_krw=0, cash_krw=cash_krw, warnings=warnings + ["평가금액이 0원입니다"])

    weights = {v.position.key: v.value_krw / total * 100 for v in priced}
    by_class, rebalance = {}, []
    band = settings.profile.rebalance_band_pct
    for cls, target in settings.target_allocation.items():
        value = sum(v.value_krw for v in priced if v.position.asset_class == cls)
        pct = value / total * 100
        diff = pct - target
        by_class[cls] = ClassWeight(label=CLASS_LABELS[cls], value_krw=value, pct=pct,
                                    target_pct=target, diff_pct=diff)
        if abs(diff) > band and not incomplete:
            rebalance.append(Rebalance(asset_class=cls, label=CLASS_LABELS[cls],
                                       action="줄이기" if diff > 0 else "늘리기",
                                       amount_krw=round(abs(diff) / 100 * total, -4)))

    if incomplete:
        warnings.append("평가 불완전 — 빠진 종목 때문에 비중이 틀릴 수 있어 리밸런싱 보류")

    limit = settings.profile.max_single_weight_pct
    for v in priced:
        weight = weights[v.position.key]
        if weight > limit and v.position.asset_class != "index":
            warnings.append(f"{v.position.name} 비중 {weight:.1f}% — 단일 종목 최대 {limit:.0f}% 초과")

    return Portfolio(total_krw=total, cash_krw=cash_krw, by_class=by_class, rebalance=rebalance,
                     warnings=warnings, weights=weights)
