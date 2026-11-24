# 성과 추적 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 월요일 리포트에 계좌 수익률 vs 지수, 신호 적중 기록, 예상 연간 배당을 보여준다.
**Architecture:** 순수 계산 모듈 `analysis/performance.py` → `apply_history`가 주간일 때 채움 → 템플릿 렌더, 검증기 숫자 추가.
**Tech Stack:** Python, pydantic, jinja2, pytest
**Spec:** docs/superpowers/specs/2026-11-24-performance-design.md

## Global Constraints
- 테스트는 가상 종목·가짜 숫자. 외부 호출 없음. 로그에 금액·종목 없음.

## Review Focus
- 신규 편입·매도 종목(한쪽 스냅샷에만 있음) → 그 구간 계산에서 빠짐, 오류 없음.
- 스냅샷이 오늘 하나뿐(첫 주) → 수익률 None, 렌더는 "-".
- 지수 값 없는 날 → 해당 지수 None, 적중 채점은 세지 않음.

### Task 1: 계산 모듈 + 스키마
- schema: `SignalScore(signal, events, hits, pending)`, `Performance(since, week_since, account_week_pct, account_total_pct, index_week_pct: dict, index_total_pct: dict, scores, dividend_krw, dividend_missing)`; Context `performance: Performance|None`, `performance_missing: list[str]`.
- `performance.py`: `chain_return(snaps) -> float|None`, `index_return(snaps, key) -> float|None`, `score_signals(snaps) -> list[SignalScore]`, `estimate_dividends(ctx) -> (float|None, list[str])`, `build_performance(snaps, week_since, ctx) -> Performance`.
- Tests `tests/test_performance.py`: 입금 무관 수익률, 환율 반영, 신규·매도 제외, 신호 이벤트·적중·대기·hold 제외, 배당 추정·누락.

### Task 2: 연결·렌더·검증
- `apply_history`: weekly일 때 별도 try로 `build_performance(store.between(...) + [make_snapshot(context)], ...)`; 실패 → `performance_missing=["성과: <오류 종류>"]`.
- 템플릿 📈 성과 섹션(지난주 대비 아래), validate shared 숫자에 performance.
- Tests: test_cli_history(주간이면 채워짐, 저장소 오류면 누락), test_render(섹션 문구), test_validate(성과 숫자 허용).
