"""Event-driven portfolio backtester.

Ordering within each bar is chosen so that no decision can ever use information
that was not available when it was made:

  1. Fill orders queued by YESTERDAY's close, at TODAY's open (plus costs)
  2. Check stops against today's high/low
  3. On today's close: exit signals, trail stops, generate tomorrow's entries

The most common way a backtest lies is by collapsing steps 1 and 3 - generating
a signal on a bar's close and filling it at that same close. That is a free look
at the future and it can turn a losing system into a spectacular one on paper.

Gap handling: if a bar OPENS beyond the stop, the fill is the open, not the stop
price. Stops do not hold through gaps, and pretending they do understates the
worst losses - which are the ones that actually matter.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .costs import CostModel, cost_for, quote_to_account_rate
from .rates import MissingRateError, RateBook
from .risk import PortfolioState, RiskParams, can_open, position_size
from .strategy import (
    Position,
    Signal,
    StrategyParams,
    compute_features,
    entry_signal,
    exit_signal,
    initial_stop,
    update_trailing_stop,
)

log = logging.getLogger(__name__)


@dataclass
class Trade:
    """A completed round trip."""

    instrument: str
    side: str
    units: float
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    pnl: float
    exit_reason: str
    bars_held: int

    @property
    def return_pips(self) -> float:
        from .costs import pip_size

        direction = 1 if self.side == "long" else -1
        return direction * (self.exit_price - self.entry_price) / pip_size(self.instrument)


@dataclass
class PendingOrder:
    """An entry decided on yesterday's close, to be filled at today's open."""

    instrument: str
    side: str
    signal_atr: float


@dataclass
class BacktestResult:
    """Everything the run produced. `summary()` renders the numbers that matter."""

    equity_curve: pd.Series
    trades: list[Trade]
    starting_equity: float
    params: StrategyParams
    risk_params: RiskParams
    rejected_entries: dict[str, int] = field(default_factory=dict)

    # ------------------------------------------------------------- statistics

    @property
    def final_equity(self) -> float:
        return float(self.equity_curve.iloc[-1]) if len(self.equity_curve) else self.starting_equity

    @property
    def total_return(self) -> float:
        return self.final_equity / self.starting_equity - 1.0

    @property
    def years(self) -> float:
        if len(self.equity_curve) < 2:
            return 0.0
        span = self.equity_curve.index[-1] - self.equity_curve.index[0]
        return max(span.days / 365.25, 1e-9)

    @property
    def cagr(self) -> float:
        """Compound annual growth rate."""
        if self.years <= 0 or self.final_equity <= 0:
            return 0.0
        return (self.final_equity / self.starting_equity) ** (1 / self.years) - 1.0

    @property
    def max_drawdown(self) -> float:
        """Worst peak-to-trough fall, as a positive fraction.

        The number to judge a system by. A 40% drawdown is not an abstraction:
        it is watching 40% of the account disappear while the bot keeps trading,
        and it is the point at which most people switch the bot off - locking in
        the loss right before the recovery.
        """
        if len(self.equity_curve) < 2:
            return 0.0
        running_peak = self.equity_curve.cummax()
        return float(((running_peak - self.equity_curve) / running_peak).max())

    @property
    def sharpe(self) -> float:
        """Annualised Sharpe on daily returns, excess over zero."""
        if len(self.equity_curve) < 30:
            return 0.0
        returns = self.equity_curve.pct_change().dropna()
        if returns.std() == 0 or np.isnan(returns.std()):
            return 0.0
        return float(returns.mean() / returns.std() * np.sqrt(252))

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return sum(1 for t in self.trades if t.pnl > 0) / len(self.trades)

    @property
    def profit_factor(self) -> float:
        """Gross wins / gross losses. Below 1.0 the system loses money."""
        gross_win = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        if gross_loss == 0:
            return float("inf") if gross_win > 0 else 0.0
        return gross_win / gross_loss

    @property
    def expectancy(self) -> float:
        """Average P&L per trade in account currency."""
        if not self.trades:
            return 0.0
        return sum(t.pnl for t in self.trades) / len(self.trades)

    @property
    def avg_win(self) -> float:
        wins = [t.pnl for t in self.trades if t.pnl > 0]
        return sum(wins) / len(wins) if wins else 0.0

    @property
    def avg_loss(self) -> float:
        losses = [t.pnl for t in self.trades if t.pnl < 0]
        return sum(losses) / len(losses) if losses else 0.0

    def summary(self) -> str:
        """Human-readable report."""
        if not self.trades:
            return (
                "NO TRADES TAKEN\n"
                "The strategy never triggered over this period. Usually this means "
                "too little history for the warmup, or filters so tight nothing passes."
            )

        longs = sum(1 for t in self.trades if t.side == "long")
        payoff = abs(self.avg_win / self.avg_loss) if self.avg_loss else float("inf")
        rejects = ", ".join(f"{k}={v}" for k, v in sorted(self.rejected_entries.items())) or "none"

        return f"""
