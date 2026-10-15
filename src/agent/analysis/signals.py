"""판단 신호: review > trim > add > hold."""
from agent.config import Profile
from agent.report.schema import Fundamentals, Signal, Valuation


def decide_signal(close: float, valuation: Valuation, fundamentals: Fundamentals, weight_pct: float,
                  profile: Profile, negative_disclosure: bool, financial: bool = False) -> tuple[Signal, list[str]]:
    review_reasons = []
    if valuation.review is not None and close <= valuation.review:
        review_reasons.append("재검토 기준가 이하")
    if negative_disclosure:
        review_reasons.append("최근 악재 유형 공시")
    if review_reasons:
        return "review", review_reasons

    trim_reasons = []
    if not valuation.insufficient and close >= valuation.sell[0]:
        trim_reasons.append("일부매도 1차 목표가 도달")
    if weight_pct > profile.max_single_weight_pct:
        trim_reasons.append("단일 종목 최대 비중 초과")
    if trim_reasons:
        return "trim", trim_reasons

    debt_ok = financial or (fundamentals.debt_ratio is not None and fundamentals.debt_ratio < 200)
    if (not valuation.insufficient
            and close <= valuation.buy[0]
            and fundamentals.op_yoy is not None and fundamentals.op_yoy > -30
            and debt_ok
            and weight_pct < profile.max_single_weight_pct):
        return "add", ["분할매수 1단계 가격 이하", "실적·재무 조건 충족"]

    return "hold", []
