import pytest

from agent.analysis.signals import decide_signal
from agent.config import Profile
from agent.report.schema import Band, Fundamentals, Valuation

VAL = Valuation(method="PER", insufficient=False, current_multiple=10,
                band=Band(p10=6, p25=8, p50=10, p75=12, p90=14),
                fair=100, buy=[80, 70, 60], sell=[120, 140], review=50)
GOOD = Fundamentals(op_yoy=5, debt_ratio=80)
NO_BAND = Valuation(method="PBR", insufficient=True, review=50, note="부족")


def signal(close, valuation=VAL, fundamentals=GOOD, weight=5, negative=False, financial=False):
    return decide_signal(close, valuation, fundamentals, weight, Profile(), negative, financial)[0]


@pytest.mark.parametrize("close, weight, negative, expected", [
    (75, 5, False, "add"),
    (100, 5, False, "hold"),
    (125, 5, False, "trim"),
    (100, 20, False, "trim"),
    (45, 5, False, "review"),
    (45, 20, False, "review"),   # 재검토가 일부매도보다 우선
    (100, 5, True, "review"),    # 악재 공시
    (75, 15, False, "hold"),     # 비중이 최대치와 같으면 추가매수 불가, 초과는 아니라 일부매도도 아님
])
def test_signal_rules(close, weight, negative, expected):
    assert signal(close, weight=weight, negative=negative) == expected


def test_add_blocked_by_falling_profit_or_high_debt_or_unknown():
    assert signal(75, fundamentals=Fundamentals(op_yoy=-40, debt_ratio=80)) == "hold"
    assert signal(75, fundamentals=Fundamentals(op_yoy=5, debt_ratio=250)) == "hold"
    assert signal(75, fundamentals=Fundamentals(op_yoy=None, debt_ratio=80)) == "hold"


def test_financial_sector_skips_debt_ratio():
    bank = Fundamentals(op_yoy=5, debt_ratio=1200)
    assert signal(75, fundamentals=bank, financial=True) == "add"


def test_insufficient_band_only_weight_and_review_rules():
    assert signal(75, valuation=NO_BAND) == "hold"
    assert signal(75, valuation=NO_BAND, weight=20) == "trim"
    assert signal(45, valuation=NO_BAND) == "review"


def test_reasons_are_reported():
    _, reasons = decide_signal(45, VAL, GOOD, 5, Profile(), True)
    assert reasons == ["재검토 기준가 이하", "최근 악재 유형 공시"]
