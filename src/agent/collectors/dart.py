"""OpenDART API 클라이언트 (https://opendart.fss.or.kr)."""
import io
import json
import logging
import time
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import httpx

from agent.analysis.financials import REPORT_CODES, parse_amount, quarter_end
from agent.collectors.common import NotACompany

log = logging.getLogger(__name__)

BASE_URL = "https://opendart.fss.or.kr/api"
CORP_CODE_MAX_AGE_SEC = 7 * 24 * 3600


class DartError(RuntimeError):
    pass


class NotInDart(DartError, NotACompany):
    """DART 고유번호 목록에 없는 종목 (ETF·ETN·펀드 등)."""


def _write_cache(path: Path, text: str) -> None:
    """캐시는 속도용 보조 수단 — Windows 백신 등이 파일을 잠가 저장에 실패해도 분석은 계속한다."""
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        log.warning("DART 캐시 저장 실패 %s: %s", path.name, e)


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
        _write_cache(cache, json.dumps(codes))
        return codes

    def corp_code(self, stock_code: str) -> str:
        if self._corp_codes is None:
            self._corp_codes = self._load_corp_codes()
        try:
            return self._corp_codes[stock_code]
        except KeyError:
            raise NotInDart(f"DART에서 종목코드 {stock_code}를 찾을 수 없습니다") from None

    def _cached_json(self, name: str, max_age_sec: float | None, fetch):
        """name 캐시가 있고 충분히 새것이면 그걸, 아니면 fetch() 결과를 저장해 돌려준다 (None은 저장 안 함)."""
        cache = self.cache_dir / name
        if cache.exists() and (max_age_sec is None or time.time() - cache.stat().st_mtime < max_age_sec):
            return json.loads(cache.read_text(encoding="utf-8"))
        value = fetch()
        if value is not None:
            _write_cache(cache, json.dumps(value, ensure_ascii=False))
        return value

    def company(self, corp_code: str) -> dict:
        return self._cached_json(f"company_{corp_code}.json", 30 * 24 * 3600,
                                 lambda: self._get_json("company.json", corp_code=corp_code)) or {}

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
        if rows is not None:  # 제출된 보고서는 바뀌지 않는다 — 미제출(None)만 매번 다시 확인
            _write_cache(cache, json.dumps(rows, ensure_ascii=False))
        return rows

    def _past_periods(self, start_year: int) -> list[tuple[int, int]]:
        return [(y, q) for y in range(start_year, self.today.year + 1) for q in range(1, 5)
                if quarter_end(y, q) <= self.today]

    def quarterly_reports(self, corp_code: str, years: int) -> dict[tuple[int, int], list[dict]]:
        periods = self._past_periods(self.today.year - years)
        # 해외(GitHub Actions)에서는 DART 응답이 건당 수 초라 동시에 요청한다
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = pool.map(lambda p: self.financial_rows(corp_code, *p), periods)
        return {period: rows for period, rows in zip(periods, results) if rows}

    def shares_outstanding(self, corp_code: str) -> float | None:
        return self._cached_json(f"shares_{corp_code}.json", 7 * 24 * 3600,
                                 lambda: self._fetch_shares(corp_code))

    def _fetch_shares(self, corp_code: str) -> float | None:
        for year, quarter in reversed(self._past_periods(self.today.year - 2)):
            data = self._get_json("stockTotqySttus.json", corp_code=corp_code, bsns_year=str(year),
                                  reprt_code=REPORT_CODES[quarter])
            for row in (data or {}).get("list", []):
                label = "".join(row.get("se", "").split())  # "의결권 있는\n보통주" → "의결권있는보통주"
                if label.endswith("보통주") and "없는" not in label:
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
