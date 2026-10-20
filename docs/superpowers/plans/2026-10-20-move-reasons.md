# "왜 움직였나" 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 크게 움직인 종목을 AI가 웹 검색으로 조사해 원인 요약+출처를 알림·주간 리포트에 붙인다.
**Architecture:** 코드가 `research_targets`를 정하고, Claude Code(WebSearch 허용)가 `analysis.move_reasons`를 쓰고, 코드가 별도로 검증해 실패 시 조사 결과만 뺀다.
**Spec:** `docs/superpowers/specs/2026-10-20-move-reasons-design.md`

## Global Constraints
- 조사 요약에 단위 붙은 숫자 금지, found면 출처 1~3개, 대상 외 티커 금지
- 조사 결과 검증 실패가 나머지 리포트를 막지 않는다
- 대상: 알림=big_move 종목, 주간=|1주 수익률|≥7, 최대 3, 변동폭 순

## Review Focus
1. 조사 결과만 실패했을 때 나머지 AI 해설이 살아남는지 → Task 3
2. found=false인데 출처가 없는 경우 통과해야 함 → Task 3
3. 주간 리포트인데 weekly가 없는 경우(첫 주) 대상 없음 → Task 1
4. 출처 URL에 숫자가 있어도(기사 ID) 요약 숫자 검사와 무관 → Task 3
5. 알림 메일 템플릿과 주간 템플릿 모두 표시 → Task 4

---

### Task 1: 스키마·설정·대상 선정
**Files:** `report/schema.py`, `config.py`, Create `analysis/research.py` · Test `tests/test_research.py`

- [ ] 테스트:
```python
from factories import sample_context
from agent.analysis.research import pick_research_targets
from agent.config import Settings
from agent.report.schema import Alert, WeeklyDiff, WeeklyHolding

def big(t, change):
    return Alert(kind="big_move", ticker=t, name=t, market="KR", message="m", values=[change, 1.0, 1.0])

def test_alert_targets_sorted_and_capped():
    ctx = sample_context(); ctx.report_type = "alert"
    ctx.alerts = [big("A", -5.5), big("B", 9.0), Alert(kind="disclosure", ticker="C", name="C", market="KR", message="m"),
                  big("D", -7.0), big("E", 6.0)]
    assert pick_research_targets(ctx, Settings()) == ["B", "D", "E"]

def test_weekly_targets_use_weekly_returns():
    ctx = sample_context(); ctx.report_type = "weekly"
    ctx.weekly = WeeklyDiff(since="2026-10-08", holdings=[
        WeeklyHolding(ticker="X", name="X", market="US", status="held", return_pct=-8.0),
        WeeklyHolding(ticker="Y", name="Y", market="US", status="held", return_pct=3.0),
        WeeklyHolding(ticker="Z", name="Z", market="US", status="new")])
    assert pick_research_targets(ctx, Settings()) == ["X"]

def test_no_targets_without_history_or_on_quiet_day():
    ctx = sample_context()               # weekly, weekly=None
    assert pick_research_targets(ctx, Settings()) == []
    ctx.report_type = "none"
    assert pick_research_targets(ctx, Settings()) == []
```
- [ ] 구현: `MoveReason(found: bool, summary: str, sources: list[str] = [])`, `Context.research_targets: list[str] = []`, `Analysis.move_reasons: dict[str, MoveReason] = {}`; Settings `research_weekly_move_pct: float = 7.0`, `research_max: int = 3`;
```python
def pick_research_targets(ctx, settings) -> list[str]:
    if ctx.report_type == "alert":
        moves = {a.ticker: abs(a.values[0]) for a in ctx.alerts if a.kind == "big_move" and a.values}
    elif ctx.report_type == "weekly" and ctx.weekly:
        moves = {h.ticker: abs(h.return_pct) for h in ctx.weekly.holdings
                 if h.status == "held" and h.return_pct is not None and abs(h.return_pct) >= settings.research_weekly_move_pct}
    else:
        moves = {}
    return sorted(moves, key=moves.get, reverse=True)[:settings.research_max]
```
- [ ] Commit `feat: 원인 조사 대상 선정`

### Task 2: apply_history에서 대상 지정
**Files:** `__main__.py` · Test `tests/test_cli_history.py`
- [ ] 테스트: `test_apply_history_alert_day`에 `assert ctx.research_targets == ["005930"]` 추가, 오류 처리 테스트에서 `research_targets == []`
- [ ] 구현: `apply_history` try 끝에 `context.research_targets = pick_research_targets(context, settings)`, except에서 `[]`
- [ ] Commit `feat: 알림·주간에 원인 조사 대상 지정`

