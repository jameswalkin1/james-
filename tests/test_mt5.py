"""MT5 adapter tests, driven by a fake MetaTrader5 module.

The real package is Windows-only and needs a live terminal, so it cannot run in
CI or on this machine. A fake stands in for it, which still exercises everything
that is actually ours: symbol translation, lot rounding, forming-bar handling,
magic-number isolation and order construction.

What this CANNOT verify is the terminal's real behaviour - fill semantics,
retcodes under stress, reconnects. That needs a demo account on Windows, which
is exactly what step one of the rollout is for.
"""
from __future__ import annotations

import types

import numpy as np
import pandas as pd
import pytest

from src.broker.base import BrokerError
from src.broker.mt5 import MT5Broker, from_mt5_symbol, to_mt5_symbol


class FakeSymbol:
    def __init__(self, name, volume_min=0.01, volume_max=100.0, volume_step=0.01):
        self.name = name
        self.volume_min = volume_min
        self.volume_max = volume_max
        self.volume_step = volume_step


class FakePosition:
    def __init__(self, ticket, symbol, volume, price_open, ptype, magic, profit=0.0, tp=0.0):
        self.ticket = ticket
        self.symbol = symbol
        self.volume = volume
        self.price_open = price_open
        self.type = ptype
        self.magic = magic
        self.profit = profit
        self.tp = tp
        self.sl = 0.0


class FakeResult:
    def __init__(self, retcode, order=1, price=1.1):
        self.retcode = retcode
        self.order = order
        self.price = price
        self.comment = "ok"


def make_fake_mt5(symbol_names=("EURUSD", "GBPUSD", "USDJPY"), suffix=""):
    """A stand-in MetaTrader5 module."""
    m = types.SimpleNamespace()

    # constants
    m.TIMEFRAME_D1, m.TIMEFRAME_H4, m.TIMEFRAME_H1 = 16408, 16388, 16385
    m.TIMEFRAME_M1 = m.TIMEFRAME_M5 = m.TIMEFRAME_M15 = 1
    m.TIMEFRAME_M30 = m.TIMEFRAME_W1 = 2
    m.POSITION_TYPE_BUY, m.POSITION_TYPE_SELL = 0, 1
    m.ORDER_TYPE_BUY, m.ORDER_TYPE_SELL = 0, 1
    m.TRADE_ACTION_DEAL, m.TRADE_ACTION_SLTP = 1, 6
    m.TRADE_RETCODE_DONE = 10009
    m.ORDER_TIME_GTC, m.ORDER_FILLING_IOC = 0, 1

    m.initialize = lambda **kw: True
    m.shutdown = lambda: None
    m.last_error = lambda: (0, "no error")
    m.terminal_info = lambda: types.SimpleNamespace(trade_allowed=True)
    m.account_info = lambda: types.SimpleNamespace(
        login=221230, currency="EUR", balance=100.0, equity=102.5, margin_free=95.0
    )
    m.symbols_get = lambda: [FakeSymbol(n + suffix) for n in symbol_names]
    m.symbol_info = lambda s: FakeSymbol(s)
    m.symbol_select = lambda s, on: any(s == n + suffix for n in symbol_names)
    m.symbol_info_tick = lambda s: types.SimpleNamespace(
        bid=1.0999, ask=1.1001, time=1_700_000_000
    )

    def copy_rates_from_pos(symbol, tf, start, count):
        n = count
        base = np.linspace(1.10, 1.12, n)
        return np.array(
            [(1_700_000_000 + i * 86400, base[i], base[i] + 0.002,
              base[i] - 0.002, base[i] + 0.001, 100, 0, 0) for i in range(n)],
            dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
                   ("close", "f8"), ("tick_volume", "i8"), ("spread", "i4"), ("real_volume", "i8")],
        )

    m.copy_rates_from_pos = copy_rates_from_pos
    m.positions = []
    m.positions_get = lambda symbol=None: [
        p for p in m.positions if symbol is None or p.symbol == symbol
    ]
    m.sent = []

    def order_send(request):
        m.sent.append(request)
        return FakeResult(m.TRADE_RETCODE_DONE, order=555, price=1.1001)

    m.order_send = order_send
    return m


