"""context.json(코드→AI)과 analysis.json(AI→코드)의 데이터 모델."""
from typing import Literal

from pydantic import BaseModel, Field

from agent.config import Profile

Signal = Literal["add", "hold", "trim", "review"]


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


class Context(BaseModel):
    date: str
    profile: Profile
    market: Market
    holdings: list[HoldingContext]
    portfolio: Portfolio
    nps_changes: list[dict] = []
    nps_annual_as_of: str | None = None
    watchlist: list[dict] = []
    glossary_terms: list[str] = []
    notes: list[str] = []


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
    holdings: list[HoldingAnalysis]
    portfolio_comment: str = ""
    watchlist_comment: str = ""
