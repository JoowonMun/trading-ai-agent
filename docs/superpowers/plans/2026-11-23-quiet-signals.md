# 조용한 신호 (2a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 월요일 주간 리포트에 보유 종목·유망 업종 회사·시총 상위 300의 지난 7일 주요 공시(계약·시설투자·자사주·유상증자)를 최대 15건 링크와 함께 보여준다.

**Architecture:** DART `list.json`을 시장 전체로 7일치 받고(`market_disclosures`), KRX에서 유망 업종 소속 회사·시총 순위를 받아(`SectorData`), 순수 함수 `pick_signals`가 분류·그룹·상한을 정한다. 업종 온도계를 수집한 실행(월요일)에서만 `build_context`가 붙인다.

**Tech Stack:** Python 3.12, pydantic v2, httpx(DART), pykrx(`get_index_portfolio_deposit_file`, `get_market_cap`), Jinja2, pytest.

**Spec:** `docs/superpowers/specs/2026-11-23-quiet-signals-design.md`

## Global Constraints

- 유망 업종 = 국내 온도계 행 중 `earnings_1y_pct > 0` 이고 `level in ("싸요", "보통")`.
- 종류(제목 키워드, "정정" 포함 제목 제외): contract(`공급계약`), facility(`신규시설투자`), buyback(`자기주식취득`), rights_issue(`유상증자결정`).
- "왜 볼까" 문구는 스펙 4절 표 그대로(코드 상수). rights_issue만 주의 표시.
- 그룹 우선순위 holding → promising → large, 그룹 안 최신순, 같은 회사·종류는 최신 1건, 최대 15건 + `signals_more`.
- 시총 상위 300. DART 공시유형 B·I, 지난 7일(`today-7` ~ `today-1`).
- KRX 실패 → 그 그룹만 빠지고 `signals_missing` 한 줄. DART 실패 → 섹션 전체 누락 한 줄. 업종 온도계가 없는 실행에선 아무것도 안 함.
- KRX 호출은 `_quiet`, 로그는 개수만. 사용자 문구 해요체. 기존 파일의 줄바꿈(LF/CRLF) 유지 — 편집은 Edit 도구로.

## Review Focus

1. 유망 업종이 0개인 주(하락장) — 보유·큰 회사 그룹만 나오고 오류 없음. → Task 1 `test_pick_without_promising`
2. DART `stock_code`가 빈 공시(비상장사) — 건너뜀. → Task 1 `test_pick_skips_unlisted`
3. 신호가 0건 — 섹션 자체가 없음. → Task 3 `test_signal_section_absent_when_empty`
4. KRX 조회일이 휴일 — 하루씩 거슬러 올라감. → Task 2 `test_latest_trading_day_walks_back`
5. 같은 회사가 보유이면서 시총 상위 — 보유 그룹 한 번만. → Task 1 `test_pick_group_priority_and_dedupe`

---

### Task 1: 스키마 + 분류·선택 (순수 함수)

**Files:** Modify `src/agent/report/schema.py`; Create `src/agent/analysis/quiet_signals.py`; Test `tests/test_quiet_signals.py`

**Interfaces — Produces:**
- `QuietSignal(BaseModel)`: `ticker, name, kind: Literal["contract","facility","buyback","rights_issue"], title, date: str (YYYY-MM-DD), url, group: Literal["holding","promising","large"], sector: str|None = None, why: str, caution: bool = False`
- `Context.signals: list[QuietSignal] = []`, `signals_more: int = 0`, `signals_missing: list[str] = []`, `promising_sectors: list[str] = []`
- `WHY: dict[str, str]`, `classify(report_nm: str) -> str | None`
- `promising_sectors(rows: list[SectorRow]) -> list[SectorRow]`
- `pick_signals(filings: list[dict], holdings: set[str], members: dict[str, str], large: set[str], limit: int = 15) -> tuple[list[QuietSignal], int]` — filings는 DART 행(`stock_code, corp_name, report_nm, rcept_dt, rcept_no`), members는 티커→유망 업종 이름

