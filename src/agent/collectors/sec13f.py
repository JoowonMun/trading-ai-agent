"""국민연금(NPS)의 미국 주식 보유 — 13F 분기 보고서.

원본은 SEC EDGAR(CIK 1608046)지만 SEC가 한국 IP와 GitHub Actions(마이크로소프트 클라우드) IP를 모두
403으로 막아서, 같은 13F 데이터를 공개하는 13f.info의 JSON(티커 포함)을 쓴다. 비공식 제3자 사이트이므로
요청은 하루 몇 건으로 최소화하고 받은 분기 보고서는 캐시한다.
"""
import json
import re
import time
from pathlib import Path

import httpx

BASE = "https://13f.info"
MANAGER_PATH = "/manager/0001608046-national-pension-service"
DROP_TOKENS = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "THE", "SA", "NV", "AG"}
TOP_N = 5


def normalize_issuer(name: str) -> str:
    tokens = re.sub(r"[^A-Z0-9]+", " ", name.upper().replace("&", " ")).split()
    return " ".join(t for t in tokens if t not in DROP_TOKENS)


def aggregate(rows: list[list]) -> tuple[dict[str, dict], dict[str, str], dict[str, str]]:
    """13f.info 행 [티커, 회사명, 종류, CUSIP, 평가액($천), 비중, 주식수, 원금, 옵션] → CUSIP별 합산 (옵션 제외).

    회사명 표기는 분기마다 바뀌기도 해서(예: BANK AMERICA CORP → BANK OF AMER CORP) 증권 고유번호로 비교한다.
    돌려주는 값: (CUSIP별 보유, 티커→CUSIP, 정규화 회사명→CUSIP)
    """
    positions: dict[str, dict] = {}
    tickers: dict[str, str] = {}
    names: dict[str, str] = {}
    for sym, name, _cls, cusip, value, _pct, shares, _principal, option in rows:
        if option or not cusip:
            continue
        p = positions.setdefault(cusip, {"name": name, "shares": 0.0, "value": 0.0})
        p["shares"] += float(shares or 0)
        p["value"] += float(value or 0) * 1000
        if sym:
            tickers.setdefault(sym, cusip)
        names.setdefault(normalize_issuer(name or ""), cusip)
    return positions, tickers, names


class Nps13fClient:
    def __init__(self, cache_dir: Path, http: httpx.Client | None = None, sleep=time.sleep):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.http = http or httpx.Client(timeout=30, follow_redirects=True,
                                         headers={"User-Agent": "Mozilla/5.0 (personal portfolio report)"})
        self.sleep = sleep

    def _get(self, path: str) -> httpx.Response:
        self.sleep(0.5)
        resp = self.http.get(f"{BASE}{path}")
        resp.raise_for_status()
        return resp

    def _filings(self) -> list[tuple[str, str]]:
        """[(accession, '2026 Q2'), ...] 최신 분기부터, 분기당 하나."""
        html = self._get(MANAGER_PATH).text
        seen, out = set(), []
        for acc, q, year in re.findall(r'href="/13f/(\d+)-national-pension-service-q([1-4])-(\d{4})"', html):
            period = f"{year} Q{q}"
            if period not in seen:
                seen.add(period)
                out.append((acc, period))
        return sorted(out, key=lambda f: f[1], reverse=True)

    def _rows(self, acc: str) -> list[list]:
        cache = self.cache_dir / f"13f_{acc}.json"
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        rows = self._get(f"/data/13f/{acc}").json()["data"]
        try:
            cache.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return rows

    def report(self) -> dict:
        filings = self._filings()
        if len(filings) < 2:
            raise RuntimeError("국민연금 13F 보고서가 2개 미만입니다")
        (latest_acc, period), (prev_acc, prev_period) = filings[0], filings[1]
        now, tickers, names = aggregate(self._rows(latest_acc))
        prev, _, _ = aggregate(self._rows(prev_acc))

        # CUSIP가 바뀐 종목(기업 분할 등)은 회사명이 같으면 같은 종목으로 본다
        prev_unmatched = {normalize_issuer(p["name"] or ""): k for k, p in prev.items() if k not in now}
        matched_prev = {}
        for key, p in now.items():
            if key not in prev and (old := prev_unmatched.get(normalize_issuer(p["name"] or ""))):
                matched_prev[key] = old

        ranked = sorted(now.items(), key=lambda kv: kv[1]["value"], reverse=True)
        positions = {}
        for rank, (key, p) in enumerate(ranked, start=1):
            before = prev.get(key) or prev.get(matched_prev.get(key, ""))
            change = ((p["shares"] - before["shares"]) / before["shares"] * 100
                      if before and before["shares"] else None)
            added_value = p["value"] * (1 - before["shares"] / p["shares"]) if before and p["shares"] else p["value"]
            positions[key] = {**p, "rank": rank, "prev_shares": before["shares"] if before else None,
                              "change_pct": change, "new": before is None, "added_value": added_value}

        movers = sorted(positions.values(), key=lambda p: p["added_value"], reverse=True)
        sold_out = sorted(({"name": p["name"], "prev_shares": p["shares"], "prev_value": p["value"]}
                           for key, p in prev.items() if key not in now and key not in matched_prev.values()),
                          key=lambda p: p["prev_value"], reverse=True)
        return {
            "period": period, "prev_period": prev_period, "source": "13f.info (SEC 13F-HR)",
            "positions": positions, "tickers": tickers, "names": names,
            "top_holdings": [positions[k] for k, _ in ranked[:TOP_N]],
            "top_buys": [p for p in movers[:TOP_N] if p["added_value"] > 0],
            "top_sells": [p for p in reversed(movers[-TOP_N:]) if p["added_value"] < 0],
            "sold_out": sold_out[:TOP_N],
        }
