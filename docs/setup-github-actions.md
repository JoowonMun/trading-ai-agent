# 매일 자동 발송 설정 (GitHub Actions)

`.github/workflows/daily-report.yml`이 **월~금 06:17(한국시간)** 에 실행된다. GitHub 예약 실행은 수십 분~2시간 늦어질 수 있다.
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

## 알림 + 주간 리포트 (기록 저장소)
- 매일 결과 요약(스냅샷)을 비공개 저장소 `JoowonMun/trading-ai-agent-data`에 커밋한다. 접근은 그 저장소에만 쓰기 권한이 있는 deploy key(Secret `DATA_REPO_DEPLOY_KEY`).
- **월요일**: 전체 리포트 + 지난주 대비 / **화~금**: 직전 기록 대비 변화(신호 변경, 기준가 통과, ±5% 변동, 새 공시, 국민연금 신고, 미국 실적 D-3)가 있을 때만 알림 메일. 변화가 없으면 메일·AI 해설을 건너뛴다.
- 첫 실행은 기준 스냅샷만 저장한다(월요일이 아니면 메일 없음).
- 수동 실행의 "메일을 보내지 않고 점검만"(dry_run)은 스냅샷도 저장하지 않는다.
- 큰 변동 기준은 `config/settings.yaml`의 `alert_move_pct`(기본 5).
