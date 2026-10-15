"""OpenDART API 클라이언트 (https://opendart.fss.or.kr)."""
import io
import json
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

import httpx

from agent.analysis.financials import REPORT_CODES, parse_amount, quarter_end

BASE_URL = "https://opendart.fss.or.kr/api"
CORP_CODE_MAX_AGE_SEC = 7 * 24 * 3600


class DartError(RuntimeError):
    pass


def disclosure_url(rcept_no: str) -> str:
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


class DartClient:
    def __init__(self, api_key: str, cache_dir: Path, http: httpx.Client | None = None,
                 today: date | None = None):
        self.api_key = api_key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.http = http or httpx.Client(timeout=30, transport=httpx.HTTPTransport(retries=2))
        self.today = today or date.today()
        self._corp_codes: dict[str, str] | None = None

    def _get_json(self, endpoint: str, **params) -> dict | None:
        resp = self.http.get(f"{BASE_URL}/{endpoint}", params={"crtfc_key": self.api_key, **params})
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        if status == "013":
            return None
        if status != "000":
            raise DartError(f"{endpoint}: {status} {data.get('message', '')}")
        return data

    def _load_corp_codes(self) -> dict[str, str]:
        cache = self.cache_dir / "corp_codes.json"
        if cache.exists() and time.time() - cache.stat().st_mtime < CORP_CODE_MAX_AGE_SEC:
            return json.loads(cache.read_text(encoding="utf-8"))
        resp = self.http.get(f"{BASE_URL}/corpCode.xml", params={"crtfc_key": self.api_key})
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            root = ET.fromstring(zf.read(zf.namelist()[0]))
        codes = {}
        for el in root.iter("list"):
            stock_code = (el.findtext("stock_code") or "").strip()
            if stock_code:
                codes[stock_code] = el.findtext("corp_code").strip()
        cache.write_text(json.dumps(codes), encoding="utf-8")
        return codes

    def corp_code(self, stock_code: str) -> str:
        if self._corp_codes is None:
            self._corp_codes = self._load_corp_codes()
        try:
            return self._corp_codes[stock_code]
        except KeyError:
            raise DartError(f"DART에서 종목코드 {stock_code}를 찾을 수 없습니다") from None

    def company(self, corp_code: str) -> dict:
        return self._get_json("company.json", corp_code=corp_code) or {}

    def financial_rows(self, corp_code: str, year: int, quarter: int) -> list[dict] | None:
        cache = self.cache_dir / f"fin_{corp_code}_{year}_{quarter}.json"
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        rows = None
        for fs_div in ("CFS", "OFS"):
            data = self._get_json("fnlttSinglAcntAll.json", corp_code=corp_code, bsns_year=str(year),
                                  reprt_code=REPORT_CODES[quarter], fs_div=fs_div)
            if data and data.get("list"):
                rows = data["list"]
                break
        if rows is not None and year < self.today.year:
            cache.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return rows

    def _past_periods(self, start_year: int) -> list[tuple[int, int]]:
        return [(y, q) for y in range(start_year, self.today.year + 1) for q in range(1, 5)
                if quarter_end(y, q) <= self.today]

    def quarterly_reports(self, corp_code: str, years: int) -> dict[tuple[int, int], list[dict]]:
        out = {}
        for year, quarter in self._past_periods(self.today.year - years):
            rows = self.financial_rows(corp_code, year, quarter)
            if rows:
                out[(year, quarter)] = rows
        return out

    def shares_outstanding(self, corp_code: str) -> float | None:
        for year, quarter in reversed(self._past_periods(self.today.year - 2)):
            data = self._get_json("stockTotqySttus.json", corp_code=corp_code, bsns_year=str(year),
                                  reprt_code=REPORT_CODES[quarter])
            for row in (data or {}).get("list", []):
                if row.get("se", "").replace(" ", "") == "보통주":
                    value = parse_amount(row.get("istc_totqy"))
                    if value:
                        return value
        return None

    def dividend_per_share(self, corp_code: str) -> float | None:
        for year in (self.today.year - 1, self.today.year - 2):
            data = self._get_json("alotMatter.json", corp_code=corp_code, bsns_year=str(year),
                                  reprt_code=REPORT_CODES[4])
            for row in (data or {}).get("list", []):
                if ("주당현금배당금" in row.get("se", "").replace(" ", "")
                        and row.get("stock_knd") in (None, "", "보통주")):
                    return parse_amount(row.get("thstrm")) or 0.0
        return None

    def disclosures(self, corp_code: str, start: date, end: date) -> list[dict]:
        data = self._get_json("list.json", corp_code=corp_code, bgn_de=start.strftime("%Y%m%d"),
                              end_de=end.strftime("%Y%m%d"), page_count="100")
        return (data or {}).get("list", [])
