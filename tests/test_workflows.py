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
