# CLAUDE.md — 개발 지침

이 저장소에서 작업할 때 따르는 규칙. **무엇을·왜** 만드는지는 @INTENT.md 를 먼저 읽는다.

## 1. 작업 원칙 (Karpathy guidelines)

LLM이 코딩하며 흔히 저지르는 실수를 줄이기 위한 원칙. 속도보다 신중함 쪽으로 기운다 — 사소한 작업은 판단껏.

### 코딩 전에 생각한다
- 가정을 드러낸다. 불확실하면 묻는다.
- 해석이 여러 개면 조용히 하나를 고르지 말고 선택지를 보여준다.
- 더 단순한 방법이 있으면 말한다. 필요하면 반대 의견을 낸다.
- 헷갈리는 게 있으면 멈추고, 무엇이 헷갈리는지 말한다.

### 단순하게
- 요청받지 않은 기능, 한 번 쓰는 추상화, 요청받지 않은 설정 가능성은 만들지 않는다.
- 일어날 수 없는 상황의 예외 처리는 넣지 않는다.
- 200줄로 썼는데 50줄로 될 것 같으면 다시 쓴다. "시니어가 보면 과하다고 할까?"를 자문한다.

### 필요한 곳만 고친다
- 옆 코드·주석·포맷을 "개선"하지 않는다. 고장 나지 않은 것을 리팩터링하지 않는다. 기존 스타일을 따른다.
- 관련 없는 죽은 코드를 발견하면 지우지 말고 알린다.
- 내 변경으로 안 쓰이게 된 import·변수·함수는 지운다.
- 바뀐 모든 줄이 요청으로 거슬러 올라가야 한다.

### 목표를 검증 가능하게
- "검증 추가" → 잘못된 입력 테스트를 쓰고 통과시킨다. "버그 수정" → 재현 테스트를 쓰고 통과시킨다.
- 여러 단계 작업은 `단계 → 확인 방법` 형태로 짧은 계획을 먼저 말한다.

## 2. 이 프로젝트의 규칙

### 개발 흐름
- 새 기능: 설계(`docs/superpowers/specs/`) → 구현 계획(`docs/superpowers/plans/`) → **테스트 먼저(TDD)** → 구현. 사용자가 각 단계를 승인한다.
- 테스트가 실패하는 것을 먼저 보고, 통과시키고, **전체 테스트**를 돌린 뒤 커밋한다.
- 실제 데이터로 확인할 땐 `--dry-run`(로컬) 또는 Actions의 `dry_run=true`(메일·스냅샷 없음)를 쓴다. 실제 발송은 사용자에게 메일이 가므로 필요할 때만.

### 절대 깨면 안 되는 불변식
- **숫자는 코드가 계산한다.** AI 해설(`analysis.json`)의 단위 붙은 숫자는 `report/validate.py`가 context 값과 대조한다. 새로운 숫자를 해설에 노출하려면 context(또는 `Alert.values`)에 먼저 넣는다.
- 신호 우선순위 review > trim > add > hold. AI는 add → hold 하향만 가능(사유 필수).
- 날짜는 항상 한국시간(`config.today_kst`). Actions는 UTC에서 돈다.
- 데이터 소스 하나의 실패가 리포트 전체를 멈추면 안 된다(해당 항목만 누락 표시). 전체 실패면 실패 알림 메일.

