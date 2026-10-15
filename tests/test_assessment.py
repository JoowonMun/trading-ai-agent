from agent.analysis.assessment import assess
from agent.report.schema import Band, Fundamentals, Valuation

PER_BAND = Valuation(method="PER", insufficient=False, current_multiple=8.0,
                     band=Band(p10=6, p25=9, p50=11, p75=18, p90=25),
                     fair=1, buy=[1, 1, 1], sell=[1, 1], review=1)


def test_strong_company():
    f = Fundamentals(per=8.0, pbr=2.0, roe=26, op_margin=37, rev_yoy=130, op_yoy=1800, debt_ratio=31, div_yield=0.8)
    a = assess(f, PER_BAND, financial=False)
    assert a == {"per": "good", "pbr": None, "roe": "good", "op_margin": "good", "rev_yoy": "good",
                 "op_yoy": "good", "debt_ratio": "good", "div_yield": "neutral"}


def test_weak_company():
    f = Fundamentals(per=20.0, roe=3, op_margin=2, rev_yoy=-10, op_yoy=-40, debt_ratio=250, div_yield=4)
    a = assess(f, PER_BAND, financial=False)
    assert a["per"] == "caution"          # 과거 75% 구간보다 비쌈
    assert a["roe"] == "caution" and a["op_margin"] == "caution"
    assert a["rev_yoy"] == "caution" and a["op_yoy"] == "caution"
    assert a["debt_ratio"] == "caution"
    assert a["div_yield"] == "good"


def test_middle_values_are_neutral_and_missing_is_none():
    f = Fundamentals(per=11.0, roe=7, op_margin=5, rev_yoy=0, op_yoy=0, debt_ratio=150)
    a = assess(f, PER_BAND, financial=False)
    assert {a[k] for k in ("per", "roe", "op_margin", "rev_yoy", "op_yoy", "debt_ratio")} == {"neutral"}
    assert a["div_yield"] is None


def test_pbr_judged_on_band_when_method_is_pbr_and_financial_debt_not_judged():
    pbr_band = PER_BAND.model_copy(update={"method": "PBR", "current_multiple": 0.5})
    a = assess(Fundamentals(pbr=0.5, debt_ratio=1200), pbr_band, financial=True)
    assert a["pbr"] == "good" and a["per"] is None
    assert a["debt_ratio"] is None


def test_no_valuation():
    assert assess(Fundamentals(per=10), None, financial=False)["per"] is None
