# 트레이딩 AI 에이전트 설계 문서

- 작성일: 2026-10-15
- 상태: 설계 확정 대기 (사용자 리뷰 전)

## 1. 목적

주식 지표를 잘 모르는 개인 투자자가 **매일 아침 근거가 붙은 투자 리포트**를 받아,
보유 종목의 매수·매도 판단과 포트폴리오 조정을 직접 할 수 있게 돕는다.

- 판단의 기준 데이터: 국민연금 국내·해외 주식 보유 변동, 기업 공시, 재무지표, 시세
- 모든 지표에는 "이 숫자가 무슨 뜻이고 왜 좋은지/나쁜지"를 쉬운 말로 붙인다
- 주문은 당분간 사용자가 직접 한다. 자동매매는 마지막 단계(나무 PLUG, 모의투자 선행)
- 이 리포트는 개인 참고용이며 투자 권유가 아니다. 모든 리포트에 면책 문구를 넣는다

### 성공 기준
1. 매일 07:30(KST) 전에 메일 뉴스레터가 도착하고, 같은 내용의 상세본이 노션 DB에 쌓인다
2. 보유 종목마다 판단(보유/추가매수/일부매도/재검토)과 가격, 그 근거 지표가 나온다
3. 리포트의 모든 가격은 코드가 계산한 값과 일치한다 (AI가 숫자를 지어내지 않는다)
4. 데이터 소스 일부가 실패해도 리포트는 발송된다

## 2. 대상 사용자와 전제

| 항목 | 내용 |
|---|---|
| 계좌 | 증권사 API로 잔고를 조회할 수 있는 계좌(현재 NH투자증권 나무) + API가 없는 계좌는 수동 입력 |
| 투자 성향 | 설정으로 선택 (기본값: 균형형, 장기투자) |
| 받는 곳 | 메일(뉴스레터, 길어도 됨) + 노션(상세 아카이브) |
| 실행 | Claude Code Routines(구독) 기본, GitHub Actions + Claude API 예비 |
| 저장소 | 비공개 GitHub 저장소 |

## 3. 범위

### 포함
- 보유 종목 분석 리포트 (국내·미국)
- 국민연금 보유 변동 추적 (국내 연간 목록, DART 5% 공시, 미국 13F)
- 공시 요약 (DART, SEC)
- 포트폴리오 비중 점검과 리밸런싱 제안 (여러 계좌 합산)
- 주간 관심 종목 추천 (국민연금 보유 종목 중)
- 부가 정보(선택): 수급, 거시지표, 시장 지수, 뉴스, 실적 일정

### 제외 (이번 설계 범위 밖)
- 실시간·장중 알림
- 자동 주문 (5단계에서 별도 설계)
- 증권사 컨센서스 목표주가 (공식 무료 API 없음)
- API가 없는 증권사 계좌 연동 (`holdings.yaml` 수동 입력)

## 4. 데이터 소스

### 4.1 필수 소스

| 소스 | 용도 | 인증 | 주기 |
|---|---|---|---|
| 공공데이터포털 「국민연금공단_국내주식 투자정보」 | 국민연금 국내 전체 보유 목록(평가액, 비중, 지분율) | 서비스키 | 연 1회 (연말 기준, 이듬해 공개) |
| OpenDART | 공시 목록, 대량보유(5%) 보고, 국내 재무제표(분기) | API 키 | 매일 |
| SEC EDGAR | 국민연금 13F(미국 보유), 미국 기업 재무(companyfacts) | 키 없음 (User-Agent에 연락처 필수) | 13F 분기, 재무 분기 |
| pykrx | 국내 시세, 지수 | 키 없음 | 매일 |
| yfinance | 미국 시세, 환율(USD/KRW) | 키 없음 | 매일 |

- 국민연금 SEC CIK는 구현 시 EDGAR에서 확인해 `settings.yaml`에 고정한다.
- 국민연금 변동은 저장 없이 출처에서 바로 비교한다: DART 대량보유 공시는 그 자체가 변동 이벤트이고, 13F는 직전 분기 보고서와 비교한다.

### 4.2 선택 소스 (있으면 좋은 것)

키가 없거나 호출이 실패하면 **해당 섹션만 빠지고 리포트는 정상 발송**된다.

