# 알림 + 주간 리포트 설계 (발전 로드맵 ①)

- 작성일: 2026-10-20
- 상위 설계: `2026-10-15-trading-ai-agent-design.md`
- 로드맵: ① 알림 + 주간 리포트(이 문서) → ② "왜 움직였나" AI 조사 → ③ 성과 추적 → ④ 새 종목 발굴

## 1. 문제와 목표

장기투자 기준으로는 하루 사이 판단이 거의 바뀌지 않아 매일 같은 전체 리포트가 반복된다. 읽을 이유가 없는 메일은 결국 안 읽게 된다.

- 평일: **의미 있는 변화가 있을 때만** 짧은 알림 메일. 없으면 메일을 보내지 않는다.
- 월요일: 전체 리포트 + **지난주 대비 변화**를 담은 주간 리포트.
- 이를 위해 매일 결과를 **비공개 기록 저장소**에 스냅샷으로 남긴다(③ 성과 추적도 이 기록을 쓴다).

### 성공 기준
1. 화~금에 알림 조건이 하나도 없으면 메일이 오지 않고, 하나라도 있으면 바뀐 것만 담긴 알림 메일이 온다.
2. 월요일에는 주간 리포트가 오며 종목별 1주 수익률·신호 변화·비중 변화·그 주 알림 목록이 들어 있다.
3. 기록 저장소에 날짜별 스냅샷과 일별 평가금액 이력이 쌓인다. 시험 실행(dry_run)은 기록을 남기지 않는다.
4. 공개 저장소·Actions 로그에는 보유 종목·스냅샷 내용이 남지 않는다.

## 2. 알림 조건 (평일)

직전 스냅샷(휴일 등으로 빠진 날이 있으면 가장 최근 것)과 오늘 context를 비교한다.

| 종류 | 조건 | 비고 |
|---|---|---|
| `signal_change` | 신호가 직전과 다름 (둘 다 있을 때) | "가나전자: 보유 → 추가매수" |
| `level_cross` | 현재가가 분할매수 1~3단계·일부매도 1~2차·재검토가를 새로 통과 | 오늘의 기준가로 판정. 직전 종가와 오늘 종가가 기준가 양쪽에 있을 때 |
| `big_move` | 직전 기록 대비 등락률 절댓값 ≥ `alert_move_pct`(기본 5) | 설정 가능 |
| `disclosure` | 직전 스냅샷에 없던 공시 | 악재 유형은 강조 |
| `nps` | 내 종목의 국민연금 지분 신고일이 직전보다 새로움 | 국내 |
| `earnings_soon` | 미국 종목 실적 발표가 0~3일 안 | yfinance 일정. 같은 발표일로 이미 알린 경우 반복하지 않음. 국내는 무료 일정 데이터가 없어 실적 공시가 나오면 `disclosure`로 잡힌다 |

알림 문구는 코드가 만든다. AI는 알림마다 의미를 한두 문장으로 풀어 쓴다(숫자 검증 규칙 동일).

## 3. 메일 종류 결정

| 조건 | 메일 |
|---|---|
| 월요일 | 주간 리포트 (기존 전체 리포트 + "지난주 대비" 섹션). 7일 전 이전 가장 가까운 스냅샷과 비교 |
| 화~금, 알림 ≥ 1 | 알림 메일 (짧게: 알림 목록 + AI 한 줄 해설 + 3줄 요약) |
| 화~금, 알림 0 | 보내지 않음. 로그 "변화 없음" |
| 직전 스냅샷 없음 (첫 실행) | 화~금은 보내지 않고 스냅샷만 저장. 월요일은 "지난주 대비" 없이 주간 리포트 |

AI 해설 단계는 메일을 보내지 않는 날 실행하지 않는다(구독 사용량 절약).

## 4. 주간 리포트의 "지난주 대비"

- 종목별: 1주 수익률(지난주 스냅샷 종가 대비), 신호 변화, 비중 변화(%p)
- 포트폴리오: 총평가액 변화율, 자산군 비중 변화
- 지수: KOSPI·S&P500 1주 등락
- 그 주 보낸 알림 목록(지난주~오늘 사이 스냅샷의 `alerts`)
- 지난주에 없던 종목은 "신규 편입", 사라진 종목은 "전량 매도"

## 5. 기록 저장소

- GitHub 비공개 저장소 `JoowonMun/trading-ai-agent-data`, 이 저장소에만 쓰기 권한이 있는 **deploy key**(SSH)로 접근. 개인 키는 공개 저장소 Secret `DATA_REPO_DEPLOY_KEY`.
- 파일
  - `snapshots/YYYY-MM-DD.json`: 날짜, 종목별(티커·이름·시장·종가·신호·기준가 6종·비중·국민연금 지분/신고일·공시 URL 목록·다음 실적일), 포트폴리오(총평가액·현금·자산군 비중), 지수 종가·환율, 보낸 알림
  - `history/portfolio.csv`: `date,total_krw,kospi,sp500,usdkrw` 날짜별 한 줄(같은 날 재실행 시 덮어씀)
- 스냅샷에는 AI 해설·키·계좌번호를 넣지 않는다.
- 저장은 발송이 끝난 뒤. 시험 실행(`dry_run`)은 저장·커밋하지 않는다.

## 6. 구성 요소

| 모듈 | 책임 |
|---|---|
| `history/snapshot.py` | `make_snapshot(context, alerts)` — context → 스냅샷 dict |
| `history/store.py` | `SnapshotStore(root)`: `latest_before(date)`, `on_or_before(date)`, `between(start, end)`, `save(snapshot)` (+ CSV 갱신) |
| `analysis/alerts.py` | `detect_alerts(prev, context, settings) -> list[Alert]` |
| `analysis/weekly.py` | `weekly_diff(prev_week, context, week_alerts) -> WeeklyDiff` |
| `report/schema.py` | `Alert`, `WeeklyDiff`, `Context.report_type`(`weekly`/`alert`/`none`), `Context.alerts`, `Context.weekly`, `HoldingContext.next_earnings`, `Analysis.alert_comments` |
| `report/templates/alert.html` | 알림 메일 |
| CLI | `collect --history-dir DIR` (알림·주간 계산, `report_type` 결정), `publish`(report_type `none`이면 발송 생략), `save-snapshot --history-dir DIR` |
| 워크플로 | 데이터 저장소 체크아웃(deploy key) → collect → report_type이 none이면 AI·발송 생략 → 발송 → 스냅샷 커밋·푸시 (dry_run 제외) |

검증기는 `report_type`이 `alert`일 때 `holdings`를 비워도 되게 하고(채운다면 기존 규칙 그대로), `alert_comments`의 숫자도 검사한다.

## 7. 오류 처리

- 기록 저장소 체크아웃 실패 → 직전 스냅샷 없음으로 취급(첫 실행과 동일), 로그 경고. 발송은 계속.
- 스냅샷 저장·푸시 실패 → 메일은 이미 발송됨. 단계 실패로 표시해 다음 확인 때 보이게 한다.
- yfinance 실적 일정 실패 → `earnings_soon`만 생략.

## 8. 테스트

- `detect_alerts`: 조건별 발생/미발생, 기준가 상향·하향 통과, 직전 스냅샷 없음, 실적 알림 중복 방지
- `SnapshotStore`: 최근/7일 전 조회, 빠진 날, CSV 덮어쓰기
- `weekly_diff`: 수익률·신규/매도 종목·그 주 알림
- report_type 결정(요일·알림 유무·첫 실행), 알림 메일 렌더링, 검증기 alert 모드
- 워크플로 파일 문법·일정 테스트 유지
