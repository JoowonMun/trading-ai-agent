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


def test_summary_table_sits_between_market_and_holdings():
    html = render_report(sample_context(), None, [])
    assert "한눈에 보기" in html
    assert html.index(">시장</h2>") < html.index("한눈에 보기") < html.index("52,846원") < html.index("보유 종목 상세")


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


REASON = {"005930": {"found": True, "summary": "반도체 업황 우려로 업종 전체가 약세였어요.",
                     "sources": ["https://www.yna.co.kr/view/AKR1", "https://www.hankyung.com/article/2"]}}


def test_move_reason_in_alert_mail():
    from agent.report.schema import Alert
    ctx = sample_context()
    ctx.report_type = "alert"
    ctx.alerts = [Alert(kind="big_move", ticker="005930", name="삼성전자", market="KR", message="삼성전자 -6.2%")]
    a = Analysis(date="2026-10-15", summary=["x"], move_reasons=REASON)
    html = render_report(ctx, a, [])
    assert "왜 움직였나" in html and "업종 전체가 약세" in html
    assert 'href="https://www.yna.co.kr/view/AKR1"' in html and ">www.yna.co.kr<" in html


def test_move_reason_in_weekly_report_and_not_found():
    ctx = sample_context()
    a = Analysis(date="2026-10-15", summary=["x"], holdings=[
        {"ticker": "005930", "signal": "hold", "headline": "h", "reasoning": "r"}],
        move_reasons={"005930": {"found": False, "summary": "뚜렷한 원인을 찾지 못했어요."}})
    html = render_report(ctx, a, [])
    assert "왜 움직였나" in html and "뚜렷한 원인을 찾지 못했어요" in html


def test_source_link_shows_real_host_not_userinfo():
    from agent.report.schema import Alert
    ctx = sample_context()
    ctx.report_type = "alert"
    ctx.alerts = [Alert(kind="big_move", ticker="005930", name="삼성전자", market="KR", message="m")]
    a = Analysis(date="2026-10-15", summary=["x"], move_reasons={"005930": {
        "found": True, "summary": "s", "sources": ["https://www.yna.co.kr@evil.example/x"]}})
    html = render_report(ctx, a, [])
    assert ">evil.example<" in html and ">www.yna.co.kr@evil.example<" not in html


def sector_ctx():
    from agent.report.schema import SectorRow
    ctx = sample_context()
    ctx.sectors = [SectorRow(key="US:XLK", name="기술", market="US", method="PER", value=26.3, history_weeks=3,
                             note="기록 3주 — 26주부터 과거와 비교", drawdown_52w_pct=-27.0),
                   SectorRow(key="KR:1013", name="전기전자", market="KR", method="PER", value=9.1, percentile=55.0,
                             level="보통"),
                   SectorRow(key="KR:1018", name="건설", market="KR", method="PBR", value=0.68, percentile=12.0,
                             level="싸요", earnings_1y_pct=-45.0, drawdown_52w_pct=-30.0, return_3m_pct=-8.0)]
    ctx.sectors_missing = ["국내 업종 증권: boom"]
    return ctx


def test_sector_section_in_weekly():
    from agent.report.glossary import GLOSSARY_SHORT
    html = render_report(sector_ctx(), None, [])
    assert "업종 온도계" in html and "PBR 0.68배" in html and "하위 12%" in html and "싸요" in html
    assert "-45.0%" in html and "기록 3주" in html and "증권: boom" in html and GLOSSARY_SHORT["이익 방향"] in html
    assert html.index("건설") < html.index("전기전자")          # 싼 업종이 위


def test_sector_section_only_in_weekly_with_rows():
    ctx = sector_ctx()
    ctx.report_type = "alert"
    assert "업종 온도계" not in render_report(ctx, None, [])
    assert "업종 온도계" not in render_report(sample_context(), None, [])


def test_huge_earnings_change_is_capped_in_display():
    ctx = sector_ctx()
    ctx.sectors[2].earnings_1y_pct = 2675.8
    html = render_report(ctx, None, [])
    assert "+200% 넘게" in html and "2675.8" not in html


def test_percentile_shown_as_top_when_above_half_and_note_shown():
    ctx = sector_ctx()
    ctx.sectors[1].percentile, ctx.sectors[1].level = 71.0, "비싸요"
    ctx.sectors[2].note = "이익이 급증해 PER이 낮아 보일 수 있어요"
    html = render_report(ctx, None, [])
    assert "상위 29%" in html and "하위 12%" in html and "이익이 급증해" in html


def signal_ctx():
    from agent.report.schema import QuietSignal
    ctx = sector_ctx()
    ctx.sectors[2].name = "금속"
    ctx.sectors[2].earnings_1y_pct = 91.2
    ctx.promising_sectors = ["금속"]
    base = dict(title="단일판매ㆍ공급계약체결", date="2026-11-18", why="계약은 앞으로 매출이 늘어날 근거예요")
    ctx.signals = [QuietSignal(ticker="000002", name="가짜제강", kind="contract", url="https://dart.fss.or.kr/x?rcpNo=1",
                               group="promising", sector="금속", **base),
                   QuietSignal(ticker="000003", name="가짜전자", kind="rights_issue", url="https://dart.fss.or.kr/x?rcpNo=2",
                               group="large", caution=True, title="유상증자결정", date="2026-11-17",
                               why="주식 수가 늘어 기존 주주 몫이 줄 수 있어요")]
    ctx.signals_more = 5
    return ctx


def test_signal_section_in_weekly():
    html = render_report(signal_ctx(), None, [])
    assert "조용한 신호" in html and "가짜제강" in html and "금속 · 이익 +91.2%" in html
    assert 'href="https://dart.fss.or.kr/x?rcpNo=1"' in html and "⚠ 주식 수가 늘어" in html and "외 5건" in html