| 소스 | 용도 | 인증 | 도입 단계 |
|---|---|---|---|
| pykrx 투자자별 매매동향 | 외국인·기관 순매수 (국내) | 없음 | 1 |
| yfinance 지수 | KOSPI, S&P500, VIX | 없음 | 1 |
| 한국은행 ECOS | 기준금리, 환율, 물가 | API 키 | 2 |
| FRED | 미국 기준금리, 10년물 국채금리, CPI | API 키 | 2 |
| SEC EDGAR 8-K / Form 4 | 미국 기업 주요 공시, 임원 매매 | 없음 | 2 |
| 네이버 검색 API | 보유 종목 뉴스 헤드라인 | Client ID/Secret | 2 |
| Finnhub (무료 티어) | 미국 실적 발표 일정 | API 키 | 4 |

예비 소스(문서화만): 금융위원회 주식시세정보 API (pykrx 장애 시 대체).

## 5. 분석 설계

모든 숫자 계산은 `analysis/` 코드가 결정적으로 수행한다. AI는 계산 결과를 해석·설명만 한다.

### 5.1 종목별 지표

| 구분 | 지표 | 계산 기준 |
|---|---|---|
| 밸류에이션 | PER, PBR, 배당수익률 | TTM(최근 4분기) 기준. 자기 과거 5년 분포와 비교 |
| 수익성 | ROE, 영업이익률 | TTM |
| 성장성 | 매출·영업이익 YoY | 최근 분기 vs 전년 동기 |
| 안정성 | 부채비율 | 최근 분기 |
| 추세 (보조) | 20/60/120일 이동평균 대비 위치, 52주 고저 대비 위치, RSI(14) | 일봉 |
| 국민연금 | 신규/증가/감소/변동없음 | DART 5% 공시, 13F 분기 비교 |
| 공시 | 최근 7일 공시 목록, 유형 분류(실적/증자/자사주/배당/기타) | DART, SEC |

장기투자 성향이므로 판단은 밸류에이션·수익성·성장성 위주로 하고, 추세 지표는 매수·매도 **시점** 보조 근거로만 쓴다.

### 5.2 가격 계산 (valuation.py)

증권사 컨센서스(예상 EPS)가 무료로 없으므로 **TTM EPS 기준 PER 밴드**를 쓴다.

1. 과거 5년간 월말 PER 시계열 = 월말 종가 / 당시 TTM EPS
2. 분위수 P10, P25, P50, P75, P90 계산
3. 가격:
   - 적정가 = TTM EPS × P50
   - 분할매수 3단계 = TTM EPS × P25, × (P10+P25)/2, × P10
   - 일부매도 목표 = TTM EPS × P75 (보유의 1/3), × P90 (추가 1/3)
   - 재검토 기준가 = 평균매수가 × (1 − 0.15)
4. 대체 규칙:
   - 금융업(은행·보험·증권) 또는 TTM EPS ≤ 0 → PBR 밴드 + BPS로 동일 계산
   - 5년 데이터가 3년 미만이면 가격을 내지 않고 "데이터 부족"으로 표시
5. 재검토 기준가 도달은 자동 손절이 아니라 "투자 이유가 아직 유효한지 다시 보라"는 알림이다 (장기투자 성향 반영).

### 5.3 판단 신호 (코드가 계산)

| 신호 | 조건 |
|---|---|
| 추가매수 | 현재가 ≤ 분할매수 1단계 가격 AND 영업이익 YoY > −30% AND 부채비율 < 200% AND 종목 비중 < 최대 비중 |
| 일부매도 | 현재가 ≥ 일부매도 1차 목표 OR 종목 비중 > 최대 비중 |
| 재검토 | 현재가 ≤ 재검토 기준가 OR 최근 7일 내 악재 유형 공시(유상증자, 감사의견 비적정 등) |
| 보유 | 위에 해당 없음 |

여러 조건이 겹치면 우선순위는 재검토 > 일부매도 > 추가매수 > 보유.
AI가 바꿀 수 있는 신호는 **추가매수 → 보유** 한 가지뿐이며, 이때 이유를 반드시 적는다. 일부매도·재검토·보유 신호는 바꿀 수 없고, 새 가격을 만들 수도 없다.

### 5.4 포트폴리오 점검 (portfolio.py)

- 전체 자산 = 모든 계좌의 국내 + 미국(원화 환산) + 지수 ETF + 현금
- 자산군 목표 비중 기본값: 국내 30% / 미국 40% / 지수 30% (`settings.yaml`에서 수정)
- 자산군 비중이 목표에서 ±5%p 넘게 벗어나면 리밸런싱 제안 (어느 쪽을 얼마 줄이고 늘릴지 금액으로)
- 단일 종목 비중 > 15%면 경고
- 내 보유 종목과 국민연금 상위 50 종목의 겹침 표시

### 5.5 주간 관심 종목 (screener.py, 4단계)

