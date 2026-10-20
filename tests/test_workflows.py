from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted(Path(".github/workflows").glob("*.yml"))


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_files_parse(path):
    """GitHub가 해석하지 못하는 워크플로는 예약 실행이 조용히 멈춘다 — 제어 문자·문법 오류를 미리 잡는다."""
    text = path.read_text(encoding="utf-8")
    assert not [c for c in text if ord(c) < 32 and c not in "\n\t"], "제어 문자가 들어 있음"
    data = yaml.safe_load(text)
    assert data["jobs"]


def test_daily_report_schedule_is_weekday_morning_kst():
    data = yaml.safe_load(Path(".github/workflows/daily-report.yml").read_text(encoding="utf-8"))
    triggers = data[True]  # YAML 1.1에서 'on'은 True로 읽힌다
    assert triggers["schedule"][0]["cron"] == "17 21 * * 0-4"   # 월~금 06:17 KST
    assert "workflow_dispatch" in triggers


def test_daily_report_uses_history_repo_and_skips_quiet_days():
    text = Path(".github/workflows/daily-report.yml").read_text(encoding="utf-8")
    assert "repository: JoowonMun/trading-ai-agent-data" in text and "DATA_REPO_DEPLOY_KEY" in text
    assert "--history-dir data" in text and "save-snapshot" in text
    assert "REPORT_TYPE" in text


def test_snapshot_step_refuses_without_history_checkout_and_data_is_ignored():
    text = Path(".github/workflows/daily-report.yml").read_text(encoding="utf-8")
    assert "[ -d data/.git ]" in text
    assert "data/" in Path(".gitignore").read_text(encoding="utf-8").splitlines()


def test_ai_step_allows_web_research():
    text = Path(".github/workflows/daily-report.yml").read_text(encoding="utf-8")
    assert '"WebSearch"' in text and '"WebFetch"' in text


def _steps():
    data = yaml.safe_load(Path(".github/workflows/daily-report.yml").read_text(encoding="utf-8"))
    return data["jobs"]["report"], {s.get("name", ""): s for s in data["jobs"]["report"]["steps"]}


def test_secrets_are_scoped_to_steps_and_ai_gets_only_its_token():
    job, steps = _steps()
    assert not any("secrets." in str(v) for v in job.get("env", {}).values())
    for name, step in steps.items():
        if "AI" in name or "원인 조사" in name:
            secrets = [v for v in step.get("env", {}).values() if "secrets." in str(v)]
            assert secrets == ["${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}"], name


def test_research_agent_has_only_web_tools_and_writer_has_no_web():
    _, steps = _steps()
    research = next(s for n, s in steps.items() if "원인 조사" in n)["run"]
    writer = next(s for n, s in steps.items() if "AI 해설" in n)["run"]
    assert '--tools "WebSearch,WebFetch"' in research and "Write" not in research
    assert "WebSearch" not in writer and "WebFetch" not in writer
    assert "timeout 600" in research and "timeout 600" in writer
