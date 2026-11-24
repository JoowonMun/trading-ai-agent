# 살펴볼 곳 기록 남기기 — 짧은 설계

## 왜
④-4 가설 채점(지난 의견이 맞았는지 몇 주 뒤 코드가 채점)은 그때 무엇을 골랐고 AI가 뭐라고 했는지 기록이 있어야 한다.
지금부터 남겨야 몇 주 뒤 채점할 재료가 생긴다.

## 목표 / 비목표
- 목표: 월요일 살펴볼 곳 업종·후보 회사(코드가 고른 것)와 검증된 AI 의견을 비공개 기록 저장소에 남긴다.
- 비목표: 채점 로직, 후보 주가 저장(과거 주가는 나중에 KRX에서 받는다), 보유 여부 저장(holdings로 알 수 있다).
- 반목표: 스냅샷에 AI 글이 섞이는 것, 공개 저장소·로그에 기록이 남는 것.

## 방식
- 고른 방식: 스냅샷에 `picks`(코드가 고른 것)를 넣고, AI 의견은 `opinions/<date>.json` 별도 파일로 복사.
- 버린 방식: 의견까지 스냅샷에 넣기(스냅샷 "AI 글 없음" 규칙과 충돌), 코드가 고른 것만 저장(그때 AI가 뭐라 했는지 돌아볼 수 없음).

## 설계
- `make_snapshot`: `"picks": {"sectors": opinion_sectors, "candidates": [{ticker,name,sector,method,value,sector_median}]}`.
  후보·업종이 없는 날(평일)은 빈 목록.
- `save-snapshot`: `out/<date>/opinions.json`이 있으면 `<history-dir>/opinions/<date>.json`으로 복사(검증 통과본 그대로).
- 워크플로 변경 없음(기록 폴더 전체를 `git add -A`). dry run은 지금처럼 저장 안 함.
