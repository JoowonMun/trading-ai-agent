# 알림 + 주간 리포트 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 평일엔 변화가 있을 때만 알림 메일, 월요일엔 "지난주 대비"가 붙은 주간 리포트를 보내고, 매일 스냅샷을 비공개 기록 저장소에 남긴다.

**Architecture:** `collect`가 기존 context를 만든 뒤 기록 저장소의 직전 스냅샷과 비교해 `alerts`를 계산하고 `report_type`(weekly/alert/none)을 정한다. `publish`는 report_type에 따라 주간 리포트(`email.html`) 또는 알림 메일(`alert.html`)을 보내거나 생략한다. 발송 후 `save-snapshot`이 오늘 스냅샷을 기록 저장소에 쓰고, 워크플로가 커밋·푸시한다.

**Tech Stack:** 기존과 동일 (Python 3.12+, pydantic, Jinja2, pytest, GitHub Actions) + 비공개 저장소 deploy key

**Spec:** `docs/superpowers/specs/2026-10-20-alerts-weekly-design.md`

## Global Constraints

- 알림 문구·숫자는 코드가 만든다. AI는 종목별 한두 문장 해설(`alert_comments`)만 쓴다. 숫자 검증 규칙 동일
- 큰 변동 기준 `alert_move_pct` 기본 5 (settings)
- 평일 06:17 KST 실행, 월요일(KST)은 주간 리포트
- 스냅샷에는 AI 해설·키·계좌번호를 넣지 않는다. 공개 저장소·Actions 로그에 보유 종목을 남기지 않는다
- 시험 실행(dry_run)은 스냅샷을 저장·커밋하지 않는다
- `--history-dir` 없이 실행하면 지금처럼 매일 전체 리포트(report_type `weekly`, 비교 없음) — 로컬 실행 호환

## Review Focus

1. **기록이 하루 이상 빠진 경우(휴일, 실행 실패)** — 직전 *가장 최근* 스냅샷과 비교해야 하고, 큰 변동 문구에 비교 기준일이 보여야 한다 → Task 4 테스트
2. **같은 실적 발표일 알림이 D-3부터 매일 반복** — 처음 창에 들어온 날 한 번만 → Task 4 테스트
3. **알림 메일의 AI 해설이 알림 문구 속 숫자를 인용** — 알림 문구 숫자도 허용 목록에 들어가야 검증에서 떨어지지 않는다 → Task 7 테스트
4. **알림 없는 평일** — AI 단계와 발송을 건너뛰되 스냅샷은 저장 → Task 6·10
5. **기록 저장소 로딩 실패** — 첫 실행처럼 처리하고 리포트는 계속 → Task 6 테스트

---

## 파일 구조

| 파일 | 책임 |
|---|---|
| `src/agent/report/schema.py` (수정) | `Alert`, `WeeklyHolding`, `WeeklyDiff`, `ReportType`, `Context.report_type/alerts/weekly`, `HoldingContext.next_earnings`, `Analysis.alert_comments`, `Analysis.holdings` 기본값 |
| `src/agent/config.py` (수정) | `Settings.alert_move_pct` |
| `src/agent/history/__init__.py`, `snapshot.py` | `holding_levels`, `make_snapshot` |
| `src/agent/history/store.py` | `SnapshotStore` |
| `src/agent/analysis/alerts.py` | `detect_alerts`, `LEVEL_LABELS`, `SIGNAL_LABELS` 재사용 |
| `src/agent/analysis/weekly.py` | `weekly_diff`, `decide_report_type` |
| `src/agent/collectors/us_fundamentals.py` (수정) | `UsFundamentalData.next_earnings` |
| `src/agent/report/context.py` (수정) | `h.next_earnings` 채움 |
| `src/agent/report/validate.py` (수정) | alert 모드, `alert_comments` 숫자 검사, 알림 문구 숫자 허용 |
| `src/agent/report/templates/alert.html`, `email.html`(수정), `render.py`(수정) | 알림 메일, 주간 섹션, 템플릿 선택 |
| `src/agent/__main__.py` (수정) | `collect --history-dir`, `publish` 생략·제목, `save-snapshot` |
| `prompts/analysis-guide.md`, `daily-prompt.md` (수정) | alert 모드 작성 규칙 |
| `.github/workflows/daily-report.yml` (수정) | 기록 저장소 체크아웃·커밋, none이면 AI·발송 생략 |

---

### Task 1: 스키마·설정 확장

**Files:** Modify `src/agent/report/schema.py`, `src/agent/config.py` · Test `tests/test_schema_alerts.py`

**Interfaces — Produces:** `Alert(kind, ticker, name, market, message, important=False)`, `WeeklyHolding`, `WeeklyDiff`, `ReportType = Literal["weekly","alert","none"]`, `Context.report_type="weekly"`, `Context.alerts=[]`, `Context.weekly=None`, `HoldingContext.next_earnings: str | None`, `Analysis.holdings` 기본 `[]`, `Analysis.alert_comments: dict[str, str] = {}`, `Settings.alert_move_pct=5.0`

- [ ] **Step 1: 실패하는 테스트**

```python
# tests/test_schema_alerts.py
from factories import sample_context

from agent.config import Settings
from agent.report.schema import Alert, Analysis, Context, WeeklyDiff


def test_context_defaults_keep_full_report_behaviour():
    ctx = sample_context()
    assert ctx.report_type == "weekly" and ctx.alerts == [] and ctx.weekly is None
    assert ctx.holdings[0].next_earnings is None


def test_alert_and_weekly_round_trip():
    ctx = sample_context()
    ctx.report_type = "alert"
    ctx.alerts = [Alert(kind="big_move", ticker="005930", name="삼성전자", market="KR",
                        message="삼성전자 -6.2% (2026-10-14 대비)", important=True)]
    ctx.weekly = WeeklyDiff(since="2026-10-13", holdings=[], alerts=ctx.alerts)
    assert Context.model_validate_json(ctx.model_dump_json()) == ctx


def test_analysis_alert_mode_allows_no_holdings():
    a = Analysis(date="2026-10-15", summary=["x"], alert_comments={"005930": "설명"})
    assert a.holdings == []


def test_alert_move_pct_default():
    assert Settings().alert_move_pct == 5.0
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_schema_alerts.py -q` → ImportError(Alert)