BACKTEST RESULT
{'=' * 62}
Period            {self.equity_curve.index[0]:%Y-%m-%d} to {self.equity_curve.index[-1]:%Y-%m-%d}  ({self.years:.1f} years)
Starting equity   {self.starting_equity:,.2f}
Final equity      {self.final_equity:,.2f}

RETURN
  Total return      {self.total_return:>9.2%}
  CAGR              {self.cagr:>9.2%}
  Max drawdown      {self.max_drawdown:>9.2%}   <-- judge the system by this
  Sharpe ratio      {self.sharpe:>9.2f}

TRADES
  Count             {len(self.trades):>9d}   ({longs} long / {len(self.trades) - longs} short)
  Win rate          {self.win_rate:>9.1%}   (trend systems are normally 30-45%)
  Profit factor     {self.profit_factor:>9.2f}   (< 1.00 means it loses money)
  Expectancy        {self.expectancy:>9.2f}   per trade
  Average win       {self.avg_win:>9.2f}
  Average loss      {self.avg_loss:>9.2f}
  Payoff ratio      {payoff:>9.2f}   (win size / loss size)

Entries blocked by risk limits: {rejects}
{'=' * 62}
Costs (spread + slippage) are included in every fill above.
""".strip()


class Backtester:
    """Runs the strategy over historical bars for a portfolio of instruments."""

    def __init__(
        self,
        strategy_params: StrategyParams | None = None,
        risk_params: RiskParams | None = None,
        starting_equity: float = 10_000.0,
        account_currency: str = "USD",
        costs: dict[str, CostModel] | None = None,
    ) -> None:
        self.params = strategy_params or StrategyParams()
        self.risk = risk_params or RiskParams()
        self.starting_equity = starting_equity
        self.account_currency = account_currency
        self._cost_override = costs or {}

    def _costs(self, instrument: str) -> CostModel:
        return self._cost_override.get(instrument, cost_for(instrument))

    def _pnl(
        self,
        pos: Position,
        instrument: str,
        exit_price: float,
        when: pd.Timestamp | None = None,
        rates: RateBook | None = None,
    ) -> float:
        """Realised P&L in account currency, converted at the time of the exit."""
        direction = 1 if pos.is_long else -1
        move = (exit_price - pos.entry_price) * direction
        rate = quote_to_account_rate(
            instrument, exit_price, self.account_currency, rates=rates, when=when
        )
        return move * pos.units * rate

    def run(
        self,
        data: dict[str, pd.DataFrame],
        conversion_data: dict[str, pd.DataFrame] | None = None,
    ) -> BacktestResult:
        """Execute the backtest.

        Args:
            data: instrument -> OHLC DataFrame, indexed by bar-close timestamp.
                These are the instruments that will be TRADED.
            conversion_data: extra series used only to convert P&L into the
                account currency (see rates.required_conversion_pairs). They are
                never traded. Omit it when every pair touches the account
                currency.
        """
        if not data:
            raise ValueError("no data supplied to backtest")

        rates = RateBook.from_candles({**(conversion_data or {}), **data})

        features = {
            inst: compute_features(df, self.params) for inst, df in data.items()
        }

        # Union of all timestamps, so instruments with gaps (holidays) still work.
        timeline = sorted(set().union(*(df.index for df in features.values())))
        if len(timeline) <= self.params.warmup_bars:
            raise ValueError(
                f"need more than {self.params.warmup_bars} bars for warmup, "
                f"got {len(timeline)}. Fetch more history."
            )

        equity = self.starting_equity
        state = PortfolioState(equity=equity, day_start_equity=equity)
        positions: dict[str, Position] = {}
        pending: list[PendingOrder] = []
        trades: list[Trade] = []
        rejected: dict[str, int] = {}
        curve: list[tuple[pd.Timestamp, float]] = []
        entry_bar_index: dict[str, int] = {}

        for i, ts in enumerate(timeline):
            bars = {
                inst: df.loc[ts] for inst, df in features.items() if ts in df.index
            }

            # -- 1. Fill orders queued at yesterday's close, at today's open ----
            for order in pending:
                bar = bars.get(order.instrument)
                if bar is None or pd.isna(bar["open"]):
                    continue  # instrument did not trade today; order lapses

                costs = self._costs(order.instrument)
                fill = costs.entry_fill(order.instrument, bar["open"], order.side)
                stop = initial_stop(fill, order.side, order.signal_atr, self.params)

                try:
                    rate = quote_to_account_rate(
                        order.instrument, fill, self.account_currency,
                        rates=rates, when=ts,
                    )
                except (ValueError, MissingRateError) as exc:
                    log.warning("skipping %s: %s", order.instrument, exc)
                    rejected["no_conversion_rate"] = rejected.get("no_conversion_rate", 0) + 1
                    continue

                units = position_size(equity, fill, stop, self.risk, rate)
                if units <= 0:
                    rejected["size_zero"] = rejected.get("size_zero", 0) + 1
                    continue

                trade_risk = abs(fill - stop) * units * rate / equity
                verdict = can_open(order.instrument, order.side, trade_risk, state, self.risk)
                if not verdict:
                    key = verdict.reason.split(":")[0].split("(")[0].strip()
                    rejected[key] = rejected.get(key, 0) + 1
                    continue

                positions[order.instrument] = Position(
                    side=order.side,
                    entry_price=fill,
                    entry_time=ts,
                    units=units,
                    stop_price=stop,
                    extreme=fill,
                )
                entry_bar_index[order.instrument] = i
                state.open_risk[order.instrument] = trade_risk
                state.open_sides[order.instrument] = order.side

            pending = []

            # -- 2. Stops, checked against today's range -----------------------
            for inst in list(positions):
                bar = bars.get(inst)
                if bar is None:
                    continue
                pos = positions[inst]

                hit = (
                    bar["low"] <= pos.stop_price if pos.is_long
                    else bar["high"] >= pos.stop_price
                )
                if not hit:
                    continue

                # A gap through the stop fills at the open, not at the stop.
                gapped = (
                    bar["open"] <= pos.stop_price if pos.is_long
                    else bar["open"] >= pos.stop_price
                )
                raw_fill = bar["open"] if gapped else pos.stop_price
                # stop_fill, not exit_fill: stops trigger into adverse movement.
                fill = self._costs(inst).stop_fill(inst, raw_fill, pos.side)

                pnl = self._pnl(pos, inst, fill, ts, rates)
                equity += pnl
                trades.append(
                    Trade(
                        instrument=inst,
                        side=pos.side,
                        units=pos.units,
                        entry_time=pos.entry_time,
                        entry_price=pos.entry_price,
                        exit_time=ts,
                        exit_price=fill,
                        pnl=pnl,
                        exit_reason="gap_through_stop" if gapped else "stop",
                        bars_held=i - entry_bar_index[inst],
                    )
                )
                del positions[inst]
                state.open_risk.pop(inst, None)
                state.open_sides.pop(inst, None)
                entry_bar_index.pop(inst, None)

            # -- 3. On the close: exits, trailing stops, tomorrow's entries -----
            for inst in list(positions):
                bar = bars.get(inst)
                if bar is None:
                    continue
                pos = positions[inst]

                if exit_signal(pos, bar):
                    fill = self._costs(inst).exit_fill(inst, bar["close"], pos.side)
                    pnl = self._pnl(pos, inst, fill, ts, rates)
                    equity += pnl
                    trades.append(
                        Trade(
                            instrument=inst,
                            side=pos.side,
                            units=pos.units,
                            entry_time=pos.entry_time,
                            entry_price=pos.entry_price,
                            exit_time=ts,
                            exit_price=fill,
                            pnl=pnl,
                            exit_reason="channel_exit",
                            bars_held=i - entry_bar_index[inst],
                        )
                    )
                    del positions[inst]
                    state.open_risk.pop(inst, None)
                    state.open_sides.pop(inst, None)
                    entry_bar_index.pop(inst, None)
                else:
                    pos.stop_price = update_trailing_stop(pos, bar, self.params)

            state.equity = equity

            # Daily kill switch. Flatten everything and stand down for the day.
            if not check_daily_limit(state, self.risk):
                for inst in list(positions):
                    bar = bars.get(inst)
                    if bar is None:
                        continue
                    pos = positions[inst]
                    fill = self._costs(inst).exit_fill(inst, bar["close"], pos.side)
                    pnl = self._pnl(pos, inst, fill, ts, rates)
                    equity += pnl
                    trades.append(
                        Trade(
                            instrument=inst, side=pos.side, units=pos.units,
                            entry_time=pos.entry_time, entry_price=pos.entry_price,
                            exit_time=ts, exit_price=fill, pnl=pnl,
                            exit_reason="kill_switch",
                            bars_held=i - entry_bar_index[inst],
                        )
                    )
                    del positions[inst]
                    state.open_risk.pop(inst, None)
                    state.open_sides.pop(inst, None)
                    entry_bar_index.pop(inst, None)
                rejected["kill_switch"] = rejected.get("kill_switch", 0) + 1
                state.equity = equity
            else:
                # Entry signals, queued for tomorrow's open.
                if i >= self.params.warmup_bars:
                    for inst, bar in bars.items():
                        if inst in positions:
                            continue
                        sig = entry_signal(bar, self.params)
                        if sig in (Signal.ENTER_LONG, Signal.ENTER_SHORT):
                            pending.append(
                                PendingOrder(
                                    instrument=inst,
                                    side="long" if sig is Signal.ENTER_LONG else "short",
                                    signal_atr=float(bar["atr"]),
                                )
                            )

            # Mark to market for the equity curve.
            unrealised = 0.0
            for inst, pos in positions.items():
                bar = bars.get(inst)
                if bar is not None and not pd.isna(bar["close"]):
                    unrealised += self._pnl(pos, inst, bar["close"], ts, rates)
            curve.append((ts, equity + unrealised))

            state.equity = equity
            state.start_new_day()

        equity_curve = pd.Series(
            [v for _, v in curve], index=pd.DatetimeIndex([t for t, _ in curve])
        )

        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            starting_equity=self.starting_equity,
            params=self.params,
            risk_params=self.risk,
            rejected_entries=rejected,
        )


def check_daily_limit(state: PortfolioState, risk: RiskParams):
    """Thin wrapper so the backtest and live engine share one kill-switch rule."""
    from .risk import check_kill_switch

    return check_kill_switch(state, risk)
