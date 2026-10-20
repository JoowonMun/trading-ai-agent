from datetime import date

from agent.history.store import SnapshotStore


def snap(d, total=100.0, kospi=2500.0):
    return {"version": 1, "date": d, "holdings": [], "portfolio": {"total_krw": total},
            "market": {"indices": {"KOSPI": kospi, "S&P500": 6000.0}, "fx_usdkrw": 1350.0}, "alerts": []}


def test_lookups_skip_missing_days(tmp_path):
    store = SnapshotStore(tmp_path)
    for d in ("2026-10-12", "2026-10-13", "2026-10-15"):   # 10-14 빠짐
        store.save(snap(d))
    assert store.latest_before(date(2026, 10, 16))["date"] == "2026-10-15"
    assert store.latest_before(date(2026, 10, 15))["date"] == "2026-10-13"
    assert store.latest_before(date(2026, 10, 12)) is None
    assert store.on_or_before(date(2026, 10, 14))["date"] == "2026-10-13"
    assert [s["date"] for s in store.between(date(2026, 10, 13), date(2026, 10, 15))] == ["2026-10-13", "2026-10-15"]


def test_empty_or_missing_root(tmp_path):
    store = SnapshotStore(tmp_path / "nothing")
    assert store.latest_before(date(2026, 10, 16)) is None and store.between(date(2026, 1, 1), date(2026, 12, 31)) == []


def test_portfolio_csv_one_row_per_date(tmp_path):
    store = SnapshotStore(tmp_path)
    store.save(snap("2026-10-15", total=100))
    store.save(snap("2026-10-14", total=90))
    store.save(snap("2026-10-15", total=110))   # 같은 날 재실행 → 덮어씀
    lines = (tmp_path / "history" / "portfolio.csv").read_text(encoding="utf-8").splitlines()
    assert lines == ["date,total_krw,kospi,sp500,usdkrw",
                     "2026-10-14,90.0,2500.0,6000.0,1350.0",
                     "2026-10-15,110.0,2500.0,6000.0,1350.0"]
