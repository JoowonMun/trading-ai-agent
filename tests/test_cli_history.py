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
    assert ctx.research_targets == ["005930"]


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
    ctx.research_targets = ["stale"]
    cli.apply_history(ctx, Settings(), Broken(), date(2026, 10, 15))
    assert ctx.report_type == "none" and ctx.research_targets == []


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
    assert not (tmp_path / "data" / "opinions").exists()


def test_apply_history_corrupt_older_snapshot_treated_as_first_run(tmp_path):
    store = seeded_store(tmp_path, close=60000)
    (tmp_path / "data" / "snapshots" / "2026-10-01.json").write_text("{깨진 파일", encoding="utf-8")
    ctx = sample_context()
    cli.apply_history(ctx, Settings(), store, date(2026, 10, 19))   # 월요일: 7일 전 조회에서 깨진 파일을 읽음
    assert ctx.report_type == "weekly" and ctx.weekly is None


def test_publish_drops_only_invalid_move_reasons(tmp_path, monkeypatch):
    from agent.report.schema import Alert
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.yaml").write_text("profile:\n  name: balanced\n", encoding="utf-8")
    day = tmp_path / "out" / "2026-10-15"
    day.mkdir(parents=True)
    ctx = sample_context()
    ctx.report_type = "alert"
    ctx.research_targets = ["005930"]
    ctx.alerts = [Alert(kind="big_move", ticker="005930", name="삼성전자", market="KR", message="삼성전자 -6.2%",
                        values=[-6.2, 69300.0, 65000.0])]
    (day / "context.json").write_text(ctx.model_dump_json(), encoding="utf-8")
    (day / "analysis.json").write_text(json.dumps({
        "date": "2026-10-15", "summary": ["삼성전자 하락"],
        "alert_comments": {"005930": "차분하게 지켜볼 때예요."},
    }), encoding="utf-8")
    (day / "research.json").write_text(json.dumps({"005930": {
        "found": True, "summary": "영업이익이 30% 줄었다는 보도", "sources": ["https://x.com/a"]}}), encoding="utf-8")
    monkeypatch.setattr(cli, "send_email", lambda *a: None)
    cli.main(publish_args(tmp_path, config, "publish"))
    html = (day / "preview.html").read_text(encoding="utf-8")
    assert "차분하게 지켜볼 때예요" in html and "원인 조사 결과 검증 실패" in html
    assert "영업이익이 30% 줄었다는" not in html


def test_apply_history_monday_enriches_us_sectors(tmp_path):
    from agent.report.schema import SectorRow
    store = SnapshotStore(tmp_path / "data")
    snap = make_snapshot(sample_context())
    snap["date"] = "2026-10-12"
    snap["sectors"] = {"US:XLK": {"method": "PER", "value": 28.0, "close": 280.0, "eps": 10.0}}
    store.save(snap)
    ctx = sample_context()
    ctx.sectors = [SectorRow(key="US:XLK", name="기술", market="US", method="PER", value=30.0, close=300.0)]
    cli.apply_history(ctx, Settings(), store, date(2026, 10, 19))
    assert ctx.report_type == "weekly" and ctx.sectors[0].history_weeks == 2


class FakeNews:
    def search(self, query, days=7):
        return [{"title": f"{query} 소식", "source": "가짜신문", "date": "2026-11-20",
                 "url": "https://news.google.com/rss/articles/A"}]


def test_collect_news_writes_separate_file_not_context(tmp_path):
    ctx = sample_context()
    cli.collect_news(Settings(news_themes=["원전"]), ctx, tmp_path, FakeNews(), date(2026, 11, 23))
    saved = json.loads((tmp_path / "news.json").read_text(encoding="utf-8"))
    assert saved["groups"][0]["items"][0]["title"] == "원전 소식"
    assert "원전 소식" not in ctx.model_dump_json()   # 웹에서 온 글은 해설 AI가 읽는 context에 넣지 않는다


