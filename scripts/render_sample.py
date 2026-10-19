"""README용 샘플 리포트 — 가상의 회사와 가짜 숫자로 메일 HTML을 만든다.

    uv run python scripts/render_sample.py   →   out/sample/preview.html
"""
from pathlib import Path

from agent.config import Profile
from agent.report.context import GLOSSARY_TERMS
from agent.report.render import render_report
from agent.report.schema import (Analysis, Band, ClassWeight, Context, Disclosure, Fundamentals, HoldingContext,
                                 IndexQuote, Market, Portfolio, PositionInfo, PriceSnapshot, Rebalance, Valuation)


def sample_context() -> Context:
    kr = HoldingContext(
        ticker="000000", name="가나전자", market="KR", asset_class="domestic",
        position=PositionInfo(qty=20, avg_price=58000, weight_pct=12.4),
        price=PriceSnapshot(close=52300, price_date="2026-10-16", ma20=54100, ma60=55800, ma120=57200,
                            rsi14=34.2, pos_52w_pct=18.0),
        fundamentals=Fundamentals(per=9.1, pbr=1.2, roe=14.3, op_margin=11.8, rev_yoy=6.4, op_yoy=12.5,
                                  debt_ratio=48.0, div_yield=2.6, latest_quarter="2026Q2"),
        valuation=Valuation(method="PER", insufficient=False, current_multiple=9.1,
                            band=Band(p10=7.8, p25=9.4, p50=11.2, p75=13.5, p90=15.9),
                            fair=64366, buy=[54024, 50579, 44828], sell=[77588, 91380], review=49300),
        assessments={"per": "good", "pbr": None, "roe": "good", "op_margin": "good", "rev_yoy": "good",
                     "op_yoy": "good", "debt_ratio": "good", "div_yield": "neutral"},
        signal="add", signal_reasons=["분할매수 1단계 가격 이하", "실적·재무 조건 충족"],
        nps={"stake_pct": 8.12, "change_pct": 0.21, "date": "2026-10-14", "annual_rank": 37, "annual_stake_pct": 7.9},
        disclosures=[Disclosure(date="2026-10-14", title="연결재무제표기준영업(잠정)실적(공정공시)",
                                category="earnings", negative=False, url="https://dart.fss.or.kr")],
    )
    us = HoldingContext(
        ticker="EXMP", name="Example Corp", market="US", asset_class="us",
        position=PositionInfo(qty=8, avg_price=140.0, weight_pct=9.8),
        price=PriceSnapshot(close=172.4, price_date="2026-10-15", ma20=168.2, ma60=160.5, ma120=151.3,
                            rsi14=61.0, pos_52w_pct=82.0),
        fundamentals=Fundamentals(per=31.5, pbr=8.4, roe=27.0, op_margin=24.1, rev_yoy=18.2, op_yoy=22.7,
                                  debt_ratio=95.0, div_yield=0.4, latest_quarter="2026Q3"),
        valuation=Valuation(method="PER", insufficient=False, current_multiple=31.5,
                            band=Band(p10=22.0, p25=25.4, p50=29.8, p75=34.1, p90=39.0),
                            fair=163.1, buy=[139.01, 129.85, 120.39], sell=[186.6, 213.45], review=119.0),
        assessments={"per": "neutral", "roe": "good", "op_margin": "good", "rev_yoy": "good", "op_yoy": "good",
                     "debt_ratio": "good", "div_yield": "neutral"},
        signal="hold",
        nps={"us_rank": 42, "us_shares": 1250000.0, "us_change_pct": 4.3, "us_new": False, "us_period": "2026 Q2"},
    )
    return Context(
        date="2026-10-16", profile=Profile(),
        market=Market(indices={"KOSPI": IndexQuote(close=3120.5, change_pct=-0.42),
                               "S&P500": IndexQuote(close=6890.1, change_pct=0.35),
                               "VIX": IndexQuote(close=15.8, change_pct=-2.1)}, fx_usdkrw=1342.5),
        holdings=[kr, us],
        portfolio=Portfolio(
            total_krw=8_400_000, cash_krw=300_000,
            by_class={"domestic": ClassWeight(label="국내", value_krw=1_046_000, pct=12.4, target_pct=15, diff_pct=-2.6),
                      "us": ClassWeight(label="미국", value_krw=4_200_000, pct=50.0, target_pct=45, diff_pct=5.0),
                      "index": ClassWeight(label="지수", value_krw=2_854_000, pct=34.0, target_pct=40, diff_pct=-6.0)},
            rebalance=[Rebalance(asset_class="index", label="지수", action="늘리기", amount_krw=500_000)],
            weights={"KR:000000": 12.4, "US:EXMP": 9.8}, nps_overlap=["가나전자"]),
        nps_changes=[{"name": "가나전자", "ticker": "000000", "stake_pct": 8.12, "change_pct": 0.21,
                      "date": "2026-10-14", "mine": True},
                     {"name": "다라화학", "ticker": "000001", "stake_pct": 10.05, "change_pct": -0.31,
                      "date": "2026-10-13", "mine": False}],
        nps_annual_as_of="2025-12-31",
        nps_us={"period": "2026 Q2", "prev_period": "2026 Q1",
                "top_buys": [{"name": "EXAMPLE CORP", "rank": 42, "change_pct": 4.3, "new": False},
                             {"name": "SAMPLE HOLDINGS INC", "rank": 120, "change_pct": None, "new": True}],
                "top_sells": [{"name": "DEMO TECHNOLOGIES INC", "rank": 88, "change_pct": -35.2, "new": False}],
                "sold_out": [{"name": "OLDCO CORP"}], "top_holdings": [{"name": "EXAMPLE CORP"}]},
        glossary_terms=GLOSSARY_TERMS[:6],
    )


