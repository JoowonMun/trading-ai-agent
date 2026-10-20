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


def test_summary_table_comes_first():
    html = render_report(sample_context(), None, [])
    assert "한눈에 보기" in html
    assert html.index("한눈에 보기") < html.index("52,846원") < html.index("보유 종목 상세")


def test_price_ladder_places_current_price():
    from agent.report.render import price_ladder
    ladder = price_ladder(sample_context().holdings[0])
    assert [label for label, _, _ in ladder] == [
        "일부매도 2차", "일부매도 1차", "적정가", "현재가", "재검토 기준가",
        "분할매수 1단계", "분할매수 2단계", "분할매수 3단계"]
    assert [is_now for _, _, is_now in ladder].count(True) == 1


def test_indicator_table_shows_grades_and_short_text():
    from agent.report.glossary import GLOSSARY_SHORT
    html = render_report(sample_context(), None, [])
    assert "좋음" in html and "보통" in html and "주의" in html
    assert GLOSSARY_SHORT["ROE"] in html
    assert html.count(GLOSSARY["PER"]) == 1   # 긴 설명은 맨 아래 용어 풀이에만


def test_html_is_escaped():
    analysis = Analysis(date="2026-10-15", summary=["<script>x</script>"], holdings=[])
    assert "<script>x" not in render_report(sample_context(), analysis, [])


def test_distorted_band_warning_is_shown():
    ctx = sample_context()
    ctx.holdings[0].valuation.distorted = True
    ctx.holdings[0].valuation.note = "적정가가 현재가의 3.0배라 과거 밴드가 지금과 맞지 않을 수 있어요"
    html = render_report(ctx, None, [])
    assert "밴드 왜곡 가능" in html and "3.0배라" in html


def test_nps_section_and_holding_line():
    ctx = sample_context()
    ctx.nps_annual_as_of = "2025-12-31"
    ctx.nps_changes = [{"name": "삼성전자", "ticker": "005930", "stake_pct": 7.5, "change_pct": -0.1,
                        "date": "2026-10-14", "mine": True},
                       {"name": "대한항공", "ticker": "003490", "stake_pct": 9.97, "change_pct": None,
                        "date": "2026-10-15", "mine": False}]
    ctx.holdings[0].nps = {"stake_pct": 7.5, "change_pct": -0.1, "date": "2026-10-14",
                           "annual_rank": 1, "annual_stake_pct": 7.76}
    ctx.portfolio.nps_overlap = ["삼성전자"]
    html = render_report(ctx, None, [])
    assert "국민연금 동향" in html and "★" in html and "대한항공" in html
    assert "국민연금 지분 7.50%" in html and "-0.10%p" in html and "국민연금 보유 1위" in html
    assert "2025년 말 기준" in html


def test_holding_with_only_annual_nps_rank_renders():
    ctx = sample_context()
    ctx.holdings[0].nps = {"annual_rank": 1, "annual_stake_pct": 7.76}
    html = render_report(ctx, None, [])
    assert "국민연금 보유 1위" in html and "국민연금 지분" not in html


def test_nps_us_section_and_holding_line():
    ctx = sample_context()
    nvda = {"name": "NVIDIA CORPORATION", "shares": 1500.0, "value": 9e9, "rank": 1, "change_pct": 50.0, "new": False}
    newco = {"name": "NEWCO INC", "shares": 100.0, "value": 5e7, "rank": 40, "change_pct": None, "new": True}
    ctx.nps_us = {"period": "2026-06-30", "filed": "2026-08-12", "prev_period": "2026-03-31",
                  "top_holdings": [nvda], "top_buys": [nvda, newco], "top_sells": [],
                  "sold_out": [{"name": "OLDCO CORP", "prev_shares": 50.0, "prev_value": 4e5}]}
    ctx.holdings[1].nps = {"us_rank": 3, "us_shares": 2000.0, "us_change_pct": -12.5, "us_new": False,
                           "us_period": "2026-06-30"}
    html = render_report(ctx, None, [])
    assert "국민연금 미국 보유" in html and "2026-06-30" in html
    assert "NVIDIA CORPORATION" in html and "+50.0%" in html and "신규" in html and "OLDCO CORP" in html
    assert "국민연금 미국 보유 3위" in html and "-12.5%" in html


def test_alert_mail_shows_only_alerts_and_comments():
    from agent.report.schema import Alert
    ctx = sample_context()
    ctx.report_type = "alert"
    ctx.alerts = [Alert(kind="level_cross", ticker="005930", name="삼성전자", market="KR",
                        message="삼성전자 현재가 65,000원 — 재검토 기준가(60,350원) 아래로 내려왔어요", important=True)]
    a = Analysis(date="2026-10-15", summary=["재검토 알림 1건"], alert_comments={"005930": "처음 산 이유를 점검해 보세요."})
    html = render_report(ctx, a, [])
    assert "투자 알림" in html and "재검토 기준가(60,350원)" in html and "처음 산 이유를 점검" in html
    assert "용어 풀이" not in html and "<strong>Apple</strong>" not in html   # 알림 없는 종목·긴 섹션은 없음 (글꼴 이름 "Apple SD Gothic"과 구분)


def test_alert_mail_without_ai_uses_auto_summary():
    from agent.report.schema import Alert
    ctx = sample_context()
    ctx.report_type = "alert"
    ctx.alerts = [Alert(kind="big_move", ticker="005930", name="삼성전자", market="KR", message="m", important=True)]
    assert "알림 1건 (중요 1건)" in render_report(ctx, None, [])


def test_weekly_section():
    from agent.report.schema import WeeklyDiff, WeeklyHolding
    ctx = sample_context()
    ctx.weekly = WeeklyDiff(since="2026-10-08", total_krw=8_000_000, prev_total_krw=7_500_000, total_change_pct=6.67,
                            index_changes={"KOSPI": 4.17},
                            holdings=[WeeklyHolding(ticker="005930", name="삼성전자", market="KR", status="held",
                                                    close=65000, prev_close=60000, return_pct=8.33,
                                                    signal="hold", prev_signal="add", weight_pct=8.2, prev_weight_pct=7.0),
                                      WeeklyHolding(ticker="OLD", name="옛종목", market="US", status="sold")])
    html = render_report(ctx, None, [])
    assert "지난주 대비" in html and "+8.3%" in html and "추가매수 → 보유" in html and "전량 매도" in html
    assert "+6.7%" in html and "주간 투자 리포트" in html
