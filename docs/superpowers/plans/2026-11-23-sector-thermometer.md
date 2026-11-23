# 업종 온도계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 월요일 주간 리포트에 국내 17개·미국 12개 업종의 가격 수준·이익 방향·주가 위치 표를 넣는다.

**Architecture:** `collectors/sectors.py`가 KRX 업종 지수(PER·PBR 일별 5년)와 업종 ETF(현재 PER·1년 가격)를 가져오고, `analysis/sectors.py`가 순수 함수로 `SectorRow`를 만든다. 미국은 과거 PER이 없으므로 스냅샷에 매주 저장한 값으로 `apply_history`에서 보강한다. 렌더는 주간 리포트에만.

**Tech Stack:** Python 3.12, pydantic v2, pandas, pykrx 1.2.x(`get_index_fundamental`), yfinance(`Ticker.info["trailingPE"]`), Jinja2, pytest.

**Spec:** `docs/superpowers/specs/2026-11-23-sector-thermometer-design.md`

## Global Constraints

- 숫자는 코드가 계산한다. AI는 업종 숫자를 만들지 않고, 검증기가 허용하는 건 context의 업종 숫자뿐.
- 레벨: 백분위 ≤30 "싸요", ≥70 "비싸요", 그 사이 "보통". 유효 일수 < 240이면 레벨·백분위 None, note "자료 부족".
- PBR 업종(국내): 화학, 금속, 건설, 기계·장비, 운송장비·부품, 운송·창고, 금융, 증권, 보험. 나머지 PER.
- PER ≤ 0인 날은 PER 백분위·이익 계산에서 제외. 업종 이익(EPS) = 종가 ÷ PER.
- 미국: PER만(PBR 미사용). 기록 26주 이상이면 백분위, 13주 이상이면 이익 3개월.
- 월요일(`today.weekday() == 0`) 실행에서만 수집. 업종 하나 실패 → 그 행만 빠지고 `sectors_missing`에 한 줄. KRX 계정 없음 → 국내 전체 누락 한 줄.
- KRX 호출은 `prices._quiet`로 감싼다(아이디 출력 방지). 로그에는 개수만.
- 사용자 문구는 해요체. 기존 스타일·패턴을 따른다.

## Review Focus

1. KRX 계정이 없는 환경(CI, 로컬) — 국내만 누락 표시, 미국 표와 리포트는 정상. → Task 3 `test_attach_sectors_without_krx`
2. yfinance가 `trailingPE`를 안 주는 ETF — 그 행은 PER 칸 "-", 하락률은 표시. → Task 1 `test_us_row_without_per`
3. 업종 기록이 없는 옛 스냅샷 — 보강이 조용히 건너뛴다. → Task 2 `test_enrich_ignores_old_snapshots`
4. 백분위가 None인 행 정렬 — 맨 아래로. → Task 1 `test_sort_rows_none_last`
5. 알림 메일·업종 없는 주간 리포트 — 온도계 섹션 없음(빈 표 금지). → Task 5 `test_sector_section_only_in_weekly_with_rows`

---

### Task 1: 스키마 + 업종 계산 (순수 함수)

**Files:**
- Modify: `src/agent/report/schema.py` (Context 위에 `SectorRow`, Context에 필드 2개)
- Create: `src/agent/analysis/sectors.py`
- Test: `tests/test_sectors.py`

