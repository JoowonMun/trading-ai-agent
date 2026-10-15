"""가격 시계열 기반 기술 지표 (매매 시점 보조 근거용)."""
import pandas as pd


def moving_average(close: pd.Series, window: int) -> float | None:
    if len(close) < window:
        return None
    return float(close.iloc[-window:].mean())


def rsi(close: pd.Series, period: int = 14) -> float | None:
    """Wilder 방식 RSI."""
    if len(close) <= period:
        return None
    delta = close.diff().dropna()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    return float(100 - 100 / (1 + avg_gain / avg_loss))


def position_in_52w(close: pd.Series) -> float | None:
    window = close.iloc[-252:]
    if len(window) < 2:
        return None
    low, high = window.min(), window.max()
    if high == low:
        return 50.0
    return float((close.iloc[-1] - low) / (high - low) * 100)
