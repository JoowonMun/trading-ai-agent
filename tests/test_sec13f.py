import httpx
import pytest

from agent.collectors.sec13f import Nps13fClient, normalize_issuer

MANAGER = ('<a href="/13f/000119312526347818-national-pension-service-q2-2026">Q2 2026</a>'
           '<a href="/13f/000119312526347818-national-pension-service-q2-2026">Q2 2026</a>'
           '<a href="/13f/000119312526217663-national-pension-service-q1-2026">Q1 2026</a>'
           '<a href="/13f/000160804626000001-national-pension-service-q4-2025">Q4 2025</a>')


def row(sym, name, cusip, value, shares, option=None):
    return [sym, name, "COM", cusip, value, 1.0, shares, None, option]


LATEST = {"data": [row("NVDA", "NVIDIA CORPORATION", "67066G104", 9000, 1500),
                   row("GOOGL", "ALPHABET INC", "02079K305", 3000, 800),
                   row("GOOG", "ALPHABET INC", "02079K107", 2000, 500),
                   row("TSLA", "TESLA INC", "88160R101", 1000, 300, "Call"),      # 옵션 제외
                   row("BAC", "BANK OF AMER CORP", "060505104", 700, 70),        # 회사명 표기만 바뀜
                   row("HON", "HONEYWELL INTL INC", "438516AAA", 300, 30),       # CUSIP가 바뀐 종목
                   row(None, "NEWCO INC", "000000001", 500, 100)]}
PREVIOUS = {"data": [row("NVDA", "NVIDIA CORPORATION", "67066G104", 6000, 1000),
                     row("GOOGL", "ALPHABET INC", "02079K305", 3000, 1300),
                     row("BAC", "BANK AMERICA CORP", "060505104", 700, 70),
                     row("HON", "HONEYWELL INTL INC", "438516106", 300, 20),
                     row("OLD", "OLDCO CORP", "000000002", 400, 50)]}


def handler_factory(calls):
    def handler(request):
        path = request.url.path
        calls.append(path)
        if path == "/manager/0001608046-national-pension-service":
            return httpx.Response(200, text=MANAGER)
        if path == "/data/13f/000119312526347818":
            return httpx.Response(200, json=LATEST)
        if path == "/data/13f/000119312526217663":
            return httpx.Response(200, json=PREVIOUS)
        return httpx.Response(404)
    return handler


def client(tmp_path, calls):
    return Nps13fClient(tmp_path, http=httpx.Client(transport=httpx.MockTransport(handler_factory(calls))),
                        sleep=lambda s: None)


@pytest.mark.parametrize("raw, expected", [
    ("NVIDIA CORPORATION", "NVIDIA"), ("Alphabet Inc.", "ALPHABET"), ("Tesla, Inc.", "TESLA"),
    ("JPMORGAN CHASE & CO", "JPMORGAN CHASE"), ("Meta Platforms, Inc.", "META PLATFORMS"),
])
def test_normalize_issuer(raw, expected):
    assert normalize_issuer(raw) == expected


def test_report_compares_latest_two_quarters(tmp_path):
    r = client(tmp_path, []).report()
    assert (r["period"], r["prev_period"]) == ("2026 Q2", "2026 Q1")
    pos = r["positions"]
    assert pos["67066G104"]["shares"] == 1500 and pos["67066G104"]["change_pct"] == pytest.approx(50.0)
    assert pos["02079K305"]["change_pct"] == pytest.approx((800 - 1300) / 1300 * 100)   # 클래스 A만 비교
    assert pos["02079K107"]["new"] is True
    assert "88160R101" not in pos
    assert pos["060505104"]["new"] is False and pos["060505104"]["change_pct"] == 0   # CUSIP로 같은 종목
    assert pos["67066G104"]["rank"] == 1
    assert r["tickers"]["GOOGL"] == "02079K305" and r["names"]["NEWCO"] == "000000001"
    assert pos["438516AAA"]["new"] is False and pos["438516AAA"]["change_pct"] == pytest.approx(50.0)
    assert [s["name"] for s in r["sold_out"]] == ["OLDCO CORP"]
    assert r["top_buys"][0]["name"] == "NVIDIA CORPORATION"


def test_filings_are_cached(tmp_path):
    calls = []
    client(tmp_path, calls).report()
    client(tmp_path, calls).report()
    assert sum(1 for c in calls if c.startswith("/data/13f/")) == 2
