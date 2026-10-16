"""수집기 공통 예외."""


class NotACompany(RuntimeError):
    """ETF·ETN·펀드처럼 개별 기업 재무 분석 대상이 아닌 종목."""
