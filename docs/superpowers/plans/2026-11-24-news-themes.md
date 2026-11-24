# 읽어볼 뉴스 구현 계획

설계: [2026-11-24-news-themes-design.md](../specs/2026-11-24-news-themes-design.md)

| 단계 | 내용 | 확인 |
|---|---|---|
| 1 | `GoogleNews.search` — RSS 파싱, 제목 끝 " - 언론사" 제거, 날짜 KST, 링크 검증 | `tests/test_news.py` (가짜 RSS) |
| 2 | `news_queries`·`pick_news`·`build_news` — 유망 업종 5개·테마, 중복 제거, 2개씩, 실패 격리 | `tests/test_news.py` |
| 3 | 스키마 `NewsItem/NewsGroup/NewsReport`, `Settings.news_themes`, settings.yaml | `tests/test_config.py` |
| 4 | CLI: 월요일 collect → news.json, publish → render(news) | `tests/test_cli_history.py` 등 |
| 5 | 템플릿 섹션 | `tests/test_render.py` |
| 6 | 실제 데이터 dry run(월요일 날짜), live 테스트 1개, 문서(INTENT·README·CLAUDE 구조) | 전체 테스트 |
