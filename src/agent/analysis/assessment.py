"""지표별 평가(좋음/보통/주의) — 초보자가 표에서 바로 읽을 수 있게 코드가 정해진 기준으로 매긴다."""
from agent.report.schema import Fundamentals, Valuation

Grade = str | None  # "good" | "neutral" | "caution" | None(판단 불가)


def _higher_is_better(value, good_at, caution_below) -> Grade:
    if value is None:
        return None
    if value >= good_at:
        return "good"
    if value < caution_below:
        return "caution"
    return "neutral"


def _band_position(value, valuation: Valuation | None, method: str) -> Grade:
    """과거 5년 밴드 하위 25% 아래면 싸다(좋음), 상위 25% 위면 비싸다(주의)."""
    if value is None or valuation is None or valuation.insufficient or valuation.method != method:
        return None
    if value < valuation.band.p25:
        return "good"
    if value > valuation.band.p75:
        return "caution"
    return "neutral"


def assess(f: Fundamentals, valuation: Valuation | None, financial: bool) -> dict[str, Grade]:
    if f.debt_ratio is None or financial:
        debt = None
    elif f.debt_ratio < 100:
        debt = "good"
    elif f.debt_ratio > 200:
        debt = "caution"
    else:
        debt = "neutral"
    return {
        "per": _band_position(f.per, valuation, "PER"),
        "pbr": _band_position(f.pbr, valuation, "PBR"),
        "roe": _higher_is_better(f.roe, 10, 5),
        "op_margin": _higher_is_better(f.op_margin, 10, 3),
        "rev_yoy": None if f.rev_yoy is None else ("good" if f.rev_yoy >= 5 else "caution" if f.rev_yoy <= -5 else "neutral"),
        "op_yoy": None if f.op_yoy is None else ("good" if f.op_yoy >= 10 else "caution" if f.op_yoy <= -30 else "neutral"),
        "debt_ratio": debt,
        "div_yield": None if f.div_yield is None else ("good" if f.div_yield >= 3 else "neutral"),
    }