def test_publish_renders_news_file(tmp_path, monkeypatch):
    config, day = setup_dirs(tmp_path, "weekly")
    cli.collect_news(Settings(news_themes=["원전"]), sample_context(), day, FakeNews(), date(2026, 11, 23))
    monkeypatch.setattr(cli, "send_email", lambda *a: None)
    cli.main(publish_args(tmp_path, config, "publish"))
    assert "원전 소식" in (day / "preview.html").read_text(encoding="utf-8")


def opinion_day(tmp_path):
    from agent.report.schema import Candidate, SectorRow
    config, day = setup_dirs(tmp_path, "weekly")
    ctx = sample_context()
    ctx.report_type = "weekly"
    ctx.sectors = [SectorRow(key="KR:1011", name="금속", market="KR", method="PBR", value=0.68, percentile=12.0,
                             level="싸요", earnings_1y_pct=91.2)]
    ctx.opinion_sectors = ["금속"]
    ctx.candidates = [Candidate(ticker="000001", name="가짜제철", sector="금속", method="PBR", value=0.4,
                                sector_median=0.85)]
    (day / "context.json").write_text(ctx.model_dump_json(), encoding="utf-8")
    cli.collect_news(Settings(news_themes=["원전"]), ctx, day, FakeNews(), date(2026, 11, 23))
    return config, day


OPINION = {"sectors": {"금속": {"up": "수요가 회복된다는 전망이에요", "down": "수입품이 늘 수 있어요",
                                "watch": "다음 분기 실적", "sources": ["https://news.example/a"]}},
           "drop_news": [1]}


def test_opinion_prompt_prints_targets(tmp_path, capsys):
    config, _ = opinion_day(tmp_path)
    cli.main(publish_args(tmp_path, config, "opinion-prompt"))
    out = capsys.readouterr().out
    assert "가짜제철" in out and "원전 소식" in out


def test_opinion_save_writes_checked_file(tmp_path):
    config, day = opinion_day(tmp_path)
    (day / "opinion_raw.json").write_text(json.dumps({"result": "설명이에요\n" + json.dumps(OPINION, ensure_ascii=False) + "\n끝"}),
                                          encoding="utf-8")
    cli.main(publish_args(tmp_path, config, "opinion-save"))
    saved = json.loads((day / "opinions.json").read_text(encoding="utf-8"))
    assert list(saved["sectors"]) == ["금속"] and saved["drop_news"] == [1]


def test_opinion_save_broken_json_writes_nothing(tmp_path):
    config, day = opinion_day(tmp_path)
    (day / "opinion_raw.json").write_text(json.dumps({"result": "{깨진"}), encoding="utf-8")
    cli.main(publish_args(tmp_path, config, "opinion-save"))
    assert not (day / "opinions.json").exists()


def test_publish_renders_opinions_and_drops_news(tmp_path, monkeypatch):
    config, day = opinion_day(tmp_path)
    (day / "opinions.json").write_text(json.dumps(OPINION, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(cli, "send_email", lambda *a: None)
    cli.main(publish_args(tmp_path, config, "publish"))
    html = (day / "preview.html").read_text(encoding="utf-8")
    assert "수요가 회복된다는 전망이에요" in html
    assert "철강 업황 소식" not in html and "원전 소식" in html   # 1번 기사만 뺀다


def test_save_snapshot_copies_opinions(tmp_path):
    config, day = opinion_day(tmp_path)
    (day / "opinions.json").write_text(json.dumps(OPINION, ensure_ascii=False), encoding="utf-8")
    cli.main(publish_args(tmp_path, config, "save-snapshot", "--history-dir", str(tmp_path / "data")))
    copied = tmp_path / "data" / "opinions" / "2026-10-15.json"
    assert json.loads(copied.read_text(encoding="utf-8")) == OPINION
    saved = json.loads((tmp_path / "data" / "snapshots" / "2026-10-15.json").read_text(encoding="utf-8"))
    assert saved["picks"]["sectors"] == ["금속"] and "수요가 회복" not in json.dumps(saved, ensure_ascii=False)
