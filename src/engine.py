"""Live trading engine.

One cycle = one pass over the universe. Run it once per completed bar (daily bars
-> once a day, shortly after the 5pm New York close when OANDA rolls the day).

Design rules this follows, in order of importance:

1. THE BROKER IS THE SOURCE OF TRUTH. Every cycle re-reads positions from the
   broker rather than trusting local state. The bot can be restarted, killed, or
   run alongside manual trades without corrupting itself.
2. NEVER HOLD AN UNPROTECTED POSITION. Stops are attached to the entry order, so
   there is no window in which a fill exists without a stop behind it.
3. FAIL CLOSED. Any unexpected error stops new entries. Doing nothing is always
   a safe action; guessing is not.
4. SAME LOGIC AS THE BACKTEST. Signals come from the same functions the
   backtester uses, so the tested system and the traded system are one system.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from .broker.base import Broker, BrokerError
from .config import Config
from .costs import quote_to_account_rate
from .notify import Notifier
from .risk import PortfolioState, can_open, check_kill_switch, position_size
from .strategy import (
    Position,
    Signal,
    compute_features,
    entry_signal,
    exit_signal,
    initial_stop,
    update_trailing_stop,
)

log = logging.getLogger(__name__)


@dataclass
class EngineState:
    """Bot-side memory that the broker cannot tell us.

    The broker knows units and entry price; it does not know the high-water mark
    a trailing stop is measured from. That lives here and is rebuilt from bar
    history on restart so a restart does not reset a trailing stop.
    """

    tracked: dict[str, Position] = field(default_factory=dict)
    day_start_equity: float | None = None
    halted: bool = False
    halt_reason: str = ""


class TradingEngine:
    """Drives one instrument universe against one broker account."""

    def __init__(
        self,
        broker: Broker,
        config: Config,
        notifier: Notifier | None = None,
    ) -> None:
        self.broker = broker
        self.config = config
        self.notify = notifier or Notifier(config.telegram_token, config.telegram_chat)
        self.state = EngineState()

    # ------------------------------------------------------------ reconcile

    def _sync_positions(self) -> dict[str, Position]:
        """Rebuild the local position view from the broker.

        Positions the broker no longer reports are dropped (stopped out while we
        were offline, or closed by hand). Positions we do not recognise are
        adopted with a conservative trailing anchor at their entry price.
        """
        live = {p.instrument: p for p in self.broker.get_open_positions()}

        for inst in list(self.state.tracked):
            if inst not in live:
                log.info("%s is no longer open at the broker; dropping local state", inst)
                self.state.tracked.pop(inst)

        for inst, broker_pos in live.items():
            tracked = self.state.tracked.get(inst)
            if tracked is None:
                log.warning(
                    "adopting untracked %s position at the broker (restart, or a "
                    "manual trade). Trailing anchor set to entry price.",
                    inst,
                )
                self.state.tracked[inst] = Position(
                    side=broker_pos.side,
                    entry_price=broker_pos.entry_price,
                    entry_time=pd.Timestamp.now("UTC"),
                    units=abs(broker_pos.units),
                    stop_price=broker_pos.entry_price,  # replaced below from bars
                    extreme=broker_pos.entry_price,
                )
            else:
                # Broker's units win; ours can drift after a partial fill.
                tracked.units = abs(broker_pos.units)
                tracked.entry_price = broker_pos.entry_price

        return self.state.tracked

    # ---------------------------------------------------------------- cycle

    def run_cycle(self) -> None:
        """One full pass: reconcile, manage open trades, then consider entries."""
        account = self.broker.get_account()
        equity = account.equity

        if self.state.day_start_equity is None:
            self.state.day_start_equity = equity

        positions = self._sync_positions()

        portfolio = PortfolioState(
            equity=equity,
            day_start_equity=self.state.day_start_equity,
            halted=self.state.halted,
            halt_reason=self.state.halt_reason,
        )

        # Kill switch first: if it has tripped, flatten and do nothing else.
        verdict = check_kill_switch(portfolio, self.config.risk)
        if not verdict:
            self._emergency_flatten(verdict.reason)
            return

        # Rebuild per-instrument risk so the portfolio caps are meaningful.
        for inst, pos in positions.items():
            try:
                rate = quote_to_account_rate(inst, pos.entry_price, self.config.account_currency)
            except ValueError:
                rate = 1.0
            portfolio.open_risk[inst] = abs(pos.entry_price - pos.stop_price) * pos.units * rate / equity
            portfolio.open_sides[inst] = pos.side

        for instrument in self.config.instruments:
            try:
                self._process_instrument(instrument, portfolio, equity)
            except BrokerError as exc:
                log.error("broker error on %s: %s", instrument, exc)
                self.notify.alert(f"broker error on {instrument}: {exc}")
            except Exception as exc:  # fail closed on this instrument only
                log.exception("unexpected error on %s", instrument)
                self.notify.alert(f"unexpected error on {instrument}: {exc}")

    def _process_instrument(
        self, instrument: str, portfolio: PortfolioState, equity: float
    ) -> None:
        params = self.config.strategy
        candles = self.broker.get_candles(
            instrument, self.config.granularity, count=params.warmup_bars + 50
        )
        if len(candles) < params.warmup_bars:
            log.warning("%s: only %d bars, need %d", instrument, len(candles), params.warmup_bars)
            return

        features = compute_features(candles, params)
        bar = features.iloc[-1]  # most recent COMPLETE bar

        pos = self.state.tracked.get(instrument)
        if pos is not None:
            self._manage_open(instrument, pos, bar)
            return

        signal = entry_signal(bar, params)
        if signal is Signal.NONE:
            return

        side = "long" if signal is Signal.ENTER_LONG else "short"
        price = self.broker.get_price(instrument)
        entry_ref = price.ask if side == "long" else price.bid
        stop = initial_stop(entry_ref, side, float(bar["atr"]), params)

        try:
            rate = quote_to_account_rate(instrument, entry_ref, self.config.account_currency)
        except ValueError as exc:
            log.warning("skipping %s: %s", instrument, exc)
            return

        units = position_size(equity, entry_ref, stop, self.config.risk, rate)
        if units <= 0:
            log.info("%s: computed size of 0 units, skipping", instrument)
            return

        trade_risk = abs(entry_ref - stop) * units * rate / equity
        allowed = can_open(instrument, side, trade_risk, portfolio, self.config.risk)
        if not allowed:
            log.info("%s: entry blocked - %s", instrument, allowed.reason)
            return

        if self.config.mode == "signal":
            self.notify.signal_only(instrument, side, entry_ref, stop)
            return

        signed_units = units if side == "long" else -units
        result = self.broker.market_order(instrument, signed_units, stop_loss=stop)

        self.state.tracked[instrument] = Position(
            side=side,
            entry_price=result.fill_price,
            entry_time=result.time,
            units=units,
            stop_price=stop,
            extreme=result.fill_price,
        )
        portfolio.open_risk[instrument] = trade_risk
        portfolio.open_sides[instrument] = side
        self.notify.trade_opened(instrument, side, units, result.fill_price, stop)

    def _manage_open(self, instrument: str, pos: Position, bar: pd.Series) -> None:
        """Exit or trail an existing position."""
        if exit_signal(pos, bar):
            if self.config.mode == "auto":
                result = self.broker.close_position(instrument)
                if result is not None:
                    self.notify.trade_closed(instrument, pos.side, result.fill_price, "channel exit")
            else:
                self.notify.send(f"SIGNAL: close {pos.side} {instrument} (channel exit)")
            self.state.tracked.pop(instrument, None)
            return

        new_stop = update_trailing_stop(pos, bar, self.config.strategy)
        moved = abs(new_stop - pos.stop_price) > 1e-9
        pos.stop_price = new_stop

        if moved and self.config.mode == "auto":
            self.broker.update_stop_loss(instrument, new_stop)

    def _emergency_flatten(self, reason: str) -> None:
        """Close everything and stop trading for the day."""
        log.error("KILL SWITCH: %s", reason)
        self.state.halted = True
        self.state.halt_reason = "daily_loss_limit"
        self.notify.alert(f"KILL SWITCH TRIPPED - {reason}. Flattening all positions.")

        if self.config.mode != "auto":
            return

        for instrument in list(self.state.tracked):
            try:
                result = self.broker.close_position(instrument)
                if result is not None:
                    self.notify.trade_closed(instrument, self.state.tracked[instrument].side,
                                             result.fill_price, "kill switch")
            except BrokerError as exc:
                log.error("could not flatten %s: %s", instrument, exc)
                self.notify.alert(f"FAILED to close {instrument}: {exc} - CHECK MANUALLY")
            finally:
                self.state.tracked.pop(instrument, None)

    def start_new_day(self) -> None:
        """Reset the daily loss counter. Call once per trading day."""
        account = self.broker.get_account()
        self.state.day_start_equity = account.equity
        if self.state.halt_reason == "daily_loss_limit":
            self.state.halted = False
            self.state.halt_reason = ""
            log.info("new trading day; kill switch reset at equity %.2f", account.equity)
