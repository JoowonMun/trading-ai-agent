from agent.analysis.quiet_signals import WHY, classify, pick_signals, promising_sectors
from agent.report.schema import SectorRow


def filing(code, nm, dt="20261118", name=None, no=None):
    return {"stock_code": code, "corp_name": name or f"회사{code}", "report_nm": nm, "rcept_dt": dt,
            "rcept_no": no or f"2026{code}{dt}"}


CONTRACT = "단일판매ㆍ공급계약체결"


def test_classify():
    assert classify(CONTRACT) == "contract"
    assert classify("신규시설투자등") == "facility"
    assert classify("자기주식취득결정") == "buyback"
    assert classify("자기주식취득신탁계약체결결정") == "buyback"
    assert classify("유상증자결정") == "rights_issue"
    assert classify("[기재정정]" + CONTRACT) is None
    assert classify("주주총회소집결의") is None


def row(name, e, level, market="KR"):
    return SectorRow(key=f"{market}:{name}", name=name, market=market, method="PER", earnings_1y_pct=e, level=level)


def test_promising_sectors():
    rows = [row("금속", 91.2, "싸요"), row("유통", 10.0, "보통"), row("건설", 50.0, "비싸요"),
            row("화학", None, "싸요"), row("운송", -3.0, "싸요"), row("오락", 5.0, None), row("기술", 5.0, "싸요", "US")]
    assert [r.name for r in promising_sectors(rows)] == ["금속", "유통"]


def test_pick_group_priority_and_dedupe():
    filings = [filing("000001", CONTRACT, "20261117"), filing("000002", "자기주식취득결정", "20261119"),
               filing("000003", "신규시설투자등", "20261118")]
    signals, more = pick_signals(filings, holdings={"000003"}, members={"000002": "금속", "000003": "금속"},
                                 large={"000001", "000003"})
    assert [(s.ticker, s.group) for s in signals] == [("000003", "holding"), ("000002", "promising"),
                                                      ("000001", "large")]
    assert signals[1].sector == "금속" and more == 0
    assert signals[0].url.endswith("rcpNo=2026000003" "20261118") and signals[0].date == "2026-11-18"


def test_pick_latest_per_company_kind_and_limit():
    filings = [filing("000001", CONTRACT, "20261117", no="a"), filing("000001", CONTRACT, "20261119", no="b")]
    filings += [filing(f"1{i:05d}", CONTRACT, f"202611{10 + i % 9:02d}") for i in range(20)]
    large = {f["stock_code"] for f in filings}
    signals, more = pick_signals(filings, set(), {}, large)
    assert len(signals) == 15 and more == 6
    first = [s for s in signals if s.ticker == "000001"] or None
    assert first is None or first[0].url.endswith("b")
    dates = [s.date for s in signals]
    assert dates == sorted(dates, reverse=True)


def test_pick_without_promising():
    signals, _ = pick_signals([filing("000001", CONTRACT)], {"000001"}, {}, set())
    assert [s.group for s in signals] == ["holding"]


def test_pick_skips_unlisted():
    filings = [filing("", CONTRACT), filing("999999", CONTRACT), filing("000001", "주주총회소집결의")]
    assert pick_signals(filings, set(), {}, {"000001"}) == ([], 0)


def test_rights_issue_is_caution():
    signals, _ = pick_signals([filing("000001", "유상증자결정")], set(), {}, {"000001"})
    assert signals[0].caution and signals[0].why == WHY["rights_issue"]
    good, _ = pick_signals([filing("000001", CONTRACT)], set(), {}, {"000001"})
    assert not good[0].caution and good[0].why == WHY["contract"]
