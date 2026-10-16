"""국민연금(NPS)의 미국 주식 보유 — SEC 13F-HR 분기 보고서.

국민연금 CIK 1608046. 분기 말 기준, 분기 종료 후 약 45일 안에 공개된다.
SEC는 한국 IP를 차단(403)하므로 실제 조회는 GitHub Actions(미국)에서만 된다.
13F에는 티커가 없어 회사 영문명을 정규화해서 내 종목(yfinance 회사명)과 맞춘다.
"""
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

NPS_CIK = 1608046
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"
DROP_TOKENS = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "THE", "SA", "NV", "AG"}
TOP_N = 5


def normalize_issuer(name: str) -> str:
    tokens = re.sub(r"[^A-Z0-9]+", " ", name.upper().replace("&", " ")).split()
    return " ".join(t for t in tokens if t not in DROP_TOKENS)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_info_table(xml_text: str) -> dict[str, dict]:
    """정보표 XML → {정규화 회사명: {name, shares, value}} (옵션 제외, 주식 종류는 합산)."""
    positions: dict[str, dict] = {}
    for row in ET.fromstring(xml_text).iter():
        if _local(row.tag) != "infoTable":
            continue
        fields = {_local(el.tag): (el.text or "").strip() for el in row.iter()}
        if fields.get("putCall"):
            continue
        key = normalize_issuer(fields.get("nameOfIssuer", ""))
        p = positions.setdefault(key, {"name": fields.get("nameOfIssuer"), "shares": 0.0, "value": 0.0})
        p["shares"] += float(fields.get("sshPrnamt") or 0)
        p["value"] += float(fields.get("value") or 0)
    return positions


class Sec13fClient:
    def __init__(self, user_agent: str, cache_dir: Path, http: httpx.Client | None = None, cik: int = NPS_CIK,
                 sleep=time.sleep):
        self.cik = cik
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.http = http or httpx.Client(timeout=30)
        self.headers = {"User-Agent": user_agent}
        self.sleep = sleep

    def _get(self, url: str) -> httpx.Response:
        self.sleep(0.2)  # SEC 공정 사용 한도(초당 10회) 준수
        resp = self.http.get(url, headers=self.headers)
        resp.raise_for_status()
        return resp

    def _filings(self) -> list[dict]:
        recent = self._get(SUBMISSIONS.format(cik=self.cik)).json()["filings"]["recent"]
        rows = [{"form": f, "acc": a, "filed": d, "period": p} for f, a, d, p in
                zip(recent["form"], recent["accessionNumber"], recent["filingDate"], recent["reportDate"])]
        originals = [r for r in rows if r["form"] == "13F-HR"]  # 정정보고(13F-HR/A)는 제외
        return sorted(originals, key=lambda r: r["filed"], reverse=True)

    def _positions(self, acc: str) -> dict[str, dict]:
        cache = self.cache_dir / f"13f_{acc}.json"
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        base = ARCHIVE.format(cik=self.cik, acc=acc.replace("-", ""))
        items = self._get(f"{base}/index.json").json()["directory"]["item"]
        xml_name = next(i["name"] for i in items
                        if i["name"].lower().endswith(".xml") and i["name"].lower() != "primary_doc.xml")
        positions = parse_info_table(self._get(f"{base}/{xml_name}").text)
        try:
            cache.write_text(json.dumps(positions, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return positions

    def report(self) -> dict:
        filings = self._filings()
        if len(filings) < 2:
            raise RuntimeError("국민연금 13F 보고서가 2개 미만입니다")
        latest, previous = filings[0], filings[1]
        now, prev = self._positions(latest["acc"]), self._positions(previous["acc"])

        ranked = sorted(now.items(), key=lambda kv: kv[1]["value"], reverse=True)
        positions = {}
        for rank, (key, p) in enumerate(ranked, start=1):
            before = prev.get(key)
            change = ((p["shares"] - before["shares"]) / before["shares"] * 100
                      if before and before["shares"] else None)
            added_value = p["value"] * (1 - (before["shares"] / p["shares"])) if before and p["shares"] else p["value"]
            positions[key] = {**p, "rank": rank, "prev_shares": before["shares"] if before else None,
                              "change_pct": change, "new": before is None, "added_value": added_value}

        movers = sorted(positions.values(), key=lambda p: p["added_value"], reverse=True)
        sold_out = sorted(({"name": p["name"], "prev_shares": p["shares"], "prev_value": p["value"]}
                           for key, p in prev.items() if key not in now), key=lambda p: p["prev_value"], reverse=True)
        return {
            "period": latest["period"], "filed": latest["filed"], "prev_period": previous["period"],
            "positions": positions,
            "top_holdings": [positions[k] for k, _ in ranked[:TOP_N]],
            "top_buys": [p for p in movers[:TOP_N] if p["added_value"] > 0],
            "top_sells": [p for p in reversed(movers[-TOP_N:]) if p["added_value"] < 0],
            "sold_out": sold_out[:TOP_N],
        }
