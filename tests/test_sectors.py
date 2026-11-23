from datetime import date, timedelta

import pandas as pd
import pytest

from agent.analysis.sectors import kr_row, level_of, price_position, sort_rows, us_row
from agent.report.schema import SectorRow


def frame(per, pbr=None, close=None, start="2021-01-01"):
    idx = pd.bdate_range(start, periods=len(per))
    return pd.DataFrame({"close": close or [100.0] * len(per), "per": per, "pbr": pbr or [1.0] * len(per)},
                        index=idx)


def test_level_boundaries():
    assert [level_of(p) for p in (30.0, 30.1, 69.9, 70.0, None)] == ["싸요", "보통", "보통", "비싸요", None]


def test_kr_row_per_percentile_and_earnings():
    per = [10.0] * 300 + [20.0] * 300 + [12.0]          # 지금 12배: 10배 300일 + 12배 1일 ≤ → 301/601
    row = kr_row("1013", "전기전자", "PER", frame(per))
    assert row.key == "KR:1013" and row.value == 12.0 and row.market == "KR"
    assert row.percentile == round(301 / 601 * 100, 1) and row.level == "보통"
    assert row.earnings_1y_pct == round((100 / 12) / (100 / 20) * 100 - 100, 1)   # 252거래일 전 EPS 대비


def test_kr_row_pbr_method_uses_pbr():
    row = kr_row("1018", "건설", "PBR", frame([15.0] * 300, pbr=[1.0] * 299 + [0.5]))
    assert row.method == "PBR" and row.value == 0.5 and row.level == "싸요"


def test_kr_row_excludes_loss_days_and_short_history():
    row = kr_row("1008", "화학", "PER", frame([0.0] * 100 + [10.0] * 200))
    assert row.percentile is None and row.level is None and "자료 부족" in row.note


def test_price_position():
    closes = pd.Series([100.0] * 200 + [80.0] * 63, index=pd.bdate_range("2025-01-01", periods=263))
    assert price_position(closes) == (-20.0, -20.0)


def test_us_row_without_per():
    closes = pd.Series([50.0, 40.0], index=pd.bdate_range("2026-11-19", periods=2))
    row = us_row("XLK", "기술", None, closes)
    assert row.key == "US:XLK" and row.value is None and row.drawdown_52w_pct == -20.0 and row.level is None


def test_sort_rows_none_last():
    rows = [SectorRow(key="a", name="a", market="KR", method="PER", percentile=None),
            SectorRow(key="b", name="b", market="KR", method="PER", percentile=50.0),
            SectorRow(key="c", name="c", market="KR", method="PER", percentile=10.0)]
    assert [r.key for r in sort_rows(rows)] == ["c", "b", "a"]


def past_snaps(n, value=20.0, eps=10.0, end=date(2026, 11, 16)):
    return [{"date": (end - timedelta(weeks=i)).isoformat(),
             "sectors": {"US:XLK": {"method": "PER", "value": value, "close": value * eps, "eps": eps}}}
            for i in range(n)]


def us(value=30.0, close=300.0):
    return SectorRow(key="US:XLK", name="기술", market="US", method="PER", value=value, close=close)


def test_enrich_needs_26_weeks_for_percentile():
    from agent.analysis.sectors import enrich_us_from_history
    row = us()
    enrich_us_from_history([row], past_snaps(24), date(2026, 11, 23))
    assert row.history_weeks == 25 and row.percentile is None and "26주" in row.note
    row = us()
    enrich_us_from_history([row], past_snaps(25), date(2026, 11, 23))
    assert row.history_weeks == 26 and row.percentile == 100.0 and row.level == "비싸요" and row.note == ""


def test_enrich_earnings_3m_after_13_weeks():
    from agent.analysis.sectors import enrich_us_from_history
    row = us()
    enrich_us_from_history([row], past_snaps(12), date(2026, 11, 23))
    assert row.earnings_3m_pct is None
    row = us()
    enrich_us_from_history([row], past_snaps(13), date(2026, 11, 23))   # 91일 전 이하 가장 가까운 기록
    assert row.earnings_3m_pct == 0.0                                   # EPS 10 → 300/30 = 10


