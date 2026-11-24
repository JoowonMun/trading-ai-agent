"""뉴스: 구글 뉴스 RSS (키 없음, 비공식 — 실패를 전제로 쓴다)."""
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from agent.config import KST

RSS_URL = "https://news.google.com/rss/search"
LINK_PREFIX = "https://news.google.com/"
MAX_TITLE = 150


class GoogleNews:
    def __init__(self, http: httpx.Client | None = None):
        self.http = http or httpx.Client(timeout=20, follow_redirects=True, transport=httpx.HTTPTransport(retries=2))

    def search(self, query: str, days: int = 7) -> list[dict]:
        """최근 days일 기사. 웹에서 온 글이라 링크는 구글 뉴스 주소만 받고 제목 길이를 자른다."""
        resp = self.http.get(RSS_URL, params={"q": f"{query} when:{days}d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
        resp.raise_for_status()
        items = []
        for node in ET.fromstring(resp.content).iter("item"):
            url = (node.findtext("link") or "").strip()
            source = (node.findtext("source") or "").strip()
            title = (node.findtext("title") or "").strip()
            pub = node.findtext("pubDate")
            if not (url.startswith(LINK_PREFIX) and title and pub):
                continue
            if source and title.endswith(f" - {source}"):
                title = title[: -len(source) - 3]
            items.append({"title": title[:MAX_TITLE], "source": source[:40],
                          "date": parsedate_to_datetime(pub).astimezone(KST).date().isoformat(), "url": url})
        return items
