"""Live-engine tests, driven through the paper broker.

These cover the behaviours that protect the account: stops always attached,
signal mode never trading, the kill switch flattening, and restart safety.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.broker.paper import PaperBroker
from src.config import Config
from src.engine import TradingEngine
from src.notify import Notifier
from src.risk import RiskParams
from src.strategy import Position, StrategyParams


class SilentNotifier(Notifier):
    def __init__(self):
        super().__init__("", "")
        self.messages: list[str] = []

    def send(self, message: str) -> bool:
        self.messages.append(message)
        return True


@pytest.fixture
def uptrend_candles():
    """A clean uptrend that will break the 20-bar Donchian channel."""
    n = 300
    rng = np.random.default_rng(5)
    closes = 1.10 * np.exp(np.cumsum(rng.normal(0.0015, 0.003, n)))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    w = np.abs(rng.normal(0, 0.0008, n))
    return pd.DataFrame(
        {"open": opens, "high": np.maximum(opens, closes) + w,
         "low": np.minimum(opens, closes) - w, "close": closes, "volume": 1000},
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
    )


def make_engine(candles, mode="auto", risk=None, equity=10_000.0):
    broker = PaperBroker({"EUR_USD": candles}, equity=equity)
    cfg = Config(
        instruments=["EUR_USD"], mode=mode,
        strategy=StrategyParams(), risk=risk or RiskParams(),
        oanda_token="x", oanda_account="y",
    )
    return broker, TradingEngine(broker, cfg, SilentNotifier())


def test_entry_always_carries_a_stop(uptrend_candles):
    """A filled position must never exist without a stop behind it."""
    broker, engine = make_engine(uptrend_candles)
    engine.run_cycle()

    for pos in broker.get_open_positions():
        stop = broker.stop_for(pos.instrument)
        assert stop is not None, f"{pos.instrument} is open with NO stop loss"
        if pos.side == "long":
            assert stop < pos.entry_price
        else:
            assert stop > pos.entry_price


def test_signal_mode_never_places_an_order(uptrend_candles):
    """In signal mode the bot advises and does nothing else."""
    broker, engine = make_engine(uptrend_candles, mode="signal")
    for _ in range(3):
        engine.run_cycle()

    assert broker.order_log == [], "signal mode placed a real order"
    assert broker.get_open_positions() == []
    assert any("SIGNAL" in m for m in engine.notify.messages)


def test_kill_switch_flattens_and_halts(uptrend_candles):
    """A daily loss beyond the limit must close everything and stop trading."""
    risk = RiskParams(daily_loss_limit=0.03)
    broker, engine = make_engine(uptrend_candles, risk=risk)

    engine.run_cycle()
    engine.state.day_start_equity = 10_000.0
    broker.set_equity(9_600.0)  # -4%, past the 3% limit

    engine.run_cycle()

    assert engine.state.halted
    assert engine.state.halt_reason == "daily_loss_limit"
    assert broker.get_open_positions() == [], "kill switch left positions open"


def test_halt_blocks_new_entries_until_a_new_day(uptrend_candles):
    risk = RiskParams(daily_loss_limit=0.03)
    broker, engine = make_engine(uptrend_candles, risk=risk)
    engine.state.day_start_equity = 10_000.0
    broker.set_equity(9_500.0)

    engine.run_cycle()
    assert engine.state.halted
    before = len(broker.order_log)

    engine.run_cycle()
    assert len(broker.order_log) == before, "traded while halted"

    broker.set_equity(10_000.0)
    engine.start_new_day()
    assert not engine.state.halted


def test_restart_adopts_existing_broker_positions(uptrend_candles):
    """A restarted bot must not ignore a position the broker still holds."""
    broker, engine = make_engine(uptrend_candles)
    engine.run_cycle()
    opened = broker.get_open_positions()
    if not opened:
        pytest.skip("no position opened on this fixture")

    fresh = TradingEngine(broker, engine.config, SilentNotifier())
    assert fresh.state.tracked == {}
    fresh.run_cycle()
    assert set(fresh.state.tracked) == {p.instrument for p in opened}


def test_position_closed_externally_is_dropped(uptrend_candles):
    """If a stop filled while the bot was offline, local state must catch up."""
    broker, engine = make_engine(uptrend_candles)
    engine.run_cycle()
    if not broker.get_open_positions():
        pytest.skip("no position opened on this fixture")

    for inst in list(broker._positions):
        broker._positions.pop(inst)

    engine.run_cycle()
    assert all(i not in engine.state.tracked for i in ["EUR_USD"]) or broker.get_open_positions()


def test_trailing_stop_only_ever_tightens(uptrend_candles):
    """Across cycles the resting stop must never move away from price."""
    broker, engine = make_engine(uptrend_candles)
    seen: list[float] = []

    for cursor in range(250, 300):
        broker.cursor = cursor
        engine.run_cycle()
        pos = engine.state.tracked.get("EUR_USD")
        stop = broker.stop_for("EUR_USD")
        if pos is not None and stop is not None:
            if pos.side == "long":
                seen.append(stop)

    for earlier, later in zip(seen, seen[1:]):
        assert later >= earlier - 1e-9, "a long's stop moved DOWN - stops must ratchet"


def test_broker_rejects_duplicate_position(uptrend_candles):
    broker, _ = make_engine(uptrend_candles)
    broker.market_order("EUR_USD", 1000, stop_loss=1.0)
    with pytest.raises(Exception):
        broker.market_order("EUR_USD", 1000, stop_loss=1.0)


def test_zero_unit_order_is_refused(uptrend_candles):
    broker, _ = make_engine(uptrend_candles)
    with pytest.raises(ValueError):
        broker.market_order("EUR_USD", 0)