def test_signal_section_absent_when_empty():
    assert "이번 주 조용한 신호" not in render_report(sector_ctx(), None, [])
    ctx = signal_ctx()
    ctx.report_type = "alert"
    assert "이번 주 조용한 신호" not in render_report(ctx, None, [])


def news_report():
    from agent.report.schema import NewsGroup, NewsItem, NewsReport
    it = NewsItem(title="가짜중공업 <b>원전</b> 수주", source="가짜신문", date="2026-11-20",
                  url="https://news.google.com/rss/articles/AAA")
    return NewsReport(groups=[NewsGroup(kind="sector", name="금속", query="철강 업황", items=[it]),
                              NewsGroup(kind="theme", name="원전", query="원전", items=[it])],
                      missing=["뉴스 조선: 막힘"])


def test_news_section_in_weekly():
    html = render_report(sector_ctx(), None, [], news=news_report())
    assert "이번 주 읽어볼 뉴스" in html and "[유망 업종 · 금속] 철강 업황" in html and "[테마 · 원전]" in html
    assert "&lt;b&gt;원전" in html and "가짜신문 (11/20)" in html and "누락: 뉴스 조선: 막힘" in html
    assert 'href="https://news.google.com/rss/articles/AAA"' in html


def test_news_section_absent_without_news_or_in_alert():
    assert "이번 주 읽어볼 뉴스" not in render_report(sector_ctx(), None, [])
    ctx = sector_ctx()
    ctx.report_type = "alert"
    assert "이번 주 읽어볼 뉴스" not in render_report(ctx, None, [], news=news_report())


def opinion_ctx():
    from agent.report.schema import Candidate
    ctx = signal_ctx()          # sectors[2] = 금속 PBR 0.68 하위 12% 싸요, 이익 +91.2%
    ctx.opinion_sectors = ["금속"]
    ctx.candidates = [Candidate(ticker="000001", name="가짜제철", sector="금속", method="PBR", value=0.4,
                                sector_median=0.85, held=True)]
    return ctx


def test_opinion_section_numbers_only():
    html = render_report(opinion_ctx(), None, [])
    assert "이번 주 살펴볼 곳" in html and "[금속] PBR 싸요" in html and "하위 12%" in html
    assert "<strong>가짜제철</strong> 000001" in html and "PBR 0.40 (업종 중간 0.85)" in html and "보유 중" in html
    assert "사라는 뜻이 아니에요" in html and "후보 기준: 시가총액 상위 300" in html
    assert html.index("이번 주 살펴볼 곳") < html.index("한눈에 보기")


def test_opinion_section_absent_without_sectors_or_in_alert():
    assert "이번 주 살펴볼 곳" not in render_report(sector_ctx(), None, [])
    ctx = opinion_ctx()
    ctx.report_type = "alert"
    assert "이번 주 살펴볼 곳" not in render_report(ctx, None, [])


def test_opinion_section_with_ai_text():
    from agent.report.schema import Opinions, SectorOpinion, ThemeOpinion
    ops = Opinions(sectors={"금속": SectorOpinion(up="수요 <회복> 전망이에요", down="수입품이 늘 수 있어요",
                                                 watch="다음 분기 실적", sources=["https://news.example/a"])},
                   themes={"원전": ThemeOpinion(view="해외 수주 기대가 이어져요", sources=["https://x.example/b"])})
    html = render_report(opinion_ctx(), None, [], opinions=ops)
    assert "오를 수 있는 이유:</strong> 수요 &lt;회복&gt; 전망이에요" in html
    assert "안 오를 수 있는 이유:</strong> 수입품이 늘 수 있어요" in html and "확인할 것:</strong> 다음 분기 실적" in html
    assert 'href="https://news.example/a"' in html and "[테마 · 원전]</strong> 해외 수주 기대가 이어져요" in html


def test_opinion_card_shows_sector_warning():
    ctx = opinion_ctx()
    ctx.sectors[2].note = "경기 정점일 수 있어요"
    html = render_report(ctx, None, [])
    card = html[html.index("이번 주 살펴볼 곳"):html.index("한눈에 보기")]
    assert "⚠ 경기 정점일 수 있어요" in card


def perf_ctx():
    from agent.report.schema import Performance, SignalScore
    ctx = sample_context()
    ctx.performance = Performance(
        since="2026-10-01", week_since="2026-10-08", account_week_pct=1.23, account_total_pct=-2.5,
        index_week_pct={"KOSPI": 0.5}, index_total_pct={"KOSPI": 3.0, "S&P500": 1.0},
        scores=[SignalScore(signal="add", events=3, hits=1, pending=1), SignalScore(signal="trim"),
                SignalScore(signal="review", events=1, pending=1)],
        dividend_krw=14_000, dividend_missing=["가짜ETF"])
    return ctx


def test_performance_section():
    html = render_report(perf_ctx(), None, [])
    assert "📈 성과" in html and "+1.2%" in html and "-2.5%" in html and "+3.0%" in html
    assert "추가매수: 2번 중 1번 지수보다 나았어요 (채점 대기 1건)" in html
    assert "재검토: 아직 채점할 신호가 없어요 (채점 대기 1건)" in html and "일부매도" not in html.split("📈 성과")[1].split("</ul>")[0]
    assert "14,000원" in html and "추정" in html and "가짜ETF" in html and "현금 포함" in html


def test_performance_missing_and_not_in_alert():
    ctx = sample_context()
    ctx.performance_missing = ["성과: OSError"]
    assert "성과: OSError" in render_report(ctx, None, [])
    alert = perf_ctx()
    alert.report_type = "alert"
    assert "📈 성과" not in render_report(alert, None, [])