@pytest.fixture
def broker():
    return MT5Broker(mt5_module=make_fake_mt5())


# ------------------------------------------------------------ symbol mapping

@pytest.mark.parametrize("instrument,suffix,expected", [
    ("EUR_USD", "", "EURUSD"),
    ("EUR_USD", ".a", "EURUSD.a"),
    ("USD_JPY", "-ECN", "USDJPY-ECN"),
])
def test_to_mt5_symbol(instrument, suffix, expected):
    assert to_mt5_symbol(instrument, suffix) == expected


def test_from_mt5_symbol_round_trips():
    assert from_mt5_symbol(to_mt5_symbol("GBP_JPY", ".a"), ".a") == "GBP_JPY"


def test_from_mt5_symbol_rejects_junk():
    with pytest.raises(ValueError):
        from_mt5_symbol("NOTASYMBOL")


def test_suffix_is_auto_detected():
    """Brokers append arbitrary suffixes; the user should not have to find out."""
    b = MT5Broker(mt5_module=make_fake_mt5(suffix=".raw"))
    assert b.symbol_suffix == ".raw"


def test_no_suffix_detected_when_there_is_none(broker):
    assert broker.symbol_suffix == ""


def test_unknown_symbol_raises_with_guidance(broker):
    with pytest.raises(BrokerError, match="not available at this broker"):
        broker.get_price("XAU_EUR")


# ------------------------------------------------------------------- reads

def test_account_reads_equity_not_balance(broker):
    """Sizing must use equity, which includes floating P&L."""
    account = broker.get_account()
    assert account.equity == 102.5
    assert account.balance == 100.0
    assert account.currency == "EUR"


def test_candles_drop_the_forming_bar(broker):
    """MT5 bar 0 is still forming. Acting on it produces signals that vanish."""
    df = broker.get_candles("EUR_USD", "D", count=50)
    assert len(df) == 50, "asked for 50 complete bars"
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.is_monotonic_increasing


def test_unsupported_granularity_raises(broker):
    with pytest.raises(ValueError, match="unsupported granularity"):
        broker.get_candles("EUR_USD", "M3")


def test_price_has_a_spread(broker):
    price = broker.get_price("EUR_USD")
    assert price.ask > price.bid
    assert price.mid == pytest.approx(1.1)


# --------------------------------------------------------------- lot sizing

def test_units_convert_to_lots(broker):
    assert broker.units_to_lots("EUR_USD", 100_000) == pytest.approx(1.0)
    assert broker.units_to_lots("EUR_USD", 10_000) == pytest.approx(0.10)


def test_lots_round_to_the_broker_step(broker):
    """A volume off the step is rejected outright, so round before sending."""
    assert broker.units_to_lots("EUR_USD", 12_345) == pytest.approx(0.12)


def test_below_minimum_lot_returns_zero(broker):
    """A €100 account with a wide stop can size below the broker minimum.

    Returning 0 makes the engine skip the trade. Silently rounding UP to the
    minimum would risk several times the intended amount - on a small account
    that is the difference between a 0.5% risk and a 10% one.
    """
    assert broker.units_to_lots("EUR_USD", 50) == 0.0


def test_lots_are_capped_at_the_broker_maximum(broker):
    assert broker.units_to_lots("EUR_USD", 50_000_000) == pytest.approx(100.0)


def test_order_below_minimum_lot_raises_clearly(broker):
    with pytest.raises(BrokerError, match="too small"):
        broker.market_order("EUR_USD", 50, stop_loss=1.09)


# ------------------------------------------------------------------ orders