### Task 3: 조사 결과 검증과 publish/check 연결
**Files:** `report/validate.py`, `__main__.py` · Test `tests/test_validate.py`, `tests/test_cli_history.py`
- [ ] 테스트 (validate):
```python
def research_context():
    ctx = alert_context(); ctx.research_targets = ["005930"]; return ctx

def reasons(**r):
    return {"005930": {"found": True, "summary": "반도체 업황 우려로 업종 전체가 약세였어요.",
                       "sources": ["https://www.yna.co.kr/view/AKR20261015000000001"], **r}}

def test_move_reasons_ok_and_not_found_ok():
    from agent.report.schema import Analysis
    from agent.report.validate import check_move_reasons
    a = Analysis(date="2026-10-15", summary=["x"], move_reasons=reasons())
    assert check_move_reasons(a, research_context()) == []
    a = Analysis(date="2026-10-15", summary=["x"], move_reasons={"005930": {"found": False, "summary": "뚜렷한 원인을 찾지 못했어요."}})
    assert check_move_reasons(a, research_context()) == []

def test_move_reasons_rules():
    from agent.report.schema import Analysis
    from agent.report.validate import check_move_reasons
    ctx = research_context()
    bad = [reasons(sources=[]), reasons(summary="매출이 20% 늘었어요"), reasons(sources=["ftp://x"])]
    for r in bad:
        assert check_move_reasons(Analysis(date="2026-10-15", summary=["x"], move_reasons=r), ctx) != []
    other = {"AAPL": reasons()["005930"]}
    assert check_move_reasons(Analysis(date="2026-10-15", summary=["x"], move_reasons=other), ctx) != []
```
- [ ] 테스트 (publish): context(report_type alert, research_targets ["005930"]) + analysis.json(유효한 알림 해설 + 숫자 든 move_reasons) → preview에 alert_comments 문장은 있고 "원인 조사 결과 검증 실패" 메모, move_reasons 요약은 없음
- [ ] 구현: `check_move_reasons(analysis, context)` — 키 ∉ targets, found & 출처 0개 또는 4개 이상, 출처가 http(s) 아님, summary에 `NUMBER_WITH_UNIT` 매치 → 에러. `validate_analysis`는 move_reasons를 보지 않는다. `cmd_publish`: analysis 통과 후 `errs = check_move_reasons(...)`; 있으면 `analysis.move_reasons = {}`, notes에 "원인 조사 결과 검증 실패 → 제외" + 최대 3건. `cmd_check`: 두 검사 결과를 합쳐 출력.
- [ ] Commit `feat: 원인 조사 결과 별도 검증, 실패 시 조사만 제외`

### Task 4: 렌더링
**Files:** `render.py`, `templates/alert.html`, `templates/email.html` · Test `tests/test_render.py`
- [ ] 테스트: 알림 메일·주간 리포트 각각 move_reasons 있을 때 "왜 움직였나", 요약 문장, 출처 도메인(`www.yna.co.kr`) 링크 표시. found=false면 "뚜렷한 원인을 찾지 못했어요".
- [ ] 구현: `render.py`에 필터 `domain`(urlparse netloc). 두 템플릿의 종목 카드(alert: 알림 카드 안, email: 보유 종목 상세 카드 상단 AI 해설 아래)에 `{% set r = analysis.move_reasons.get(ticker) if analysis else none %}` 블록: "🔎 왜 움직였나" + summary + 출처 링크(도메인 표시).
- [ ] Commit `feat: 리포트에 '왜 움직였나' 표시`

### Task 5: AI 지침·워크플로
**Files:** `prompts/analysis-guide.md`, `prompts/daily-prompt.md`, `.github/workflows/daily-report.yml`(편집 도구로) · Test `tests/test_workflows.py`
- [ ] 테스트: `"WebSearch" in text and "WebFetch" in text`
- [ ] 지침: spec 5절 규칙 + 출력 형식 예시 + 숫자 금지 강조. daily-prompt에 "research_targets가 있으면 지침의 원인 조사 절차를 먼저 수행".
- [ ] 워크플로 allowedTools에 `"WebSearch" "WebFetch"` 추가, `timeout-minutes` 여유 확인(45 유지)
- [ ] Commit `feat: AI 원인 조사 지침과 웹 검색 허용`

### Task 6: 종단 확인 (로컬, 메일 없음)
- [ ] 실제 context.json에 `report_type="alert"`, 가짜 big_move 알림과 `research_targets=[실제 보유 미국 종목 1개]`를 넣은 임시 복사본(out/research-test/)으로 Claude Code(구독 토큰, WebSearch 허용)를 daily-prompt대로 실행 → `agent check` 통과·출처 품질 확인 → `publish --dry-run`으로 preview 확인. 임시 파일은 커밋하지 않는다.
