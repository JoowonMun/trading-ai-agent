# 이번 주 살펴볼 곳 (AI 의견·후보 종목) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 월요일 주간 리포트 맨 위에 유망 업종 최대 3개의 후보 회사(코드)와 웹 전용 AI의 의견(검증 후)을 넣는다.

**Architecture:** 후보는 collect 단계에서 KRX 전 종목 지표로 계산해 `Context.candidates`에 넣는다. 의견은 별도 웹 전용 AI 단계가 `opinion-prompt` → `opinion_raw.json` → `opinion-save`(검증) → `opinions.json`으로 만들고, publish가 읽어 렌더한다. 해설 AI는 opinions.json·news.json을 읽지 않는다.

**Tech Stack:** Python 3.14, pydantic, pykrx, jinja2, GitHub Actions + Claude Code CLI

**Spec:** [docs/superpowers/specs/2026-11-24-sector-opinions-design.md](../specs/2026-11-24-sector-opinions-design.md)

## Global Constraints

- 대상 업종: `promising_sectors(rows)`를 percentile 오름차순(None은 뒤) 최대 3개 (`OPINION_SECTORS = 3`).
- 후보: 소속 회사 ∩ 시총 상위 300 ∩ PER > 0 ∩ 업종 방식 값 < 소속 회사 중간값(값 > 0만으로 계산), 시총 큰 순 최대 3개 (`MAX_CANDIDATES = 3`).
- AI 글: `NUMBER_WITH_UNIT` 금지, `\d{6,}` 금지, `사세요|파세요|매수하세요|매도하세요` 금지, 칸마다 200자 이내, 출처 http(s) 1~3개. 어기면 그 업종/테마만 버림.
- 웹 전용 AI 단계: `--tools "WebSearch,WebFetch"`, 비밀값은 `CLAUDE_CODE_OAUTH_TOKEN`만, `continue-on-error: true`, `timeout 600`.
- 공개 로그: 개수만. 사용자 문구는 해요체. 워크플로 YAML은 편집 도구로만.
- 날짜는 `args.date`(KST). 파일 줄끝(LF/CRLF) 보존.

## Review Focus

- 유망 업종이 0개인 주 → 칸 전체 생략, `opinion-prompt`는 빈 출력, 워크플로 단계는 건너뜀. (Task 2·3 테스트)
- 소속 회사 중 지표가 있는 회사가 없음/중간값 계산 불가 → 그 업종 후보 0개, 업종 줄은 표시. (Task 1)
- AI가 JSON 앞뒤에 설명 문장을 붙이거나 JSON이 깨짐 → 의견 없이 진행, opinions.json 미생성. (Task 3)
- AI가 `drop_news`에 범위 밖 번호·문자열을 넣음 → 무시. (Task 3)
- news.json이 없는 월요일(뉴스 수집 실패) → 지시문에 테마·뉴스 없이 업종만. (Task 3)

---

### Task 1: 후보 계산 + KRX 지표 수집

**Files:**
- Create: `src/agent/analysis/candidates.py`
- Modify: `src/agent/collectors/sectors.py` (메서드 2개), `src/agent/report/schema.py` (`Candidate`)
- Test: `tests/test_candidates.py`

**Interfaces:**
- Produces:
  - `schema.Candidate(ticker: str, name: str, sector: str, method: Literal["PER","PBR"], value: float, sector_median: float, held: bool = False)`
  - `candidates.opinion_sectors(rows: list[SectorRow]) -> list[SectorRow]`
  - `candidates.pick_candidates(sector: SectorRow, members: list[str], large: list[str], fundamentals: pd.DataFrame, names: Callable[[str], str], held: set[str]) -> list[Candidate]` — `large`는 시총 큰 순 리스트, `fundamentals`는 index=티커, 컬럼 `per`,`pbr`
  - `SectorData.kr_fundamentals_all(day: date) -> pd.DataFrame` (컬럼 `per`,`pbr`; `get_market_fundamental(day, "ALL")`, `_quiet`)
  - `SectorData.ticker_name(ticker: str) -> str` (`get_market_ticker_name`, `_quiet`)