**Interfaces:**
- Produces:
  - `SectorRow(BaseModel)`: `key: str`("KR:1018"/"US:XLK"), `name: str`, `market: Literal["KR","US"]`, `method: Literal["PER","PBR"]`, `value: float|None`, `percentile: float|None`, `level: Literal["싸요","보통","비싸요"]|None`, `close: float|None`, `earnings_3m_pct: float|None`, `earnings_1y_pct: float|None`, `drawdown_52w_pct: float|None`, `return_3m_pct: float|None`, `history_weeks: int = 0`, `note: str = ""`
  - `Context.sectors: list[SectorRow] = []`, `Context.sectors_missing: list[str] = []`
  - `level_of(pct: float|None) -> str|None`
  - `percentile_of(values: pd.Series, current: float) -> float` — `values <= current` 비율 × 100, 소수 1자리
  - `price_position(closes: pd.Series) -> tuple[float|None, float|None]` — (최근 252거래일 고점 대비 %, 63거래일 전 대비 %), 소수 1자리
  - `kr_row(code: str, name: str, method: str, df: pd.DataFrame) -> SectorRow` — df 열 `close, per, pbr`, 날짜 인덱스 오름차순
  - `us_row(ticker: str, name: str, per: float|None, closes: pd.Series) -> SectorRow`
  - `sort_rows(rows: list[SectorRow]) -> list[SectorRow]` — 백분위 오름차순, None은 뒤

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_sectors.py`, 가짜 숫자)

```python
def frame(per, pbr=None, close=None, start="2021-01-01"):
    idx = pd.bdate_range(start, periods=len(per))
    return pd.DataFrame({"close": close or [100.0] * len(per), "per": per, "pbr": pbr or [1.0] * len(per)}, index=idx)

def test_level_boundaries():
    assert [level_of(p) for p in (30.0, 30.1, 69.9, 70.0, None)] == ["싸요", "보통", "보통", "비싸요", None]

def test_kr_row_per_percentile_and_earnings():
    per = [10.0] * 300 + [20.0] * 300 + [12.0]          # 지금 12배: 10배 300일 + 12배 1일 ≤ → 301/601
    close = [100.0] * 601
    row = kr_row("1013", "전기전자", "PER", frame(per, close=close))
    assert row.key == "KR:1013" and row.value == 12.0
    assert row.percentile == round(301 / 601 * 100, 1) and row.level == "보통"
    assert row.earnings_1y_pct == round((100 / 12) / (100 / 20) * 100 - 100, 1)   # 252거래일 전 EPS 대비

def test_kr_row_pbr_method_uses_pbr():
    row = kr_row("1018", "건설", "PBR", frame([15.0] * 300, pbr=[1.0] * 299 + [0.5]))
    assert row.method == "PBR" and row.value == 0.5 and row.level == "싸요"

def test_kr_row_excludes_loss_days_and_short_history():
    row = kr_row("1008", "화학", "PER", frame([0.0] * 100 + [10.0] * 200))
    assert row.percentile is None and row.level is None and "자료 부족" in row.note

def test_price_position():
    closes = pd.Series([100.0] * 200 + [80.0] * 63, index=pd.bdate_range("2025-01-01", periods=263))
    assert price_position(closes) == (-20.0, -20.0)

def test_us_row_without_per():
    closes = pd.Series([50.0, 40.0], index=pd.bdate_range("2026-11-19", periods=2))
    row = us_row("XLK", "기술", None, closes)
    assert row.key == "US:XLK" and row.value is None and row.drawdown_52w_pct == -20.0 and row.level is None

