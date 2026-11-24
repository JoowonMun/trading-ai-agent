"""성과 추적: 계좌 수익률 vs 지수, 신호 적중 기록, 예상 연간 배당 (모두 코드가 계산)."""
from datetime import date, timedelta

from agent.report.schema import Context, Performance, SignalScore

SCORE_AFTER = timedelta(days=28)
BENCHMARK = {"KR": "KOSPI", "US": "S&P500"}
SCORED = {"add": "beat", "trim": "lag", "review": "lag"}  # hold는 채점하지 않는다


def _pct(now, before):
    return (now / before - 1) * 100 if now is not None and before else None


def _krw(h: dict, s: dict) -> float | None:
    close = h.get("close")
    if close is None:
        return None
    if h["market"] == "US":
        fx = s.get("market", {}).get("fx_usdkrw")
        return close * fx if fx else None
    return close


def chain_return(snaps: list[dict]) -> float | None:
    """전날 비중 × 종목 원화 수익률을 이어 붙인다. 입출금은 영향이 없고 현금은 수익 0."""
    if len(snaps) < 2:
        return None
    growth = 1.0
    for prev, cur in zip(snaps, snaps[1:]):
        now = {(h["market"], h["ticker"]): _krw(h, cur) for h in cur.get("holdings", [])}
        day = 0.0
        for h in prev.get("holdings", []):
            before, after = _krw(h, prev), now.get((h["market"], h["ticker"]))
            if before and after is not None and h.get("weight_pct") is not None:
                day += h["weight_pct"] / 100 * (after / before - 1)
        growth *= 1 + day
    return (growth - 1) * 100


def _index(s: dict, key: str):
    return s.get("market", {}).get("indices", {}).get(key)


def index_return(snaps: list[dict], key: str) -> float | None:
    return _pct(_index(snaps[-1], key), _index(snaps[0], key)) if len(snaps) >= 2 else None


def score_signals(snaps: list[dict]) -> list[SignalScore]:
    """신호가 바뀐 날(처음 붙은 날 포함)마다 28일 뒤 같은 시장 지수와 비교한다.

    신호가 며칠 사이 오락가락하면 같은 신호가 28일 안에 다시 붙어도 한 번만 센다.
    """
    scores = {k: SignalScore(signal=k) for k in SCORED}
    last: dict[tuple, str] = {}
    counted: dict[tuple, date] = {}
    for i, s in enumerate(snaps):
        for h in s.get("holdings", []):
            key, signal = (h["market"], h["ticker"]), h.get("signal")
            changed = signal and last.get(key) != signal
            if signal:
                last[key] = signal
            if not changed or signal not in SCORED:
                continue
            day = date.fromisoformat(s["date"])
            if (prev := counted.get((key, signal))) and day - prev < SCORE_AFTER:
                continue
            counted[(key, signal)] = day
            due = day + SCORE_AFTER
            later = next((x for x in snaps[i + 1:] if date.fromisoformat(x["date"]) >= due), None)
            if later is None:
                scores[signal].events += 1
                scores[signal].pending += 1
                continue
            after = next((x.get("close") for x in later.get("holdings", []) if (x["market"], x["ticker"]) == key), None)
            stock = _pct(after, h.get("close"))
            bench = _pct(_index(later, BENCHMARK[h["market"]]), _index(s, BENCHMARK[h["market"]]))
            if stock is None or bench is None:  # 그 사이 팔았거나 지수가 없으면 세지 않는다
                continue
            scores[signal].events += 1
            scores[signal].hits += (stock > bench) if SCORED[signal] == "beat" else (stock < bench)
    return list(scores.values())


def estimate_dividends(ctx: Context) -> tuple[float | None, list[str]]:
    """오늘 평가액 × 배당수익률 합 (천 원 단위). 실제 받은 금액이 아니다."""
    total, missing, found = 0.0, [], False
    for h in ctx.holdings:
        y = h.fundamentals.div_yield if h.fundamentals else None
        if y is None or h.position.weight_pct is None:
            missing.append(h.name)
            continue
        total += ctx.portfolio.total_krw * h.position.weight_pct / 100 * y / 100
        found = True
    return (round(total, -3) if found else None), missing


def build_performance(snaps: list[dict], week_since: str | None, ctx: Context) -> Performance:
    week = [s for s in snaps if week_since and s["date"] >= week_since]
    dividend, missing = estimate_dividends(ctx)
    return Performance(
        since=snaps[0]["date"], week_since=week_since,
        account_week_pct=chain_return(week), account_total_pct=chain_return(snaps),
        index_week_pct={k: v for k in BENCHMARK.values() if (v := index_return(week, k)) is not None},
        index_total_pct={k: v for k in BENCHMARK.values() if (v := index_return(snaps, k)) is not None},
        scores=score_signals(snaps), dividend_krw=dividend, dividend_missing=missing)
