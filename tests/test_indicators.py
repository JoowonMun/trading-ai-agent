import pandas as pd
import pytest

from agent.analysis.indicators import moving_average, position_in_52w, rsi


def test_moving_average():
    s = pd.Series(range(1, 11), dtype=float)
    assert moving_average(s, 5) == 8.0
    assert moving_average(s, 20) is None


def test_rsi_all_up_is_100():
    assert rsi(pd.Series(range(1, 40), dtype=float)) == 100.0


def test_rsi_alternating_is_near_50():
    s = pd.Series([100 + (i % 2) for i in range(100)], dtype=float)
    assert 45 <= rsi(s) <= 55


def test_rsi_too_short():
    assert rsi(pd.Series([1.0, 2.0, 3.0])) is None


def test_position_in_52w():
    assert position_in_52w(pd.Series([10.0, 20.0, 15.0])) == pytest.approx(50.0)
    assert position_in_52w(pd.Series([10.0, 10.0])) == 50.0
    assert position_in_52w(pd.Series([10.0])) is None