- [ ] **Step 3: 구현** — `schema.py`에 추가:

```python
AlertKind = Literal["signal_change", "level_cross", "big_move", "disclosure", "nps", "earnings_soon"]
ReportType = Literal["weekly", "alert", "none"]


class Alert(BaseModel):
    kind: AlertKind
    ticker: str
    name: str
    market: Literal["KR", "US"]
    message: str
    important: bool = False


class WeeklyHolding(BaseModel):
    ticker: str
    name: str
    market: Literal["KR", "US"]
    status: Literal["held", "new", "sold"]
    close: float | None = None
    prev_close: float | None = None
    return_pct: float | None = None
    signal: str | None = None
    prev_signal: str | None = None
    weight_pct: float | None = None
    prev_weight_pct: float | None = None


class WeeklyDiff(BaseModel):
    since: str
    holdings: list[WeeklyHolding] = []
    total_krw: float | None = None
    prev_total_krw: float | None = None
    total_change_pct: float | None = None
    class_changes: dict[str, dict] = {}
    index_changes: dict[str, float] = {}
    alerts: list[Alert] = []
```

`HoldingContext`에 `next_earnings: str | None = None`, `Context`에 `report_type: ReportType = "weekly"`, `alerts: list[Alert] = []`, `weekly: WeeklyDiff | None = None`, `Analysis`의 `holdings: list[HoldingAnalysis] = []` 와 `alert_comments: dict[str, str] = {}` (Alert/WeeklyDiff 정의는 HoldingContext·Context보다 위). `Settings`에 `alert_move_pct: float = 5.0`.

- [ ] **Step 4: 통과 확인** — 위 명령 → 4 passed, 전체 `uv run pytest -q -p no:warnings` 통과
- [ ] **Step 5: Commit** — `feat: 알림·주간 리포트 스키마와 설정`

---

### Task 2: 스냅샷 만들기

**Files:** Create `src/agent/history/__init__.py`(빈 파일), `src/agent/history/snapshot.py` · Test `tests/test_snapshot.py`

**Interfaces — Produces:** `LEVEL_KEYS: list[tuple[str, str]]` (`[("sell2","일부매도 2차"),("sell1","일부매도 1차"),("buy1","분할매수 1단계"),("buy2","분할매수 2단계"),("buy3","분할매수 3단계"),("review","재검토 기준가")]`), `holding_levels(h: HoldingContext) -> dict[str, float]`, `make_snapshot(ctx: Context) -> dict`

- [ ] **Step 1: 실패하는 테스트**

```python
# tests/test_snapshot.py
import json

from factories import sample_context

from agent.history.snapshot import holding_levels, make_snapshot
from agent.report.schema import Alert


def test_holding_levels_from_valuation():
    levels = holding_levels(sample_context().holdings[0])
    assert levels == {"buy1": 52846, "buy2": 47561, "buy3": 42276, "sell1": 84553, "sell2": 100406,
                      "review": 60350}
    assert holding_levels(sample_context().holdings[1]) == {}   # 밴드 없는 종목


def test_make_snapshot_contents_and_no_ai_text():
    ctx = sample_context()
    ctx.holdings[0].nps = {"stake_pct": 7.5, "date": "2026-10-14"}
    ctx.alerts = [Alert(kind="big_move", ticker="005930", name="삼성전자", market="KR", message="m")]
    snap = make_snapshot(ctx)
    assert snap["version"] == 1 and snap["date"] == "2026-10-15"
    h = snap["holdings"][0]
    assert (h["ticker"], h["market"], h["close"], h["signal"], h["weight_pct"]) == ("005930", "KR", 65000, "hold", 8.2)
    assert h["nps_stake_pct"] == 7.5 and h["nps_date"] == "2026-10-14"
    assert snap["portfolio"]["total_krw"] == 8_000_000 and snap["portfolio"]["by_class"]["domestic"] == 8.2
    assert snap["market"]["indices"]["KOSPI"] == 2500.0 and snap["market"]["fx_usdkrw"] == 1350.0
    assert snap["alerts"][0]["kind"] == "big_move"
    json.dumps(snap)   # 직렬화 가능
```

- [ ] **Step 2: 실패 확인** — ModuleNotFoundError
- [ ] **Step 3: 구현**

```python
# src/agent/history/snapshot.py
"""그날의 계산 결과 요약(스냅샷) — 알림 비교·주간 비교·성과 추적용. AI 해설·키·계좌번호는 넣지 않는다."""
from agent.report.schema import Context, HoldingContext

LEVEL_KEYS = [("sell2", "일부매도 2차"), ("sell1", "일부매도 1차"), ("buy1", "분할매수 1단계"),
              ("buy2", "분할매수 2단계"), ("buy3", "분할매수 3단계"), ("review", "재검토 기준가")]


def holding_levels(h: HoldingContext) -> dict[str, float]:
    v = h.valuation
    if v is None:
        return {}
    levels = {}
    if not v.insufficient:
        levels.update(buy1=v.buy[0], buy2=v.buy[1], buy3=v.buy[2], sell1=v.sell[0], sell2=v.sell[1])
    if v.review is not None:
        levels["review"] = v.review
    return levels


def make_snapshot(ctx: Context) -> dict:
    return {
        "version": 1,
        "date": ctx.date,
        "holdings": [{
            "ticker": h.ticker, "name": h.name, "market": h.market,
            "close": h.price.close if h.price else None,
            "signal": h.signal,
            "levels": holding_levels(h),
            "weight_pct": h.position.weight_pct,
            "nps_stake_pct": (h.nps or {}).get("stake_pct"),
            "nps_date": (h.nps or {}).get("date"),
            "disclosures": [d.url for d in h.disclosures],
            "next_earnings": h.next_earnings,
        } for h in ctx.holdings],
        "portfolio": {"total_krw": ctx.portfolio.total_krw, "cash_krw": ctx.portfolio.cash_krw,
                      "by_class": {k: w.pct for k, w in ctx.portfolio.by_class.items()}},
        "market": {"indices": {k: q.close for k, q in ctx.market.indices.items()},
                   "fx_usdkrw": ctx.market.fx_usdkrw},
        "alerts": [a.model_dump() for a in ctx.alerts],
    }
```

참고: sample_context의 두 번째 종목(AAPL)은 valuation이 없다 → `{}`.

