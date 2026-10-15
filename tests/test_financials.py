from datetime import date

from factories import report_rows

from agent.analysis.financials import build_quarters, extract_report, parse_amount, quarter_end, ttm


def year_reports(year, cums, **bs):
    """cums: 분기별 (매출, 영업이익, 순이익) 누적값 4개."""
    return {
        (year, q): report_rows(*cums[q - 1], **bs, with_add=(q < 4))
        for q in range(1, 5)
    }


def test_parse_amount():
    assert parse_amount("1,234") == 1234
    assert parse_amount("-300") == -300
    assert parse_amount("(500)") == -500
    assert parse_amount("-") is None
    assert parse_amount("") is None
    assert parse_amount(None) is None


def test_quarter_end():
    assert quarter_end(2026, 1) == date(2026, 3, 31)
    assert quarter_end(2026, 2) == date(2026, 6, 30)
    assert quarter_end(2026, 3) == date(2026, 9, 30)
    assert quarter_end(2026, 4) == date(2026, 12, 31)


def test_cumulative_to_quarterly_and_ttm():
    reports = year_reports(2025, [(100, 10, 8), (250, 25, 20), (420, 42, 33), (600, 60, 48)],
                           equity_owners=200, equity_total=250, liabilities=100)
    quarters = build_quarters(reports)
    assert [q.revenue for q in quarters] == [100, 150, 170, 180]
    assert [q.net_income for q in quarters] == [8, 12, 13, 15]
    assert quarters[-1].equity_owners == 200
    assert ttm(quarters, 3) == {"revenue": 600, "op_income": 60, "net_income": 48}
    assert ttm(quarters, 2)["revenue"] is None  # 4분기 미만


def test_missing_previous_report_breaks_flow():
    reports = year_reports(2025, [(100, 10, 8), (250, 25, 20), (420, 42, 33), (600, 60, 48)])
    del reports[(2025, 2)]
    quarters = build_quarters(reports)
    assert [(q.quarter, q.revenue) for q in quarters] == [(1, 100), (3, None), (4, 180)]
    assert ttm(quarters, 2)["revenue"] is None  # 연속 4분기 아님


def test_owner_net_income_preferred_over_total():
    rows = report_rows(100, 10, 8)
    rows.insert(0, {"sj_div": "IS", "account_id": "ifrs-full_ProfitLoss", "account_nm": "당기순이익",
                    "thstrm_add_amount": "9,999"})
    assert extract_report(rows)["ni"] == 8


def test_account_name_fallback_and_cis():
    rows = [{"sj_div": "CIS", "account_id": "-표준계정코드 미사용-", "account_nm": "영업 이익",
             "thstrm_amount": "77"}]
    assert extract_report(rows)["op"] == 77