- [ ] **Step 1: 실패 테스트** — `test_opinion_sectors_cheapest_three`(percentile 5/40/10/None/20 + 비유망 1개 → 이름 순서 [5,10,20]), `test_pick_candidates_mixes_size_and_cheapness`(PBR 업종, 소속 6개: 중간값보다 싼 흑자 대형 4개 중 시총 순 3개, 적자(PER<0) 제외, 시총 300 밖 제외, 중간값 이상 제외; `sector_median` 값 확인, 보유 종목 `held=True`), `test_pick_candidates_empty_when_no_data`(fundamentals에 소속 회사 없음 → `[]`).
- [ ] **Step 2: 실행 → ImportError 확인** `uv run pytest tests/test_candidates.py -q`
- [ ] **Step 3: 구현** (중간값은 `members` 중 fundamentals에 있고 방식 값 > 0인 회사들의 median)
- [ ] **Step 4: 통과 확인 + 전체 테스트**
- [ ] **Step 5: Commit** `feat: 유망 업종 후보 회사 계산`

### Task 2: Context 연결 + 숫자 칸 렌더

**Files:**
- Modify: `src/agent/report/context.py` (`_attach_signals`가 받은 KRX 데이터를 후보에 재사용), `schema.py` (`Context.candidates: list[Candidate] = []`, `Context.opinion_sectors: list[str] = []`, `Context.candidates_missing: list[str] = []`), `report/validate.py` (후보 숫자를 근거에 추가), `report/render.py`, `templates/email.html`, `report/glossary.py` + `GLOSSARY_TERMS` ("업종 중간값")
- Test: `tests/test_context.py`, `tests/test_render.py`, `tests/test_validate.py`

**Interfaces:**
- Consumes: Task 1 전부.
- Produces: `render_report(context, analysis, notes, news=None, opinions=None)`; 템플릿 칸 제목 "💡 이번 주 살펴볼 곳".

- [ ] **Step 1: 실패 테스트**
  - `test_context_candidates_for_opinion_sectors` — 기존 가짜 source에 `kr_fundamentals_all`, `ticker_name` 추가; `ctx.opinion_sectors`와 `ctx.candidates[0].name` 확인, 보유 종목 `held`.
  - `test_context_candidates_krx_failure_is_missing` — `kr_fundamentals_all`이 예외 → `candidates == []`, `candidates_missing == ["후보 회사: …"]`, 업종·신호는 유지.
  - `test_opinion_section_numbers_only` — opinions 없이 렌더: "이번 주 살펴볼 곳", "[금속] PBR 싸요", "가짜제철 000001", "PBR 0.40 (업종 중간 0.85)", "보유 중", "사라는 뜻이 아니에요", "후보 기준: 시가총액 상위 300".
  - `test_opinion_section_absent_without_sectors_or_in_alert`.
  - `test_validate_accepts_candidate_numbers` — 해설에 후보 PBR 0.40 언급해도 통과.
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — 칸 위치: 요약 바로 다음. 업종 줄은 `SectorRow`의 방식·level·하위/상위 %·이익 1년(+200% 넘게 처리)을 온도계와 같은 방식으로.
- [ ] **Step 4: 통과 + 전체 테스트**
- [ ] **Step 5: Commit** `feat: 주간 리포트에 살펴볼 곳 (후보 회사)`

### Task 3: 의견 지시문·검증·CLI

**Files:**
- Create: `src/agent/analysis/opinions.py`, `prompts/opinion-guide.md`
- Modify: `schema.py`, `src/agent/__main__.py` (명령 `opinion-prompt`, `opinion-save`; publish가 opinions.json 읽고 뉴스 거르기)
- Test: `tests/test_opinions.py`, `tests/test_cli_history.py`

