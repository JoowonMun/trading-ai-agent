"""국민연금(NPS) 국내 주식 보유 정보.

- 연 1회 전체 보유 목록: 공공데이터포털 파일데이터(키 불필요, CSV cp949) — 연말 기준
- 최근 지분 변동: DART 지분공시(pblntf_ty=D) 중 신고인이 국민연금공단인 것
  → 회사별 임원·주요주주 소유보고(elestock.json)로 지분율과 직전 신고 대비 변동 계산
"""
import csv
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import httpx

from agent.collectors.dart import BASE_URL as DART_URL, DartError

ANNUAL_PAGE = "https://www.data.go.kr/data/3070507/fileData.do"
ANNUAL_DOWNLOAD = "https://www.data.go.kr/cmm/cmm/fileDownload.do"
NPS_NAME = "국민연금공단"
MAX_DETAIL_CORPS = 15  # 해외 서버에서 DART가 느려 상세 조회 수를 제한


def parse_annual_csv(content: bytes) -> list[dict]:
    text = content.decode("cp949", errors="replace")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        values = list(row.values())
        try:
            rows.append({"rank": int(values[0]), "name": values[1].strip(), "value_eok": float(values[2]),
                         "weight_pct": float(values[3]), "stake_pct": float(values[4])})
        except (ValueError, IndexError):
            continue
    return rows


class NpsClient:
    def __init__(self, dart_key: str, cache_dir: Path, http: httpx.Client | None = None, today: date | None = None):
        self.dart_key = dart_key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.http = http or httpx.Client(timeout=30, follow_redirects=True, transport=httpx.HTTPTransport(retries=2))
        self.today = today or date.today()

    # ---- 연 1회 전체 보유 목록
    def annual_holdings(self) -> dict:
        cache = self.cache_dir / "nps_annual.json"
        if cache.exists() and time.time() - cache.stat().st_mtime < 30 * 24 * 3600:
            return json.loads(cache.read_text(encoding="utf-8"))
        page = self.http.get(ANNUAL_PAGE).text
        link = re.search(r"fileDownload\.do\?atchFileId=([A-Za-z0-9_]+)&(?:amp;)?fileDetailSn=(\d+)", page)
        stamp = re.search(r"국민연금공단_국내주식 투자정보_(\d{8})", page)
        if not link:
            raise RuntimeError("공공데이터포털에서 국민연금 보유 목록 파일을 찾지 못했습니다")
        resp = self.http.get(ANNUAL_DOWNLOAD, params={"atchFileId": link.group(1), "fileDetailSn": link.group(2),
                                                      "insertDataPrcus": "N"})
        resp.raise_for_status()
        d = stamp.group(1) if stamp else ""
        result = {"as_of": f"{d[:4]}-{d[4:6]}-{d[6:]}" if d else None, "rows": parse_annual_csv(resp.content)}
        try:
            cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return result

    # ---- DART
    def _dart(self, endpoint: str, **params) -> dict | None:
        data = self.http.get(f"{DART_URL}/{endpoint}", params={"crtfc_key": self.dart_key, **params}).json()
        if data.get("status") == "013":
            return None
        if data.get("status") != "000":
            raise DartError(f"{endpoint}: {data.get('status')} {data.get('message', '')}")
        return data

    def _nps_history(self, corp_code: str) -> list[tuple[str, float]]:
        data = self._dart("elestock.json", corp_code=corp_code) or {}
        rows = [(r["rcept_dt"], float(r["sp_stock_lmp_rate"].replace(",", "")))
                for r in data.get("list", []) if NPS_NAME in r.get("repror", "") and r.get("sp_stock_lmp_rate")]
        return sorted(rows)

    def stake(self, corp_code: str) -> dict | None:
        """해당 회사의 가장 최근 국민연금 지분율과 직전 신고 대비 변동(%p)."""
        history = self._nps_history(corp_code)
        if not history:
            return None
        latest_date, latest = history[-1]
        change = round(latest - history[-2][1], 2) if len(history) >= 2 else None
        return {"stake_pct": latest, "change_pct": change, "date": latest_date}

    def recent_changes(self, days: int = 7) -> list[dict]:
        start = (self.today - timedelta(days=days)).strftime("%Y%m%d")
        end = self.today.strftime("%Y%m%d")
        latest: dict[str, dict] = {}
        page, total = 1, 1
        while page <= total:
            data = self._dart("list.json", bgn_de=start, end_de=end, pblntf_ty="D", page_count="100",
                              page_no=str(page)) or {}
            total = int(data.get("total_page") or 1)
            for f in data.get("list", []):
                if NPS_NAME in f.get("flr_nm", "") and f.get("stock_code"):
                    if f["corp_code"] not in latest or f["rcept_dt"] > latest[f["corp_code"]]["rcept_dt"]:
                        latest[f["corp_code"]] = f
            page += 1

        corps = sorted(latest.values(), key=lambda f: f["rcept_dt"], reverse=True)[:MAX_DETAIL_CORPS]
        with ThreadPoolExecutor(max_workers=4) as pool:
            stakes = list(pool.map(lambda f: self.stake(f["corp_code"]), corps))
        changes = [{"name": f["corp_name"], "ticker": f["stock_code"], "corp_code": f["corp_code"], **s}
                   for f, s in zip(corps, stakes) if s]
        return sorted(changes, key=lambda c: (abs(c["change_pct"] or 0), c["date"]), reverse=True)
