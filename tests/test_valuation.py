import numpy as np
import pandas as pd

from agent.analysis.financials import QuarterFigures
from agent.analysis.valuation import band_valuation, choose_method, is_financial, monthly_multiples
from agent.config import Profile


def quarters_2024_2025():
    return [QuarterFigures(y, q, 100, 10, 10, 100, 120, 50) for y in (2024, 2025) for q in (1, 2, 3, 4)]


def test_is_financial():
    assert is_financial("64110")
    assert is_financial("651")
    assert not is_financial("26410")
    assert not is_financial(None)


def test_choose_method():
    assert choose_method(False, 100) == "PER"
    assert choose_method(True, 100) == "PBR"
    assert choose_method(False, -5) == "PBR"
    assert choose_method(False, None) == "PBR"


def test_monthly_per_respects_reporting_lag():
    monthly = pd.Series(100.0, index=pd.date_range("2025-01-31", periods=6, freq="ME"))
    per = monthly_multiples(monthly, quarters_2024_2025(), shares=10, method="PER")
    # 2024Q4(12/31) 실적은 3/1부터 사용 가능 → 1·2월은 TTM 불가로 제외
    assert list(per.index.strftime("%Y-%m")) == ["2025-03", "2025-04", "2025-05", "2025-06"]
    assert per.iloc[0] == 25.0  # 100 × 10주 / TTM 40


def test_monthly_pbr():
    monthly = pd.Series(100.0, index=pd.date_range("2025-01-31", periods=6, freq="ME"))
    pbr = monthly_multiples(monthly, quarters_2024_2025(), shares=10, method="PBR")
    assert len(pbr) == 6
    assert pbr.iloc[0] == 10.0  # 100 × 10주 / 자본 100


def test_band_valuation_prices():
    multiples = pd.Series(np.arange(1, 61, dtype=float), index=pd.date_range("2021-01-31", periods=60, freq="ME"))
    v = band_valuation(multiples, "PER", current_multiple=30, close=300, avg_price=10000,
                       profile=Profile(), band_years=5, min_points=36)
    assert not v.insufficient
    assert v.fair == 305  # 중앙값 30.5배 × 주당이익 10
    assert v.buy[0] > v.buy[1] > v.buy[2]
    assert v.buy[0] < v.fair < v.sell[0] < v.sell[1]
    assert v.review == 8500
    assert v.band.p50 == 30.5


def test_band_insufficient_data_still_has_review_price():
    multiples = pd.Series(np.arange(1, 21, dtype=float), index=pd.date_range("2025-01-31", periods=20, freq="ME"))
    v = band_valuation(multiples, "PBR", current_multiple=1.0, close=100, avg_price=10000,
                       profile=Profile(), band_years=5, min_points=36)
    assert v.insufficient
    assert v.buy == [] and v.fair is None
    assert v.review == 8500
    assert "부족" in v.note


def test_band_without_current_multiple_is_insufficient():
    multiples = pd.Series(np.arange(1, 61, dtype=float), index=pd.date_range("2021-01-31", periods=60, freq="ME"))
    v = band_valuation(multiples, "PER", current_multiple=None, close=300, avg_price=None,
                       profile=Profile(), band_years=5, min_points=36)
    assert v.insufficient and v.review is None
