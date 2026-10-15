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


def _find(rows, sj_divs, ids, names, getter):
    candidates = [r for div in sj_divs for r in rows if r.get("sj_div") == div]
    for account_id in ids:
        for r in candidates:
            if r.get("account_id") == account_id:
                value = getter(r)
                if value is not None:
                    return value
    wanted = [_normalize(n) for n in names]
    for name in wanted:
        for r in candidates:
            if _normalize(r.get("account_nm", "")) == name:
                value = getter(r)
                if value is not None:
                    return value
    return None


def _cumulative(row):
    value = parse_amount(row.get("thstrm_add_amount"))
    return value if value is not None else parse_amount(row.get("thstrm_amount"))


def _period_end_value(row):
    return parse_amount(row.get("thstrm_amount"))


def extract_report(rows: list[dict]) -> dict[str, float | None]:
    out = {}
    for key, (ids, names) in FLOW_ACCOUNTS.items():
        out[key] = _find(rows, ("IS", "CIS"), ids, names, _cumulative)
    for key, (ids, names) in STOCK_ACCOUNTS.items():
        out[key] = _find(rows, ("BS",), ids, names, _period_end_value)
    return out


def build_quarters(reports: dict[tuple[int, int], list[dict]]) -> list[QuarterFigures]:
    extracted = {k: extract_report(v) for k, v in reports.items()}
    result = []
    for year, quarter in sorted(extracted):
        cur = extracted[(year, quarter)]
        prev = extracted.get((year, quarter - 1)) if quarter > 1 else None

        def flow(key):
            if cur[key] is None:
                return None
            if quarter == 1:
                return cur[key]
            if prev is None or prev[key] is None:
                return None
            return cur[key] - prev[key]

        result.append(QuarterFigures(
            year=year, quarter=quarter,
            revenue=flow("revenue"), op_income=flow("op"), net_income=flow("ni"),
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
