"""context.json(코드→AI)과 analysis.json(AI→코드)의 데이터 모델."""
from typing import Literal

from pydantic import BaseModel, Field

from agent.config import Profile

Signal = Literal["add", "hold", "trim", "review"]
AlertKind = Literal["signal_change", "level_cross", "big_move", "disclosure", "nps", "earnings_soon"]
ReportType = Literal["weekly", "alert", "none"]


class Alert(BaseModel):
    kind: AlertKind
    ticker: str
    name: str
    market: Literal["KR", "US"]
    message: str
    important: bool = False
    values: list[float] = []  # 문구에 들어간 숫자(가격·등락률 등) — 검증기가 AI 해설의 근거로 쓴다


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


class PriceSnapshot(BaseModel):
    close: float
    price_date: str
    ma20: float | None = None
    ma60: float | None = None
    ma120: float | None = None
    rsi14: float | None = None
    pos_52w_pct: float | None = None


class Fundamentals(BaseModel):
    per: float | None = None
    pbr: float | None = None
    roe: float | None = None
    op_margin: float | None = None
    rev_yoy: float | None = None
    op_yoy: float | None = None
    debt_ratio: float | None = None
    div_yield: float | None = None
    ttm_net_income: float | None = None
    latest_quarter: str | None = None


class Band(BaseModel):
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float


class Valuation(BaseModel):
    method: Literal["PER", "PBR"]
    insufficient: bool
    current_multiple: float | None = None
    band: Band | None = None
    fair: float | None = None
    buy: list[float] = []
    sell: list[float] = []
    review: float | None = None
    distorted: bool = False  # 적정가가 현재가의 2배 초과 또는 절반 미만 → 밴드가 현실과 동떨어졌을 가능성
    note: str | None = None


class PositionInfo(BaseModel):
    qty: float
    avg_price: float
    weight_pct: float | None = None


class Disclosure(BaseModel):
    date: str
    title: str
    category: str
    negative: bool
    url: str


class Flows(BaseModel):
    foreign_5d_krw: float | None = None
    institution_5d_krw: float | None = None


class HoldingContext(BaseModel):
    ticker: str
    name: str
    market: Literal["KR", "US"]
    asset_class: str
    position: PositionInfo
    price: PriceSnapshot | None = None
    fundamentals: Fundamentals | None = None
    valuation: Valuation | None = None
    financial_sector: bool = False
    assessments: dict[str, Literal["good", "neutral", "caution"] | None] = {}
    signal: Signal | None = None
    signal_reasons: list[str] = []
    nps: dict | None = None
    disclosures: list[Disclosure] = []
    flows: Flows | None = None
    next_earnings: str | None = None  # 미국 종목 다음 실적 발표일 (YYYY-MM-DD)
    missing: list[str] = []


class IndexQuote(BaseModel):
    close: float
    change_pct: float | None = None


class Market(BaseModel):
    indices: dict[str, IndexQuote] = {}
    fx_usdkrw: float | None = None
    missing: list[str] = []


class ClassWeight(BaseModel):
    label: str
    value_krw: float
    pct: float
    target_pct: float
    diff_pct: float


class Rebalance(BaseModel):
    asset_class: str
    label: str
    action: Literal["늘리기", "줄이기"]
    amount_krw: float


class Portfolio(BaseModel):
    total_krw: float
    cash_krw: float
    by_class: dict[str, ClassWeight] = {}
    rebalance: list[Rebalance] = []
    warnings: list[str] = []
    weights: dict[str, float] = {}
    nps_overlap: list[str] = []


class SectorRow(BaseModel):
    """업종 온도계 한 줄 (코드가 계산)."""
    key: str  # "KR:1018" / "US:XLK"
    name: str
    market: Literal["KR", "US"]
    method: Literal["PER", "PBR"]
    value: float | None = None
    percentile: float | None = None  # 과거 값 중 지금 위치 (0=가장 쌈, 100=가장 비쌈)
    level: Literal["싸요", "보통", "비싸요"] | None = None
    close: float | None = None
    earnings_3m_pct: float | None = None
    earnings_1y_pct: float | None = None
    drawdown_52w_pct: float | None = None
    return_3m_pct: float | None = None
    history_weeks: int = 0
    note: str = ""


class QuietSignal(BaseModel):
    """조용한 신호: 큰 뉴스가 되기 전 회사가 공시한 일 (코드가 고름)."""
    ticker: str
    name: str
    kind: Literal["contract", "facility", "buyback", "rights_issue"]
    title: str
    date: str
    url: str
    group: Literal["holding", "promising", "large"]
    sector: str | None = None
    why: str
    caution: bool = False


class Candidate(BaseModel):
    """살펴볼 곳 후보 회사 (코드가 고름): 시총 상위 300 · 흑자 · 업종 중간값보다 쌈."""
    ticker: str
    name: str
    sector: str
    method: Literal["PER", "PBR"]
    value: float
    sector_median: float
    held: bool = False


class NewsItem(BaseModel):
    title: str
    source: str
    date: str
    url: str


class NewsGroup(BaseModel):
    kind: Literal["sector", "theme"]
    name: str
    query: str
    items: list[NewsItem] = []


class NewsReport(BaseModel):
    """읽어볼 뉴스 (월요일). 웹에서 온 글이라 해설 AI가 읽는 Context가 아니라 news.json에 따로 둔다."""
    groups: list[NewsGroup] = []
    missing: list[str] = []


class Context(BaseModel):
    date: str
    profile: Profile
    market: Market
    holdings: list[HoldingContext]
    portfolio: Portfolio
    nps_changes: list[dict] = []
    nps_annual_as_of: str | None = None
    nps_us: dict | None = None  # 국민연금 미국 보유 13F 요약
    watchlist: list[dict] = []
    glossary_terms: list[str] = []
    notes: list[str] = []
    report_type: ReportType = "weekly"  # weekly=전체 리포트, alert=알림 메일, none=보내지 않음
    research_targets: list[str] = []  # AI가 '왜 움직였나'를 조사할 티커 (코드가 정함)
    alerts: list[Alert] = []
    weekly: WeeklyDiff | None = None
    sectors: list[SectorRow] = []  # 업종 온도계 (월요일만)
    sectors_missing: list[str] = []
    signals: list[QuietSignal] = []  # 조용한 신호 (월요일만)
    signals_more: int = 0
    signals_missing: list[str] = []
    promising_sectors: list[str] = []


class MoveReason(BaseModel):
    found: bool
    summary: str
    sources: list[str] = []


class IndicatorNote(BaseModel):
    term: str
    value: str
    plain: str


class HoldingAnalysis(BaseModel):
    ticker: str
    signal: Signal
    signal_downgraded_reason: str | None = None
    headline: str
    reasoning: str
    indicator_notes: list[IndicatorNote] = []
    disclosure_notes: str = ""


class Analysis(BaseModel):
    date: str
    summary: list[str] = Field(min_length=1, max_length=3)
    market_comment: str = ""
    holdings: list[HoldingAnalysis] = []
    portfolio_comment: str = ""
    watchlist_comment: str = ""
    alert_comments: dict[str, str] = {}  # 알림 메일: 티커 → 한두 문장 해설
    move_reasons: dict[str, "MoveReason"] = {}  # 티커 → AI가 웹에서 찾은 변동 원인
