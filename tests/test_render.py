from factories import sample_context

from agent.report.context import GLOSSARY_TERMS
from agent.report.glossary import GLOSSARY
from agent.report.render import auto_summary, render_report
from agent.report.schema import Analysis


def test_glossary_covers_all_terms():
    assert set(GLOSSARY_TERMS) <= set(GLOSSARY)


def test_auto_summary():
    lines = auto_summary(sample_context())
    assert lines[0].startswith("추가매수 후보 0개")
    assert "국내 1,740,000원 늘리기" in lines[1]


def test_numeric_report():
    html = render_report(sample_context(), None, ["AI 분석 없음 → 숫자 리포트"])
    assert "삼성전자" in html
    assert "보유" in html
    assert "68,699원" in html          # 적정가
    assert "$230.50" in html           # 미국 종목 가격
    assert "2단계" in html             # 누락 안내
    assert GLOSSARY["PER"] in html
    assert "투자 권유가 아닙니다" in html
    assert "숫자 리포트" in html


def test_report_with_analysis_uses_ai_text():
    analysis = Analysis(date="2026-10-15", summary=["오늘은 관망"], holdings=[{
        "ticker": "005930", "signal": "hold", "headline": "적정가 근처라 보유",
        "reasoning": "PER이 과거 평균보다 조금 낮아요."}])
    html = render_report(sample_context(), analysis, [])
    assert "오늘은 관망" in html
    assert "적정가 근처라 보유" in html


def test_html_is_escaped():
    analysis = Analysis(date="2026-10-15", summary=["<script>x</script>"], holdings=[])
    assert "<script>x" not in render_report(sample_context(), analysis, [])
