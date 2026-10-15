import io
import zipfile
from datetime import date

import httpx
import pytest

from agent.collectors.dart import DartClient, DartError

TODAY = date(2026, 10, 15)


def corp_zip(entries):
    body = "".join(
        f"<list><corp_code>{c}</corp_code><corp_name>n</corp_name><stock_code>{s}</stock_code>"
        f"<modify_date>20260101</modify_date></list>" for c, s in entries)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", f"<result>{body}</result>".encode("utf-8"))
    return buf.getvalue()


def client(tmp_path, handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return DartClient("KEY", tmp_path, http=http, today=TODAY)


def test_corp_code_lookup_and_cache(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, content=corp_zip([("00126380", "005930"), ("00999999", " ")]))

    assert client(tmp_path, handler).corp_code("005930") == "00126380"
    assert client(tmp_path, handler).corp_code("005930") == "00126380"  # 새 클라이언트도 캐시 사용
    assert len(calls) == 1
    with pytest.raises(DartError, match="찾을 수 없습니다"):
        client(tmp_path, handler).corp_code("123456")


def test_financial_rows_fall_back_to_ofs(tmp_path):
    def handler(request):
        if request.url.params["fs_div"] == "CFS":
            return httpx.Response(200, json={"status": "013", "message": "조회된 데이타가 없습니다."})
        return httpx.Response(200, json={"status": "000", "list": [{"account_id": "x"}]})

    assert client(tmp_path, handler).financial_rows("C", 2025, 4) == [{"account_id": "x"}]


def test_financial_rows_cache_only_past_years(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.params["bsns_year"])
        return httpx.Response(200, json={"status": "000", "list": [{"a": 1}]})

    c = client(tmp_path, handler)
    c.financial_rows("C", 2025, 4)
    c.financial_rows("C", 2025, 4)
    c.financial_rows("C", 2026, 2)
    c.financial_rows("C", 2026, 2)
    assert calls == ["2025", "2026", "2026"]


def test_quarterly_reports_skip_future_quarters(tmp_path):
    requested = set()

    def handler(request):
        requested.add((request.url.params["bsns_year"], request.url.params["reprt_code"]))
        return httpx.Response(200, json={"status": "013"})

    assert client(tmp_path, handler).quarterly_reports("C", years=1) == {}
    assert ("2026", "11014") in requested      # 2026Q3 (9/30 종료) 요청
    assert ("2026", "11011") not in requested  # 2026Q4는 미래
    assert min(int(y) for y, _ in requested) == 2025


def test_error_status_raises(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"status": "020", "message": "요청 제한을 초과하였습니다."})

    with pytest.raises(DartError, match="020"):
        client(tmp_path, handler).company("C")


def test_shares_outstanding_uses_common_stock(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"status": "000", "list": [
            {"se": "보통주", "istc_totqy": "5,969,782,550"},
            {"se": "우선주", "istc_totqy": "822,886,700"},
        ]})

    assert client(tmp_path, handler).shares_outstanding("C") == 5_969_782_550


def test_dividend_per_share(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"status": "000", "list": [
            {"se": "주당 현금배당금(원)", "stock_knd": "보통주", "thstrm": "1,444"},
            {"se": "주당 현금배당금(원)", "stock_knd": "우선주", "thstrm": "1,445"},
        ]})

    assert client(tmp_path, handler).dividend_per_share("C") == 1444


def test_disclosures(tmp_path):
    def handler(request):
        assert request.url.params["bgn_de"] == "20261008"
        return httpx.Response(200, json={"status": "000", "list": [
            {"report_nm": "유상증자결정", "rcept_no": "20261014000001", "rcept_dt": "20261014"}]})

    rows = client(tmp_path, handler).disclosures("C", date(2026, 10, 8), TODAY)
    assert rows[0]["report_nm"] == "유상증자결정"


def test_shares_outstanding_accepts_voting_common_stock_label(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"status": "000", "list": [
            {"se": "의결권 있는\n보통주", "istc_totqy": "474,654,361"},
            {"se": "의결권 없는\n우선주", "istc_totqy": "-"},
            {"se": "합계", "istc_totqy": "474,654,361"},
        ]})

    assert client(tmp_path, handler).shares_outstanding("C") == 474_654_361


def test_cache_write_failure_does_not_lose_data(tmp_path, monkeypatch):
    from pathlib import Path

    def handler(request):
        return httpx.Response(200, json={"status": "000", "list": [{"a": 1}]})

    real_write = Path.write_text

    def locked(self, *a, **k):
        if self.name.startswith("fin_"):
            raise PermissionError(13, "Permission denied")
        return real_write(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", locked)
    assert client(tmp_path, handler).financial_rows("C", 2025, 4) == [{"a": 1}]
