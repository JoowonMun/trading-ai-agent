"""공시 제목 → 분류·악재 여부."""

CATEGORIES = [
    ("rights_issue", ("유상증자",)),
    ("buyback", ("자기주식",)),
    ("earnings", ("영업(잠정)실적", "매출액또는손익구조")),
    ("dividend", ("배당",)),
]
NEGATIVE_KEYWORDS = ("유상증자결정", "감자결정", "관리종목", "불성실공시", "횡령", "배임",
                     "회생절차", "상장폐지", "의견거절", "부적정의견", "한정의견")


def classify(report_nm: str) -> tuple[str, bool]:
    title = report_nm.replace(" ", "")
    category = next((name for name, words in CATEGORIES if any(w in title for w in words)), "other")
    negative = any(word in title for word in NEGATIVE_KEYWORDS)
    return category, negative
