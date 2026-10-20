import json

from factories import sample_context

import agent.__main__ as cli
from agent.report.schema import Alert


def setup(tmp_path, targets=("005930",)):
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.yaml").write_text("profile:\n  name: balanced\n", encoding="utf-8")
    day = tmp_path / "out" / "2026-10-15"
    day.mkdir(parents=True)
    ctx = sample_context()
    ctx.report_type = "alert"
    ctx.alerts = [Alert(kind="big_move", ticker="005930", name="삼성전자", market="KR", message="삼성전자 -6.2% (2026-10-14 대비)",
                        values=[-6.2])]
    ctx.research_targets = list(targets)
    (day / "context.json").write_text(ctx.model_dump_json(), encoding="utf-8")
    return config, day


def args(tmp_path, config, *cmd):
    return [*cmd, "--date", "2026-10-15", "--out", str(tmp_path / "out"), "--config-dir", str(config)]


def test_research_prompt_lists_targets_with_guide(tmp_path, capsys):
    config, _ = setup(tmp_path)
    cli.main(args(tmp_path, config, "research-prompt"))
    out = capsys.readouterr().out
    assert "005930" in out and "삼성전자" in out and "-6.2%" in out and "출처 우선순위" in out


def test_research_save_extracts_json_and_keeps_only_targets(tmp_path):
    config, day = setup(tmp_path)
    result = ('조사 결과입니다.\n```json\n{"005930": {"found": true, "summary": "업종 약세", '
              '"sources": ["https://www.yna.co.kr/a"]}, "AAPL": {"found": false, "summary": "x"}}\n```')
    (day / "research_raw.json").write_text(json.dumps({"subtype": "success", "result": result}), encoding="utf-8")
    cli.main(args(tmp_path, config, "research-save"))
    saved = json.loads((day / "research.json").read_text(encoding="utf-8"))
    assert list(saved) == ["005930"] and saved["005930"]["sources"] == ["https://www.yna.co.kr/a"]


def test_research_save_ignores_garbage(tmp_path):
    config, day = setup(tmp_path)
    (day / "research_raw.json").write_text(json.dumps({"subtype": "success", "result": "찾지 못했어요"}), encoding="utf-8")
    cli.main(args(tmp_path, config, "research-save"))
    assert not (day / "research.json").exists()


def test_publish_uses_research_file_not_ai_written_reasons(tmp_path, monkeypatch):
    config, day = setup(tmp_path)
    (day / "analysis.json").write_text(json.dumps({
        "date": "2026-10-15", "summary": ["삼성전자 하락"], "alert_comments": {"005930": "차분하게 지켜볼 때예요."},
        "move_reasons": {"005930": {"found": True, "summary": "AI가 몰래 쓴 원인", "sources": ["https://x.com/a"]}}}),
        encoding="utf-8")
    (day / "research.json").write_text(json.dumps({"005930": {
        "found": True, "summary": "조사 담당이 찾은 원인", "sources": ["https://www.yna.co.kr/a"]}}), encoding="utf-8")
    monkeypatch.setattr(cli, "send_email", lambda *a: None)
    cli.main(args(tmp_path, config, "publish"))
    html = (day / "preview.html").read_text(encoding="utf-8")
    assert "조사 담당이 찾은 원인" in html and "AI가 몰래 쓴 원인" not in html
