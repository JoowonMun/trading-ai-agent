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
