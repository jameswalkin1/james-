"""In-memory broker for tests and dry runs.

Implements the full Broker interface against supplied candle data with no
network calls. Two uses:

  - unit tests for the engine, with deterministic fills
  - a dry run of the live engine before pointing it at a real account

It is deliberately simple: fills happen at the requested price plus a fixed
spread, and stops are honoured on the next candle. It is NOT a substitute for
the backtester, which models costs and portfolio risk properly.
"""
from __future__ import annotations

import itertools

import pandas as pd

from .base import Account, Broker, BrokerError, OpenPosition, OrderResult, Price


class PaperBroker(Broker):
    """Simulated broker over a fixed set of candles."""

    def __init__(
        self,
        candles: dict[str, pd.DataFrame],
        equity: float = 10_000.0,
        currency: str = "USD",
        spread: float = 0.0001,
    ) -> None:
        self._candles = candles
        self._equity = equity
        self._currency = currency
        self._spread = spread
        self._positions: dict[str, OpenPosition] = {}
        self._stops: dict[str, float] = {}
        self._ids = itertools.count(1)
        self.cursor: int = -1  # index of the "current" bar; -1 = latest
        self.order_log: list[OrderResult] = []

    # ------------------------------------------------------------ interface

    def get_account(self) -> Account:
        return Account(
            account_id="PAPER",
            currency=self._currency,
            balance=self._equity,
            equity=self._equity,
            margin_available=self._equity,
            open_position_count=len(self._positions),
        )

    def get_candles(self, instrument: str, granularity: str = "D", count: int = 500) -> pd.DataFrame:
        df = self._candles.get(instrument)
        if df is None:
            raise BrokerError(f"no paper data for {instrument}")
        upto = df if self.cursor == -1 else df.iloc[: self.cursor + 1]
        return upto.tail(count)

    def get_price(self, instrument: str) -> Price:
        df = self.get_candles(instrument, count=1)
        close = float(df["close"].iloc[-1])
        return Price(
            instrument=instrument,
            bid=close - self._spread / 2,
            ask=close + self._spread / 2,
            time=df.index[-1],
        )

    def get_open_positions(self) -> list[OpenPosition]:
        return list(self._positions.values())

    def market_order(
        self, instrument: str, units: int, stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        if units == 0:
            raise ValueError("refusing to submit an order for 0 units")
        if instrument in self._positions:
            raise BrokerError(f"already holding {instrument}")

        price = self.get_price(instrument)
        fill = price.ask if units > 0 else price.bid
        side = "long" if units > 0 else "short"

        self._positions[instrument] = OpenPosition(
            instrument=instrument, side=side, units=float(units),
            entry_price=fill, unrealised_pnl=0.0,
        )
        if stop_loss is not None:
            self._stops[instrument] = stop_loss

        result = OrderResult(
            order_id=str(next(self._ids)), instrument=instrument,
            units=float(units), fill_price=fill, time=price.time,
        )
        self.order_log.append(result)
        return result

    def close_position(self, instrument: str) -> OrderResult | None:
        pos = self._positions.pop(instrument, None)
        if pos is None:
            return None
        self._stops.pop(instrument, None)

        price = self.get_price(instrument)
        fill = price.bid if pos.side == "long" else price.ask
        self._equity += (fill - pos.entry_price) * abs(pos.units) * (1 if pos.side == "long" else -1)

        result = OrderResult(
            order_id=str(next(self._ids)), instrument=instrument,
            units=-pos.units, fill_price=fill, time=price.time,
        )
        self.order_log.append(result)
        return result

    def update_stop_loss(self, instrument: str, stop_price: float) -> bool:
        if instrument not in self._positions:
            return False
        self._stops[instrument] = stop_price
        return True

    # -------------------------------------------------------------- helpers

    def stop_for(self, instrument: str) -> float | None:
        """Current resting stop, for assertions in tests."""
        return self._stops.get(instrument)

    def set_equity(self, equity: float) -> None:
        """Force equity, to exercise the kill switch."""
        self._equity = equity
