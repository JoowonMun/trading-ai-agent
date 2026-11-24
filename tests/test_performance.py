import pytest

from factories import sample_context

from agent.analysis.performance import (build_performance, chain_return, estimate_dividends, index_return,
                                        score_signals)


def snap(day, holdings, kospi=100.0, sp=100.0, fx=1000.0, total=1_000_000):
    return {"date": day, "portfolio": {"total_krw": total},
            "market": {"indices": {"KOSPI": kospi, "S&P500": sp}, "fx_usdkrw": fx},
            "holdings": [{"market": m, "ticker": t, "name": f"가짜{t}", "close": c, "weight_pct": w, "signal": s}
                         for m, t, c, w, s in holdings]}


def test_chain_return_ignores_deposits_and_counts_cash_as_zero():
    a = snap("2026-11-02", [("KR", "000001", 100.0, 50.0, "hold")], total=1_000_000)
    b = snap("2026-11-03", [("KR", "000001", 110.0, 30.0, "hold")], total=5_000_000)  # 입금으로 총액 급증
    c = snap("2026-11-04", [("KR", "000001", 99.0, 30.0, "hold")])
    assert chain_return([a, b]) == pytest.approx(5.0)          # 비중 50% × +10%
    assert chain_return([a, b, c]) == pytest.approx((1.05 * 0.97 - 1) * 100)  # 다음 날 30% × -10%


def test_chain_return_uses_fx_for_us_and_skips_new_or_sold():
    a = snap("2026-11-02", [("US", "FAKE", 10.0, 40.0, "hold"), ("KR", "000002", 100.0, 20.0, "hold")], fx=1000.0)
    b = snap("2026-11-03", [("US", "FAKE", 10.0, 40.0, "hold"), ("KR", "000003", 50.0, 20.0, "hold")], fx=1100.0)
    assert chain_return([a, b]) == pytest.approx(4.0)  # 달러 그대로, 환율 +10% × 40%; 매도·신규는 제외


def test_chain_return_needs_two_snapshots():
    assert chain_return([snap("2026-11-02", [])]) is None


def test_index_return():
    snaps = [snap("2026-11-02", [], kospi=100.0), snap("2026-11-09", [], kospi=103.0)]
    assert index_return(snaps, "KOSPI") == pytest.approx(3.0)
    assert index_return(snaps[:1], "KOSPI") is None


def test_score_signals_counts_changes_and_compares_with_index_after_four_weeks():
    snaps = [
        snap("2026-10-05", [("KR", "000001", 100.0, 10, "add"), ("KR", "000002", 100.0, 10, "trim")]),
        snap("2026-10-06", [("KR", "000001", 100.0, 10, "add"), ("KR", "000002", 100.0, 10, "trim")]),  # 반복은 안 셈
        snap("2026-10-20", [("KR", "000001", 100.0, 10, "hold"), ("KR", "000002", 100.0, 10, "trim")]),
        snap("2026-11-02", [("KR", "000001", 120.0, 10, "add"), ("KR", "000002", 90.0, 10, "trim")], kospi=105.0),
        snap("2026-11-03", [("KR", "000001", 120.0, 10, "add"), ("KR", "000002", 90.0, 10, "trim")], kospi=105.0),
    ]
    scores = {s.signal: s for s in score_signals(snaps)}
    assert (scores["add"].events, scores["add"].hits, scores["add"].pending) == (2, 1, 1)  # 10/5 적중, 11/2 대기
    assert (scores["trim"].events, scores["trim"].hits, scores["trim"].pending) == (1, 1, 0)  # 지수보다 못함 = 적중
    assert "hold" not in scores and scores["review"].events == 0


def test_score_signals_skips_sold_or_missing_index():
    snaps = [snap("2026-10-05", [("KR", "000001", 100.0, 10, "add"), ("US", "FAKE", 10.0, 10, "review")]),
             snap("2026-11-05", [("US", "FAKE", 9.0, 10, "review")], sp=None)]
    scores = {s.signal: s for s in score_signals(snaps)}
    assert scores["add"].events == 0 and scores["review"].events == 0


def test_estimate_dividends_and_missing():
    ctx = sample_context()  # 총 8,000,000 · 첫 종목 비중 8.2% · 배당수익률 2.2% · 둘째 종목은 배당수익률 없음
    krw, missing = estimate_dividends(ctx)
    assert krw == 14_000  # 8,000,000 × 8.2% × 2.2% = 14,432 → 천 원 단위
    assert missing == [ctx.holdings[1].name]


def test_build_performance_week_and_total():
    ctx = sample_context()
    snaps = [snap("2026-10-01", [("KR", "000001", 100.0, 50.0, "hold")], kospi=100.0),
             snap("2026-10-08", [("KR", "000001", 120.0, 50.0, "hold")], kospi=110.0),
             snap("2026-10-15", [("KR", "000001", 132.0, 50.0, "hold")], kospi=121.0)]
    p = build_performance(snaps, "2026-10-08", ctx)
    assert (p.since, p.week_since) == ("2026-10-01", "2026-10-08")
    assert p.account_week_pct == pytest.approx(5.0) and p.account_total_pct == pytest.approx(15.5)
    assert p.index_week_pct["KOSPI"] == pytest.approx(10.0) and p.index_total_pct["KOSPI"] == pytest.approx(21.0)
    assert p.dividend_krw == 14_000


def test_score_signals_ignores_flicker_back_to_same_signal_within_four_weeks():
    seq = [("2026-10-05", "trim"), ("2026-10-06", "review"), ("2026-10-07", "trim"), ("2026-10-08", "review"),
           ("2026-11-10", "trim")]
    snaps = [snap(d, [("KR", "000001", 100.0, 10, s)]) for d, s in seq]
    scores = {s.signal: s for s in score_signals(snaps)}
    assert scores["trim"].events == 2 and scores["review"].events == 1  # 10/7 trim·10/8 review는 4주 안 재등장