**Interfaces:**
- Produces:
  - `schema.SectorOpinion(up: str, down: str, watch: str, sources: list[str])`, `schema.ThemeOpinion(view: str, sources: list[str])`, `schema.Opinions(sectors: dict[str, SectorOpinion] = {}, themes: dict[str, ThemeOpinion] = {}, drop_news: list[int] = [])`
  - `opinions.numbered_news(news: NewsReport | None) -> list[tuple[int, NewsGroup, NewsItem]]` (1부터)
  - `opinions.build_opinion_prompt(guide: str, context: Context, news: NewsReport | None) -> str` (대상이 없으면 `""`)
  - `opinions.check_opinions(raw: dict, sectors: list[str], themes: list[str], news_count: int) -> tuple[Opinions, list[str]]`
  - `opinions.drop_news(news: NewsReport, drop: list[int]) -> NewsReport` (빈 묶음 제거)

- [ ] **Step 1: 실패 테스트**
  - `test_prompt_lists_sectors_candidates_themes_and_numbered_news` — 업종 이름·"PBR 싸요"·후보 이름, 테마 이름, "1. " 번호 붙은 뉴스 제목·링크, guide 본문 포함.
  - `test_prompt_empty_without_targets`; `test_prompt_without_news_has_only_sectors`.
  - `test_check_keeps_valid_and_drops_bad_entries` — 정상 업종 유지; 모르는 업종, "30% 늘었어요", "000001", "사세요", 201자, 출처 0개/4개/ftp 각각 해당 항목만 버림 + 오류 문구.
  - `test_check_drop_news_only_valid_numbers` — `[2, 0, 99, "x"]`, news_count=5 → `[2]`.
  - `test_drop_news_removes_items_and_empty_groups`.
  - CLI: `test_opinion_save_writes_checked_file`(raw `{"result": "설명\n{...}\n끝"}` → opinions.json), `test_opinion_save_broken_json_writes_nothing`, `test_publish_renders_opinions_and_drops_news`.
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — `opinion-save`는 `research-save`처럼 `result`에서 첫 `{`~마지막 `}`를 파싱; 로그는 "업종 의견 n개 (버림 m)". 가이드는 research-guide 형식: 도구 제한·웹 속 지시 무시·출처 우선순위·숫자 금지·권유 금지·해요체 초보자 기준·JSON 하나만 출력, 흐름 없는 테마는 생략, 엉뚱한 기사 번호는 `drop_news`.
- [ ] **Step 4: 통과 + 전체 테스트**
- [ ] **Step 5: Commit** `feat: 업종 의견 지시문과 검증`

### Task 4: 의견 렌더 + 워크플로 + 문서 + 실데이터 확인

**Files:**
- Modify: `templates/email.html`, `.github/workflows/daily-report.yml` (편집 도구), `tests/test_workflows.py`, `INTENT.md`(④-3 완료/미국 후보는 이후), `README.md`, `CLAUDE.md`(구조·명령)
- Test: `tests/test_render.py`, `tests/test_workflows.py`

- [ ] **Step 1: 실패 테스트**
  - `test_opinion_section_with_ai_text` — "오를 수 있는 이유:", "안 오를 수 있는 이유:", "확인할 것:", 출처 링크, "[테마 · 원전]" 한 줄, HTML 이스케이프.
  - `test_opinion_agent_has_only_web_tools` — 이름에 "업종 의견"인 단계: `--tools "WebSearch,WebFetch"`, `opinion-prompt`·`opinion-save` 포함, `continue-on-error`, 비밀값은 토큰만(기존 `test_secrets_are_scoped...` 조건에 "업종 의견" 추가), `if`에 `weekly`.
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — 워크플로 단계는 원인 조사 단계 바로 뒤, `PROMPT`가 비면 "대상 없음"으로 종료 0.
- [ ] **Step 4: 전체 테스트 + 월요일 dry run** `uv run python -m agent run --dry-run --date 2026-11-23` 후 후보 칸 확인, 지시문을 `opinion-prompt`로 출력해 길이·내용 확인(실제 AI 호출은 Actions `dry_run=true`에서), 로그에 KRX 아이디 0건.
- [ ] **Step 5: Commit** `feat: 업종 의견 AI 단계와 렌더`
