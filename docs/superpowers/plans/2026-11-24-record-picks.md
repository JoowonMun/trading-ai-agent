# 살펴볼 곳 기록 남기기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 살펴볼 곳 업종·후보와 AI 의견을 비공개 기록 저장소에 남긴다.
**Architecture:** 스냅샷에 `picks` 추가, `save-snapshot`이 opinions.json을 `opinions/<date>.json`으로 복사.
**Tech Stack:** Python, pydantic, pytest
**Spec:** docs/superpowers/specs/2026-11-24-record-picks-design.md

## Global Constraints
- 스냅샷에는 AI 글을 넣지 않는다. 테스트에는 가상 회사·가짜 숫자만.

## Review Focus
- opinions.json이 없는 날(평일·의견 실패) → 스냅샷만 저장, opinions 폴더 안 만듦.

### Task 1: 스냅샷에 picks
- Test `tests/test_snapshot.py::test_snapshot_saves_picks_without_held`: sectors == ["금속"], candidates[0] == {ticker,name,sector,method,value,sector_median}, "held" 없음; 기본 컨텍스트는 `{"sectors": [], "candidates": []}`.
- Implement in `src/agent/history/snapshot.py::make_snapshot`.

### Task 2: save-snapshot이 의견 복사
- Test `tests/test_cli_history.py::test_save_snapshot_copies_opinions`: opinions.json 있으면 `data/opinions/2026-10-15.json` 내용 동일.
- Test `test_save_snapshot` 확장: opinions.json 없으면 `data/opinions` 없음.
- Implement in `cmd_save_snapshot` (`src/agent/__main__.py`).
- 문서: CLAUDE.md/README 기록 설명 필요 시 한 줄.