- [ ] **Step 4: 통과 확인** — 2 passed
- [ ] **Step 5: Commit** — `feat: 일일 스냅샷 생성`

---

### Task 3: 스냅샷 저장소

**Files:** Create `src/agent/history/store.py` · Test `tests/test_store.py`

**Interfaces — Produces:** `SnapshotStore(root: Path)` with `latest_before(d: date) -> dict | None`, `on_or_before(d: date) -> dict | None`, `between(start: date, end: date) -> list[dict]` (양 끝 포함, 날짜순), `save(snapshot: dict) -> None` (`snapshots/<date>.json` + `history/portfolio.csv` 갱신)

- [ ] **Step 1: 실패하는 테스트**

```python
# tests/test_store.py
from datetime import date

from agent.history.store import SnapshotStore


def snap(d, total=100.0, kospi=2500.0):
    return {"version": 1, "date": d, "holdings": [], "portfolio": {"total_krw": total},
            "market": {"indices": {"KOSPI": kospi, "S&P500": 6000.0}, "fx_usdkrw": 1350.0}, "alerts": []}


def test_lookups_skip_missing_days(tmp_path):
    store = SnapshotStore(tmp_path)
    for d in ("2026-10-12", "2026-10-13", "2026-10-15"):   # 10-14 빠짐
        store.save(snap(d))
    assert store.latest_before(date(2026, 10, 16))["date"] == "2026-10-15"
    assert store.latest_before(date(2026, 10, 15))["date"] == "2026-10-13"
    assert store.latest_before(date(2026, 10, 12)) is None
    assert store.on_or_before(date(2026, 10, 14))["date"] == "2026-10-13"
    assert [s["date"] for s in store.between(date(2026, 10, 13), date(2026, 10, 15))] == ["2026-10-13", "2026-10-15"]


def test_empty_or_missing_root(tmp_path):
    store = SnapshotStore(tmp_path / "nothing")
    assert store.latest_before(date(2026, 10, 16)) is None and store.between(date(2026, 1, 1), date(2026, 12, 31)) == []


def test_portfolio_csv_one_row_per_date(tmp_path):
    store = SnapshotStore(tmp_path)
    store.save(snap("2026-10-15", total=100))
    store.save(snap("2026-10-14", total=90))
    store.save(snap("2026-10-15", total=110))   # 같은 날 재실행 → 덮어씀
    lines = (tmp_path / "history" / "portfolio.csv").read_text(encoding="utf-8").splitlines()
    assert lines == ["date,total_krw,kospi,sp500,usdkrw",
                     "2026-10-14,90.0,2500.0,6000.0,1350.0",
                     "2026-10-15,110.0,2500.0,6000.0,1350.0"]
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**

```python
# src/agent/history/store.py
"""비공개 기록 저장소(체크아웃된 폴더)의 스냅샷 읽기·쓰기."""
import csv
import io
import json
from datetime import date
from pathlib import Path

CSV_HEADER = ["date", "total_krw", "kospi", "sp500", "usdkrw"]


class SnapshotStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.snap_dir = self.root / "snapshots"

    def _dates(self) -> list[date]:
        if not self.snap_dir.exists():
            return []
        out = []
        for p in self.snap_dir.glob("*.json"):
            try:
                out.append(date.fromisoformat(p.stem))
            except ValueError:
                continue
        return sorted(out)

    def _load(self, d: date) -> dict:
        return json.loads((self.snap_dir / f"{d.isoformat()}.json").read_text(encoding="utf-8"))

    def latest_before(self, d: date) -> dict | None:
        earlier = [x for x in self._dates() if x < d]
        return self._load(earlier[-1]) if earlier else None

    def on_or_before(self, d: date) -> dict | None:
        earlier = [x for x in self._dates() if x <= d]
        return self._load(earlier[-1]) if earlier else None

    def between(self, start: date, end: date) -> list[dict]:
        return [self._load(x) for x in self._dates() if start <= x <= end]

    def save(self, snapshot: dict) -> None:
        self.snap_dir.mkdir(parents=True, exist_ok=True)
        (self.snap_dir / f"{snapshot['date']}.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
        self._update_csv(snapshot)

    def _update_csv(self, snapshot: dict) -> None:
        path = self.root / "history" / "portfolio.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = {}
        if path.exists():
            for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))):
                rows[row["date"]] = row
        idx = snapshot.get("market", {}).get("indices", {})
        rows[snapshot["date"]] = {
            "date": snapshot["date"], "total_krw": snapshot.get("portfolio", {}).get("total_krw"),
            "kospi": idx.get("KOSPI"), "sp500": idx.get("S&P500"),
            "usdkrw": snapshot.get("market", {}).get("fx_usdkrw")}
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_HEADER, lineterminator="\n")
        writer.writeheader()
        for d in sorted(rows):
            writer.writerow(rows[d])
        path.write_text(buf.getvalue(), encoding="utf-8")
```

- [ ] **Step 4: 통과 확인** — 3 passed
- [ ] **Step 5: Commit** — `feat: 스냅샷 저장소(조회·저장·평가금액 이력)`

---

### Task 4: 알림 감지

**Files:** Create `src/agent/analysis/alerts.py` · Test `tests/test_alerts.py`

**Interfaces — Consumes:** `holding_levels`, `LEVEL_KEYS` (Task 2), `Alert` (Task 1), `SIGNAL_LABELS` (`report/render.py`) · **Produces:** `detect_alerts(prev: dict | None, ctx: Context, settings: Settings) -> list[Alert]`

- [ ] **Step 1: 실패하는 테스트**

```python
# tests/test_alerts.py
from factories import sample_context

from agent.analysis.alerts import detect_alerts
from agent.config import Settings
from agent.history.snapshot import make_snapshot
from agent.report.schema import Disclosure


def prev_from(ctx, **changes):
    """sample_context를 어제 스냅샷으로 바꾸고 첫 종목 값을 덮어쓴다."""
    snap = make_snapshot(ctx)
    snap["date"] = "2026-10-14"
    snap["holdings"][0].update(changes)
    return snap


def kinds(alerts):
    return [a.kind for a in alerts]


def test_no_prev_snapshot_means_no_alerts():
    assert detect_alerts(None, sample_context(), Settings()) == []


