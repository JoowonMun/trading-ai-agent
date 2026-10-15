"""AI가 쓴 analysis.json이 context.json의 숫자·신호를 벗어나지 않는지 검사."""
import re

from pydantic import ValidationError

from agent.report.schema import Analysis, Context

NUMBER_WITH_UNIT = re.compile(r"\$\s?(-?\d[\d,]*(?:\.\d+)?)|(-?\d[\d,]*(?:\.\d+)?)\s*(?:원|달러|%|배)")


def _numbers(obj) -> list[float]:
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in _numbers(v)]
    if isinstance(obj, list):
        return [n for v in obj for n in _numbers(v)]
    return []


def _matches(text_number: str, allowed: list[float]) -> bool:
    value = abs(float(text_number.replace(",", "")))
    decimals = len(text_number.split(".")[1]) if "." in text_number else 0
    tolerance = 0.5 * 10 ** (-decimals) + 1e-9
    return any(abs(value - abs(a)) <= tolerance for a in allowed)


def _texts(analysis: Analysis) -> list[str]:
    texts = [*analysis.summary, analysis.market_comment, analysis.portfolio_comment, analysis.watchlist_comment]
    for h in analysis.holdings:
        texts += [h.headline, h.reasoning, h.signal_downgraded_reason or "", h.disclosure_notes]
        for note in h.indicator_notes:
            texts += [note.value, note.plain]
    return texts


def validate_analysis(raw: dict, context: Context) -> tuple[Analysis | None, list[str]]:
    try:
        analysis = Analysis.model_validate(raw)
    except ValidationError as e:
        return None, [f"스키마 오류 {e.error_count()}건: {e.errors()[0]['loc']} {e.errors()[0]['msg']}"]

    errors = []
    expected = {h.ticker: h.signal for h in context.holdings if h.signal}
    got = {h.ticker: h for h in analysis.holdings}
    if set(got) != set(expected):
        errors.append(f"종목 불일치: 기대 {sorted(expected)} / 실제 {sorted(got)}")

    for ticker, h in got.items():
        want = expected.get(ticker)
        if want is None or h.signal == want:
            continue
        if want == "add" and h.signal == "hold" and (h.signal_downgraded_reason or "").strip():
            continue
        errors.append(f"{ticker}: 신호 변경 불가 ({want} → {h.signal})")

    allowed = _numbers(context.model_dump())
    for text in _texts(analysis):
        for match in NUMBER_WITH_UNIT.finditer(text):
            number = match.group(1) or match.group(2)
            if not _matches(number, allowed):
                errors.append(f"근거 없는 숫자: {match.group(0)}")

    return (None if errors else analysis), errors
