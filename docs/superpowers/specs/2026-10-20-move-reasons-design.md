# "왜 움직였나" AI 조사 설계 (발전 로드맵 ②)

- 작성일: 2026-10-20
- 선행: `2026-10-20-alerts-weekly-design.md` (알림·주간 리포트)

## 1. 목표

크게 움직인 보유 종목에 대해 AI가 **스스로 웹을 검색**해 원인을 찾아 2~3문장으로 요약하고, 출처 링크와 함께 알림·주간 리포트에 붙인다.
무엇을 검색할지 AI가 판단하는 에이전트 단계다. 숫자를 만들지 않는다는 원칙(INTENT.md)은 그대로 지킨다.

## 2. 조사 대상 (코드가 정함)

| 메일 | 대상 |
|---|---|
| 알림 (화~금) | `big_move` 알림이 있는 종목 |
| 주간 (월) | 지난주 대비 수익률 절댓값 ≥ `research_weekly_move_pct`(기본 7)인 보유 종목 |
| 공통 | 변동폭 큰 순, 최대 `research_max`(기본 3)종목. 메일을 보내지 않는 날(none)과 기록 비교가 없는 실행(로컬)은 대상 없음 |

`Context.research_targets: list[str]`(티커)에 담는다.

## 3. 조사 결과 형식

`Analysis.move_reasons: dict[str, MoveReason]`, `MoveReason = {found: bool, summary: str, sources: list[str]}`

## 4. 검증 (코드)

- 키는 `research_targets` 안의 티커여야 한다.
- `found=true`면 `sources`에 `http(s)://` 링크 1~3개.
- `summary`에 단위 붙은 숫자(원·달러·$·%·배, 만·억·조 포함) 금지 — 뉴스 속 숫자는 검증할 수 없으므로 "실적이 크게 늘었어요"처럼 쓴다.
- 검증 실패 시 **조사 결과만 제외**하고(실행 메모에 사유) 나머지 AI 해설과 리포트는 그대로 발송한다.

## 5. AI 조사 규칙 (prompts/analysis-guide.md)

- 대상 종목마다 WebSearch(필요하면 WebFetch)로 최근 며칠의 원인을 찾는다. 종목당 검색 3회 이내.
- 출처 우선순위: 거래소·공시(DART, SEC), 회사 발표, 주요 언론(국내 경제지·통신사, Reuters·Bloomberg·CNBC 등). 출처가 불분명한 블로그·커뮤니티·기계 번역 사이트는 쓰지 않는다.
- 실제로 읽은 페이지만 출처로 적는다. 확신이 없으면 `found=false`, "뚜렷한 원인을 찾지 못했어요".
- 업종·시장 전체 흐름 때문이라면 그렇게 쓴다(개별 악재로 단정하지 않는다).

## 6. 구성

| 모듈 | 변경 |
|---|---|
| `report/schema.py` | `MoveReason`, `Context.research_targets`, `Analysis.move_reasons` |
| `config.py` | `research_weekly_move_pct=7`, `research_max=3` |
| `analysis/research.py` | `pick_research_targets(ctx, settings) -> list[str]` |
| `__main__.py` | `apply_history`에서 대상 지정, `publish`·`check`에서 조사 결과 별도 검증 |
| `report/validate.py` | `check_move_reasons(analysis, context) -> list[str]` |
| 템플릿 | 종목 카드에 "🔎 왜 움직였나" (요약 + 출처 도메인 링크) |
| 워크플로 | Claude Code `--allowedTools`에 `WebSearch`, `WebFetch` 추가 |

## 7. 확인된 사실

- 2026-10-20: 구독 OAuth 토큰으로 headless Claude Code가 WebSearch 도구를 사용함을 확인. 결과 출처 품질이 들쭉날쭉해 출처 우선순위 규칙이 필요.

## 8. 테스트

- 대상 선정: 알림/주간/none, 상한 3, 정렬
- 검증: 대상 외 티커, 출처 없음, 단위 숫자 포함, 정상, found=false
- publish: 조사 결과만 실패하면 나머지 해설은 유지
- 렌더: 요약·출처 링크 표시
- 워크플로: allowedTools에 WebSearch
