# API 키 발급 안내 (1단계)

키는 `.env` 파일에만 넣고 git에 올리지 않는다 (`.env.example`을 복사해서 `.env`로 저장).

## OpenDART API 키 (필수)
1. https://opendart.fss.or.kr 회원가입
2. 상단 메뉴 "인증키 신청/관리" → 인증키 신청 (개인, 사용 목적: 개인 투자 분석)
3. 발급된 40자리 키를 `DART_API_KEY`에 입력
- 하루 호출 한도: 20,000건 (이 프로그램은 종목당 첫 실행 약 30건, 이후 캐시로 감소)

## 네이버 메일 SMTP (필수)
1. 네이버 메일 → 환경설정 → POP3/IMAP 설정 → "SMTP 사용: 사용함" 저장
2. 네이버 2단계 인증을 쓰는 경우: 네이버 내정보 → 보안설정 → 2단계 인증 → "애플리케이션 비밀번호 관리"에서 "직접 입력"으로 비밀번호 생성 (안 쓰면 네이버 로그인 비밀번호 사용 — 보안상 2단계 인증 + 애플리케이션 비밀번호 권장)
3. `.env`에 입력: `SMTP_USER`=네이버 아이디, `SMTP_PASSWORD`=위 비밀번호, `MAIL_FROM`=아이디@naver.com
- 받는 주소를 다르게 하려면 `MAIL_TO`에 입력
- Gmail 등 다른 서비스로 바꾸려면 `SMTP_HOST`, `SMTP_PORT`만 바꾸고 해당 서비스의 앱 비밀번호 사용

## KRX 정보데이터시스템 계정 (선택)
1. https://data.krx.co.kr 회원가입 (무료)
2. 아이디·비밀번호를 `KRX_ID`, `KRX_PW`에 입력
- 없으면 외국인·기관 수급 항목만 빠지고 나머지는 정상 동작

## 보유 종목 파일 (필수)
`config/holdings.example.yaml`을 복사해 `config/holdings.yaml`로 저장하고 실제 보유 종목을 적는다. 이 파일은 개인정보라 git에 올라가지 않는다(`.gitignore`).

## NH투자증권 나무 플러그 (보유 종목 자동 수집)
https://www.nhplug.com 에서 Open API 신청 → 앱키·앱 시크릿을 `NH_APP_KEY`, `NH_APP_SECRET`에 입력. 주문 기능은 쓰지 않고 잔고 조회만 사용한다. 키가 있으면 holdings.yaml의 나무(broker: nh) 계좌 대신 실제 잔고를 매일 자동으로 가져온다. 토큰을 새로 받을 때마다 NH 보안 알림이 오며, 토큰은 24시간 캐시된다.

## 2단계 이후 추가될 키
공공데이터포털(`DATA_GO_KR_KEY`), SEC 연락처(`SEC_USER_AGENT`), 노션(`NOTION_TOKEN`, `NOTION_DATABASE_ID`), 선택 소스(`ECOS_API_KEY`, `FRED_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `FINNHUB_API_KEY`) — 해당 단계 계획에서 안내