def test_nothing_changed():
    ctx = sample_context()
    assert detect_alerts(prev_from(ctx), ctx, Settings()) == []


def test_signal_change():
    ctx = sample_context()
    alerts = detect_alerts(prev_from(ctx, signal="add"), ctx, Settings())
    assert kinds(alerts) == ["signal_change"] and "추가매수 → 보유" in alerts[0].message


def test_level_cross_down_and_big_move_with_base_date():
    ctx = sample_context()                       # 오늘 65,000원, 재검토 기준가 60,350원
    ctx.holdings[0].price.close = 59000
    alerts = detect_alerts(prev_from(ctx, close=66000), ctx, Settings())
    assert set(kinds(alerts)) == {"level_cross", "big_move"}
    cross = next(a for a in alerts if a.kind == "level_cross")
    assert "재검토 기준가(60,350원) 아래로" in cross.message and cross.important
    move = next(a for a in alerts if a.kind == "big_move")
    assert "-10.6%" in move.message and "2026-10-14" in move.message


def test_level_cross_up():
    ctx = sample_context()
    ctx.holdings[0].price.close = 85000             # 일부매도 1차 84,553원 위로
    alerts = detect_alerts(prev_from(ctx, close=84000), ctx, Settings())
    assert kinds(alerts) == ["level_cross"] and "일부매도 1차(84,553원) 위로" in alerts[0].message


def test_small_move_below_threshold_ignored():
    ctx = sample_context()
    assert detect_alerts(prev_from(ctx, close=63000), ctx, Settings()) == []   # +3.2%


def test_new_disclosure_only():
    ctx = sample_context()
    old = Disclosure(date="2026-10-13", title="옛 공시", category="other", negative=False, url="u1")
    new = Disclosure(date="2026-10-15", title="유상증자결정", category="rights_issue", negative=True, url="u2")
    ctx.holdings[0].disclosures = [old, new]
    alerts = detect_alerts(prev_from(ctx, disclosures=["u1"]), ctx, Settings())
    assert kinds(alerts) == ["disclosure"] and "유상증자결정" in alerts[0].message and alerts[0].important


def test_nps_new_filing():
    ctx = sample_context()
    ctx.holdings[0].nps = {"stake_pct": 7.5, "change_pct": -0.1, "date": "2026-10-15"}
    alerts = detect_alerts(prev_from(ctx, nps_date="2026-09-30"), ctx, Settings())
    assert kinds(alerts) == ["nps"] and "7.50%" in alerts[0].message and "-0.10%p" in alerts[0].message


def test_earnings_soon_only_once_per_date():
    ctx = sample_context()                     # 오늘 2026-10-15
    ctx.holdings[1].next_earnings = "2026-10-17"
    prev = prev_from(ctx)
    prev["holdings"][1]["next_earnings"] = None
    assert kinds(detect_alerts(prev, ctx, Settings())) == ["earnings_soon"]
    prev["holdings"][1]["next_earnings"] = "2026-10-17"    # 어제(10-14)도 D-3 안이었다
    assert detect_alerts(prev, ctx, Settings()) == []


def test_new_holding_has_no_comparison_alerts():
    ctx = sample_context()
    prev = prev_from(ctx)
    prev["holdings"] = prev["holdings"][1:]     # 어제는 첫 종목이 없었다
    assert detect_alerts(prev, ctx, Settings()) == []
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**

```python
# src/agent/analysis/alerts.py
"""직전 스냅샷 대비 의미 있는 변화 → 알림. 문구와 숫자는 여기서 만든다(AI는 해설만)."""
from datetime import date

from agent.config import Settings
from agent.history.snapshot import LEVEL_KEYS, holding_levels
from agent.report.schema import Alert, Context

SIGNAL_LABELS = {"add": "추가매수", "hold": "보유", "trim": "일부매도", "review": "재검토"}
IMPORTANT_LEVELS = {"review", "buy1", "sell1"}
EARNINGS_WINDOW_DAYS = 3


def _money(value: float, market: str) -> str:
    return f"${value:,.2f}" if market == "US" else f"{value:,.0f}원"


def _crossed(before: float, after: float, level: float) -> bool:
    return before > level >= after or before < level <= after


def _days_until(target: str | None, today: date) -> int | None:
    return None if not target else (date.fromisoformat(target) - today).days


def detect_alerts(prev: dict | None, ctx: Context, settings: Settings) -> list[Alert]:
    if prev is None:
        return []
    today = date.fromisoformat(ctx.date)
    prev_date = prev["date"]
    prev_by = {(p["market"], p["ticker"]): p for p in prev.get("holdings", [])}
    alerts: list[Alert] = []

    for h in ctx.holdings:
        def add(kind, message, important=False):
            alerts.append(Alert(kind=kind, ticker=h.ticker, name=h.name, market=h.market, message=message,
                                important=important))

        p = prev_by.get((h.market, h.ticker))
        close = h.price.close if h.price else None
        if p is not None:
            if h.signal and p.get("signal") and h.signal != p["signal"]:
                add("signal_change", f"{h.name}: {SIGNAL_LABELS[p['signal']]} → {SIGNAL_LABELS[h.signal]}",
                    important=h.signal != "hold")
            before = p.get("close")
            if close and before:
                levels = holding_levels(h)
                for key, label in LEVEL_KEYS:
                    level = levels.get(key)
                    if level and _crossed(before, close, level):
                        direction = "아래로 내려왔어요" if close < level else "위로 올라섰어요"
                        add("level_cross", f"{h.name} 현재가 {_money(close, h.market)} — "
                                           f"{label}({_money(level, h.market)}) {direction}",
                            important=key in IMPORTANT_LEVELS)
                change = (close / before - 1) * 100
                if abs(change) >= settings.alert_move_pct:
                    add("big_move", f"{h.name} {change:+.1f}% ({prev_date} 대비, {_money(before, h.market)} → "
                                    f"{_money(close, h.market)})", important=True)
            known = set(p.get("disclosures", []))
            for d in h.disclosures:
                if d.url not in known:
                    add("disclosure", f"{h.name} 공시: {d.title} ({d.date})", important=d.negative)
            nps_date = (h.nps or {}).get("date")
            if h.nps and nps_date and nps_date > (p.get("nps_date") or ""):
                change_txt = (f" ({h.nps['change_pct']:+.2f}%p)" if h.nps.get("change_pct") is not None else "")
                add("nps", f"국민연금 {h.name} 지분 {h.nps['stake_pct']:.2f}%{change_txt} · {nps_date} 신고")

        days = _days_until(h.next_earnings, today)
        if days is not None and 0 <= days <= EARNINGS_WINDOW_DAYS:
            prev_days = _days_until(p.get("next_earnings"), date.fromisoformat(prev_date)) if p else None
            already = (p is not None and p.get("next_earnings") == h.next_earnings
                       and prev_days is not None and 0 <= prev_days <= EARNINGS_WINDOW_DAYS)
            if not already:
                add("earnings_soon", f"{h.name} 실적 발표 {'오늘' if days == 0 else f'D-{days}'} ({h.next_earnings})")
    return alerts
```

