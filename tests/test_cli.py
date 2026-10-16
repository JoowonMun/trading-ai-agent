import json

from factories import sample_context

import agent.__main__ as cli


def setup_dirs(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.yaml").write_text("profile:\n  name: balanced\n", encoding="utf-8")
    day = tmp_path / "out" / "2026-10-15"
    day.mkdir(parents=True)
    (day / "context.json").write_text(sample_context().model_dump_json(), encoding="utf-8")
    return config, day


def args(tmp_path, config, *extra):
    return ["publish", "--date", "2026-10-15", "--out", str(tmp_path / "out"), "--config-dir", str(config), *extra]


def test_publish_dry_run_writes_preview(tmp_path, monkeypatch):
    config, day = setup_dirs(tmp_path)
    monkeypatch.setattr(cli, "send_email", lambda *a, **k: (_ for _ in ()).throw(AssertionError("발송 금지")))
    cli.main(args(tmp_path, config, "--dry-run"))
    html = (day / "preview.html").read_text(encoding="utf-8")
    assert "삼성전자" in html and "숫자 리포트" in html


def test_publish_with_invalid_analysis_falls_back(tmp_path, monkeypatch):
    config, day = setup_dirs(tmp_path)
    (day / "analysis.json").write_text(json.dumps({"date": "2026-10-15"}), encoding="utf-8")
    cli.main(args(tmp_path, config, "--dry-run"))
    assert "검증 실패" in (day / "preview.html").read_text(encoding="utf-8")


def test_run_sends_failure_email_on_any_error(tmp_path, monkeypatch):
    import pytest

    config, _ = setup_dirs(tmp_path)
    sent = []
    monkeypatch.setattr(cli, "send_email", lambda subject, html: sent.append((subject, html)))

    def broken_collect(args):
        raise ValueError('종목코드 432는 따옴표로 감싸야 합니다 <ticker>')

    monkeypatch.setattr(cli, "cmd_collect", broken_collect)
    with pytest.raises(ValueError):
        cli.main(["run", "--date", "2026-10-15", "--out", str(tmp_path / "out"), "--config-dir", str(config)])
    assert sent[0][0] == "[투자 리포트] 2026-10-15 생성 실패"
    assert "따옴표" in sent[0][1] and "&lt;ticker&gt;" in sent[0][1]


def test_http_client_logs_do_not_expose_api_keys(tmp_path):
    import logging

    config, _ = setup_dirs(tmp_path)
    root, httpx_logger = logging.getLogger(), logging.getLogger("httpx")
    old_root, old_httpx = root.level, httpx_logger.level
    try:
        root.setLevel(logging.INFO)          # 실제 실행처럼 INFO 로그가 켜진 상태
        httpx_logger.setLevel(logging.NOTSET)
        cli.main(args(tmp_path, config, "--dry-run"))
        assert httpx_logger.getEffectiveLevel() >= logging.WARNING
    finally:
        root.setLevel(old_root)
        httpx_logger.setLevel(old_httpx)


def test_publish_sends_email(tmp_path, monkeypatch):
    config, day = setup_dirs(tmp_path)
    sent = []
    monkeypatch.setattr(cli, "send_email", lambda subject, html: sent.append(subject))
    cli.main(args(tmp_path, config))
    assert sent == ["[투자 리포트] 2026-10-15"]


def _manual():
    from agent.config import Account, Holdings, Position
    return Holdings(accounts=[Account(name="ISA", broker="mirae", market="KR", asset_class="index",
                                      positions=[Position(ticker="360750", qty=1, avg_price=1)])])


def test_resolve_holdings_without_nh_keys_uses_yaml(monkeypatch):
    from agent.config import Settings
    monkeypatch.delenv("NH_APP_KEY", raising=False)
    notes = []
    h = cli.resolve_holdings(Settings(), _manual(), notes)
    assert [a.name for a in h.accounts] == ["ISA"] and notes == []


def test_resolve_holdings_merges_nh(monkeypatch):
    from agent.config import Account, Position, Settings
    monkeypatch.setenv("NH_APP_KEY", "k")
    monkeypatch.setenv("NH_APP_SECRET", "s")

    class FakeNh:
        def holdings(self, index_tickers):
            assert index_tickers == {"IVV"}
            return [Account(name="나무 국내", broker="nh", market="KR", asset_class="domestic",
                            positions=[Position(ticker="005930", qty=1, avg_price=1)])], 777.0

    notes = []
    h = cli.resolve_holdings(Settings(index_tickers=["IVV"]), _manual(), notes, nh_factory=lambda: FakeNh())
    assert [a.name for a in h.accounts] == ["나무 국내", "ISA"] and h.cash_krw == 777.0
    assert notes == ["나무 잔고 자동 조회: 1종목"]


def test_resolve_holdings_falls_back_when_nh_fails(monkeypatch):
    from agent.config import Settings
    monkeypatch.setenv("NH_APP_KEY", "k")
    monkeypatch.setenv("NH_APP_SECRET", "s")

    class BrokenNh:
        def holdings(self, index_tickers):
            raise RuntimeError("HTTP 500")

    notes = []
    h = cli.resolve_holdings(Settings(), _manual(), notes, nh_factory=lambda: BrokenNh())
    assert [a.name for a in h.accounts] == ["ISA"]
    assert notes[0].startswith("나무 잔고 조회 실패")


def test_context_notes_appear_in_report(tmp_path):
    from agent.report.render import render_report
    ctx = sample_context()
    ctx.notes = ["나무 잔고 조회 실패 → holdings.yaml 사용"]
    assert "나무 잔고 조회 실패" in render_report(ctx, None, [])


def test_nh_failure_with_no_manual_holdings_raises_clear_error(monkeypatch):
    import pytest
    from agent.config import Holdings, Settings
    monkeypatch.setenv("NH_APP_KEY", "k")
    monkeypatch.setenv("NH_APP_SECRET", "s")

    class BrokenNh:
        def holdings(self, index_tickers):
            raise RuntimeError("HTTP 500")

    with pytest.raises(RuntimeError, match="보유 종목이 없습니다"):
        cli.resolve_holdings(Settings(), Holdings(accounts=[]), [], nh_factory=lambda: BrokenNh())


def test_check_command_reports_validation_result(tmp_path, capsys):
    import pytest
    config, day = setup_dirs(tmp_path)
    base = ["check", "--date", "2026-10-15", "--out", str(tmp_path / "out"), "--config-dir", str(config)]
    (day / "analysis.json").write_text(json.dumps({
        "date": "2026-10-15", "summary": ["보유 유지"],
        "holdings": [{"ticker": "005930", "signal": "hold", "headline": "현재가 65,000원", "reasoning": "PER 12.3배"}],
    }), encoding="utf-8")
    cli.main(base)
    assert "검증 통과" in capsys.readouterr().out

    (day / "analysis.json").write_text(json.dumps({
        "date": "2026-10-15", "summary": ["x"],
        "holdings": [{"ticker": "005930", "signal": "hold", "headline": "목표 999,999원", "reasoning": "-"}],
    }), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        cli.main(base)
    assert exc.value.code == 1
    assert "999,999원" in capsys.readouterr().out
