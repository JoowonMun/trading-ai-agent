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
