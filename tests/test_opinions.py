from factories import sample_context

from agent.analysis.opinions import build_opinion_prompt, check_opinions, drop_news, numbered_news
from agent.report.schema import Candidate, NewsGroup, NewsItem, NewsReport, SectorRow


def ctx():
    c = sample_context()
    c.sectors = [SectorRow(key="KR:1011", name="금속", market="KR", method="PBR", value=0.68, percentile=12.0,
                           level="싸요", earnings_1y_pct=91.2)]
    c.opinion_sectors = ["금속"]
    c.candidates = [Candidate(ticker="000001", name="가짜제철", sector="금속", method="PBR", value=0.4,
                              sector_median=0.85)]
    return c


def item(t):
    return NewsItem(title=t, source="가짜신문", date="2026-11-20", url=f"https://news.google.com/rss/articles/{t}")


def news():
    return NewsReport(groups=[NewsGroup(kind="sector", name="금속", query="철강 업황", items=[item("철강A"), item("철강B")]),
                              NewsGroup(kind="theme", name="원전", query="원전", items=[item("원전A")])])


def test_numbered_news():
    assert [(n, g.name, i.title) for n, g, i in numbered_news(news())] == [
        (1, "금속", "철강A"), (2, "금속", "철강B"), (3, "원전", "원전A")]
    assert numbered_news(None) == []


def test_prompt_lists_sectors_candidates_themes_and_numbered_news():
    p = build_opinion_prompt("지침 본문", ctx(), news())
    assert p.startswith("지침 본문")
    assert "금속" in p and "PBR 싸요" in p and "가짜제철" in p
    assert "원전" in p and "3. 원전A" in p and "https://news.google.com/rss/articles/철강A" in p


def test_prompt_empty_without_targets():
    c = ctx()
    c.opinion_sectors = []
    assert build_opinion_prompt("지침", c, None) == ""
    assert build_opinion_prompt("지침", c, NewsReport()) == ""


def test_prompt_themes_only_when_no_sectors():
    c = ctx()
    c.opinion_sectors = []
    p = build_opinion_prompt("지침", c, news())
    assert "원전" in p and "가짜제철" not in p


def test_prompt_without_news_has_only_sectors():
    p = build_opinion_prompt("지침", ctx(), None)
    assert "금속" in p and "원전" not in p


GOOD = {"up": "조선·건설 쪽 수요가 회복된다는 전망이 나왔어요", "down": "중국산 저가 제품이 계속 들어올 수 있어요",
        "watch": "다음 분기 실적과 중국 수출 흐름", "sources": ["https://news.example/a"]}


def test_check_keeps_valid_and_drops_bad_entries():
    raw = {"sectors": {"금속": GOOD, "모르는업종": GOOD},
           "themes": {"원전": {"view": "해외 수주 기대가 이어지고 있어요", "sources": ["https://x.example/b"]},
                      "조선업": {"view": "좋아요", "sources": ["https://x.example/c"]}}}
    ops, errors = check_opinions(raw, ["금속"], ["원전"], 3)
    assert list(ops.sectors) == ["금속"] and list(ops.themes) == ["원전"]
    assert len(errors) == 2


def bad(**change):
    return check_opinions({"sectors": {"금속": {**GOOD, **change}}}, ["금속"], [], 0)


def test_check_rejects_numbers_codes_advice_length_and_sources():
    for change in ({"up": "이익이 30% 늘었어요"}, {"down": "가짜제철(000001)이 약해요"}, {"watch": "지금 사세요"},
                   {"up": "가" * 201}, {"sources": []}, {"sources": ["https://a.example"] * 4},
                   {"sources": ["ftp://a.example"]}, {"up": 3}):
        ops, errors = bad(**change)
        assert ops.sectors == {} and len(errors) == 1, change


def test_check_drop_news_only_valid_numbers():
    ops, _ = check_opinions({"drop_news": [2, 0, 99, "x", 2]}, [], [], 5)
    assert ops.drop_news == [2]
    assert check_opinions({"drop_news": "2"}, [], [], 5)[0].drop_news == []


def test_check_ignores_non_dict_input():
    ops, errors = check_opinions({"sectors": ["금속"], "themes": None}, ["금속"], [], 0)
    assert ops.sectors == {} and ops.themes == {}


def test_drop_news_removes_items_and_empty_groups():
    kept = drop_news(news(), [3, 1])
    assert [(g.name, [i.title for i in g.items]) for g in kept.groups] == [("금속", ["철강B"])]
