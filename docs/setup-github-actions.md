# 매일 자동 발송 설정 (GitHub Actions)

`.github/workflows/daily-report.yml`이 **월~금 07:00(한국시간)** 에 실행된다.
데이터 수집 → Claude Code(구독)가 AI 해설 작성 → 검증 → 메일 발송.

## 1. Claude 구독 토큰 발급 (1회)
PC 터미널에서:
```
claude setup-token
```
브라우저에서 로그인하면 `sk-ant-oat...`로 시작하는 토큰이 출력된다. 이 값을 다음 단계의 `CLAUDE_CODE_OAUTH_TOKEN`에 넣는다. (채팅에 붙여넣지 말 것)

## 2. GitHub Secrets 등록
저장소 → Settings → Secrets and variables → Actions → **New repository secret**으로 아래 이름과 값을 하나씩 등록한다. 값은 로컬 `.env`와 같다.

| 이름 | 필수 |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | ✅ (AI 해설) |
| `DART_API_KEY` | ✅ |
| `NH_APP_KEY`, `NH_APP_SECRET` | ✅ |
| `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` | ✅ |
| `MAIL_TO` | 선택 |
| `KRX_ID`, `KRX_PW` | 선택 (수급) |

### 빠른 방법: GitHub CLI로 .env 한 번에 등록
```
winget install GitHub.cli
gh auth login
gh secret set -f .env --repo JoowonMun/trading-ai-agent
gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo JoowonMun/trading-ai-agent
```
(마지막 명령은 토큰을 붙여넣으라고 물어본다)

## 3. 수동 실행으로 확인
저장소 → Actions → daily-report → **Run workflow**. 끝나면 메일함을 확인한다.

## 참고
- 로그에는 성공/실패만 남고 보유 내역은 남지 않는다(저장소 공개 대비).
- 나무 토큰은 실행마다 새로 받으므로 **평일마다 NH 보안 알림 1건**이 온다.
- 수집이 실패하면 "생성 실패" 메일이, AI 해설이 실패하면 숫자 리포트가 발송된다.
- 실행 시각은 GitHub 사정으로 몇 분~수십 분 늦어질 수 있다.
