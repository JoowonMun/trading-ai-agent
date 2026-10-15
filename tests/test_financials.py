from datetime import date

from factories import report_rows

from agent.analysis.financials import build_quarters, parse_amount, quarter_end, ttm

CUMS = [(100, 10, 8), (250, 25, 20), (420, 42, 33), (600, 60, 48)]


def year_reports(year, cums, with_add=True, **bs):
    """cums: 분기별 (매출, 영업이익, 순이익) 연초 누적값 4개 → DART 보고서 4개."""
    out, prev = {}, (0, 0, 0)
    for q in range(1, 5):
        cum = cums[q - 1]
        if q < 4:
            three_month = tuple(c - p for c, p in zip(cum, prev))
            out[(year, q)] = report_rows(*three_month, add=cum if with_add else None, **bs)
        else:
            out[(year, q)] = report_rows(*cum, **bs)  # 사업보고서: thstrm_amount = 연간 합계
        prev = cum
    return out


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
    quarters = build_quarters(year_reports(2025, CUMS, equity_owners=200, equity_total=250, liabilities=100))
    assert [q.revenue for q in quarters] == [100, 150, 170, 180]
    assert [q.net_income for q in quarters] == [8, 12, 13, 15]
    assert quarters[-1].equity_owners == 200
    assert ttm(quarters, 3) == {"revenue": 600, "op_income": 60, "net_income": 48}
    assert ttm(quarters, 2)["revenue"] is None  # 4분기 미만


def test_reports_without_cumulative_field_use_three_month_amounts():
    quarters = build_quarters(year_reports(2025, CUMS, with_add=False))
    assert [q.revenue for q in quarters] == [100, 150, 170, 180]
    assert ttm(quarters, 3)["net_income"] == 48


def test_missing_previous_report_keeps_three_month_but_breaks_q4():
    reports = year_reports(2025, CUMS)
    del reports[(2025, 3)]
    quarters = build_quarters(reports)
    assert [(q.quarter, q.revenue) for q in quarters] == [(1, 100), (2, 150), (4, None)]


def test_owner_net_income_preferred_over_total():
    rows = report_rows(100, 10, 8)
    rows.insert(0, {"sj_div": "IS", "account_id": "ifrs-full_ProfitLoss", "account_nm": "당기순이익",
                    "thstrm_amount": "9,999"})
    assert build_quarters({(2025, 1): rows})[0].net_income == 8


def test_account_name_fallback_and_cis():
    rows = [{"sj_div": "CIS", "account_id": "-표준계정코드 미사용-", "account_nm": "영업 이익",
             "thstrm_amount": "77"}]
    assert build_quarters({(2025, 1): rows})[0].op_income == 77
