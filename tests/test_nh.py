import json

import httpx
import pytest

from agent.collectors.nh import NhClient, NhError, mask_account

TOKEN_PATH = "/oauth2/token"


def kr_balance(rows, dca=1_000_000):
    return {"rsp_cd": "00000", "rsp_msg": "조회가 완료되었습니다.", "Output_0": {"dca": dca}, "Output_1": rows}


def us_balance(rows):
    return {"rsp_cd": "00000", "rsp_msg": "조회가 완료되었습니다.", "Output_0": {}, "Output_1": rows}


def make_handler(calls, accounts=None, kr=None, us=None):
    accounts = accounts or [{"acct_no": "98765432101", "acct_type": "01"},
                            {"acct_no": "50001234540", "acct_type": "03"}]

    def handler(request):
        path = request.url.path
        calls.append(path)
        if path == TOKEN_PATH:
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 86400})
        assert request.headers["authorization"] == "Bearer tok"
        assert request.headers["x-client-id"] == "KEY"
        act = json.loads(request.content)["Input_0"].get("act_no")
        assert act in (None, "98765432101"), "모의투자 계좌(03)는 조회하면 안 된다"
        if path == "/n2/acctinfo":
            return httpx.Response(200, json={"rsp_msg": "ok", "Output_0": accounts})
        if path == "/krstock/inquiry/v1/balance":
            return httpx.Response(200, json=kr if kr is not None else kr_balance([
                {"iem_cd": "005930", "iem_nm": "삼성전자", "itg_bnc_qty": 10.0, "phs_pr": 276000},
                {"iem_cd": "0189B0", "iem_nm": "TIGER 은액티브", "itg_bnc_qty": 3.0, "phs_pr": 7970},
                {"iem_cd": "017670", "iem_nm": "SK텔레콤", "itg_bnc_qty": 0.0, "phs_pr": 50000},
            ]))
        if path == "/gbstock/inquiry/v1/balance":
            return httpx.Response(200, json=us if us is not None else us_balance([
                {"iem_cd": "GOOGL", "iem_nm": "알파벳 Class A", "cns_bse_bnc_qty": 2, "fc_avg_phs_pr": 180.5},
                {"iem_cd": "IVV", "iem_nm": "아이셰어즈 코어 S&P500 ETF", "cns_bse_bnc_qty": 4, "fc_avg_phs_pr": 600.0},
            ]))
        return httpx.Response(404)

    return handler


def client(tmp_path, handler, now=1_000.0):
    return NhClient("KEY", "SECRET", tmp_path, http=httpx.Client(transport=httpx.MockTransport(handler)),
                    now=lambda: now, sleep=lambda s: None)


def test_holdings_from_live_account_only(tmp_path):
    calls = []
    accounts, cash = client(tmp_path, make_handler(calls)).holdings(index_tickers={"IVV"})
    by_class = {(a.market, a.asset_class): a for a in accounts}
    kr = by_class[("KR", "domestic")]
    assert [(p.ticker, p.name, p.qty, p.avg_price) for p in kr.positions] == [
        ("005930", "삼성전자", 10.0, 276000), ("0189B0", "TIGER 은액티브", 3.0, 7970)]  # 수량 0은 제외
    assert [p.ticker for p in by_class[("US", "us")].positions] == ["GOOGL"]
    assert [p.ticker for p in by_class[("US", "index")].positions] == ["IVV"]
    assert all(a.broker == "nh" for a in accounts)
    assert "98765432101" not in " ".join(a.name for a in accounts)  # 계좌번호는 가린다
    assert cash == 1_000_000


def test_token_is_cached_across_clients(tmp_path):
    calls = []
    client(tmp_path, make_handler(calls)).holdings()
    client(tmp_path, make_handler(calls)).holdings()
    assert calls.count(TOKEN_PATH) == 1


def test_expired_token_is_reissued(tmp_path):
    calls = []
    client(tmp_path, make_handler(calls), now=1_000.0).holdings()
    client(tmp_path, make_handler(calls), now=1_000.0 + 90_000).holdings()
    assert calls.count(TOKEN_PATH) == 2


def test_order_paths_are_blocked_before_any_request(tmp_path):
    calls = []
    with pytest.raises(NhError, match="허용되지 않은"):
        client(tmp_path, make_handler(calls))._call("/krstock/order/v1/cash-buy", {})
    assert calls == []


def test_account_without_stock_balance_is_skipped(tmp_path):
    calls = []
    empty = {"rsp_msg": "조회할 내역이 없습니다.", "Output_0": {}}
    accounts, cash = client(tmp_path, make_handler(calls, kr=empty, us=empty)).holdings()
    assert accounts == [] and cash == 0


def test_http_error_raises(tmp_path):
    def handler(request):
        if request.url.path == TOKEN_PATH:
            return httpx.Response(401, text="invalid appkey")
        return httpx.Response(500)

    with pytest.raises(NhError, match="토큰"):
        client(tmp_path, handler).holdings()


def test_mask_account():
    assert mask_account("98765432101") == "9876*****01"
    assert mask_account("") == "****"