- 후보군: 국민연금 국내 보유 목록 + 13F 보유 목록 − 내 보유 종목
- 점수 = 밸류에이션(PER 밴드 위치가 낮을수록) + 수익성(ROE) + 성장성(영업이익 YoY) + 국민연금 최근 증가 여부
- 부채비율 200% 이상, 적자 종목 제외
- 매주 월요일 리포트에 상위 2~3개를 추천, 나머지 요일은 지난 추천의 현재 상태만 표시

### 5.6 성향 기준값 (균형형 B)

```yaml
profile:
  name: balanced
  review_drawdown_pct: 15      # 재검토 기준 하락폭
  max_single_weight_pct: 15    # 단일 종목 최대 비중
  rebalance_band_pct: 5        # 자산군 비중 허용 오차
  buy_tranches: 3              # 분할매수 횟수
target_allocation:
  domestic: 30
  us: 40
  index: 30
```

## 6. 시스템 구조

### 6.1 저장소 구조

```
trading-ai-agent/
├─ config/
│  ├─ settings.yaml          # 성향 기준값, 목표 비중, 발송 설정, 모델, 국민연금 CIK
│  └─ holdings.yaml          # 내 보유 종목 (수동 입력)
├─ src/agent/
│  ├─ __main__.py            # CLI: collect / analyze / publish / run
│  ├─ collectors/
│  │   ├─ nps.py             # 공공데이터포털
│  │   ├─ dart.py            # OpenDART
│  │   ├─ sec.py             # 13F, companyfacts, 8-K, Form 4
│  │   ├─ prices.py          # pykrx, yfinance, 환율, 지수
│  │   ├─ flows.py           # 외국인·기관 수급 (선택)
│  │   ├─ macro.py           # ECOS, FRED (선택)
│  │   ├─ news.py            # 네이버 뉴스 (선택)
│  │   └─ calendar.py        # 실적 일정 (선택)
│  ├─ analysis/
│  │   ├─ indicators.py
│  │   ├─ valuation.py
│  │   ├─ signals.py
│  │   ├─ portfolio.py
│  │   └─ screener.py
│  ├─ report/
│  │   ├─ context.py         # context.json 생성
│  │   ├─ schema.py          # context / analysis 스키마 (pydantic)
│  │   ├─ validate.py        # analysis.json 검증
│  │   ├─ glossary.py        # 지표 용어 풀이 사전
│  │   └─ templates/         # 메일 HTML, 노션 블록 (Jinja2)
│  ├─ delivery/
│  │   ├─ email.py           # SMTP 발송 (기본 네이버 메일)
│  │   └─ notion.py          # Notion API
│  └─ llm/
│      └─ api_analyzer.py    # API 모드 분석 (예비)
├─ prompts/analysis-guide.md # AI 분석 규칙
├─ docs/
│  ├─ superpowers/specs/
│  └─ setup-keys.md          # API 키 발급 방법
├─ tests/
├─ pyproject.toml
├─ .env.example
└─ .gitignore                # .env, out/ 제외
```

- 언어/도구: Python 3.12, pyproject.toml, pytest
- 주요 라이브러리: httpx, pandas, pykrx, yfinance, pydantic, jinja2, pyyaml, notion-client, anthropic(API 모드 전용)

### 6.2 `holdings.yaml` 형식

```yaml
accounts:
  - name: 나무 국내
    broker: nh
    market: KR
    asset_class: domestic
    positions:
      - { ticker: "005930", name: 삼성전자, qty: 10, avg_price: 71000 }
  - name: 나무 미국
    broker: nh
    market: US
    asset_class: us
    positions:
      - { ticker: AAPL, qty: 5, avg_price: 185.2 }   # avg_price는 USD
  - name: 다른 증권사 계좌
    broker: other
    market: KR
    asset_class: index
    analyze: false            # 지수 ETF: 개별 분석 없이 비중 계산에만 사용
    positions:
      - { ticker: "360750", name: TIGER 미국S&P500, qty: 30, avg_price: 18500 }
cash_krw: 0
```

### 6.3 매일 실행 흐름

```
07:00 Routine 시작 (setup: pip install -e .)
  │
  ├─ 1. python -m agent collect
  │     수집 → 지표·가격·신호·비중 계산 → out/YYYY-MM-DD/context.json
  │
  ├─ 2. Claude(Routine 세션)가 context.json + prompts/analysis-guide.md를 읽고
  │     out/YYYY-MM-DD/analysis.json 작성
  │
  └─ 3. python -m agent publish
        analysis.json 검증 → 메일 발송 + 노션 페이지 생성
```

