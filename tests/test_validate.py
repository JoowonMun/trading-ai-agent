import copy

from factories import sample_context

from agent.report.validate import validate_analysis

BASE = {
    "date": "2026-10-15",
    "summary": ["삼성전자는 보유 유지"],
    "holdings": [{
        "ticker": "005930",
        "signal": "hold",
        "headline": "현재가 65,000원, 적정가 68,699원 근처",
        "reasoning": "PER 12.3배로 과거 중앙값 13.0배보다 조금 낮고, 재검토 기준(-15%)과는 거리가 있어요.",
        "indicator_notes": [{"term": "PER", "value": "12.3배", "plain": "이익 대비 주가 수준"}],
    }],
}


def analysis(**changes):
    raw = copy.deepcopy(BASE)
    raw["holdings"][0].update(changes)
    return raw


def test_valid_analysis_passes():
    result, errors = validate_analysis(analysis(), sample_context())
    assert errors == []
    assert result.holdings[0].headline.startswith("현재가")


def test_fabricated_price_rejected():
    result, errors = validate_analysis(analysis(headline="목표가 999,999원"), sample_context())
    assert result is None
    assert any("999,999원" in e for e in errors)


def test_signal_upgrade_rejected():
    _, errors = validate_analysis(analysis(signal="add"), sample_context())
    assert any("신호" in e for e in errors)


def test_add_to_hold_downgrade_needs_reason():
    ctx = sample_context()
    ctx.holdings[0].signal = "add"
    assert validate_analysis(analysis(signal="hold", signal_downgraded_reason="실적 발표 직전"), ctx)[1] == []
    assert validate_analysis(analysis(signal="hold"), ctx)[1] != []


def test_missing_ticker_rejected():
    raw = analysis()
    raw["holdings"] = []
    _, errors = validate_analysis(raw, sample_context())
    assert any("종목" in e for e in errors)


def test_schema_error():
    result, errors = validate_analysis({"date": "x"}, sample_context())
    assert result is None and errors[0].startswith("스키마")


def test_numbers_without_unit_are_ignored():
    _, errors = validate_analysis(analysis(reasoning="2026년 들어 5일 연속 상승"), sample_context())
    assert errors == []