def test_sort_rows_none_last():
    rows = [SectorRow(key="a", name="a", market="KR", method="PER", percentile=None),
            SectorRow(key="b", name="b", market="KR", method="PER", percentile=50.0),
            SectorRow(key="c", name="c", market="KR", method="PER", percentile=10.0)]
    assert [r.key for r in sort_rows(rows)] == ["c", "b", "a"]
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_sectors.py -q` → ImportError
- [ ] **Step 3: 구현** — `schema.py`에 모델·필드, `analysis/sectors.py`에 위 함수. `kr_row`: 가격 수준은 `method` 열의 값 > 0 인 날만으로 백분위(유효 < 240이면 None + note "자료 부족"). EPS 시계열 = close/per (per > 0인 날), 이익 3개월·1년 = 지금 EPS vs 63·252거래일 전 행(없으면 None). 주가 위치 = `price_position(df.close)`.
- [ ] **Step 4: 통과 확인** — 같은 명령 PASS
- [ ] **Step 5: 커밋** — `feat: 업종 온도계 계산 (가격 수준·이익 방향·주가 위치)`

### Task 2: 스냅샷 저장 + 미국 기록 보강

**Files:**
- Modify: `src/agent/history/snapshot.py` (`make_snapshot`에 `sectors`)
- Modify: `src/agent/analysis/sectors.py` (`enrich_us_from_history`)
- Test: `tests/test_snapshot.py`, `tests/test_sectors.py`

**Interfaces:**
- Consumes: `SectorRow`, `percentile_of`, `level_of` (Task 1)
- Produces:
  - 스냅샷 키 `"sectors": {row.key: {"method", "value", "close", "eps"}}` — `eps = close / value` (method PER이고 둘 다 있고 value > 0일 때), 아니면 None
  - `enrich_us_from_history(rows: list[SectorRow], past: list[dict], today: date) -> None` — US 행만 수정

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# test_snapshot.py
def test_snapshot_saves_sectors():
    ctx = sample_context()
    ctx.sectors = [SectorRow(key="US:XLK", name="기술", market="US", method="PER", value=25.0, close=200.0)]
    assert make_snapshot(ctx)["sectors"] == {"US:XLK": {"method": "PER", "value": 25.0, "close": 200.0, "eps": 8.0}}

# test_sectors.py
def past_snaps(n, value=20.0, eps=10.0, end=date(2026, 11, 16)):
    return [{"date": (end - timedelta(weeks=i)).isoformat(),
             "sectors": {"US:XLK": {"method": "PER", "value": value, "close": value * eps, "eps": eps}}}
            for i in range(n)]

def us(value=30.0, close=300.0):
    return SectorRow(key="US:XLK", name="기술", market="US", method="PER", value=value, close=close)

def test_enrich_needs_26_weeks_for_percentile():
    row = us(); enrich_us_from_history([row], past_snaps(24), date(2026, 11, 23))
    assert row.history_weeks == 25 and row.percentile is None and "26주" in row.note
    row = us(); enrich_us_from_history([row], past_snaps(25), date(2026, 11, 23))
    assert row.history_weeks == 26 and row.percentile == 100.0 and row.level == "비싸요"

def test_enrich_earnings_3m_after_13_weeks():
    row = us(); enrich_us_from_history([row], past_snaps(13), date(2026, 11, 23))   # 91일 전 이하 가장 가까운 기록
    assert row.earnings_3m_pct == 0.0                                               # EPS 10 → 300/30 = 10

def test_enrich_ignores_old_snapshots():
    row = us(); enrich_us_from_history([row], [{"date": "2026-11-16", "holdings": []}], date(2026, 11, 23))
    assert row.history_weeks == 1 and row.percentile is None
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_snapshot.py tests/test_sectors.py -q`
- [ ] **Step 3: 구현** — `history_weeks` = 그 키가 있는 과거 스냅샷 수 + 1(이번 주). ≥26이면 과거 value들 + 현재로 `percentile_of`·`level_of`, 아니면 note `"기록 {n}주 — 26주부터 과거와 비교"`. 이익 3개월: `today - 91일` 이전 중 가장 최근 기록의 eps가 있고 기록 ≥13주면 계산.
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 커밋** — `feat: 업종 기록을 스냅샷에 저장하고 미국 업종 비교에 사용`

### Task 3: 수집기 + context 연결 (월요일만)

**Files:**
- Create: `src/agent/collectors/sectors.py`
- Modify: `src/agent/report/context.py` (`_attach_sectors`, `build_context(..., sectors=None)`)
- Modify: `src/agent/__main__.py` `cmd_collect` (월요일이면 `SectorData()` 전달)
- Test: `tests/test_sectors.py`, `tests/test_context.py`

**Interfaces:**
- Consumes: `kr_row`, `us_row`, `sort_rows` (Task 1)
- Produces:
  - `KR_SECTORS: list[tuple[str, str, str]]` — (코드, 이름, 방식) 17개, 스펙 3절 순서·코드 그대로
  - `US_SECTORS: list[tuple[str, str]]` — (티커, 이름) 12개, 스펙 그대로
  - `class SectorData`: `kr_fundamentals(code, start: date, end: date) -> pd.DataFrame`(열 close/per/pbr로 이름 변경; KRX 계정 없으면 `RuntimeError("KRX 계정이 없어요")`; 빈 결과면 RuntimeError), `us_quote(ticker, today: date) -> tuple[float|None, pd.Series]`(info의 trailingPE, 1년 종가 — `MarketData().us_closes` 재사용)
  - `_attach_sectors(source, today: date) -> tuple[list[SectorRow], list[str]]` — 5년 = `today - 365*5`일부터

