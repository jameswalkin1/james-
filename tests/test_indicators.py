import numpy as np
import pandas as pd
import pytest

from src.indicators import atr, donchian_high, donchian_low, ema, true_range


def test_ema_converges_to_constant():
    s = pd.Series([5.0] * 50)
    assert ema(s, 10).iloc[-1] == pytest.approx(5.0)


def test_ema_rejects_bad_period():
    with pytest.raises(ValueError):
        ema(pd.Series([1.0, 2.0]), 0)


def test_true_range_captures_gaps():
    # Bar 1 has a tiny range but gaps far above the prior close.
    high = pd.Series([1.10, 1.30])
    low = pd.Series([1.09, 1.29])
    close = pd.Series([1.10, 1.30])
    tr = true_range(high, low, close)
    # TR must reflect the 0.20 gap, not the 0.01 intrabar span.
    assert tr.iloc[1] == pytest.approx(0.20)


def test_atr_is_positive_and_warms_up():
    n = 60
    rng = np.random.default_rng(1)
    close = pd.Series(1.1 + np.cumsum(rng.normal(0, 0.002, n)))
    high, low = close + 0.003, close - 0.003
    a = atr(high, low, close, 20)
    assert a.iloc[:19].isna().all(), "ATR must not produce values during warmup"
    assert (a.dropna() > 0).all()


def test_donchian_excludes_current_bar():
    """The critical anti-lookahead property.

    If the current bar were included, its own high would define the level it is
    tested against, and every new high would register as a breakout.
    """
    high = pd.Series([1.0, 1.1, 1.2, 1.3, 1.4])
    dh = donchian_high(high, 3)
    # At index 3 the prior 3 bars are [1.0, 1.1, 1.2] -> 1.2, NOT 1.3.
    assert dh.iloc[3] == pytest.approx(1.2)
    assert dh.iloc[4] == pytest.approx(1.3)


def test_donchian_low_excludes_current_bar():
    low = pd.Series([1.5, 1.4, 1.3, 1.2, 1.1])
    dl = donchian_low(low, 3)
    assert dl.iloc[3] == pytest.approx(1.3)


def test_donchian_warmup_is_nan():
    high = pd.Series([1.0, 1.1, 1.2])
    assert donchian_high(high, 5).isna().all()