def test_market_order_attaches_the_stop(broker):
    """A position must never exist without a stop, even briefly."""
    broker.market_order("EUR_USD", 10_000, stop_loss=1.0950)
    sent = broker._mt5.sent[-1]
    assert sent["sl"] == pytest.approx(1.0950)
    assert sent["volume"] == pytest.approx(0.10)
    assert sent["type"] == broker._mt5.ORDER_TYPE_BUY


def test_sell_order_uses_sell_type_and_bid(broker):
    broker.market_order("EUR_USD", -10_000, stop_loss=1.1050)
    sent = broker._mt5.sent[-1]
    assert sent["type"] == broker._mt5.ORDER_TYPE_SELL
    assert sent["price"] == pytest.approx(1.0999)  # bid


def test_zero_unit_order_refused(broker):
    with pytest.raises(ValueError):
        broker.market_order("EUR_USD", 0)


def test_rejected_order_raises(broker):
    broker._mt5.order_send = lambda req: FakeResult(10013)  # invalid request
    with pytest.raises(BrokerError, match="rejected"):
        broker.market_order("EUR_USD", 10_000, stop_loss=1.09)


def test_orders_carry_the_magic_number(broker):
    broker.market_order("EUR_USD", 10_000, stop_loss=1.09)
    assert broker._mt5.sent[-1]["magic"] == broker.magic


# ------------------------------------------------- isolation from manual trades

def test_manual_positions_are_invisible(broker):
    """The bot must never manage a position a human opened by hand."""
    m = broker._mt5
    m.positions = [
        FakePosition(1, "EURUSD", 0.1, 1.10, m.POSITION_TYPE_BUY, magic=broker.magic),
        FakePosition(2, "GBPUSD", 0.5, 1.28, m.POSITION_TYPE_BUY, magic=0),  # manual
    ]
    instruments = [p.instrument for p in broker.get_open_positions()]
    assert instruments == ["EUR_USD"], "a manually opened position was picked up"


def test_close_ignores_manual_positions(broker):
    m = broker._mt5
    m.positions = [FakePosition(2, "GBPUSD", 0.5, 1.28, m.POSITION_TYPE_BUY, magic=0)]
    assert broker.close_position("GBP_USD") is None
    assert m.sent == [], "sent an order against a manual position"


def test_close_sends_opposite_side_against_the_ticket(broker):
    m = broker._mt5
    m.positions = [FakePosition(7, "EURUSD", 0.2, 1.10, m.POSITION_TYPE_BUY, magic=broker.magic)]
    broker.close_position("EUR_USD")
    sent = m.sent[-1]
    assert sent["type"] == m.ORDER_TYPE_SELL
    assert sent["position"] == 7
    assert sent["volume"] == pytest.approx(0.2)


def test_close_nothing_open_returns_none(broker):
    assert broker.close_position("EUR_USD") is None


# ------------------------------------------------------------ stop movement

def test_update_stop_loss_preserves_take_profit(broker):
    m = broker._mt5
    m.positions = [FakePosition(9, "EURUSD", 0.1, 1.10, m.POSITION_TYPE_BUY,
                                magic=broker.magic, tp=1.15)]
    assert broker.update_stop_loss("EUR_USD", 1.095)
    sent = m.sent[-1]
    assert sent["action"] == m.TRADE_ACTION_SLTP
    assert sent["sl"] == pytest.approx(1.095)
    assert sent["tp"] == pytest.approx(1.15), "existing take-profit was wiped"


def test_update_stop_on_missing_position_returns_false(broker):
    assert broker.update_stop_loss("EUR_USD", 1.09) is False


# ------------------------------------------------------------- connection

def test_failed_initialize_explains_itself():
    m = make_fake_mt5()
    m.initialize = lambda **kw: False
    with pytest.raises(BrokerError, match="could not connect"):
        MT5Broker(mt5_module=m)


def test_algo_trading_disabled_is_warned(caplog):
    m = make_fake_mt5()
    m.terminal_info = lambda: types.SimpleNamespace(trade_allowed=False)
    with caplog.at_level("WARNING"):
        MT5Broker(mt5_module=m)
    assert "Algo Trading" in caplog.text
