"""읽어볼 뉴스: 유망 업종·테마별 검색어를 정하고 기사를 고른다 (해석은 하지 않음)."""
from datetime import date, timedelta

from agent.analysis.quiet_signals import promising_sectors
from agent.report.schema import NewsGroup, NewsItem, NewsReport, SectorRow

# 업종 이름 그대로("금속 업종")는 엉뚱한 기사가 섞여서 업종마다 업계에서 쓰는 말로 검색한다
SECTOR_QUERIES = {
    "전기전자": "반도체 업황", "화학": "석유화학 업황", "금속": "철강 업황", "건설": "건설 수주",
    "기계·장비": "기계 수주", "운송장비·부품": "자동차 업황", "제약": "제약 업계", "음식료·담배": "식품 업계 실적",
    "유통": "유통업계 실적", "전기·가스": "전기요금 가스요금", "통신": "통신3사 실적", "금융": "은행 실적",
    "증권": "증권사 실적", "보험": "보험업계 실적", "IT 서비스": "IT 서비스 업계", "운송·창고": "해운 운임",
    "오락·문화": "엔터 실적",
}
SKIP_WORDS = ("특징주",)  # 하루 주가 움직임 기사 — 장기투자 판단 재료가 아니다
MAX_SECTORS = 5
PER_GROUP = 2
DAYS = 7


def news_queries(rows: list[SectorRow], themes: list[str]) -> list[tuple[str, str, str]]:
    """(묶음, 이름, 검색어). 유망 업종은 가격 위치가 낮은 순으로 최대 5개, 그다음 테마."""
    promising = sorted(promising_sectors(rows), key=lambda r: (r.percentile is None, r.percentile or 0))
    sectors = [("sector", r.name, SECTOR_QUERIES[r.name]) for r in promising if r.name in SECTOR_QUERIES]
    return sectors[:MAX_SECTORS] + [("theme", t, t) for t in themes]


def _norm(title: str) -> str:
    return " ".join(title.split())


def pick_news(items: list[dict], seen: set[str], today: date) -> list[NewsItem]:
    """최근 7일 기사 중 최신 2개. 앞 묶음에 나온 제목은 건너뛴다."""
    since = (today - timedelta(days=DAYS)).isoformat()
    picked = []
    for i in sorted(items, key=lambda i: i["date"], reverse=True):
        key = _norm(i["title"])
        if i["date"] < since or key in seen or any(w in key for w in SKIP_WORDS):
            continue
        seen.add(key)
        picked.append(NewsItem(**{**i, "title": key}))
        if len(picked) == PER_GROUP:
            break
    return picked


def build_news(source, rows: list[SectorRow], themes: list[str], today: date) -> NewsReport:
    groups, errors = [], []
    seen: set[str] = set()
    queries = news_queries(rows, themes)
    for kind, name, query in queries:
        try:
            items = pick_news(source.search(query, days=DAYS), seen, today)
        except Exception as e:
            errors.append((name, str(e).splitlines()[0]))
            continue
        if items:
            groups.append(NewsGroup(kind=kind, name=name, query=query, items=items))
    if queries and len(errors) == len(queries):
        return NewsReport(missing=[f"뉴스: {errors[0][1]}"])
    return NewsReport(groups=groups, missing=[f"뉴스 {name}: {why}" for name, why in errors])
