"""설정·보유 종목 YAML 로딩과 한국시간 날짜."""
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, field_validator, model_validator

KST = ZoneInfo("Asia/Seoul")

AssetClass = Literal["domestic", "us", "index"]


class Profile(BaseModel):
    name: str = "balanced"
    review_drawdown_pct: float = 15
    max_single_weight_pct: float = 15
    rebalance_band_pct: float = 5
    buy_tranches: Literal[3] = 3


class Settings(BaseModel):
    profile: Profile = Profile()
    target_allocation: dict[AssetClass, float] = {"domestic": 30, "us": 40, "index": 30}
    band_years: int = 5
    min_band_points: int = 36
    disclosure_days: int = 7
    report_subject_prefix: str = "[투자 리포트]"

    @model_validator(mode="after")
    def _allocation_sums_to_100(self):
        total = sum(self.target_allocation.values())
        if abs(total - 100) > 0.01:
            raise ValueError(f"target_allocation 합계가 100이 아닙니다: {total}")
        return self


class Position(BaseModel):
    ticker: str
    name: str | None = None
    qty: float
    avg_price: float

    @field_validator("ticker", mode="before")
    @classmethod
    def _ticker_must_be_string(cls, value):
        if not isinstance(value, str):
            raise ValueError(f'종목코드 {value!r}는 따옴표로 감싸야 합니다 (예: ticker: "000660")')
        return value.strip()


class Account(BaseModel):
    name: str
    broker: str
    market: Literal["KR", "US"]
    asset_class: AssetClass
    analyze: bool = True
    positions: list[Position]


class Holdings(BaseModel):
    accounts: list[Account]
    cash_krw: float = 0


def _read_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings(path: Path) -> Settings:
    return Settings.model_validate(_read_yaml(path))


def load_holdings(path: Path) -> Holdings:
    return Holdings.model_validate(_read_yaml(path))


def today_kst(now: datetime | None = None) -> date:
    now = now or datetime.now(KST)
    return now.astimezone(KST).date()
