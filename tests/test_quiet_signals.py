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


class FakeDartMarket:
    def __init__(self, fail=False):
        self.fail = fail

    def market_disclosures(self, start, end):
        if self.fail:
            raise RuntimeError("DART 다운")
        assert (start.isoformat(), end.isoformat()) == ("2026-11-16", "2026-11-22")
        return [filing("000001", CONTRACT, "20261118"), filing("000002", "자기주식취득결정", "20261119"),
                filing("000003", "유상증자결정", "20261117")]


class FakeSource:
    def __init__(self, fail_members=False):
        self.fail_members = fail_members

    def latest_trading_day(self, today):
        from datetime import date
        return date(2026, 11, 20)

    def kr_constituents(self, code, day):
        if self.fail_members:
            raise RuntimeError("KRX 오류")
        return ["000002"] if code == "1011" else []

    def market_cap_top(self, day, n):
        return ["000003"]


SECTORS = [SectorRow(key="KR:1011", name="금속", market="KR", method="PBR", earnings_1y_pct=91.2, level="싸요"),
           SectorRow(key="KR:1018", name="건설", market="KR", method="PBR", earnings_1y_pct=50.0, level="비싸요")]


def test_attach_signals_happy():
    from datetime import date

    from agent.report.context import _attach_signals
    signals, more, missing, promising = _attach_signals(FakeDartMarket(), FakeSource(), SECTORS, {"000001"},
                                                        date(2026, 11, 23))
    assert [(s.ticker, s.group) for s in signals] == [("000001", "holding"), ("000002", "promising"),
                                                      ("000003", "large")]
    assert promising == ["금속"] and missing == [] and more == 0


def test_attach_signals_krx_failure_drops_group():
    from datetime import date

    from agent.report.context import _attach_signals
    signals, _, missing, _ = _attach_signals(FakeDartMarket(), FakeSource(fail_members=True), SECTORS, set(),
                                             date(2026, 11, 23))
    assert [s.group for s in signals] == ["large"] and len(missing) == 1 and "금속" in missing[0]


def test_attach_signals_dart_failure():
    from datetime import date

    from agent.report.context import _attach_signals
    signals, _, missing, _ = _attach_signals(FakeDartMarket(fail=True), FakeSource(), SECTORS, set(),
                                             date(2026, 11, 23))
    assert signals == [] and missing == ["조용한 신호: DART 다운"]
