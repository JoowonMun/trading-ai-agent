"""조용한 신호: 유망 업종·큰 회사·내 종목의 지난주 주요 공시를 고른다."""
from agent.collectors.dart import disclosure_url
from agent.report.schema import QuietSignal, SectorRow

KEYWORDS = [("공급계약", "contract"), ("신규시설투자", "facility"), ("자기주식취득", "buyback"),
            ("유상증자결정", "rights_issue")]
WHY = {
    "contract": "계약은 앞으로 매출이 늘어날 근거예요",
    "facility": "회사가 수요가 늘 거라고 자신할 때 설비를 늘려요",
    "buyback": "회사가 스스로 주가가 싸다고 볼 때 자사주를 사요",
    "rights_issue": "주식 수가 늘어 기존 주주 몫이 줄 수 있어요",
}
CAUTION = {"rights_issue"}
GROUP_ORDER = ["holding", "promising", "large"]


def classify(report_nm: str) -> str | None:
    if "정정" in report_nm:
        return None
    return next((kind for key, kind in KEYWORDS if key in report_nm), None)


def promising_sectors(rows: list[SectorRow]) -> list[SectorRow]:
    """이익이 늘고 있고 아직 비싸지 않은 국내 업종."""
    return [r for r in rows if r.market == "KR" and (r.earnings_1y_pct or 0) > 0 and r.level in ("싸요", "보통")]


def pick_signals(filings: list[dict], holdings: set[str], members: dict[str, str], large: set[str],
                 limit: int = 15) -> tuple[list[QuietSignal], int]:
    latest: dict[tuple[str, str], dict] = {}
    for f in filings:
        ticker, kind = f.get("stock_code") or "", classify(f.get("report_nm", ""))
        if not ticker or kind is None:
            continue
        key = (ticker, kind)
        if key not in latest or f["rcept_dt"] > latest[key]["rcept_dt"]:
            latest[key] = f

    picked = []
    for (ticker, kind), f in latest.items():
        if ticker in holdings:
            group = "holding"
        elif ticker in members:
            group = "promising"
        elif ticker in large:
            group = "large"
        else:
            continue
        d = f["rcept_dt"]
        picked.append(QuietSignal(ticker=ticker, name=f["corp_name"], kind=kind, title=f["report_nm"].strip(),
                                  date=f"{d[:4]}-{d[4:6]}-{d[6:]}", url=disclosure_url(f["rcept_no"]), group=group,
                                  sector=members.get(ticker) if group == "promising" else None,
                                  why=WHY[kind], caution=kind in CAUTION))
    picked.sort(key=lambda s: s.date, reverse=True)
    picked.sort(key=lambda s: GROUP_ORDER.index(s.group))
    return picked[:limit], max(0, len(picked) - limit)