주의: `test_new_holding_has_no_comparison_alerts`에서 첫 종목은 p가 없고 next_earnings도 없으므로 알림 0. `prev_from`은 오늘 context로 스냅샷을 만드므로 공시·국민연금 날짜가 같아 기본은 알림 0.

- [ ] **Step 4: 통과 확인** — 10 passed
- [ ] **Step 5: Commit** — `feat: 직전 스냅샷 대비 알림 6종 감지`

---

### Task 5: 주간 비교와 메일 종류 결정

**Files:** Create `src/agent/analysis/weekly.py` · Test `tests/test_weekly.py`

**Interfaces — Produces:** `weekly_diff(prev: dict | None, ctx: Context, week_alerts: list[Alert]) -> WeeklyDiff | None`, `decide_report_type(today: date, prev: dict | None, alerts: list[Alert]) -> ReportType`

- [ ] **Step 1: 실패하는 테스트**

```python
# tests/test_weekly.py
from datetime import date

import pytest
from factories import sample_context

from agent.analysis.weekly import decide_report_type, weekly_diff
from agent.history.snapshot import make_snapshot
from agent.report.schema import Alert

ALERT = Alert(kind="big_move", ticker="005930", name="삼성전자", market="KR", message="m")


@pytest.mark.parametrize("today, prev, alerts, expected", [
    (date(2026, 10, 19), None, [], "weekly"),        # 월요일은 항상 주간
    (date(2026, 10, 19), {}, [ALERT], "weekly"),
    (date(2026, 10, 20), {}, [ALERT], "alert"),      # 화요일 + 알림
    (date(2026, 10, 20), {}, [], "none"),            # 화요일 + 알림 없음
    (date(2026, 10, 20), None, [], "none"),          # 첫 실행
])
def test_decide_report_type(today, prev, alerts, expected):
    assert decide_report_type(today, prev, alerts) == expected


def test_weekly_diff():
    ctx = sample_context()                                   # 삼성전자 65,000원, AAPL $230.50
    prev = make_snapshot(ctx)
    prev["date"] = "2026-10-08"
    prev["holdings"][0].update(close=60000, signal="add", weight_pct=7.0)
    prev["holdings"] = [prev["holdings"][0], {"ticker": "OLD", "name": "옛종목", "market": "US", "close": 10.0,
                                              "signal": None, "weight_pct": 1.0}]  # AAPL은 신규, OLD는 매도
    prev["portfolio"]["total_krw"] = 7_500_000
    prev["market"]["indices"]["KOSPI"] = 2400.0
    d = weekly_diff(prev, ctx, [ALERT])
    assert d.since == "2026-10-08"
    by = {h.ticker: h for h in d.holdings}
    assert by["005930"].status == "held" and by["005930"].return_pct == pytest.approx(65000 / 60000 * 100 - 100)
    assert (by["005930"].prev_signal, by["005930"].signal) == ("add", "hold")
    assert by["AAPL"].status == "new" and by["OLD"].status == "sold"
    assert d.total_change_pct == pytest.approx(8_000_000 / 7_500_000 * 100 - 100)
    assert d.index_changes["KOSPI"] == pytest.approx(2500 / 2400 * 100 - 100)
    assert d.alerts == [ALERT]


def test_weekly_diff_without_prev():
    assert weekly_diff(None, sample_context(), []) is None
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**

```python
# src/agent/analysis/weekly.py
"""주간 리포트의 '지난주 대비'와 메일 종류 결정."""
from datetime import date

from agent.report.schema import Alert, Context, ReportType, WeeklyDiff, WeeklyHolding


def decide_report_type(today: date, prev: dict | None, alerts: list[Alert]) -> ReportType:
    if today.weekday() == 0:
        return "weekly"
    if prev is None or not alerts:
        return "none"
    return "alert"


def _pct(now, before):
    return (now / before - 1) * 100 if now is not None and before else None


def weekly_diff(prev: dict | None, ctx: Context, week_alerts: list[Alert]) -> WeeklyDiff | None:
    if prev is None:
        return None
    prev_by = {(p["market"], p["ticker"]): p for p in prev.get("holdings", [])}
    rows, seen = [], set()
    for h in ctx.holdings:
        key = (h.market, h.ticker)
        seen.add(key)
        p = prev_by.get(key)
        close = h.price.close if h.price else None
        rows.append(WeeklyHolding(
            ticker=h.ticker, name=h.name, market=h.market, status="held" if p else "new",
            close=close, prev_close=p.get("close") if p else None,
            return_pct=_pct(close, p.get("close")) if p else None,
            signal=h.signal, prev_signal=p.get("signal") if p else None,
            weight_pct=h.position.weight_pct, prev_weight_pct=p.get("weight_pct") if p else None))
    for key, p in prev_by.items():
        if key not in seen:
            rows.append(WeeklyHolding(ticker=p["ticker"], name=p["name"], market=p["market"], status="sold",
                                      prev_close=p.get("close"), prev_signal=p.get("signal"),
                                      prev_weight_pct=p.get("weight_pct")))
    prev_total = prev.get("portfolio", {}).get("total_krw")
    prev_classes = prev.get("portfolio", {}).get("by_class", {})
    prev_idx = prev.get("market", {}).get("indices", {})
    return WeeklyDiff(
        since=prev["date"], holdings=rows,
        total_krw=ctx.portfolio.total_krw, prev_total_krw=prev_total,
        total_change_pct=_pct(ctx.portfolio.total_krw, prev_total),
        class_changes={k: {"pct": w.pct, "prev_pct": prev_classes.get(k)} for k, w in ctx.portfolio.by_class.items()},
        index_changes={k: c for k, q in ctx.market.indices.items()
                       if (c := _pct(q.close, prev_idx.get(k))) is not None},
        alerts=week_alerts)