- [ ] **Step 1: 실패하는 테스트 작성** (가짜 source)

```python
class FakeSectors:
    def __init__(self, fail=(), krx=True): self.fail, self.krx = set(fail), krx
    def kr_fundamentals(self, code, start, end):
        if not self.krx: raise RuntimeError("KRX 계정이 없어요")
        if code in self.fail: raise RuntimeError("boom")
        return frame([10.0] * 300)
    def us_quote(self, ticker, today):
        if ticker in self.fail: raise RuntimeError("boom")
        return 20.0, pd.Series([1.0, 1.0], index=pd.bdate_range("2026-11-19", periods=2))

def test_attach_sectors_one_failure_only_drops_that_row():
    rows, missing = _attach_sectors(FakeSectors(fail={"1018", "XLE"}), date(2026, 11, 23))
    assert len(rows) == 17 + 12 - 2 and len(missing) == 2 and any("건설" in m for m in missing)

def test_attach_sectors_without_krx():
    rows, missing = _attach_sectors(FakeSectors(krx=False), date(2026, 11, 23))
    assert {r.market for r in rows} == {"US"} and missing == ["국내 업종: KRX 계정이 없어요"]

def test_build_context_with_sectors(...):   # test_context.py의 기존 가짜 market/dart 사용
    ctx = build_context(..., sectors=FakeSectors())
    assert len(ctx.sectors) == 29

def test_collect_passes_sectors_only_on_monday(monkeypatch, tmp_path):
    # cli.build_context를 가로채 sectors 인자를 기록: 2026-11-23(월) → SectorData 인스턴스, 2026-11-24(화) → None
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_sectors.py tests/test_context.py tests/test_cli.py -q`
- [ ] **Step 3: 구현** — 국내 계정 없음 오류는 첫 업종에서 한 번만 기록하고 국내 루프 중단(17줄 반복 금지). 로그 `log.info("업종 온도계 %d개 (누락 %d)", ...)`. `cmd_collect`: `sectors=SectorData() if args.date.weekday() == 0 else None`.
- [ ] **Step 4: 통과 확인** + live 테스트 추가: `@pytest.mark.live test_live_sector_data` — `kr_fundamentals("1018", …)` 행 ≥ 1000, `us_quote("XLK", …)` PER > 0. `uv run pytest -m live tests/test_sectors.py -q`(KRX 계정 필요)
- [ ] **Step 5: 커밋** — `feat: 월요일 업종 온도계 수집 (KRX 업종 지수·미국 업종 ETF)`

### Task 4: 기록 보강 연결 + 검증기

**Files:**
- Modify: `src/agent/__main__.py` `apply_history` (weekly 분기에서 보강)
- Modify: `src/agent/report/validate.py` (업종 숫자를 `shared`에)
- Test: `tests/test_cli_history.py`, `tests/test_validate.py`

**Interfaces:**
- Consumes: `enrich_us_from_history` (Task 2)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_apply_history_monday_enriches_us_sectors(tmp_path):
    store = seeded_store(tmp_path, close=60000)   # 2026-10-14 스냅샷에 sectors 추가해 저장
    ctx = sample_context(); ctx.sectors = [SectorRow(key="US:XLK", name="기술", market="US", method="PER", value=30.0, close=300.0)]
    cli.apply_history(ctx, Settings(), store, date(2026, 10, 19))
    assert ctx.sectors[0].history_weeks == 2

