"""비공개 기록 저장소(체크아웃된 폴더)의 스냅샷 읽기·쓰기."""
import csv
import io
import json
from datetime import date
from pathlib import Path

CSV_HEADER = ["date", "total_krw", "kospi", "sp500", "usdkrw"]


def _num(value):
    return None if value is None else float(value)


class SnapshotStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.snap_dir = self.root / "snapshots"

    def _dates(self) -> list[date]:
        if not self.snap_dir.exists():
            return []
        out = []
        for p in self.snap_dir.glob("*.json"):
            try:
                out.append(date.fromisoformat(p.stem))
            except ValueError:
                continue
        return sorted(out)

    def _load(self, d: date) -> dict:
        return json.loads((self.snap_dir / f"{d.isoformat()}.json").read_text(encoding="utf-8"))

    def latest_before(self, d: date) -> dict | None:
        earlier = [x for x in self._dates() if x < d]
        return self._load(earlier[-1]) if earlier else None

    def on_or_before(self, d: date) -> dict | None:
        earlier = [x for x in self._dates() if x <= d]
        return self._load(earlier[-1]) if earlier else None

    def between(self, start: date, end: date) -> list[dict]:
        return [self._load(x) for x in self._dates() if start <= x <= end]

    def save(self, snapshot: dict) -> None:
        self.snap_dir.mkdir(parents=True, exist_ok=True)
        (self.snap_dir / f"{snapshot['date']}.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
        self._update_csv(snapshot)

    def _update_csv(self, snapshot: dict) -> None:
        path = self.root / "history" / "portfolio.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = {}
        if path.exists():
            for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))):
                rows[row["date"]] = row
        market = snapshot.get("market", {})
        idx = market.get("indices", {})
        rows[snapshot["date"]] = {
            "date": snapshot["date"], "total_krw": _num(snapshot.get("portfolio", {}).get("total_krw")),
            "kospi": _num(idx.get("KOSPI")), "sp500": _num(idx.get("S&P500")), "usdkrw": _num(market.get("fx_usdkrw"))}
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_HEADER, lineterminator="\n")
        writer.writeheader()
        for d in sorted(rows):
            writer.writerow(rows[d])
        path.write_text(buf.getvalue(), encoding="utf-8")
