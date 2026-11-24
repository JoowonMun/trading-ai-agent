from datetime import date

import httpx
import pytest

from agent.analysis.news import SECTOR_QUERIES, build_news, news_queries, pick_news
from agent.collectors.news import GoogleNews
from agent.collectors.sectors import KR_SECTORS
from agent.report.schema import SectorRow

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>t</title>
<item><title>가짜중공업, 원전 펌프 인증 획득 - 가짜신문</title>
<link>https://news.google.com/rss/articles/AAA?oc=5</link>
<pubDate>Fri, 20 Nov 2026 16:30:00 GMT</pubDate><source url="https://fake.example">가짜신문</source></item>
<item><title>수상한 링크 - 어딘가</title><link>javascript:alert(1)</link>
<pubDate>Fri, 20 Nov 2026 01:00:00 GMT</pubDate><source url="https://x">어딘가</source></item>
<item><title>날짜 없는 기사 - 가짜일보</title><link>https://news.google.com/rss/articles/BBB</link>
<source url="https://y">가짜일보</source></item>
</channel></rss>"""


def client(text=RSS, status=200, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request.url)
        return httpx.Response(status, text=text)
    return GoogleNews(http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_search_parses_items_and_drops_bad_links():
    seen = []
    items = client(seen=seen).search("원전", days=7)
    assert items == [{"title": "가짜중공업, 원전 펌프 인증 획득", "source": "가짜신문",
                      "date": "2026-11-21", "url": "https://news.google.com/rss/articles/AAA?oc=5"}]  # KST 날짜
    assert seen[0].params["q"] == "원전 when:7d" and seen[0].params["hl"] == "ko"


def test_search_truncates_long_title():
    long = RSS.replace("가짜중공업, 원전 펌프 인증 획득", "가" * 300)
    assert len(client(long).search("원전")[0]["title"]) == 150


def test_search_raises_on_http_error():
    with pytest.raises(httpx.HTTPStatusError):
        client(status=503).search("원전")


def test_every_kr_sector_has_a_query():
    assert {name for _, name, _ in KR_SECTORS} <= set(SECTOR_QUERIES)


def row(name, percentile, e=10.0, level="싸요", market="KR"):
    return SectorRow(key=f"{market}:{name}", name=name, market=market, method="PBR", percentile=percentile,
                     level=level, earnings_1y_pct=e)


def test_news_queries_cheapest_promising_sectors_then_themes():
    rows = [row("유통", 40, level="보통"), row("금속", 5), row("건설", 10, e=-3), row("보험", 20), row("화학", 25),
            row("증권", 28), row("통신", 35, level="보통"), row("기술", 1, market="US")]
    queries = news_queries(rows, ["원전", "조선"])
    assert queries == [("sector", "금속", "철강 업황"), ("sector", "보험", SECTOR_QUERIES["보험"]),
                       ("sector", "화학", SECTOR_QUERIES["화학"]), ("sector", "증권", SECTOR_QUERIES["증권"]),
                       ("sector", "통신", SECTOR_QUERIES["통신"]),
                       ("theme", "원전", "원전"), ("theme", "조선", "조선")]


def item(title, d="2026-11-20"):
    return {"title": title, "source": "가짜신문", "date": d, "url": f"https://news.google.com/rss/articles/{title}"}


def test_pick_news_newest_first_two_each_and_dedupes_across_groups():
    seen: set[str] = set()
    first = pick_news([item("A", "2026-11-18"), item("B", "2026-11-21"), item("C", "2026-11-20")], seen,
                      today=date(2026, 11, 23))
    second = pick_news([item("B "), item("D", "2026-11-10"), item("E")], seen, today=date(2026, 11, 23))
    assert [i.title for i in first] == ["B", "C"]
    assert [i.title for i in second] == ["E"]   # B는 중복, D는 7일 넘음


def test_pick_news_skips_short_term_stock_tips():
    picked = pick_news([item("[특징주] 가짜전자 10% 급등"), item("가짜전자, 설비 증설")], set(), today=date(2026, 11, 23))
    assert [i.title for i in picked] == ["가짜전자, 설비 증설"]


class FakeSource:
    def __init__(self, fail=()):
        self.fail = fail

    def search(self, query, days=7):
        if query in self.fail:
            raise RuntimeError(f"막힘 {query}\n자세히")
        return [item(f"{query} 기사1"), item(f"{query} 기사2"), item(f"{query} 기사3")]


def test_build_news_isolates_failures():
    report = build_news(FakeSource(fail={"조선"}), [row("금속", 5)], ["원전", "조선"], date(2026, 11, 23))
    assert [(g.kind, g.name, g.query, len(g.items)) for g in report.groups] == [
        ("sector", "금속", "철강 업황", 2), ("theme", "원전", "원전", 2)]
    assert report.missing == ["뉴스 조선: 막힘 조선"]


def test_build_news_all_failed_is_one_line():
    report = build_news(FakeSource(fail={"철강 업황", "원전"}), [row("금속", 5)], ["원전"], date(2026, 11, 23))
    assert report.groups == [] and report.missing == ["뉴스: 막힘 철강 업황"]


@pytest.mark.live
def test_google_news_live():
    items = GoogleNews().search("원전")
    assert items and all(i["url"].startswith("https://news.google.com/") for i in items)
