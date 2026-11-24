from datetime import date

import pandas as pd

from agent.analysis.candidates import opinion_sectors, pick_candidates
from agent.report.schema import SectorRow


def row(name, percentile, e=10.0, level="싸요", method="PBR"):
    return SectorRow(key=f"KR:{name}", name=name, market="KR", method=method, percentile=percentile,
                     level=level, earnings_1y_pct=e)


def test_opinion_sectors_cheapest_three():
    rows = [row("A", 5), row("B", 40, level="보통"), row("C", 10), row("D", None), row("E", 20), row("F", 1, e=-5)]
    assert [r.name for r in opinion_sectors(rows)] == ["A", "C", "E"]


FUND = pd.DataFrame({"per": [8.0, 6.0, 12.0, -3.0, 5.0, 20.0, 7.0],
                     "pbr": [0.4, 0.6, 0.7, 0.3, 0.5, 2.0, 1.5]},
                    index=["000001", "000002", "000003", "000004", "000005", "000006", "000007"])
NAMES = {t: f"가짜{t[-1]}" for t in FUND.index}


def test_pick_candidates_mixes_size_and_cheapness():
    members = list(FUND.index)          # 중간값(PBR) = 0.6
    large = ["000006", "000004", "000003", "000002", "000001", "000007"]   # 시총 큰 순, 000005는 300 밖
    picked = pick_candidates(row("금속", 5), members, large, FUND, NAMES.get, held={"000001"})
    # 000006·000007·000003: 중간값 이상, 000004: 적자, 000005: 시총 밖, 000002: 중간값과 같아 제외
    assert [(c.ticker, c.name, c.value, c.sector_median, c.held) for c in picked] == [
        ("000001", "가짜1", 0.4, 0.6, True)]
    assert picked[0].sector == "금속" and picked[0].method == "PBR"


def test_pick_candidates_top_three_by_size():
    fund = pd.DataFrame({"per": [5.0] * 8, "pbr": [0.1, 0.2, 0.3, 0.4, 2.0, 2.0, 2.0, 2.0]},
                        index=[f"00000{i}" for i in range(8)])
    large = ["000003", "000000", "000002", "000001"]
    picked = pick_candidates(row("금속", 5), list(fund.index), large, fund, lambda t: t, held=set())
    assert [c.ticker for c in picked] == ["000003", "000000", "000002"]


def test_pick_candidates_per_method():
    picked = pick_candidates(row("전기전자", 5, method="PER"), list(FUND.index), list(FUND.index), FUND,
                             NAMES.get, held=set())
    # PER>0 값: 8,6,12,5,20,7 → 중간값 7.5 → 8·12·20 제외
    assert [(c.ticker, c.value) for c in picked] == [("000002", 6.0), ("000005", 5.0), ("000007", 7.0)]


def test_pick_candidates_empty_when_no_data():
    assert pick_candidates(row("금속", 5), ["999999"], ["999999"], FUND, NAMES.get, held=set()) == []


def test_kr_fundamentals_all_and_ticker_name(monkeypatch):
    from pykrx import stock

    from agent.collectors.sectors import SectorData
    raw = pd.DataFrame({"BPS": [1.0], "PER": [8.0], "PBR": [0.5], "EPS": [1.0], "DIV": [2.0], "DPS": [1.0]},
                       index=["000001"])
    monkeypatch.setattr(stock, "get_market_fundamental", lambda day, market: raw)
    monkeypatch.setattr(stock, "get_market_ticker_name", lambda t: "가짜제철")
    df = SectorData().kr_fundamentals_all(date(2026, 11, 20))
    assert list(df.columns) == ["per", "pbr"] and df.loc["000001", "pbr"] == 0.5
    assert SectorData().ticker_name("000001") == "가짜제철"
