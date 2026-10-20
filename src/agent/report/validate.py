"""AI가 쓴 analysis.json이 context.json의 숫자·신호를 벗어나지 않는지 검사."""
import re

from pydantic import ValidationError

from agent.report.schema import Analysis, Context

NUMBER_WITH_UNIT = re.compile(
    r"\$\s?(?P<usd>-?\d[\d,]*(?:\.\d+)?)"
    r"|(?P<num>-?\d[\d,]*(?:\.\d+)?)\s*(?P<mult>[만억조])?\s*(?P<unit>원|달러|%|배)")
MULTIPLIERS = {"만": 1e4, "억": 1e8, "조": 1e12}


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


def _matches(text_number: str, multiplier: float, allowed: list[float]) -> bool:
    value = abs(float(text_number.replace(",", ""))) * multiplier
    decimals = len(text_number.split(".")[1]) if "." in text_number else 0
    tolerance = 0.5 * 10 ** (-decimals) * multiplier + 1e-9
    return any(abs(value - abs(a)) <= tolerance for a in allowed)


def _unsupported(text: str, allowed: list[float], percent_only: list[float]) -> list[str]:
    bad = []
    for m in NUMBER_WITH_UNIT.finditer(text):
        if m.group("usd"):
            ok = _matches(m.group("usd"), 1, allowed)
        else:
            pool = allowed + percent_only if m.group("unit") == "%" else allowed
            ok = _matches(m.group("num"), MULTIPLIERS.get(m.group("mult"), 1), pool)
        if not ok:
            bad.append(m.group(0))
    return bad


def _holding_texts(h) -> list[str]:
    texts = [h.headline, h.reasoning, h.signal_downgraded_reason or "", h.disclosure_notes]
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
    alert_mode_without_holdings = context.report_type == "alert" and not analysis.holdings
    if set(got) != set(expected) and not alert_mode_without_holdings:
        errors.append(f"종목 불일치: 기대 {sorted(expected)} / 실제 {sorted(got)}")

    for ticker, h in got.items():
        want = expected.get(ticker)
        if want is None or h.signal == want:
            continue
        if want == "add" and h.signal == "hold" and (h.signal_downgraded_reason or "").strip():
            continue
        errors.append(f"{ticker}: 신호 변경 불가 ({want} → {h.signal})")

    # 종목 설명에는 그 종목 숫자 + 포트폴리오·시장 숫자만, 전체 요약에는 모든 종목 숫자까지 허용.
    # 성향 기준값(15% 등)은 % 단위로 쓸 때만 허용.
    shared = _numbers(context.portfolio.model_dump()) + _numbers(context.market.model_dump())
    if context.weekly is not None:  # 월요일 '지난주 대비' 숫자
        shared += _numbers(context.weekly.model_dump(exclude={"alerts"}))
    per_holding = {h.ticker: _numbers(h.model_dump()) for h in context.holdings}
    percent_only = _numbers(context.profile.model_dump())

    # 알림의 숫자 값(코드가 계산해 문구에 넣은 값)도 근거로 인정한다 — 해설에서는 그 종목 알림의 값만
    alert_values: dict[str, list[float]] = {}
    for a in context.alerts:
        alert_values.setdefault(a.ticker, []).extend(a.values)
    alert_numbers = [n for values in alert_values.values() for n in values]
    alert_tickers = set(alert_values)

    general = [*analysis.summary, analysis.market_comment, analysis.portfolio_comment, analysis.watchlist_comment]
    everything = shared + [n for nums in per_holding.values() for n in nums] + alert_numbers
    checks = [(text, everything) for text in general]
    for h in analysis.holdings:
        checks += [(text, shared + per_holding.get(h.ticker, [])) for text in _holding_texts(h)]
    for ticker, comment in analysis.alert_comments.items():
        if ticker not in alert_tickers:
            errors.append(f"알림에 없는 종목 해설: {ticker}")
            continue
        checks.append((comment, shared + per_holding.get(ticker, []) + alert_values[ticker]))
    for text, allowed in checks:
        errors += [f"근거 없는 숫자: {bad}" for bad in _unsupported(text, allowed, percent_only)]

    return (None if errors else analysis), errors


def check_move_reasons(analysis: Analysis, context: Context) -> list[str]:
    """AI가 웹에서 찾은 '왜 움직였나'를 검사한다. 뉴스 속 숫자는 검증할 수 없어 단위 붙은 숫자를 금지한다."""
    errors = []
    targets = set(context.research_targets)
    for ticker, reason in analysis.move_reasons.items():
        if ticker not in targets:
            errors.append(f"조사 대상이 아닌 종목: {ticker}")
            continue
        if reason.found and not 1 <= len(reason.sources) <= 3:
            errors.append(f"{ticker}: 출처 링크는 1~3개여야 합니다")
        if any(not s.startswith(("https://", "http://")) for s in reason.sources):
            errors.append(f"{ticker}: 출처는 http(s) 링크여야 합니다")
        if NUMBER_WITH_UNIT.search(reason.summary):
            errors.append(f"{ticker}: 원인 요약에 숫자를 쓸 수 없습니다 ({NUMBER_WITH_UNIT.search(reason.summary).group(0)})")
    return errors