def test_sector_numbers_allowed_in_market_comment():
    ctx = sample_context(); ctx.sectors = [SectorRow(key="KR:1018", name="건설", market="KR", method="PBR", value=0.68, percentile=12.0)]
    raw = analysis(); raw["market_comment"] = "건설 업종 PBR 0.68배로 과거 5년 중 하위 12%예요"
    assert validate_analysis(raw, ctx)[1] == []
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — `apply_history`의 weekly 분기: `enrich_us_from_history(context.sectors, store.between(today - timedelta(days=365), today - timedelta(days=1)), today)`. `validate.py`: `shared += _numbers([r.model_dump() for r in context.sectors])`.
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 커밋** — `feat: 주간 리포트에서 미국 업종 기록 보강, 업종 숫자 인용 허용`

### Task 5: 리포트 표시 + 용어

**Files:**
- Modify: `src/agent/report/templates/email.html` (주간 비교 섹션 바로 뒤, 국민연금 섹션 앞)
- Modify: `src/agent/report/glossary.py`, `src/agent/report/context.py` `GLOSSARY_TERMS`
- Test: `tests/test_render.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def sector_ctx():
    ctx = sample_context()
    ctx.sectors = [SectorRow(key="KR:1018", name="건설", market="KR", method="PBR", value=0.68, percentile=12.0, level="싸요",
                             earnings_1y_pct=-45.0, drawdown_52w_pct=-30.0, return_3m_pct=-8.0),
                   SectorRow(key="US:XLK", name="기술", market="US", method="PER", value=26.3, history_weeks=3,
                             note="기록 3주 — 26주부터 과거와 비교", drawdown_52w_pct=-27.0)]
    ctx.sectors_missing = ["국내 업종 증권: boom"]
    return ctx

def test_sector_section_in_weekly():
    html = render_report(sector_ctx(), None, [])
    assert "업종 온도계" in html and "PBR 0.68배" in html and "하위 12%" in html and "싸요" in html
    assert "-45.0%" in html and "기록 3주" in html and "증권: boom" in html and GLOSSARY_SHORT["이익 방향"] in html

def test_sector_section_only_in_weekly_with_rows():
    ctx = sector_ctx(); ctx.report_type = "alert"
    assert "업종 온도계" not in render_report(ctx, None, [])
    assert "업종 온도계" not in render_report(sample_context(), None, [])
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_render.py -q`
- [ ] **Step 3: 구현** — 국내·미국 두 표(행은 `sort_rows`). 열: 업종 · 가격 수준(`{method} {value}배 · 하위 {pct}%` + 레벨 배지, 없으면 note) · 이익 방향(국내 1년, 미국 3개월) · 고점 대비 · 3개월. 표 아래 읽는 법(스펙 7절 문구). 누락은 작은 회색 글씨. `GLOSSARY_SHORT`/`GLOSSARY`에 "업종 온도계", "이익 방향" 추가(쉬운 해요체), `GLOSSARY_TERMS`에 추가(`test_glossary_covers_all_terms` 유지).
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 커밋** — `feat: 주간 리포트에 업종 온도계 표`

### Task 6: 문서 + 전체 확인

**Files:**
- Modify: `INTENT.md` (로드맵·하지 않는 것), `CLAUDE.md` 4절 구조(`collectors/ sectors`, `analysis/ sectors`), `README.md` 기능 목록 한 줄

- [ ] **Step 1:** INTENT 로드맵 ④를 "시장 인사이트: ① 업종 온도계(완료) → ② 조용한 신호·뉴스(DART·네이버 뉴스) → ③ AI 의견·후보 종목 → ④ 가설 채점"으로 교체하고 기존 "새 종목 발굴"을 ③에 흡수. "하지 않는 것"의 "업종·테마 비중 조언"을 "업종 비중 지시(업종 해설은 학습용으로 제공)"로.
- [ ] **Step 2:** 전체 테스트 — `uv run pytest -q -p no:warnings` → 전부 통과
- [ ] **Step 3:** 실제 데이터 점검 — `uv run python -m agent run --dry-run --date 2026-11-23` → `out/2026-11-23/preview.html`에 온도계 표(국내 17·미국 12에 가깝게), 출력에 KRX 아이디 없음
- [ ] **Step 4:** 커밋 — `docs: INTENT 로드맵에 시장 인사이트 단계 반영` 후 사용자 확인 받고 push