- API 모드: 2단계를 `python -m agent analyze --api`로 대체 (GitHub Actions cron에서 실행). 모델은 `settings.yaml`의 `llm.model`.
- `python -m agent run --dry-run`: 로컬에서 1~3단계를 실행하되 발송 대신 `out/YYYY-MM-DD/preview.html` 생성. 2단계는 `--api`를 주면 API 모드로, 안 주면 생략하고 숫자 리포트로 만든다.
- 신호 값: `add`(추가매수), `hold`(보유), `trim`(일부매도), `review`(재검토).
- Routine은 저장소에 커밋·푸시하지 않는다. 이력은 노션에 남는다.

### 6.4 `context.json` (코드 → AI)

```json
{
  "date": "2026-10-16",
  "market": { "indices": {}, "fx_usdkrw": 0, "macro": {}, "missing": [] },
  "holdings": [
    {
      "ticker": "005930", "name": "삼성전자", "market": "KR",
      "position": { "qty": 10, "avg_price": 71000, "weight_pct": 8.2 },
      "price": { "close": 0, "ma20": 0, "ma60": 0, "ma120": 0, "rsi14": 0, "pos_52w_pct": 0 },
      "fundamentals": { "per": 0, "pbr": 0, "roe": 0, "op_margin": 0, "rev_yoy": 0, "op_yoy": 0, "debt_ratio": 0, "div_yield": 0 },
      "valuation": { "method": "PER", "band": {}, "fair": 0, "buy": [0, 0, 0], "sell": [0, 0], "review": 0 },
      "signal": "hold",
      "nps": { "status": "unchanged", "detail": "" },
      "disclosures": [], "flows": {}, "news": [], "events": [],
      "missing": []
    }
  ],
  "portfolio": { "by_class": {}, "rebalance": [], "warnings": [], "nps_overlap": [] },
  "nps_changes": [],
  "watchlist": [],
  "glossary_terms": ["PER", "ROE"]
}
```

### 6.5 `analysis.json` (AI → 코드)

```json
{
  "date": "2026-10-16",
  "summary": ["3줄 요약 1", "2", "3"],
  "market_comment": "시장 분위기 한 단락",
  "holdings": [
    {
      "ticker": "005930",
      "signal": "hold",
      "signal_downgraded_reason": null,
      "headline": "한 줄 판단",
      "reasoning": "근거 설명 (context의 숫자만 인용)",
      "indicator_notes": [{ "term": "PER", "value": "12.3", "plain": "쉬운 풀이" }],
      "disclosure_notes": "공시·뉴스 요약"
    }
  ],
  "portfolio_comment": "비중·리밸런싱 설명",
  "watchlist_comment": "관심 종목 설명 (월요일)"
}
```

### 6.6 검증 규칙 (validate.py)

1. 스키마 일치 (pydantic)
2. `holdings`의 ticker 집합이 context와 동일
3. `signal`은 context의 신호와 같아야 함. 예외는 context가 `add`(추가매수)이고 analysis가 `hold`이면서 `signal_downgraded_reason`이 비어 있지 않은 경우뿐
4. 텍스트 안의 단위 붙은 숫자(원, 달러/$, %, 배)는 context에 있는 값과 일치해야 함 (표시 반올림 허용). 날짜·횟수 등 단위 없는 숫자는 검사하지 않음
5. 실패 시: AI 텍스트를 버리고 context만으로 만든 "숫자 리포트"를 발송, 실패 사유를 리포트 하단에 표시

### 6.7 `prompts/analysis-guide.md` 핵심 규칙

- 독자는 주식 초보다. 전문 용어는 처음 나올 때 풀어서 쓴다
- context.json에 없는 숫자를 만들지 않는다
- 신호는 낮출 수만 있고, 낮추면 이유를 쓴다
- 각 종목 판단에 근거 지표를 최소 2개 인용한다
- 장기투자 관점: 단기 등락보다 실적·가치 변화를 우선 설명한다
- 출력은 analysis.json 스키마를 정확히 따른다

## 7. 리포트 구성

### 7.1 메일 (뉴스레터, HTML)
1. 오늘의 3줄 요약
2. 시장 분위기 (지수, VIX, 환율, 금리 — 선택 소스 있을 때)
3. 보유 종목 카드: 판단 배지 + 현재가/적정가/분할매수가/매도목표가/재검토가 + 근거 + 지표 풀이
4. 포트폴리오 점검: 자산군 비중 vs 목표, 리밸런싱 제안, 경고
5. 국민연금·공시 변동
6. 관심 종목 (월요일 신규 추천, 그 외 추적)
7. 오늘 등장한 용어 풀이
8. 노션 상세 링크, 실행 로그(소요 시간, 누락 소스), 면책 문구