### 개인정보·보안 (저장소는 공개다)
- 보유 종목·계좌번호·평가금액·개인 투자 상황을 코드·문서·테스트·커밋 메시지에 쓰지 않는다. 예시는 가상의 회사·가짜 숫자로.
- 커밋 작성자는 `JoowonMun <274365675+JoowonMun@users.noreply.github.com>` (저장소 로컬 git 설정).
- Actions 로그는 공개다. 출력은 성공/실패·개수만, 종목은 `(KR|US):<종목>`, 6자리 이상 숫자는 `<num>`으로 가린다. 보유 내역이 담긴 출력은 파일로만.
- 키는 `.env`(로컬)·GitHub Secrets(Actions)만. `config/holdings.yaml`, `out/`, `.cache/`, `data/`는 git 제외.
- 기록(스냅샷)은 비공개 저장소 `JoowonMun/trading-ai-agent-data`에만. 주문 API는 호출하지 않는다(`collectors/nh.py`의 `ALLOWED_PATHS`).
- **웹을 읽는 AI와 파일·명령을 다루는 AI를 섞지 않는다(프롬프트 인젝션 방어).** 원인 조사 AI는 `--tools "WebSearch,WebFetch"`만, 해설 AI는 웹 도구 없음. 비밀값은 job 전체가 아니라 필요한 단계에만, AI 단계엔 Claude 토큰만. 웹에서 온 결과는 코드가 검증한 뒤에만 리포트에 들어간다.

### 사용자에게 보이는 글
- 리포트·메일·알림 문구는 한국어 해요체, 초보자 기준으로 쉽게.

## 3. 명령어

```bash
uv sync --extra dev
uv run pytest -q -p no:warnings          # 단위 테스트 (외부 호출 없음)
uv run pytest -m live -q                  # 실제 API 호출 테스트
uv run python -m agent run --dry-run      # 로컬 수집→preview.html (메일 없음)
uv run python -m agent collect|check|publish|save-snapshot [--date YYYY-MM-DD] [--history-dir DIR]
uv run python scripts/render_sample.py    # README용 샘플 리포트
gh workflow run daily-report.yml -f dry_run=true   # Actions 점검 실행
```

## 4. 구조

```
src/agent/collectors/  dart · nh(잔고, 조회 전용) · prices · us_fundamentals · nps · sec13f(13f.info)
src/agent/analysis/    financials · fundamentals · valuation · signals · assessment · portfolio
                       · disclosures · indicators · alerts · weekly · research
src/agent/history/     snapshot · store (비공개 기록 저장소)
src/agent/report/      context(오케스트레이션) · schema · validate · render · templates/{email,alert}.html · glossary
src/agent/__main__.py  CLI
prompts/               analysis-guide.md(해설 AI 규칙) · daily-prompt.md · research-guide.md(원인 조사 AI 규칙)
.github/workflows/     daily-report.yml(평일 06:17 KST) · tests.yml(CI)
```

## 5. 겪어본 함정 (다시 밟지 않기)

- **워크플로 YAML을 셸(sed·python 문자열)로 고치지 않는다.** `\1` 같은 이스케이프가 제어 문자로 바뀌어 GitHub가 파일을 못 읽고 예약 실행이 조용히 멈춘 적이 있다. 편집 도구로 고치고 `tests/test_workflows.py`를 돌린다.
- **DART:** 반기·3분기 손익 `thstrm_amount`는 3개월치, `thstrm_add_amount`가 누적. 해외(Actions)에서는 응답이 건당 수 초 → 캐시·병렬 요청 유지. 주식수 항목명이 "의결권 있는\n보통주"인 회사가 있다.
- **SEC EDGAR는 한국 IP와 GitHub Actions(Azure) IP를 모두 403으로 막는다** → 13F는 13f.info, 미국 재무는 yfinance.
- **pykrx**는 KRX 로그인(`KRX_ID`/`KRX_PW`)이 필요한 함수가 많고, 로그인 시 아이디를 print한다(`prices._quiet`로 숨김). 1.2.x 이상 필요.
- **yfinance**는 최근 종가를 NaN으로 줄 때가 있다 → `dropna`. 공식 데이터가 아니므로 실패를 전제로 짠다.
- **httpx INFO 로그는 URL 전체를 찍는다**(DART 키가 쿼리에 있음) → `httpx` 로거는 WARNING.
- **나무 토큰**은 다른 곳에서 새로 받으면 기존 토큰이 무효가 된다(재발급 1회 재시도). 발급마다 NH 보안 알림이 간다.
- **GitHub 예약 실행**은 정각에 몰려 수십 분~2시간 늦을 수 있다. 공개 저장소는 60일간 커밋이 없으면 예약이 꺼진다.
