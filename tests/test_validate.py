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


def test_korean_unit_multipliers_are_checked():
    assert validate_analysis(analysis(headline="현재가 6.5만원"), sample_context())[1] == []
    _, errors = validate_analysis(analysis(headline="목표가 7.5만원"), sample_context())
    assert any("7.5만원" in e for e in errors)
    _, errors = validate_analysis(analysis(headline="순이익 5조원"), sample_context())
    assert any("5조원" in e for e in errors)


def test_number_from_another_holding_rejected():
    _, errors = validate_analysis(analysis(headline="현재가 $230.50"), sample_context())  # AAPL 가격
    assert any("230.50" in e for e in errors)


def test_profile_numbers_only_allowed_as_percent():
    _, errors = validate_analysis(analysis(reasoning="PER 15배라 적정"), sample_context())
    assert any("15배" in e for e in errors)


def test_numbers_without_unit_are_ignored():
    _, errors = validate_analysis(analysis(reasoning="2026년 들어 5일 연속 상승"), sample_context())
    assert errors == []


def alert_context():
    from agent.report.schema import Alert
    ctx = sample_context()
    ctx.report_type = "alert"
    ctx.alerts = [Alert(kind="big_move", ticker="005930", name="삼성전자", market="KR",
                        message="삼성전자 -6.2% (2026-10-14 대비, 69,300원 → 65,000원)", important=True,
                        values=[-6.2, 69300.0, 65000.0])]
    return ctx


def test_alert_mode_allows_empty_holdings_and_checks_comments():
    raw = {"date": "2026-10-15", "summary": ["삼성전자가 크게 내렸어요"],
           "alert_comments": {"005930": "하루에 -6.2% 내려 69,300원에서 65,000원이 됐어요."}}
    assert validate_analysis(raw, alert_context())[1] == []          # 알림 문구 숫자 허용


def test_alert_comment_fabricated_number_rejected():
    raw = {"date": "2026-10-15", "summary": ["x"], "alert_comments": {"005930": "목표가 99,000원"}}
    assert any("99,000원" in e for e in validate_analysis(raw, alert_context())[1])


def test_alert_comment_for_unknown_ticker_rejected():
    raw = {"date": "2026-10-15", "summary": ["x"], "alert_comments": {"ZZZZ": "설명"}}
    assert any("ZZZZ" in e for e in validate_analysis(raw, alert_context())[1])


def test_weekly_numbers_are_allowed_in_summary():
    from agent.report.schema import WeeklyDiff
    ctx = sample_context()
    ctx.weekly = WeeklyDiff(since="2026-10-08", total_change_pct=3.27)
    raw = analysis()
    raw["summary"] = ["지난주 대비 총평가액 +3.3%"]
    assert validate_analysis(raw, ctx)[1] == []


def test_date_fragments_in_alerts_do_not_become_allowed_numbers():
    raw = {"date": "2026-10-15", "summary": ["x"],
           "alert_comments": {"005930": "앞으로 14% 더 빠질 수 있어요"}}   # 14는 알림 문구의 날짜(10-14)뿐
    assert any("14%" in e for e in validate_analysis(raw, alert_context())[1])


def test_alert_numbers_of_other_stock_not_allowed():
    from agent.report.schema import Alert
    ctx = alert_context()
    ctx.alerts.append(Alert(kind="big_move", ticker="AAPL", name="Apple", market="US",
                            message="Apple +7.7%", values=[7.7, 214.0, 230.5]))
    raw = {"date": "2026-10-15", "summary": ["x"], "alert_comments": {"005930": "Apple처럼 7.7% 오를 수도"}}
    assert any("7.7%" in e for e in validate_analysis(raw, ctx)[1])


def research_context():
    ctx = alert_context()
    ctx.research_targets = ["005930"]
    return ctx


def reasons(**r):
    return {"005930": {"found": True, "summary": "반도체 업황 우려로 업종 전체가 약세였어요.",
                       "sources": ["https://www.yna.co.kr/view/AKR20261015000000001"], **r}}


def test_move_reasons_ok_and_not_found_ok():
    from agent.report.schema import Analysis
    from agent.report.validate import check_move_reasons
    a = Analysis(date="2026-10-15", summary=["x"], move_reasons=reasons())
    assert check_move_reasons(a, research_context()) == []
    a = Analysis(date="2026-10-15", summary=["x"],
                 move_reasons={"005930": {"found": False, "summary": "뚜렷한 원인을 찾지 못했어요."}})
    assert check_move_reasons(a, research_context()) == []


def test_move_reasons_rules():
    from agent.report.schema import Analysis
    from agent.report.validate import check_move_reasons
    ctx = research_context()
    bad = [reasons(sources=[]), reasons(summary="매출이 20% 늘었어요"), reasons(sources=["ftp://x"]),
           reasons(sources=["https://a", "https://b", "https://c", "https://d"])]
    for r in bad:
        assert check_move_reasons(Analysis(date="2026-10-15", summary=["x"], move_reasons=r), ctx) != []
    other = {"AAPL": reasons()["005930"]}
    assert check_move_reasons(Analysis(date="2026-10-15", summary=["x"], move_reasons=other), ctx) != []


def test_validate_analysis_ignores_move_reasons():
    raw = {"date": "2026-10-15", "summary": ["삼성전자가 크게 내렸어요"],
           "alert_comments": {"005930": "하루에 -6.2% 내렸어요."},
           "move_reasons": reasons(summary="매출이 20% 늘었어요")}
    assert validate_analysis(raw, research_context())[1] == []
