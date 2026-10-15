"""테스트 데이터 생성기."""


def report_rows(rev_cum, op_cum, ni_cum, equity_owners=None, equity_total=None, liabilities=None, *, with_add=True):
    """DART fnlttSinglAcntAll 응답의 list 항목 모양을 흉내낸다."""

    def flow(account_id, name, cum):
        row = {"sj_div": "IS", "account_id": account_id, "account_nm": name}
        if with_add:
            row["thstrm_amount"] = "999"  # 3개월치 값 — 누적값이 있으면 쓰이면 안 된다
            row["thstrm_add_amount"] = f"{cum:,.0f}"
        else:
            row["thstrm_amount"] = f"{cum:,.0f}"
        return row

    rows = [
        flow("ifrs-full_Revenue", "매출액", rev_cum),
        flow("dart_OperatingIncomeLoss", "영업이익", op_cum),
        flow("ifrs-full_ProfitLossAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 당기순이익", ni_cum),
    ]
    for account_id, name, value in (
        ("ifrs-full_EquityAttributableToOwnersOfParent", "지배기업의 소유주에게 귀속되는 자본", equity_owners),
        ("ifrs-full_Equity", "자본총계", equity_total),
        ("ifrs-full_Liabilities", "부채총계", liabilities),
    ):
        if value is not None:
            rows.append({"sj_div": "BS", "account_id": account_id, "account_nm": name, "thstrm_amount": f"{value:,.0f}"})
    return rows
