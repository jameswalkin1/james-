"""Trend-following strategy: Donchian breakout with a regime filter.

WHY THIS STRATEGY
-----------------
Time-series momentum is the most durably documented return premium in currency
markets. Moskowitz, Ooi & Pedersen (2012) found it across 58 futures markets
including FX over ~25 years; it is the core of what managed-futures funds
actually run. It is not a secret and it is not exotic, which is precisely the
point: an edge that survives being public has a better claim to being real than
one that only exists in a curve-fitted backtest.

It is also a good fit for automation. The rules are unambiguous, the trade
frequency is low enough that spread costs stay a small fraction of the average
win, and there is nothing discretionary to second-guess at 3am.

What it is NOT: it is not a high win rate. Trend systems typically win 30-45% of
trades and make money because winners run several times the size of losers. Long
flat or losing stretches are normal and expected, not a sign of breakage.

THE RULES
---------
Entry long   : today's close breaks above the highest high of the last N bars
               AND close is above the long EMA (only trade with the tide)
Entry short  : mirror image
Initial stop : entry -/+ (stop_atr_mult x ATR)
Trailing exit: Chandelier - highest high since entry minus (trail_atr_mult x ATR),
               which ratchets up and never loosens
Time exit    : opposite Donchian channel of exit_period bars
Position size: risk a fixed % of equity between entry and stop (see risk.py)

Signals are computed on CLOSED bars only and acted on at the next bar's open.
Anything else is lookahead bias and inflates a backtest into fiction.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from .indicators import atr, donchian_high, donchian_low, ema


class Signal(str, Enum):
    """What the strategy wants to do on the next bar."""

    NONE = "none"
    ENTER_LONG = "enter_long"
    ENTER_SHORT = "enter_short"
    EXIT = "exit"


@dataclass(frozen=True)
class StrategyParams:
    """Tunable parameters.

    Defaults are conventional trend-following values (close to the original
    Turtle system), deliberately NOT optimised against any particular history.
    Parameters tuned to make a backtest curve look pretty are the single most
    common way a system that "worked" dies in live trading.
    """

    entry_period: int = 20      # breakout lookback for entries
    exit_period: int = 10       # faster opposite channel for exits
    trend_ema: int = 100        # regime filter: only trade with the trend
    atr_period: int = 20        # volatility measurement window
    stop_atr_mult: float = 2.0  # initial stop distance, in ATRs
    trail_atr_mult: float = 3.0 # Chandelier trailing distance, in ATRs

    def __post_init__(self) -> None:
        if self.exit_period >= self.entry_period:
            raise ValueError(
                "exit_period must be shorter than entry_period, otherwise positions "
                "exit on the same channel that entered them and never run"
            )
        for name in ("entry_period", "exit_period", "trend_ema", "atr_period"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
        for name in ("stop_atr_mult", "trail_atr_mult"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")

    @property
    def warmup_bars(self) -> int:
        """Bars needed before any signal is trustworthy."""
        return max(self.entry_period, self.trend_ema, self.atr_period) + 1


@dataclass
class Position:
    """An open position, as the strategy tracks it."""

    side: str            # "long" or "short"
    entry_price: float
    entry_time: pd.Timestamp
    units: float
    stop_price: float
    extreme: float       # best price seen since entry, drives the trailing stop

    @property
    def is_long(self) -> bool:
        return self.side == "long"


def compute_features(candles: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    """Attach indicator columns to OHLC candles.

    Expects columns: open, high, low, close (index = bar close timestamp).
    """
    required = {"open", "high", "low", "close"}
    missing = required - set(candles.columns)
    if missing:
        raise ValueError(f"candles missing required columns: {sorted(missing)}")

    df = candles.copy()
    df["atr"] = atr(df["high"], df["low"], df["close"], params.atr_period)
    df["ema"] = ema(df["close"], params.trend_ema)
    df["entry_high"] = donchian_high(df["high"], params.entry_period)
    df["entry_low"] = donchian_low(df["low"], params.entry_period)
    df["exit_high"] = donchian_high(df["high"], params.exit_period)
    df["exit_low"] = donchian_low(df["low"], params.exit_period)
    return df


def entry_signal(bar: pd.Series, params: StrategyParams) -> Signal:
    """Decide whether a closed bar triggers a new entry.

    `bar` must carry the indicator columns from compute_features. Returns NONE
    if any indicator is still warming up - never guess during warmup.
    """
    needed = ("close", "entry_high", "entry_low", "ema", "atr")
    if any(pd.isna(bar.get(k)) for k in needed):
        return Signal.NONE

    breaks_up = bar["close"] > bar["entry_high"]
    breaks_down = bar["close"] < bar["entry_low"]
    uptrend = bar["close"] > bar["ema"]
    downtrend = bar["close"] < bar["ema"]

    if breaks_up and uptrend:
        return Signal.ENTER_LONG
    if breaks_down and downtrend:
        return Signal.ENTER_SHORT
    return Signal.NONE


def initial_stop(entry_price: float, side: str, bar_atr: float, params: StrategyParams) -> float:
    """Stop distance scaled to current volatility."""
    if bar_atr <= 0:
        raise ValueError("ATR must be positive to size a stop")
    offset = params.stop_atr_mult * bar_atr
    return entry_price - offset if side == "long" else entry_price + offset


def update_trailing_stop(pos: Position, bar: pd.Series, params: StrategyParams) -> float:
    """Chandelier trailing stop, ratcheted.

    Returns the new stop price. The max()/min() guard is what makes it a ratchet:
    the stop may tighten as the trade moves in our favour but must never widen,
    because a stop that can back away is not a stop.
    """
    bar_atr = bar["atr"]
    if pd.isna(bar_atr) or bar_atr <= 0:
        return pos.stop_price

    if pos.is_long:
        pos.extreme = max(pos.extreme, bar["high"])
        candidate = pos.extreme - params.trail_atr_mult * bar_atr
        return max(pos.stop_price, candidate)

    pos.extreme = min(pos.extreme, bar["low"])
    candidate = pos.extreme + params.trail_atr_mult * bar_atr
    return min(pos.stop_price, candidate)


def exit_signal(pos: Position, bar: pd.Series) -> bool:
    """Opposite-channel exit, checked on closed bars.

    This is separate from the stop. The stop is a hard intrabar price level the
    broker holds; this is a slower "the trend has turned" signal that gets us out
    on the close even if the stop was never touched.
    """
    if pos.is_long:
        level = bar.get("exit_low")
        return not pd.isna(level) and bar["close"] < level
    level = bar.get("exit_high")
    return not pd.isna(level) and bar["close"] > level
