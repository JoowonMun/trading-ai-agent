import httpx
import pytest

from agent.collectors.sec13f import Sec13fClient, normalize_issuer

NS = "http://www.sec.gov/edgar/document/thirteenf/informationtable"


def info_table(rows):
    body = "".join(
        f"<infoTable><nameOfIssuer>{name}</nameOfIssuer><titleOfClass>{cls}</titleOfClass><cusip>{cusip}</cusip>"
        f"<value>{value}</value><shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType>"
        f"</shrsOrPrnAmt>{f'<putCall>{put}</putCall>' if put else ''}<investmentDiscretion>SOLE</investmentDiscretion>"
        f"</infoTable>" for name, cls, cusip, value, shares, put in rows)
    return f'<?xml version="1.0"?><informationTable xmlns="{NS}">{body}</informationTable>'


LATEST = info_table([("NVIDIA CORPORATION", "COM", "67066G104", 9_000_000, 1500, None),
                     ("ALPHABET INC", "CAP STK CL A", "02079K305", 3_000_000, 800, None),
                     ("ALPHABET INC", "CAP STK CL C", "02079K107", 2_000_000, 500, None),
                     ("TESLA INC", "COM", "88160R101", 1_000_000, 300, "CALL"),   # 옵션은 제외
                     ("NEWCO INC", "COM", "000000001", 500_000, 100, None)])
PREVIOUS = info_table([("NVIDIA CORPORATION", "COM", "67066G104", 6_000_000, 1000, None),
                       ("ALPHABET INC", "CAP STK CL A", "02079K305", 3_000_000, 1300, None),
                       ("OLDCO CORP", "COM", "000000002", 400_000, 50, None)])


def handler_factory(calls):
    def handler(request):
        path = request.url.path
        calls.append(path)
        assert "test@example.com" in request.headers["user-agent"]
        if path == "/submissions/CIK0001608046.json":
            return httpx.Response(200, json={"filings": {"recent": {
                "form": ["13F-HR", "8-K", "13F-HR/A", "13F-HR"],
                "accessionNumber": ["0001608046-26-000005", "x", "0001608046-26-000004", "0001608046-26-000003"],
                "filingDate": ["2026-08-12", "2026-07-01", "2026-06-01", "2026-05-13"],
                "reportDate": ["2026-06-30", "", "2026-03-31", "2026-03-31"]}}})
        if path.endswith("/index.json"):
            return httpx.Response(200, json={"directory": {"item": [
                {"name": "primary_doc.xml"}, {"name": "infotable.xml"}, {"name": "0001608046-26-000005.txt"}]}})
        if path.endswith("000160804626000005/infotable.xml"):
            return httpx.Response(200, text=LATEST)
        if path.endswith("000160804626000003/infotable.xml"):
            return httpx.Response(200, text=PREVIOUS)
        return httpx.Response(404)
    return handler


def client(tmp_path, calls):
    return Sec13fClient("trading-ai-agent test@example.com", tmp_path,
                        http=httpx.Client(transport=httpx.MockTransport(handler_factory(calls))), sleep=lambda s: None)


@pytest.mark.parametrize("raw, expected", [
    ("NVIDIA CORPORATION", "NVIDIA"), ("NVIDIA Corporation", "NVIDIA"), ("Alphabet Inc.", "ALPHABET"),
    ("ALPHABET INC", "ALPHABET"), ("Tesla, Inc.", "TESLA"), ("IonQ, Inc.", "IONQ"),
    ("JPMORGAN CHASE & CO", "JPMORGAN CHASE"), ("Meta Platforms, Inc.", "META PLATFORMS"),
])
def test_normalize_issuer(raw, expected):
    assert normalize_issuer(raw) == expected


def test_report_compares_latest_two_original_filings(tmp_path):
    r = client(tmp_path, []).report()
    assert (r["period"], r["filed"], r["prev_period"]) == ("2026-06-30", "2026-08-12", "2026-03-31")
    pos = r["positions"]
    assert pos["NVIDIA"]["shares"] == 1500 and pos["NVIDIA"]["change_pct"] == pytest.approx(50.0)
    assert pos["ALPHABET"]["shares"] == 1300 and pos["ALPHABET"]["change_pct"] == pytest.approx(0.0)  # A+C 합산
    assert "TESLA" not in pos                                    # 옵션 제외
    assert pos["NEWCO"]["change_pct"] is None and pos["NEWCO"]["new"] is True
    assert pos["NVIDIA"]["rank"] == 1 and pos["ALPHABET"]["rank"] == 2
    assert [s["name"] for s in r["sold_out"]] == ["OLDCO CORP"]


def test_filings_are_cached(tmp_path):
    calls = []
    client(tmp_path, calls).report()
    client(tmp_path, calls).report()
    assert sum(1 for c in calls if c.endswith("infotable.xml")) == 2  # 제출된 보고서는 다시 받지 않음
