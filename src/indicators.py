"""Technical indicators.

Pure functions over pandas Series/DataFrames. No I/O, no broker calls, so the
same code runs identically in the backtester and in live trading. That matters:
if the backtest and the live bot computed signals differently, the backtest
would be measuring a strategy you never actually trade.
"""
from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average."""
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True range: the greatest of the current bar's span, or either gap from
    the prior close. Captures overnight gaps that a plain high-low misses."""
    prev_close = close.shift(1)
    spans = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    )
    return spans.max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    """Average true range, Wilder-smoothed.

    This is the volatility unit the whole system is denominated in: stops are
    ATR multiples, and position size is derived from the stop distance. A pair
    that swings 200 pips a day gets a wider stop and a smaller position than one
    that swings 40, so each trade risks the same fraction of the account.
    """
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def donchian_high(high: pd.Series, period: int) -> pd.Series:
    """Highest high of the prior `period` bars, EXCLUDING the current bar.

    The shift is not cosmetic. Without it the current bar's own high is part of
    its own breakout level, so `high >= donchian_high` is true on every new high
    and the backtest fills trades it could never have taken live.
    """
    return high.rolling(window=period, min_periods=period).max().shift(1)


def donchian_low(low: pd.Series, period: int) -> pd.Series:
    """Lowest low of the prior `period` bars, excluding the current bar."""
    return low.rolling(window=period, min_periods=period).min().shift(1)
