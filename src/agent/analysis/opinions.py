"""살펴볼 곳 AI 의견: 웹 전용 AI에게 줄 지시문을 만들고, 답을 검증한다."""
import re

from agent.report.schema import Context, NewsGroup, NewsItem, NewsReport, Opinions, SectorOpinion, ThemeOpinion
from agent.report.validate import NUMBER_WITH_UNIT

MAX_CHARS = 200
LONG_NUMBER = re.compile(r"\d{6,}")
ADVICE = re.compile(r"사세요|파세요|매수하세요|매도하세요")


def numbered_news(news: NewsReport | None) -> list[tuple[int, NewsGroup, NewsItem]]:
    items = [(g, i) for g in (news.groups if news else []) for i in g.items]
    return [(n, g, i) for n, (g, i) in enumerate(items, start=1)]


def _themes(news: NewsReport | None) -> list[str]:
    return [g.name for g in (news.groups if news else []) if g.kind == "theme"]


def build_opinion_prompt(guide: str, context: Context, news: NewsReport | None) -> str:
    """대상(살펴볼 업종 또는 뉴스가 있는 테마)이 없으면 빈 문자열."""
    themes = _themes(news)
    if not context.opinion_sectors and not themes:
        return ""
    rows = {r.name: r for r in context.sectors if r.market == "KR"}
    lines = [guide, "", f"## 살펴볼 업종 (기준일 {context.date})"]
    for name in context.opinion_sectors:
        r = rows.get(name)
        picks = ", ".join(c.name for c in context.candidates if c.sector == name) or "없음"
        state = f"{r.method} {r.level}, 이익 {'늘고' if (r.earnings_1y_pct or 0) > 0 else '줄고'} 있음" if r else ""
        lines.append(f"- {name}: {state} · 후보 회사: {picks}")
    lines += ["", "## 테마", *(f"- {t}" for t in themes)]
    lines += ["", "## 읽어볼 뉴스 (번호)"]
    lines += [f"{n}. {i.title} — {i.source} ({i.date}) [{g.name}] {i.url}" for n, g, i in numbered_news(news)]
    return "\n".join(lines)


def _text_error(name: str, texts: list, sources) -> str | None:
    if not all(isinstance(t, str) and t.strip() for t in texts):
        return f"{name}: 글이 비었거나 문자가 아니에요"
    for t in texts:
        if len(t) > MAX_CHARS:
            return f"{name}: {MAX_CHARS}자를 넘었어요"
        for pattern, why in ((NUMBER_WITH_UNIT, "숫자"), (LONG_NUMBER, "긴 숫자"), (ADVICE, "권유 표현")):
            if m := pattern.search(t):
                return f"{name}: {why}를 쓸 수 없어요 ({m.group(0)})"
    if not (isinstance(sources, list) and 1 <= len(sources) <= 3
            and all(isinstance(s, str) and s.startswith(("https://", "http://")) for s in sources)):
        return f"{name}: 출처는 http(s) 링크 1~3개여야 해요"
    return None


def check_opinions(raw: dict, sectors: list[str], themes: list[str], news_count: int) -> tuple[Opinions, list[str]]:
    """지시문에 준 업종·테마만, 규칙을 지킨 항목만 남긴다. 어긴 항목만 버린다."""
    ops, errors = Opinions(), []
    for key, allowed, fields, model, target in (("sectors", sectors, ("up", "down", "watch"), SectorOpinion, ops.sectors),
                                                ("themes", themes, ("view",), ThemeOpinion, ops.themes)):
        entries = raw.get(key)
        for name, entry in (entries.items() if isinstance(entries, dict) else []):
            if name not in allowed or not isinstance(entry, dict):
                errors.append(f"{name}: 대상이 아니에요")
                continue
            if error := _text_error(name, [entry.get(f) for f in fields], entry.get("sources")):
                errors.append(error)
                continue
            target[name] = model(**{f: entry[f].strip() for f in fields}, sources=entry["sources"])
    drops = raw.get("drop_news")
    ops.drop_news = sorted({n for n in drops if type(n) is int and 1 <= n <= news_count}) if isinstance(drops, list) else []
    return ops, errors


def drop_news(news: NewsReport, drop: list[int]) -> NewsReport:
    kept: dict[int, list[NewsItem]] = {}
    for n, g, i in numbered_news(news):
        if n not in drop:
            kept.setdefault(id(g), []).append(i)
    groups = [g.model_copy(update={"items": kept[id(g)]}) for g in news.groups if id(g) in kept]
    return news.model_copy(update={"groups": groups})
