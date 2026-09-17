"""Broker interface.

Every broker-specific detail lives behind this interface so the strategy and
risk code never import an SDK. Two payoffs:

1. The backtester and the live bot drive the SAME strategy code through the same
   interface, so a backtest measures the system you actually trade.
2. Moving to a different broker (Vantage/MT5, IG, cTrader) means writing one new
   subclass, not rewriting the bot.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


class BrokerError(RuntimeError):
    """Broker rejected a request or is unreachable."""


@dataclass(frozen=True)
class Price:
    """Current two-sided market price."""

    instrument: str
    bid: float
    ask: float
    time: pd.Timestamp

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class Account:
    """Account snapshot."""

    account_id: str
    currency: str
    balance: float
    equity: float          # balance + unrealised P&L; this is what we size against
    margin_available: float
    open_position_count: int


@dataclass(frozen=True)
class OpenPosition:
    """A position as the BROKER reports it - the source of truth.

    The bot's own view can drift from reality (a manual close, a stop filled
    while we were offline, a partial fill). Reconciling against this on every
    cycle is what stops the bot acting on a position that no longer exists.
    """

    instrument: str
    side: str              # "long" or "short"
    units: float
    entry_price: float
    unrealised_pnl: float


@dataclass(frozen=True)
class OrderResult:
    """Outcome of a submitted order."""

    order_id: str
    instrument: str
    units: float           # signed: positive long, negative short
    fill_price: float
    time: pd.Timestamp


class Broker(ABC):
    """Minimum surface the engine needs."""

    @abstractmethod
    def get_account(self) -> Account:
        """Current account state, including equity for position sizing."""

    @abstractmethod
    def get_candles(
        self, instrument: str, granularity: str, count: int = 500
    ) -> pd.DataFrame:
        """Historical OHLC, oldest first, indexed by bar-close time.

        Must return COMPLETE bars only. A half-formed current bar changes under
        the bot's feet and will produce signals that vanish on the next poll.
        Columns: open, high, low, close, volume.
        """

    @abstractmethod
    def get_price(self, instrument: str) -> Price:
        """Current bid/ask."""

    @abstractmethod
    def get_open_positions(self) -> list[OpenPosition]:
        """All open positions, as the broker sees them."""

    @abstractmethod
    def market_order(
        self,
        instrument: str,
        units: int,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        """Submit a market order. Positive units buy, negative sell.

        The stop MUST be attached to the order itself, not placed afterwards in a
        second call. If the bot dies between the two calls, an order placed that
        way sits on the account with no stop at all.
        """

    @abstractmethod
    def close_position(self, instrument: str) -> OrderResult | None:
        """Flatten an instrument. Returns None if nothing was open."""

    @abstractmethod
    def update_stop_loss(self, instrument: str, stop_price: float) -> bool:
        """Move the resting stop for an open position (trailing)."""
