"""살펴볼 곳: 유망 업종을 고르고, 업종 안에서 크고 흑자이면서 싼 후보 회사를 고른다."""
from collections.abc import Callable

import pandas as pd

from agent.analysis.quiet_signals import promising_sectors
from agent.report.schema import Candidate, SectorRow

OPINION_SECTORS = 3
MAX_CANDIDATES = 3


def opinion_sectors(rows: list[SectorRow]) -> list[SectorRow]:
    """유망 업종 중 가격 위치가 낮은 순 최대 3개."""
    ranked = sorted(promising_sectors(rows), key=lambda r: (r.percentile is None, r.percentile or 0))
    return ranked[:OPINION_SECTORS]


def pick_candidates(sector: SectorRow, members: list[str], large: list[str], fundamentals: pd.DataFrame,
                    names: Callable[[str], str], held: set[str]) -> list[Candidate]:
    """large는 시가총액 큰 순. 중간값은 지표가 있는(값 > 0) 소속 회사로 계산한다."""
    col = sector.method.lower()
    data = fundamentals[fundamentals.index.isin(members)]
    values = data.loc[data[col] > 0, col]
    if values.empty:
        return []
    median = float(values.median())
    cheap = data[(data["per"] > 0) & (data[col] > 0) & (data[col] < median)]
    picked = [t for t in large if t in cheap.index][:MAX_CANDIDATES]
    return [Candidate(ticker=t, name=names(t), sector=sector.name, method=sector.method,
                      value=round(float(cheap.loc[t, col]), 2), sector_median=round(median, 2), held=t in held)
            for t in picked]
