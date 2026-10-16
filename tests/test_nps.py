from datetime import date

import httpx
import pytest

from agent.collectors.nps import NpsClient, parse_annual_csv

TODAY = date(2026, 10, 16)
CSV = ("번호,종목명,평가액(억 원),자산군 내 비중(퍼센트),지분율(퍼센트)\n"
       "1,삼성전자,551095,21.06,7.76\n2,SK하이닉스,374316,14.31,7.9\n13,신한지주,33709,1.29,9.03\n").encode("cp949")
PAGE = ('<a href="/cmm/cmm/fileDownload.do?atchFileId=FILE_000000007701374&fileDetailSn=1&insertDataPrcus=N">'
        "국민연금공단_국내주식 투자정보_20251231</a>")


def filing(corp, name, code, dt, flr="국민연금공단", report="임원ㆍ주요주주특정증권등소유상황보고서"):
    return {"corp_code": corp, "corp_name": name, "stock_code": code, "report_nm": report,
            "rcept_no": f"{dt}000001", "flr_nm": flr, "rcept_dt": dt}


def elestock(rows):
    return {"status": "000", "list": [
        {"rcept_dt": dt, "repror": who, "sp_stock_lmp_rate": rate} for dt, who, rate in rows]}


def handler_factory(calls):
    def handler(request):
        path = request.url.path
        calls.append(path)
        if path.endswith("fileData.do"):
            return httpx.Response(200, text=PAGE)
        if path.endswith("fileDownload.do"):
            assert request.url.params["atchFileId"] == "FILE_000000007701374"
            return httpx.Response(200, content=CSV)
        if path.endswith("list.json"):
            page = int(request.url.params["page_no"])
            rows = {1: [filing("C1", "대한항공", "003490", "20261015"),
                        filing("C9", "다른회사", "111111", "20261015", flr="홍길동")],
                    2: [filing("C1", "대한항공", "003490", "20261012"),
                        filing("C2", "NC", "036570", "20261012")]}[page]
            return httpx.Response(200, json={"status": "000", "total_page": 2, "list": rows})
        if path.endswith("elestock.json"):
            corp = request.url.params["corp_code"]
            data = {"C1": [("2026-10-07", "국민연금공단", "10.00"), ("2026-10-12", "국민연금공단", "9.97"),
                           ("2026-10-13", "다른주주", "5.00"), ("2026-10-15", "국민연금공단", "9.97")],
                    "C2": [("2026-09-01", "국민연금공단", "11.20"), ("2026-10-12", "국민연금공단", "12.10")],
                    "C3": [("2026-03-02", "국민연금공단", "8.10")]}.get(corp, [])
            return httpx.Response(200, json=elestock(data) if data else {"status": "013"})
        return httpx.Response(404)
    return handler


def client(tmp_path, calls):
    return NpsClient("KEY", tmp_path, http=httpx.Client(transport=httpx.MockTransport(handler_factory(calls))),
                     today=TODAY)


def test_parse_annual_csv():
    rows = parse_annual_csv(CSV)
    assert rows[0] == {"rank": 1, "name": "삼성전자", "value_eok": 551095.0, "weight_pct": 21.06, "stake_pct": 7.76}
    assert len(rows) == 3


def test_annual_holdings_downloaded_and_cached(tmp_path):
    calls = []
    for _ in range(2):
        annual = client(tmp_path, calls).annual_holdings()
        assert annual["as_of"] == "2025-12-31" and annual["rows"][2]["name"] == "신한지주"
    assert calls.count("/cmm/cmm/fileDownload.do") == 1


def test_recent_changes_only_nps_and_change_vs_previous_filing(tmp_path):
    calls = []
    changes = client(tmp_path, calls).recent_changes(days=7)
    by_name = {c["name"]: c for c in changes}
    assert set(by_name) == {"대한항공", "NC"}                       # 다른 신고인은 제외, 회사별 1건
    assert by_name["대한항공"]["stake_pct"] == 9.97
    assert by_name["대한항공"]["change_pct"] == pytest.approx(0.0)  # 직전 국민연금 신고(9.97) 대비
    assert by_name["NC"]["change_pct"] == pytest.approx(0.9)
    assert by_name["NC"]["date"] == "2026-10-12" and by_name["NC"]["ticker"] == "036570"
    assert changes[0]["name"] == "NC"                                # 변동 큰 순


def test_stake_for_holding(tmp_path):
    nps = client(tmp_path, [])
    assert nps.stake("C3") == {"stake_pct": 8.1, "change_pct": None, "date": "2026-03-02"}
    assert nps.stake("C404") is None