- [ ] **Step 1: 실패하는 테스트** — `test_classify` (각 키워드 → 종류, "[기재정정]단일판매ㆍ공급계약체결" → None, "주주총회소집결의" → None), `test_promising_sectors` (이익 + & 싸요/보통만, 비싸요·레벨 None·이익 음수·미국 제외), `test_pick_group_priority_and_dedupe` (보유이면서 큰 회사 → holding 1건; 순서 holding, promising(sector 이름 채워짐), large), `test_pick_latest_per_company_kind_and_limit` (같은 회사 계약 2건 → 최신 1건; 20건 → 15건 + more 5; 그룹 안 최신순), `test_pick_without_promising`, `test_pick_skips_unlisted` (stock_code "" 제외, 대상 외 회사 제외), `test_rights_issue_is_caution` (caution True, why가 WHY 값)
- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_quiet_signals.py -q`
- [ ] **Step 3: 구현** — url은 `disclosure_url(rcept_no)`, date는 rcept_dt를 YYYY-MM-DD로.
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 커밋** — `feat: 조용한 신호 분류·선택`

### Task 2: 수집기 (DART 시장 전체 · KRX 소속 회사·시총)

**Files:** Modify `src/agent/collectors/dart.py`, `src/agent/collectors/sectors.py`; Test `tests/test_dart.py`, `tests/test_sectors.py`

**Interfaces — Produces:**
- `DartClient.market_disclosures(start: date, end: date) -> list[dict]` — 공시유형 B·I 각각 `page_no` 1..`total_page`, `page_count=100`
- `SectorData.latest_trading_day(today: date) -> date` — `today-1`부터 최대 7일, `get_market_cap(d, market="ALL")`가 비지 않은 첫 날
- `SectorData.kr_constituents(code: str, day: date) -> list[str]`
- `SectorData.market_cap_top(day: date, n: int) -> list[str]` — 시가총액 내림차순 티커

- [ ] **Step 1: 실패하는 테스트** — `test_market_disclosures_reads_all_pages` (기존 test_dart의 가짜 http 방식으로 B 2페이지·I 1페이지 → 3페이지 행 합침, 요청 파라미터에 pblntf_ty), `test_latest_trading_day_walks_back` (월요일 today, 일·토 빈 결과 → 금요일), `test_market_cap_top_sorted` (가짜 get_market_cap → 상위 n 순서). 가짜 pykrx는 monkeypatch, 외부 호출 없음. live: `test_live_signals_sources` (실제 1주 공시 > 0건, 금속 소속 > 10, 시총 300개).
- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_dart.py tests/test_sectors.py -q`
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** + `uv run pytest -m live tests/test_sectors.py -q` (KRX·DART 키 필요, `.env` 로드)
- [ ] **Step 5: 커밋** — `feat: DART 시장 전체 공시, KRX 업종 소속 회사·시총 순위 수집`

### Task 3: context 연결 + 메일 표시

**Files:** Modify `src/agent/report/context.py` (`_attach_signals`, `build_context`), `src/agent/report/templates/email.html` (온도계 섹션 바로 아래), `src/agent/report/glossary.py` + `GLOSSARY_TERMS`; Test `tests/test_quiet_signals.py`, `tests/test_render.py`

**Interfaces:**
- Consumes: Task 1·2 전부
- Produces: `_attach_signals(dart, source, sector_rows: list[SectorRow], holdings: set[str], today: date) -> tuple[list[QuietSignal], int, list[str], list[str]]` (signals, more, missing, promising 이름). `build_context`는 `sectors`가 있고 업종 행이 있을 때만 호출(dart는 이미 인자).

- [ ] **Step 1: 실패하는 테스트** — `test_attach_signals_happy` (가짜 dart·source로 3그룹), `test_attach_signals_krx_failure_drops_group` (kr_constituents 실패 → promising 없음 + missing 한 줄, large는 있음), `test_attach_signals_dart_failure` (missing == ["조용한 신호: …"] 하나, signals 빈 목록), `test_signal_section_in_weekly` (제목 "조용한 신호", 그룹 제목에 "금속 · 이익 +91.2%", 링크 href, ⚠ 주의 문구, "외 5건"), `test_signal_section_absent_when_empty` (신호 0건·알림 메일 → 섹션 없음)
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — 그룹 제목의 업종 숫자는 `context.sectors`에서 이름으로 찾음(국내). 문구 끝에 "공시는 사고팔 신호가 아니라 더 알아볼 거리예요". GLOSSARY "조용한 신호" 추가.
- [ ] **Step 4: 통과 확인** + 전체 `uv run pytest -q -p no:warnings`
- [ ] **Step 5: 커밋** — `feat: 주간 리포트에 조용한 신호`

### Task 4: 실제 데이터 점검 + 문서

- [ ] **Step 1:** `uv run python -m agent run --dry-run --date 2026-11-23` (`.env` 로드, 백그라운드) → preview에 신호 섹션, 로그에 KRX 아이디 없음, 수집 시간 기록
- [ ] **Step 2:** INTENT 로드맵 ④-2를 "2a 조용한 신호(DART) 완료 / 2b 뉴스·테마 키워드·수출 통계 다음"으로, README 기능 표 한 줄, CLAUDE.md 구조에 `quiet_signals`
- [ ] **Step 3:** 전체 테스트 → 커밋 `docs: 조용한 신호 반영`
