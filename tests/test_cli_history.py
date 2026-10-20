import json
from datetime import date

from factories import sample_context

import agent.__main__ as cli
from agent.config import Settings
from agent.history.snapshot import make_snapshot
from agent.history.store import SnapshotStore


def seeded_store(tmp_path, close):
    store = SnapshotStore(tmp_path / "data")
    snap = make_snapshot(sample_context())
    snap["date"] = "2026-10-14"
    snap["holdings"][0]["close"] = close
    store.save(snap)
    return store


def test_apply_history_alert_day(tmp_path):
    ctx = sample_context()                                   # 2026-10-15 (목)
    cli.apply_history(ctx, Settings(), seeded_store(tmp_path, close=70000), date(2026, 10, 15))
    assert ctx.report_type == "alert" and [a.kind for a in ctx.alerts] == ["big_move"]


def test_apply_history_quiet_day(tmp_path):
    ctx = sample_context()
    cli.apply_history(ctx, Settings(), seeded_store(tmp_path, close=65000), date(2026, 10, 15))
    assert ctx.report_type == "none" and ctx.alerts == []


def test_apply_history_monday_weekly(tmp_path):
    ctx = sample_context()
    cli.apply_history(ctx, Settings(), seeded_store(tmp_path, close=60000), date(2026, 10, 19))
    assert ctx.report_type == "weekly" and ctx.weekly.since == "2026-10-14"


def test_apply_history_store_error_treated_as_first_run(tmp_path):
    class Broken:
        def latest_before(self, d):
            raise OSError("checkout failed")

    ctx = sample_context()
    cli.apply_history(ctx, Settings(), Broken(), date(2026, 10, 15))
    assert ctx.report_type == "none"


def setup_dirs(tmp_path, report_type):
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.yaml").write_text("profile:\n  name: balanced\n", encoding="utf-8")
    day = tmp_path / "out" / "2026-10-15"
    day.mkdir(parents=True)
    ctx = sample_context()
    ctx.report_type = report_type
    (day / "context.json").write_text(ctx.model_dump_json(), encoding="utf-8")
    return config, day


def publish_args(tmp_path, config, *extra):
    return [*extra, "--date", "2026-10-15", "--out", str(tmp_path / "out"), "--config-dir", str(config)]


def test_publish_skips_when_nothing_to_report(tmp_path, monkeypatch):
    config, day = setup_dirs(tmp_path, "none")
    monkeypatch.setattr(cli, "send_email", lambda *a: (_ for _ in ()).throw(AssertionError("발송 금지")))
    cli.main(publish_args(tmp_path, config, "publish"))
    assert not (day / "preview.html").exists()


def test_publish_subjects(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(cli, "send_email", lambda subject, html: sent.append(subject))
    config, _ = setup_dirs(tmp_path, "alert")
    cli.main(publish_args(tmp_path, config, "publish"))
    assert sent == ["[투자 알림] 2026-10-15"]


def test_save_snapshot(tmp_path):
    config, _ = setup_dirs(tmp_path, "alert")
    cli.main(publish_args(tmp_path, config, "save-snapshot", "--history-dir", str(tmp_path / "data")))
    saved = json.loads((tmp_path / "data" / "snapshots" / "2026-10-15.json").read_text(encoding="utf-8"))
    assert saved["date"] == "2026-10-15"


def test_apply_history_corrupt_older_snapshot_treated_as_first_run(tmp_path):
    store = seeded_store(tmp_path, close=60000)
    (tmp_path / "data" / "snapshots" / "2026-10-01.json").write_text("{깨진 파일", encoding="utf-8")
    ctx = sample_context()
    cli.apply_history(ctx, Settings(), store, date(2026, 10, 19))   # 월요일: 7일 전 조회에서 깨진 파일을 읽음
    assert ctx.report_type == "weekly" and ctx.weekly is None