```

- [ ] **Step 4: 통과 확인** — 7 passed
- [ ] **Step 5: Commit** — `feat: 주간 비교와 메일 종류 결정`

---

### Task 6: CLI 연결 (collect·publish·save-snapshot) + 미국 실적일

**Files:** Modify `src/agent/__main__.py`, `src/agent/collectors/us_fundamentals.py`, `src/agent/report/context.py`, `tests/factories.py` · Test `tests/test_cli_history.py`, `tests/test_us_fundamentals.py`

**Interfaces — Consumes:** Task 2~5 · **Produces:** `apply_history(context, settings, store: SnapshotStore | None, today: date) -> None` (alerts·report_type·weekly 채움, 저장소 오류 시 첫 실행처럼), CLI `collect --history-dir DIR`, `publish`(none이면 생략, 제목 분기), `save-snapshot --history-dir DIR`; `UsFundamentalData.next_earnings: str | None`

- [ ] **Step 1: 실패하는 테스트**

```python
# tests/test_cli_history.py
import json
from datetime import date

from factories import sample_context

import agent.__main__ as cli
from agent.config import Settings
from agent.history.snapshot import make_snapshot
from agent.history.store import SnapshotStore


def seeded_store(tmp_path, close):
    store = SnapshotStore(tmp_path / "data")
    snap = make_snapshot(sample_context())
    snap["date"] = "2026-10-14"
    snap["holdings"][0]["close"] = close
    store.save(snap)
    return store


def test_apply_history_alert_day(tmp_path):
    ctx = sample_context()                                   # 2026-10-15 (목)
    cli.apply_history(ctx, Settings(), seeded_store(tmp_path, close=70000), date(2026, 10, 15))
    assert ctx.report_type == "alert" and [a.kind for a in ctx.alerts] == ["big_move"]


def test_apply_history_quiet_day(tmp_path):
    ctx = sample_context()
    cli.apply_history(ctx, Settings(), seeded_store(tmp_path, close=65000), date(2026, 10, 15))
    assert ctx.report_type == "none" and ctx.alerts == []


def test_apply_history_monday_weekly(tmp_path):
    ctx = sample_context()
    cli.apply_history(ctx, Settings(), seeded_store(tmp_path, close=60000), date(2026, 10, 19))
    assert ctx.report_type == "weekly" and ctx.weekly.since == "2026-10-14"


def test_apply_history_store_error_treated_as_first_run(tmp_path):
    class Broken:
        def latest_before(self, d):
            raise OSError("checkout failed")

    ctx = sample_context()
    cli.apply_history(ctx, Settings(), Broken(), date(2026, 10, 15))
    assert ctx.report_type == "none"


def setup_dirs(tmp_path, report_type):
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.yaml").write_text("profile:\n  name: balanced\n", encoding="utf-8")
    day = tmp_path / "out" / "2026-10-15"
    day.mkdir(parents=True)
    ctx = sample_context()
    ctx.report_type = report_type
    (day / "context.json").write_text(ctx.model_dump_json(), encoding="utf-8")
    return config, day


def publish_args(tmp_path, config, *extra):
    return [*extra, "--date", "2026-10-15", "--out", str(tmp_path / "out"), "--config-dir", str(config)]


def test_publish_skips_when_nothing_to_report(tmp_path, monkeypatch):
    config, day = setup_dirs(tmp_path, "none")
    monkeypatch.setattr(cli, "send_email", lambda *a: (_ for _ in ()).throw(AssertionError("발송 금지")))
    cli.main(publish_args(tmp_path, config, "publish"))
    assert not (day / "preview.html").exists()


