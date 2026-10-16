"""NH투자증권 나무 플러그 Open API — 보유 종목(잔고) 조회 전용.

명세: https://www.nhplug.com/openapi-docs/{common,krstock,gbstock}/openapi.json
공식 SDK: https://github.com/PLUG-OpenAPI/nhplug-sdk

🔒 조회 API만 호출한다. 주문 API는 ALLOWED_PATHS에 없으므로 요청 전에 막힌다.
토큰(24시간 유효)은 재발급할 때마다 NH가 보안 알림을 보내므로 파일에 캐시한다.
"""
import json
import time
from pathlib import Path

import httpx

from agent.config import Account, Position

BASE_URL = "https://api.nhplug.com:8443"
ALLOWED_PATHS = {"/n2/acctinfo", "/krstock/inquiry/v1/balance", "/gbstock/inquiry/v1/balance"}
LIVE_ACCOUNT_TYPES = {"01", "02"}  # 03은 모의투자 계좌


class NhError(RuntimeError):
    pass


def mask_account(acct_no: str | None) -> str:
    if not acct_no or len(acct_no) <= 6:
        return "****"
    return acct_no[:4] + "*" * (len(acct_no) - 6) + acct_no[-2:]


class NhClient:
    def __init__(self, app_key: str, app_secret: str, cache_dir: Path, http: httpx.Client | None = None,
                 now=time.time, sleep=time.sleep):
        self.app_key, self.app_secret = app_key, app_secret
        self.token_file = Path(cache_dir) / "token.json"
        self.http = http or httpx.Client(timeout=20)
        self.now, self.sleep = now, sleep
        self._token: str | None = None

    def _get_token(self) -> str:
        if self._token:
            return self._token
        if self.token_file.exists():
            cached = json.loads(self.token_file.read_text(encoding="utf-8"))
            if cached.get("exp", 0) > self.now() + 60:
                self._token = cached["token"]
                return self._token
        resp = self.http.post(f"{BASE_URL}/oauth2/token", params={
            "appkey": self.app_key, "appsecretkey": self.app_secret,
            "grant_type": "client_credentials", "scope": "oob",
        }, headers={"content-type": "application/x-www-form-urlencoded"})
        if resp.status_code != 200 or "access_token" not in resp.text:
            raise NhError(f"나무 토큰 발급 실패: HTTP {resp.status_code} {resp.text[:200]}")
        data = resp.json()
        self._token = data["access_token"]
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(json.dumps({"token": self._token,
                                               "exp": self.now() + int(data.get("expires_in", 86400))}),
                                   encoding="utf-8")
        return self._token

    def _call(self, path: str, input_0: dict) -> dict:
        if path not in ALLOWED_PATHS:
            raise NhError(f"허용되지 않은 나무 API 경로입니다(조회 전용): {path}")
        for attempt in range(2):
            self.sleep(0.3)  # 초당 5회 한도
            resp = self.http.post(f"{BASE_URL}{path}", json={"Input_0": input_0}, headers={
                "x-client-id": self.app_key, "x-client-secret": self.app_secret,
                "authorization": f"Bearer {self._get_token()}", "content-type": "application/json; charset=UTF-8",
            })
            # 다른 곳(예: GitHub Actions)에서 새 토큰을 받으면 캐시된 토큰이 무효가 된다 → 1회 재발급
            if attempt == 0 and (resp.status_code == 401 or "IGW40043" in resp.text):
                self._token = None
                self.token_file.unlink(missing_ok=True)
                continue
            break
        if resp.status_code != 200:
            raise NhError(f"나무 API {path} 실패: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json()

    def live_accounts(self) -> list[str]:
        data = self._call("/n2/acctinfo", {})
        return [a["acct_no"] for a in data.get("Output_0") or []
                if (a.get("acct_type") or "").strip() in LIVE_ACCOUNT_TYPES and a.get("acct_no")]

    def holdings(self, index_tickers=frozenset()) -> tuple[list[Account], float]:
        """나무 실계좌의 국내·미국 보유 종목을 (계좌 목록, 원화 예수금 합)으로 돌려준다."""
        groups: dict[tuple[str, str], list[Position]] = {}
        cash = 0.0
        for acct in self.live_accounts():
            kr = self._call("/krstock/inquiry/v1/balance", {
                "act_no": acct, "bnc_bse_cd": "5", "ltg_aot_dit_cd": "9", "aet_bse": "2",
                "qut_dit_cd": "UNT", "aly_qut_cd": "1"})
            cash += float((kr.get("Output_0") or {}).get("dca") or 0)
            for row in kr.get("Output_1") or []:
                qty = float(row.get("itg_bnc_qty") or 0)
                if qty > 0:
                    ticker = row["iem_cd"].strip()
                    cls = "index" if ticker in index_tickers else "domestic"
                    groups.setdefault(("KR", cls), []).append(Position(
                        ticker=ticker, name=row.get("iem_nm"), qty=qty, avg_price=float(row.get("phs_pr") or 0)))

            us = self._call("/gbstock/inquiry/v1/balance", {
                "act_no": acct, "qut_iqr_dit_cd": "9", "fc_sec_trd_nat_cd": "200", "cur_cd": "USD",
                "xns_dit_cd": "1"})
            for row in us.get("Output_1") or []:
                qty = float(row.get("cns_bse_bnc_qty") or 0)
                if qty > 0:
                    ticker = row["iem_cd"].strip()
                    cls = "index" if ticker in index_tickers else "us"
                    groups.setdefault(("US", cls), []).append(Position(
                        ticker=ticker, name=row.get("iem_nm"), qty=qty,
                        avg_price=float(row.get("fc_avg_phs_pr") or 0)))

        labels = {"KR": "국내", "US": "미국"}
        accounts = [Account(name=f"나무 {labels[market]}{' (지수)' if cls == 'index' else ''}", broker="nh",
                            market=market, asset_class=cls, positions=positions)
                    for (market, cls), positions in groups.items()]
        return accounts, cash
