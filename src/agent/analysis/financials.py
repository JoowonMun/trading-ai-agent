"""DART 재무제표 응답 → 분기 실적·TTM (순수 함수)."""
from dataclasses import dataclass
from datetime import date

REPORT_CODES = {1: "11013", 2: "11012", 3: "11014", 4: "11011"}

# (우선 account_id 목록, 대체 account_nm 목록)
FLOW_ACCOUNTS = {
    "revenue": (["ifrs-full_Revenue"], ["매출액", "수익(매출액)", "영업수익", "매출"]),
    "op": (["dart_OperatingIncomeLoss"], ["영업이익", "영업이익(손실)"]),
    "ni": (
        ["ifrs-full_ProfitLossAttributableToOwnersOfParent", "ifrs-full_ProfitLoss"],
        ["지배기업의 소유주에게 귀속되는 당기순이익", "당기순이익", "당기순이익(손실)"],
    ),
}
STOCK_ACCOUNTS = {
    "equity_owners": (
        ["ifrs-full_EquityAttributableToOwnersOfParent", "ifrs-full_Equity"],
        ["지배기업의 소유주에게 귀속되는 자본", "자본총계"],
    ),
    "equity_total": (["ifrs-full_Equity"], ["자본총계"]),
    "liabilities": (["ifrs-full_Liabilities"], ["부채총계"]),
}


def quarter_end(year: int, quarter: int) -> date:
    month = quarter * 3
    return date(year, month, 31 if month in (3, 12) else 30)


@dataclass(frozen=True)
class QuarterFigures:
    year: int
    quarter: int
    revenue: float | None
    op_income: float | None
    net_income: float | None
    equity_owners: float | None
    equity_total: float | None
    liabilities: float | None

    @property
    def period_end(self) -> date:
        return quarter_end(self.year, self.quarter)


def parse_amount(text) -> float | None:
    if text is None:
        return None
    s = str(text).strip().replace(",", "")
    if s in ("", "-"):
        return None
    negative = s.startswith("(") and s.endswith(")")
    try:
        value = float(s.strip("()"))
    except ValueError:
        return None
    return -value if negative else value


def _normalize(name: str) -> str:
    return name.replace(" ", "")


def _has_amount(row) -> bool:
    return (parse_amount(row.get("thstrm_amount")) is not None
            or parse_amount(row.get("thstrm_add_amount")) is not None)


def _find_row(rows, sj_divs, ids, names) -> dict | None:
    candidates = [r for div in sj_divs for r in rows if r.get("sj_div") == div and _has_amount(r)]
    for account_id in ids:
        for r in candidates:
            if r.get("account_id") == account_id:
                return r
    for name in (_normalize(n) for n in names):
        for r in candidates:
            if _normalize(r.get("account_nm", "")) == name:
                return r
    return None


def extract_report(rows: list[dict]) -> dict[str, float | None]:
    """손익 항목은 `<key>_amt`(thstrm_amount)와 `<key>_add`(thstrm_add_amount)를 따로 돌려준다.

    DART 정의: 분기·반기 보고서의 손익 thstrm_amount는 3개월치, thstrm_add_amount는 연초부터 누적.
    사업보고서(4분기)의 thstrm_amount는 연간 합계.
    """
    out = {}
    for key, (ids, names) in FLOW_ACCOUNTS.items():
        row = _find_row(rows, ("IS", "CIS"), ids, names) or {}
        out[f"{key}_amt"] = parse_amount(row.get("thstrm_amount"))
        out[f"{key}_add"] = parse_amount(row.get("thstrm_add_amount"))
    for key, (ids, names) in STOCK_ACCOUNTS.items():
        row = _find_row(rows, ("BS",), ids, names) or {}
        out[key] = parse_amount(row.get("thstrm_amount"))
    return out


def _flow_and_cumulative(quarter: int, amt, add, prev_cum):
    """(해당 분기 3개월치, 연초부터 누적)."""
    if quarter == 4:
        cum = add if add is not None else amt
        flow = cum - prev_cum if cum is not None and prev_cum is not None else None
        return flow, cum
    flow = amt if amt is not None else (add - prev_cum if add is not None and prev_cum is not None else None)
    if add is not None:
        cum = add
    elif quarter == 1:
        cum = amt
    else:
        cum = prev_cum + amt if prev_cum is not None and amt is not None else None
    return flow, cum


def build_quarters(reports: dict[tuple[int, int], list[dict]]) -> list[QuarterFigures]:
    extracted = {k: extract_report(v) for k, v in reports.items()}
    cumulative: dict[tuple[int, int], dict[str, float | None]] = {}
    result = []
    for year, quarter in sorted(extracted):
        cur = extracted[(year, quarter)]
        prev_cum = cumulative.get((year, quarter - 1), {})
        flows, cums = {}, {}
        for key in FLOW_ACCOUNTS:
            flows[key], cums[key] = _flow_and_cumulative(quarter, cur[f"{key}_amt"], cur[f"{key}_add"],
                                                         prev_cum.get(key))
        cumulative[(year, quarter)] = cums
        result.append(QuarterFigures(
            year=year, quarter=quarter,
            revenue=flows["revenue"], op_income=flows["op"], net_income=flows["ni"],
            equity_owners=cur["equity_owners"], equity_total=cur["equity_total"], liabilities=cur["liabilities"],
        ))
    return result


def ttm(quarters: list[QuarterFigures], index: int) -> dict[str, float | None]:
    """index 분기를 끝으로 하는 연속 4개 분기 합. 연속이 아니거나 값이 빠지면 None."""
    keys = ("revenue", "op_income", "net_income")
    if index < 3:
        return dict.fromkeys(keys)
    window = quarters[index - 3:index + 1]
    ordinals = [q.year * 4 + q.quarter for q in window]
    if ordinals != list(range(ordinals[0], ordinals[0] + 4)):
        return dict.fromkeys(keys)
    out = {}
    for key in keys:
        values = [getattr(q, key) for q in window]
        out[key] = None if any(v is None for v in values) else sum(values)
    return out