SAMPLE_ANALYSIS = Analysis(
    date="2026-10-16",
    summary=["가나전자가 분할매수 1단계 가격(54,024원) 아래로 내려와 추가매수 후보예요.",
             "지수 비중이 목표보다 낮아 지수 ETF를 500,000원 늘리는 리밸런싱을 제안해요."],
    market_comment="코스피는 소폭 내렸고 S&P500은 올랐어요. 변동성 지수(VIX)가 낮아 시장 분위기는 차분한 편이에요.",
    holdings=[
        {"ticker": "000000", "signal": "add", "headline": "실적은 좋아지는데 주가는 과거 평균보다 싸요",
         "reasoning": "PER 9.1배로 과거 5년 중앙값 11.2배보다 낮아요. ROE 14.3%, 영업이익 성장률 12.5%로 "
                      "돈을 잘 벌고 있어서 싸진 이유가 실적 때문은 아니에요. 한 번에 다 사기보다 분할매수 가격대에서 "
                      "나눠 사는 방법을 고려해 보세요.",
         "indicator_notes": [{"term": "PER", "value": "9.1배", "plain": "1년 이익의 몇 배 가격인지 — 과거보다 낮아요"},
                             {"term": "ROE", "value": "14.3%", "plain": "주주 돈으로 1년에 번 비율 — 10% 이상이면 우수"}]},
        {"ticker": "EXMP", "signal": "hold", "headline": "적정가 근처라 지켜보며 보유",
         "reasoning": "현재가 $172.40은 적정가 $163.10보다 조금 높고 일부매도 1차 가격 $186.60에는 아직 못 미쳐요. "
                      "매출 성장률 18.2%로 성장이 이어지고 있어 보유를 유지할 만해요."},
    ],
    portfolio_comment="미국 비중이 50.0%로 목표 45%보다 높고 지수는 34.0%로 낮아요. 새로 투자할 돈은 지수 ETF에 먼저 넣는 걸 고려해 보세요.",
)


if __name__ == "__main__":
    out = Path("out/sample")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "preview.html"
    path.write_text(render_report(sample_context(), SAMPLE_ANALYSIS, ["샘플 데이터 — 가상의 회사와 숫자"]), encoding="utf-8")
    print(path)
