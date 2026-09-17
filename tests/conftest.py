"""Shared fixtures: synthetic price series with known properties."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _ohlc_from_closes(closes: np.ndarray, index: pd.DatetimeIndex, noise: float) -> pd.DataFrame:
    """Build plausible OHLC bars around a close series."""
    rng = np.random.default_rng(7)
    opens = np.concatenate([[closes[0]], closes[:-1]])
    wiggle = rng.normal(0, noise, size=len(closes))
    highs = np.maximum(opens, closes) + np.abs(wiggle)
    lows = np.minimum(opens, closes) - np.abs(wiggle)
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": 1000,
        },
        index=index,
    )


@pytest.fixture
def random_walk() -> pd.DataFrame:
    """A pure random walk: no trend, no mean reversion, no edge to find.

    Any strategy run on this MUST lose roughly its transaction costs. A
    backtester that reports a profit here is reading the future.
    """
    rng = np.random.default_rng(42)
    n = 2000
    steps = rng.normal(0, 0.005, size=n)
    closes = 1.10 * np.exp(np.cumsum(steps))
    index = pd.date_range("2015-01-01", periods=n, freq="B")
    return _ohlc_from_closes(closes, index, noise=0.0015)


@pytest.fixture
def strong_trend() -> pd.DataFrame:
    """A persistent uptrend with noise. A trend system should profit here."""
    rng = np.random.default_rng(11)
    n = 1200
    drift = 0.0012
    steps = rng.normal(drift, 0.004, size=n)
    closes = 1.00 * np.exp(np.cumsum(steps))
    index = pd.date_range("2016-01-01", periods=n, freq="B")
    return _ohlc_from_closes(closes, index, noise=0.0010)


@pytest.fixture
def flat_market() -> pd.DataFrame:
    """A strongly mean-reverting range - the worst regime for a breakout system.

    Modelled as an Ornstein-Uhlenbeck process: every move away from the mean is
    actively pulled back. Breakouts therefore fail by construction, which is
    exactly the "whipsaw" environment that hurts trend following in practice.

    (An earlier version of this fixture used a slow sine wave. That was a poor
    choice: a smooth oscillation with a period longer than the entry lookback is
    a sequence of clean mini-trends, which a breakout system rightly profits
    from. It tested the opposite of what it claimed to.)
    """
    rng = np.random.default_rng(3)
    n = 900
    theta, mu, sigma = 0.25, 1.20, 0.004
    closes = np.empty(n)
    closes[0] = mu
    for i in range(1, n):
        closes[i] = closes[i - 1] + theta * (mu - closes[i - 1]) + rng.normal(0, sigma)
    index = pd.date_range("2017-01-01", periods=n, freq="B")
    return _ohlc_from_closes(closes, index, noise=0.0008)
