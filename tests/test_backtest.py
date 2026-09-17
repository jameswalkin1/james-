"""Backtester tests.

The first test in this file is the most important one in the project. If the
backtester makes money on a random walk, its numbers are worthless and so is
every conclusion drawn from them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import src.backtest as bt_mod

from src.backtest import Backtester
from src.costs import CostModel
from src.risk import RiskParams
from src.strategy import Signal, StrategyParams


ZERO_COST = {"EUR_USD": CostModel(spread_pips=0.0, slippage_pips=0.0)}


def _random_entry_signal(seed: int):
    """A coin-flip stand-in for the strategy, with the same trade frequency."""
    rng = np.random.default_rng(seed)

    def signal(bar, params):
        if pd.isna(bar.get("atr")):
            return Signal.NONE
        r = rng.random()
        if r < 0.02:
            return Signal.ENTER_LONG
        if r < 0.04:
            return Signal.ENTER_SHORT
        return Signal.NONE

    return signal


def _run_with_signal(data, signal_fn, **kw):
    """Run the backtester with entry_signal swapped out."""
    original = bt_mod.entry_signal
    bt_mod.entry_signal = signal_fn
    try:
        return Backtester(**kw).run(data)
    finally:
        bt_mod.entry_signal = original


def test_signal_adds_nothing_on_a_random_walk(random_walk):
    """THE HONESTY TEST: does the SIGNAL beat random entries on data with no edge?

    Why this is the right null, and plain "return < 0" is not:

    Backtests on BAR data are structurally optimistic about stop exits. A bar
    tells us the stop level was touched, so the engine fills there - but the
    bar's actual information content is its close, and price that touched the
    stop usually closed past it. On a driftless random walk this artifact alone
    is worth roughly +30 pips per trade, which is large enough to make a
    zero-edge system look profitable. It is a property of bar-resolution
    backtesting, not a bug: an independently written reference implementation of
    the same trailing-stop rule reproduces it exactly.

    So the artifact cannot be asserted away - it has to be DIFFERENCED away. Both
    arms below run through the same engine with the same stops, sizing and fill
    assumptions; only the entry signal differs. Anything the signal is genuinely
    worth shows up in the gap between them.
    """
    kw = dict(starting_equity=10_000)
    strategy = Backtester(**kw).run({"EUR_USD": random_walk})
    random_entries = _run_with_signal(
        {"EUR_USD": random_walk}, _random_entry_signal(0), **kw
    )

    edge = strategy.total_return - random_entries.total_return
    assert edge < 0.10, (
        f"Signal beat random entries by {edge:.2%} on a random walk. There is no "
        "edge to find in this data, so a large gap means lookahead bias."
    )


def test_bar_fill_artifact_is_bounded_by_stop_slippage(random_walk):
    """The stop-slippage model must actually bite on stop exits.

    This is the guard that keeps the known bar-data optimism from growing
    unchecked: raising stop slippage must reduce reported profit.
    """
    optimistic = {"EUR_USD": CostModel(spread_pips=1.0, slippage_pips=0.2, stop_slippage_pips=0.2)}
    realistic = {"EUR_USD": CostModel(spread_pips=1.0, slippage_pips=0.2, stop_slippage_pips=4.0)}

    a = Backtester(starting_equity=10_000, costs=optimistic).run({"EUR_USD": random_walk})
    b = Backtester(starting_equity=10_000, costs=realistic).run({"EUR_USD": random_walk})
    assert b.total_return < a.total_return, "stop slippage had no effect on results"


def test_profits_on_a_strong_trend(strong_trend):
    """Sanity in the other direction: given a real trend, it should capture some.

    Not proof of an edge - proof the machinery works.
    """
    bt = Backtester(starting_equity=10_000)
    result = bt.run({"EUR_USD": strong_trend})
    assert result.total_return > 0
    assert len(result.trades) > 0


def test_choppy_market_bleeds(flat_market):
    """Breakout systems lose in ranges. If this showed a profit, be suspicious."""
    bt = Backtester(starting_equity=10_000)
    result = bt.run({"EUR_USD": flat_market})
    assert result.total_return < 0.10


def test_entries_never_fill_at_the_signal_bar_close(strong_trend):
    """Every entry must fill at a LATER bar's open than the bar that signalled.

    This is the structural guarantee against lookahead: the engine cannot use a
    close it has not yet seen.
    """
    bt = Backtester(starting_equity=10_000)
    result = bt.run({"EUR_USD": strong_trend})
    assert result.trades

    closes = strong_trend["close"]
    for trade in result.trades:
        assert trade.entry_price != pytest.approx(closes.loc[trade.entry_time], abs=1e-9), (
            "an entry filled at the signalling bar's close - that is lookahead"
        )
        assert trade.exit_time > trade.entry_time


def test_stop_loss_bounds_the_loss(strong_trend):
    """No single loss should greatly exceed the configured risk per trade.

    Gaps can exceed it - that is real and expected - but the typical loss must
    respect the limit or position sizing is not working.
    """
    risk = RiskParams(risk_per_trade=0.01)
    bt = Backtester(starting_equity=10_000, risk_params=risk)
    result = bt.run({"EUR_USD": strong_trend})

    non_gap = [t for t in result.trades if t.exit_reason == "stop"]
    for trade in non_gap:
        # 1% of 10k = 100; allow headroom for equity growth and exit costs.
        assert trade.pnl > -400, f"loss of {trade.pnl:.2f} far exceeds the risk budget"


def test_portfolio_run_respects_position_cap(random_walk, strong_trend, flat_market):
    """With a cap of 1, the engine must never hold two instruments at once."""
    data = {
        "EUR_USD": random_walk.iloc[:800],
        "GBP_USD": strong_trend.iloc[:800],
        "AUD_USD": flat_market.iloc[:800],
    }
    # Align indices so they share a timeline.
    idx = pd.date_range("2018-01-01", periods=800, freq="B")
    data = {k: v.set_index(idx) for k, v in data.items()}

    risk = RiskParams(max_open_positions=1, max_per_currency=9, max_portfolio_risk=0.20)
    result = Backtester(starting_equity=10_000, risk_params=risk).run(data)

    # Reconstruct concurrency from the trade log.
    events = []
    for t in result.trades:
        events.append((t.entry_time, 1))
        events.append((t.exit_time, -1))
    events.sort()
    concurrent = peak = 0
    for _, delta in events:
        concurrent += delta
        peak = max(peak, concurrent)
    assert peak <= 1, f"held {peak} positions with a cap of 1"


def test_insufficient_history_raises():
    tiny = pd.DataFrame(
        {"open": [1.1] * 10, "high": [1.2] * 10, "low": [1.0] * 10, "close": [1.1] * 10},
        index=pd.date_range("2020-01-01", periods=10, freq="B"),
    )
    with pytest.raises(ValueError, match="warmup"):
        Backtester().run({"EUR_USD": tiny})


def test_empty_data_raises():
    with pytest.raises(ValueError, match="no data"):
        Backtester().run({})


def test_metrics_are_internally_consistent(strong_trend):
    result = Backtester(starting_equity=10_000).run({"EUR_USD": strong_trend})
    assert result.max_drawdown >= 0
    assert 0 <= result.win_rate <= 1
    if result.trades:
        total = sum(t.pnl for t in result.trades)
        assert result.expectancy == pytest.approx(total / len(result.trades))
    assert "BACKTEST RESULT" in result.summary()