def test_enrich_ignores_old_snapshots_and_kr_rows():
    from agent.analysis.sectors import enrich_us_from_history
    row = us()
    kr = SectorRow(key="KR:1018", name="건설", market="KR", method="PBR", value=0.7, percentile=12.0)
    enrich_us_from_history([row, kr], [{"date": "2026-11-16", "holdings": []}], date(2026, 11, 23))
    assert row.history_weeks == 1 and row.percentile is None
    assert kr.history_weeks == 0 and kr.percentile == 12.0


class FakeSectors:
    def __init__(self, fail=(), krx=True):
        self.fail, self.krx = set(fail), krx

    def kr_fundamentals(self, code, start, end):
        if not self.krx:
            raise RuntimeError("KRX 계정이 없어요")
        if code in self.fail:
            raise RuntimeError("boom")
        return frame([10.0] * 300)

    def us_quote(self, ticker, today):
        if ticker in self.fail:
            raise RuntimeError("boom")
        return 20.0, pd.Series([1.0, 1.0], index=pd.bdate_range("2026-11-19", periods=2))


def test_sector_lists_match_spec():
    from agent.collectors.sectors import KR_SECTORS, US_SECTORS
    assert len(KR_SECTORS) == 17 and len(US_SECTORS) == 12
    pbr = {name for _, name, method in KR_SECTORS if method == "PBR"}
    assert pbr == {"화학", "금속", "건설", "기계·장비", "운송장비·부품", "운송·창고", "금융", "증권", "보험"}
    assert ("1018", "건설", "PBR") in KR_SECTORS and ("SOXX", "반도체") in US_SECTORS


def test_attach_sectors_one_failure_only_drops_that_row():
    from agent.report.context import _attach_sectors
    rows, missing = _attach_sectors(FakeSectors(fail={"1018", "XLE"}), date(2026, 11, 23))
    assert len(rows) == 17 + 12 - 2 and len(missing) == 2 and any("건설" in m for m in missing)


def test_attach_sectors_without_krx():
    from agent.report.context import _attach_sectors
    rows, missing = _attach_sectors(FakeSectors(krx=False), date(2026, 11, 23))
    assert {r.market for r in rows} == {"US"} and missing == ["국내 업종: KRX 계정이 없어요"]


def test_collect_passes_sectors_only_on_monday(monkeypatch, tmp_path):
    import agent.__main__ as cli
    from agent.collectors.sectors import SectorData
    seen = []

    class Stop(Exception):
        pass

    def fake_build(*args, **kwargs):
        seen.append(kwargs.get("sectors"))
        raise Stop

    monkeypatch.setenv("DART_API_KEY", "x")
    monkeypatch.setattr(cli, "load_holdings", lambda path: None)
    monkeypatch.setattr(cli, "resolve_holdings", lambda settings, manual, notes: manual)
    monkeypatch.setattr(cli, "build_context", fake_build)
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.yaml").write_text("profile:\n  name: balanced\n", encoding="utf-8")
    for day in ("2026-11-23", "2026-11-24"):
        try:
            cli.main(["collect", "--date", day, "--out", str(tmp_path / "out"), "--config-dir", str(config)])
        except Stop:
            pass
    assert isinstance(seen[0], SectorData) and seen[1] is None


@pytest.mark.live
def test_live_sector_data():
    from agent.collectors.sectors import SectorData
    today = date.today()
    df = SectorData().kr_fundamentals("1018", today - timedelta(days=365 * 5), today)
    assert len(df) >= 1000 and set(df.columns) >= {"close", "per", "pbr"}
    per, closes = SectorData().us_quote("XLK", today)
    assert per and per > 0 and len(closes) > 200