### 7.2 노션
- 데이터베이스 「Daily Reports」: 속성 = 날짜, 3줄 요약, 신호 개수(추가매수/일부매도/재검토), 상태(정상/숫자 리포트)
- 날짜별 페이지: 메일 내용 전체 + 종목별 원본 지표 표, PER 밴드 분위수, 가격 계산 과정, 공시 원문 링크

## 8. 오류 처리

| 상황 | 동작 |
|---|---|
| 필수 소스 일부 실패 | 해당 종목/섹션에 "데이터 누락" 표시, 나머지 진행 |
| 선택 소스 키 없음/실패 | 해당 섹션 생략, 로그에 기록 |
| 시세 자체 실패 (전 종목) | 숫자 없이 "오늘 리포트 생성 실패" 메일만 발송 |
| analysis.json 검증 실패/없음 | 숫자 리포트로 대체 발송 |
| 노션 실패 | 메일은 발송, 메일 하단에 노션 실패 표시 |
| 메일 실패 | 노션은 생성, 프로세스는 실패 코드로 종료 |
| 외부 API 호출 | 타임아웃 + 2회 재시도, 소스별 호출 간격 준수(SEC 초당 10회 이하 등) |

## 9. 테스트

- `analysis/`: 고정 샘플 데이터로 단위 테스트 (PER 밴드 분위수, 가격, 신호 우선순위, 비중·리밸런싱 금액, 데이터 부족 분기)
- `collectors/`: 저장해 둔 응답(fixtures)으로 파싱 테스트. 실제 호출 테스트는 `-m live` 마커로 분리
- `report/validate.py`: 정상/숫자 위조/신호 상향/ticker 누락 케이스
- `--dry-run`으로 생성한 preview.html을 사람이 확인

## 10. 비밀 정보

- 로컬: `.env` (git 제외), `.env.example`에 키 이름만
- Routine: 클라우드 환경 환경변수
- GitHub Actions(예비): Repository Secrets
- 키 목록: `DART_API_KEY`, `DATA_GO_KR_KEY`, `SEC_USER_AGENT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`, `MAIL_TO`(선택), `SMTP_HOST`/`SMTP_PORT`(선택, 기본 smtp.naver.com:465), `NOTION_TOKEN`, `NOTION_DATABASE_ID` / 선택: `ECOS_API_KEY`, `FRED_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `FINNHUB_API_KEY` / API 모드: `ANTHROPIC_API_KEY`
- 발급 방법은 `docs/setup-keys.md`에 정리

## 11. 구현 단계

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| 1. MVP | holdings.yaml, 국내 종목 시세·재무(DART)·지표·PER 밴드·신호, DART 공시, 수급·지수, 포트폴리오 점검, 메일 발송, dry-run | 로컬에서 국내 보유 종목 리포트 메일 수신 |
| 2. 확장 | 미국 종목(SEC companyfacts, yfinance), 국민연금(공공데이터포털, DART 5%, 13F), 노션, ECOS·FRED·8-K·Form 4·뉴스 | 국내+미국+국민연금 섹션이 있는 메일과 노션 페이지 |
| 3. 자동화 | Routine 구성(환경변수, setup, 지시문), 외부 접속 확인 스파이크, API 모드 + GitHub Actions 예비 경로 | 3일 연속 07:30 전 자동 수신 |
| 4. 추천 | 주간 관심 종목 스크리너, 실적 일정 | 월요일 리포트에 추천 2~3개 |
| 5. 증권사 | 나무 PLUG 잔고 조회로 holdings 자동 동기화 → 모의투자 자동매매 (별도 설계) | 별도 설계 문서 |

## 12. 위험과 미확인 사항

- **Routine 외부 접속**: 클라우드 환경에서 DART·data.go.kr·KRX·SEC 접속이 허용되는지 3단계 첫 작업으로 확인. 막히면 API 모드(GitHub Actions)로 전환
- **Routine은 베타**: 실행 지연, 사양 변경 가능. 구독 사용량 한도와 공유
- **pykrx·yfinance는 비공식**: 사이트 변경 시 깨질 수 있음. 예비 소스 문서화
- **TTM 기반 PER 밴드의 한계**: 실적이 급변하는 종목(턴어라운드, 적자 전환)은 가격이 왜곡될 수 있음. 리포트에 계산 방식과 한계를 함께 표시
- **국민연금 데이터 지연**: 국내 전체 목록은 연 1회, 13F는 약 45일 지연. 리포트에 기준일 명시
- **나무 PLUG 세부 사양**: 모의투자 지원 여부 등 5단계 착수 시 확인. 대안은 한국투자증권 KIS API