def test_publish_subjects(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(cli, "send_email", lambda subject, html: sent.append(subject))
    config, _ = setup_dirs(tmp_path, "alert")
    cli.main(publish_args(tmp_path, config, "publish"))
    assert sent == ["[투자 알림] 2026-10-15"]


def test_save_snapshot(tmp_path):
    config, _ = setup_dirs(tmp_path, "alert")
    cli.main(publish_args(tmp_path, config, "save-snapshot", "--history-dir", str(tmp_path / "data")))
    saved = json.loads((tmp_path / "data" / "snapshots" / "2026-10-15.json").read_text(encoding="utf-8"))
    assert saved["date"] == "2026-10-15"
```

`tests/test_us_fundamentals.py`에 추가:

```python
def test_next_earnings_from_calendar():
    t = FakeTicker()
    t.calendar = {"Earnings Date": [date(2026, 10, 20), date(2026, 10, 24)]}
    assert load(t).next_earnings == "2026-10-20"
    t.calendar = {"Earnings Date": [date(2026, 7, 1)]}      # 지난 날짜만 있으면 없음
    assert load(t).next_earnings is None
```

(`FakeTicker`에 `self.calendar = {}` 기본값 추가)

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**

`us_fundamentals.py`: `UsFundamentalData`에 `next_earnings: str | None = None`; `load()` 끝에서
```python
        next_earnings = None
        try:
            dates = (t.calendar or {}).get("Earnings Date") or []
            upcoming = sorted(d for d in dates if d >= today)
            next_earnings = upcoming[0].isoformat() if upcoming else None
        except Exception:
            pass   # 실적 일정은 선택 정보
```
를 계산해 `UsFundamentalData(..., next_earnings=next_earnings)`.

`context.py` `_analyze_us`: `h.next_earnings = data.next_earnings` (`_value` 호출 전).

`__main__.py`:
```python
from datetime import timedelta
from agent.analysis.alerts import detect_alerts
from agent.analysis.weekly import decide_report_type, weekly_diff
from agent.history.snapshot import make_snapshot
from agent.history.store import SnapshotStore
from agent.report.schema import Alert


def apply_history(context: Context, settings: Settings, store, today: date) -> None:
    """직전 스냅샷과 비교해 알림·메일 종류·주간 비교를 채운다. 저장소 오류는 첫 실행처럼 처리."""
    try:
        prev = store.latest_before(today)
    except Exception as e:
        log.warning("기록 저장소 읽기 실패: %s", type(e).__name__)
        store, prev = None, None
    context.alerts = detect_alerts(prev, context, settings)
    context.report_type = decide_report_type(today, prev, context.alerts)
    if context.report_type == "weekly" and store is not None:
        week_prev = store.on_or_before(today - timedelta(days=7)) or prev
        if week_prev is not None:
            start = date.fromisoformat(week_prev["date"]) + timedelta(days=1)
            week_alerts = [Alert(**a) for s in store.between(start, today - timedelta(days=1))
                           for a in s.get("alerts", [])] + context.alerts
            context.weekly = weekly_diff(week_prev, context, week_alerts)
    log.info("메일 종류: %s (알림 %d건)", context.report_type, len(context.alerts))
```
- `cmd_collect`: build_context 뒤 `if args.history_dir: apply_history(context, settings, SnapshotStore(args.history_dir), args.date)`
- `cmd_publish`: context 읽은 직후 `if context.report_type == "none": log.info("변화 없음 — 메일 생략"); return None`. 제목: `alert` → `f"[투자 알림] {context.date}"`, 그 외 `f"{settings.report_subject_prefix} {context.date}"`.
- `cmd_save_snapshot(args)`: `if not args.history_dir: raise SystemExit("--history-dir 필요")`; context 읽어 `SnapshotStore(args.history_dir).save(make_snapshot(context))`; `log.info("스냅샷 저장")`.
- parser: `choices`에 `"save-snapshot"`, `parser.add_argument("--history-dir", type=Path, default=None)`, commands dict에 추가.
- `tests/factories.py` `FakeUs`는 next_earnings 기본 None이므로 변경 불필요.

- [ ] **Step 4: 통과 확인** — `uv run pytest -q -p no:warnings` 전체 통과
- [ ] **Step 5: Commit** — `feat: collect·publish·save-snapshot에 기록 비교 연결, 미국 실적 발표일`

---

### Task 7: 검증기 alert 모드

**Files:** Modify `src/agent/report/validate.py` · Test `tests/test_validate.py`

**Interfaces — Consumes:** `Context.report_type/alerts`, `Analysis.alert_comments`

- [ ] **Step 1: 실패하는 테스트** (`tests/test_validate.py`에 추가)

```python
def alert_context():
    from agent.report.schema import Alert
    ctx = sample_context()
    ctx.report_type = "alert"
    ctx.alerts = [Alert(kind="big_move", ticker="005930", name="삼성전자", market="KR",
                        message="삼성전자 -6.2% (2026-10-14 대비, 69,300원 → 65,000원)", important=True)]
    return ctx


def test_alert_mode_allows_empty_holdings_and_checks_comments():
    raw = {"date": "2026-10-15", "summary": ["삼성전자가 크게 내렸어요"],
           "alert_comments": {"005930": "하루에 -6.2% 내려 69,300원에서 65,000원이 됐어요."}}
    assert validate_analysis(raw, alert_context())[1] == []          # 알림 문구 숫자 허용


def test_alert_comment_fabricated_number_rejected():
    raw = {"date": "2026-10-15", "summary": ["x"], "alert_comments": {"005930": "목표가 99,000원"}}
    assert any("99,000원" in e for e in validate_analysis(raw, alert_context())[1])


def test_alert_comment_for_unknown_ticker_rejected():
    raw = {"date": "2026-10-15", "summary": ["x"], "alert_comments": {"ZZZZ": "설명"}}
    assert any("ZZZZ" in e for e in validate_analysis(raw, alert_context())[1])
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** (`validate_analysis` 수정)
  - 종목 집합 검사: `if not (context.report_type == "alert" and not analysis.holdings):` 일 때만 기존 집합 비교 수행
  - `alert_numbers = [n for a in context.alerts for n in _text_numbers(a.message)]`, `_text_numbers(text)`는 `re.findall(r"-?\d[\d,]*(?:\.\d+)?", text)` → float 리스트
  - `everything`에 `alert_numbers` 추가
  - `alert_tickers = {a.ticker for a in context.alerts}`; `alert_comments`의 키가 그 집합에 없으면 `f"알림에 없는 종목 해설: {ticker}"`
  - 각 `alert_comments[ticker]` 문장은 `shared + per_holding[ticker] + alert_numbers` 범위로 숫자 검사
- [ ] **Step 4: 통과 확인** — 전체 통과
- [ ] **Step 5: Commit** — `feat: 검증기 알림 모드(alert_comments·알림 문구 숫자)`

---

### Task 8: 알림 메일·주간 섹션 렌더링

**Files:** Create `src/agent/report/templates/alert.html` · Modify `render.py`, `templates/email.html` · Test `tests/test_render.py`

**Interfaces — Produces:** `render_report`가 `context.report_type == "alert"`이면 `alert.html`, 아니면 `email.html`(주간 섹션 포함)

- [ ] **Step 1: 실패하는 테스트** (`tests/test_render.py`에 추가)

```python
def test_alert_mail_shows_only_alerts_and_comments():
    from agent.report.schema import Alert
    ctx = sample_context()
    ctx.report_type = "alert"
    ctx.alerts = [Alert(kind="level_cross", ticker="005930", name="삼성전자", market="KR",
                        message="삼성전자 현재가 65,000원 — 재검토 기준가(60,350원) 아래로 내려왔어요", important=True)]
    a = Analysis(date="2026-10-15", summary=["재검토 알림 1건"], alert_comments={"005930": "처음 산 이유를 점검해 보세요."})
    html = render_report(ctx, a, [])
    assert "투자 알림" in html and "재검토 기준가(60,350원)" in html and "처음 산 이유를 점검" in html
    assert "용어 풀이" not in html and "Apple" not in html     # 알림 없는 종목·긴 섹션은 없음


def test_weekly_section():
    from agent.report.schema import WeeklyDiff, WeeklyHolding
    ctx = sample_context()
    ctx.weekly = WeeklyDiff(since="2026-10-08", total_krw=8_000_000, prev_total_krw=7_500_000, total_change_pct=6.67,
                            index_changes={"KOSPI": 4.17},
                            holdings=[WeeklyHolding(ticker="005930", name="삼성전자", market="KR", status="held",
                                                    close=65000, prev_close=60000, return_pct=8.33,
                                                    signal="hold", prev_signal="add", weight_pct=8.2, prev_weight_pct=7.0),
                                      WeeklyHolding(ticker="OLD", name="옛종목", market="US", status="sold")])
    html = render_report(ctx, None, [])
    assert "지난주 대비" in html and "+8.3%" in html and "추가매수 → 보유" in html and "전량 매도" in html
    assert "+6.7%" in html
```

- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**
  - `render.py`: 템플릿 이름 `"alert.html" if context.report_type == "alert" else "email.html"`, 제목 `"투자 알림 {date}"` / `"투자 리포트 {date}"`(주간이면 `"주간 투자 리포트 {date}"` when `context.weekly`), `alerts_by_ticker`(순서 유지 dict) 전달, `auto_summary`는 alert이면 `[f"알림 {n}건 (중요 {k}건)"]`.
  - `alert.html`: email.html과 같은 H2/TH/TD/badge 매크로. 제목·요약 → 종목별 카드(이름, 현재 판단 배지, 알림 문구 목록 — 중요는 빨간 "중요" 배지, AI 해설 문단) → 실행 메모·면책. 종목 카드는 알림이 있는 종목만.
  - `email.html`: "한눈에 보기" 다음에 `{% if context.weekly %}` "지난주 대비 ({{ since }} 이후)" 섹션 — 총평가액 변화(`%+.1f%`), 지수 변화, 표(종목 | 1주 수익률 | 신호 변화(`이전 → 현재`, 같으면 `-`) | 비중 변화), status `new`→"신규 편입", `sold`→"전량 매도", 그 주 알림 목록(최대 15개).
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: Commit** — `feat: 알림 메일 템플릿과 주간 리포트 '지난주 대비' 섹션`

---

### Task 9: AI 작성 지침

**Files:** Modify `prompts/analysis-guide.md`, `prompts/daily-prompt.md`

- [ ] **Step 1**: `analysis-guide.md`에 "메일 종류별 작성" 절 추가 — context의 `report_type`이 `alert`면: `holdings`는 빈 배열, `summary` 1~2줄(가장 중요한 알림), `alert_comments`에 알림이 있는 종목마다 한두 문장(알림 문구의 숫자 그대로 인용 가능, 장기투자 관점으로 차분하게, 큰 하락은 "재검토 = 바로 매도 아님" 원칙 유지). `weekly`면 기존 규칙 + `context.weekly`가 있으면 summary 첫 줄에 지난주 대비 총평가액 변화와 가장 큰 변화 하나.
- [ ] **Step 2**: `daily-prompt.md` 1번에 "context.json의 report_type을 먼저 확인합니다" 추가.
- [ ] **Step 3**: `uv run pytest tests/test_sample.py -q`로 샘플 검증 유지 확인
- [ ] **Step 4: Commit** — `docs: 알림·주간 모드 AI 작성 지침`

---

### Task 10: 기록 저장소와 워크플로

**Files:** Modify `.github/workflows/daily-report.yml`, `docs/setup-github-actions.md`, `README.md` · Test `tests/test_workflows.py`

- [ ] **Step 1: 기록 저장소 만들기 (운영 작업)**
```bash
gh repo create JoowonMun/trading-ai-agent-data --private --description "trading-ai-agent 일일 스냅샷 (비공개)"
ssh-keygen -t ed25519 -N "" -C "trading-ai-agent actions" -f <scratchpad>/data_deploy_key
gh repo deploy-key add <scratchpad>/data_deploy_key.pub --repo JoowonMun/trading-ai-agent-data --allow-write --title actions
gh secret set DATA_REPO_DEPLOY_KEY --repo JoowonMun/trading-ai-agent < <scratchpad>/data_deploy_key
rm <scratchpad>/data_deploy_key*
```
초기 커밋: README 한 줄(`snapshots/`, `history/` 설명)을 넣어 main 브랜치 생성.

- [ ] **Step 2: 실패하는 테스트** (`tests/test_workflows.py`에 추가)
```python
def test_daily_report_uses_history_repo_and_skips_quiet_days():
    text = Path(".github/workflows/daily-report.yml").read_text(encoding="utf-8")
    assert "repository: JoowonMun/trading-ai-agent-data" in text and "DATA_REPO_DEPLOY_KEY" in text
    assert "--history-dir data" in text and "save-snapshot" in text
    assert "REPORT_TYPE" in text
```
- [ ] **Step 3: 워크플로 수정**
  - checkout 다음: `actions/checkout@v4`로 `repository: JoowonMun/trading-ai-agent-data`, `path: data`, `ssh-key: ${{ secrets.DATA_REPO_DEPLOY_KEY }}`, `continue-on-error: true`(실패 시 첫 실행처럼)
  - collect에 `--history-dir data`, 이후 `echo "REPORT_TYPE=$(uv run python -c "import json; print(json.load(open('out/$REPORT_DATE/context.json', encoding='utf-8'))['report_type'])")" >> "$GITHUB_ENV"`, 로그에 `메일 종류: $REPORT_TYPE`
  - AI 해설 단계: `if: env.REPORT_TYPE != 'none'`
  - 발송 단계는 그대로(publish가 none이면 알아서 생략) — 로그 "발송 완료" 대신 none이면 "변화 없음 — 발송 생략"
  - 마지막 단계 "스냅샷 저장": `if: inputs.dry_run != true` 에서 `uv run python -m agent save-snapshot --history-dir data --date "$REPORT_DATE"` 후 `cd data && git config user.name "trading-ai-agent" && git config user.email "actions@users.noreply.github.com" && git add -A && (git diff --cached --quiet || git commit -qm "snapshot $REPORT_DATE") && git push -q`
- [ ] **Step 4: 통과 확인** — `uv run pytest -q -p no:warnings`
- [ ] **Step 5: 문서** — `docs/setup-github-actions.md`에 기록 저장소·알림 규칙, README "무엇을 해 주나"에 알림/주간 행 추가
- [ ] **Step 6: Commit·Push** — `feat: 기록 저장소 연동, 알림 없는 날 AI·발송 생략`
- [ ] **Step 7: 검증 실행** — `gh workflow run daily-report.yml -f dry_run=true` → 로그에 `메일 종류:` 표시·저장 단계 생략 확인. 이어서 dry_run 없이 1회 실행 → 기록 저장소에 오늘 스냅샷 커밋 확인 (첫 실행: 월요일이 아니면 none → 메일 없음)
