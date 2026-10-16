오늘({{DATE}}) 투자 리포트의 AI 해설을 작성해 주세요.

1. `prompts/analysis-guide.md`를 읽고 그 지침을 그대로 따릅니다.
2. `out/{{DATE}}/context.json`을 읽습니다. 여기 있는 숫자만 사용합니다.
3. `out/{{DATE}}/analysis.json`을 작성합니다 (JSON만).
4. `uv run python -m agent check --date {{DATE}}`로 검증합니다. "검증 실패"가 나오면 지적된 부분을 context.json 값에 맞게 고치고 다시 검증합니다. "검증 통과"가 나올 때까지 반복하되 최대 3번까지만 고칩니다.

다른 파일은 수정하지 말고, 저장소에 커밋하지 마세요. 최종 답변은 "검증 통과" 또는 남은 오류 한 줄만 쓰세요.
