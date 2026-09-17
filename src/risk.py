"""Position sizing, portfolio limits and the kill switch.

This module is the reason the account survives long enough for any edge to show
up. The strategy decides direction; everything about how much is decided here.

The governing idea is constant fractional risk: every trade risks the same small
slice of equity between entry and stop, regardless of instrument or volatility.
A wide stop gets a small position, a tight stop a larger one. Without this, one
high-volatility pair quietly dominates the whole portfolio's P&L.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

log = logging.getLogger(__name__)

from .rates import split_pair  # single definition, shared with the rate book


@dataclass(frozen=True)
class RiskParams:
    """Risk limits. Every one of these is a brake, not an accelerator."""

    risk_per_trade: float = 0.005      # 0.5% of equity between entry and stop
    max_open_positions: int = 4        # concurrency cap
    max_portfolio_risk: float = 0.02   # 2% total open risk across all positions
    max_per_currency: int = 2          # cap correlated bets on one currency
    daily_loss_limit: float = 0.03     # -3% on the day -> flatten and stand down
    max_units_per_trade: int = 1_000_000  # absolute backstop against a sizing bug

    def __post_init__(self) -> None:
        if not 0 < self.risk_per_trade <= 0.05:
            raise ValueError(
                "risk_per_trade must be in (0, 0.05]. Above 5% per trade a normal "
                "losing streak is an account-ending event."
            )
        if not 0 < self.max_portfolio_risk <= 0.20:
            raise ValueError("max_portfolio_risk must be in (0, 0.20]")
        if not 0 < self.daily_loss_limit <= 0.50:
            raise ValueError("daily_loss_limit must be in (0, 0.50]")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be >= 1")
        if self.max_per_currency < 1:
            raise ValueError("max_per_currency must be >= 1")

        # The two caps are COUPLED. Every position consumes risk_per_trade of the
        # portfolio budget, so the budget imposes its own position limit. Setting
        # max_open_positions above that limit is dead configuration - it reads
        # like a change but cannot alter a single trade, which is exactly the
        # kind of silent no-op that wastes days of tuning.
        if self.max_open_positions > self.effective_max_positions:
            log.warning(
                "max_open_positions=%d is unreachable: max_portfolio_risk=%.1f%% "
                "at %.2f%% per trade allows only %d concurrent positions. "
                "Raise max_portfolio_risk to make the position cap bite.",
                self.max_open_positions,
                self.max_portfolio_risk * 100,
                self.risk_per_trade * 100,
                self.effective_max_positions,
            )

    @property
    def effective_max_positions(self) -> int:
        """Positions actually reachable, given both caps.

        The binding limit is whichever cap is tighter: the explicit position
        count, or how many full-size trades the portfolio risk budget affords.
        """
        from_budget = int(self.max_portfolio_risk / self.risk_per_trade)
        return max(1, min(self.max_open_positions, from_budget))


def position_size(
    equity: float,
    entry_price: float,
    stop_price: float,
    risk_params: RiskParams,
    quote_to_account_rate: float = 1.0,
) -> int:
    """Units to trade so that entry -> stop costs exactly risk_per_trade of equity.

    Args:
        equity: account equity in the account's currency.
        entry_price / stop_price: in quote currency per unit of base.
        quote_to_account_rate: multiplier converting a quote-currency amount into
            account currency. 1.0 when the quote currency IS the account currency
            (e.g. EUR_USD on a USD account). For USD_JPY on a USD account this is
            1/USDJPY, since the P&L lands in yen and must be converted back.

    Returns a whole number of units, floored, and 0 if the trade cannot be sized
    safely. Returning 0 is a valid and intentional outcome - skipping a trade is
    always cheaper than guessing at its size.
    """
    if equity <= 0:
        return 0
    if quote_to_account_rate <= 0:
        raise ValueError(f"quote_to_account_rate must be positive, got {quote_to_account_rate}")

    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return 0

    risk_amount = equity * risk_params.risk_per_trade
    risk_per_unit = stop_distance * quote_to_account_rate
    units = int(risk_amount / risk_per_unit)
    return max(0, min(units, risk_params.max_units_per_trade))


@dataclass
class PortfolioState:
    """Live view of what is at risk right now.

    `open_risk` maps a position key to the fraction of equity it would cost if
    stopped out, so the portfolio cap is checked against real exposure rather
    than a position count.
    """

    equity: float
    day_start_equity: float
    open_risk: dict[str, float] = field(default_factory=dict)
    open_sides: dict[str, str] = field(default_factory=dict)
    halted: bool = False
    halt_reason: str = ""

    @property
    def total_open_risk(self) -> float:
        return sum(self.open_risk.values())

    @property
    def open_count(self) -> int:
        return len(self.open_risk)

    @property
    def day_pnl_pct(self) -> float:
        """Today's return so far, as a fraction of the day's opening equity."""
        if self.day_start_equity <= 0:
            return 0.0
        return (self.equity - self.day_start_equity) / self.day_start_equity

    def currency_exposure(self) -> dict[str, int]:
        """How many open positions touch each currency.

        Long EUR_USD and long GBP_USD are not two independent bets - they are
        substantially one short-USD bet. Counting per currency is a crude but
        effective brake on stacking the same trade under different tickers.
        """
        counts: dict[str, int] = {}
        for instrument in self.open_risk:
            base, quote = split_pair(instrument)
            for ccy in (base, quote):
                counts[ccy] = counts.get(ccy, 0) + 1
        return counts

    def start_new_day(self, now: pd.Timestamp | None = None) -> None:
        """Reset the daily loss counter and lift a daily halt."""
        self.day_start_equity = self.equity
        if self.halted and self.halt_reason == "daily_loss_limit":
            self.halted = False
            self.halt_reason = ""


@dataclass(frozen=True)
class RiskDecision:
    """Verdict on a proposed trade. `reason` is logged so refusals are auditable."""

    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.allowed


def check_kill_switch(state: PortfolioState, risk_params: RiskParams) -> RiskDecision:
    """Has the account lost more than the daily limit?

    Trips on a drawdown measured from the day's opening equity. Once tripped,
    the engine closes everything and takes no new trades until the next day.
    The point is to bound the damage from a broken assumption, a bad data feed
    or a genuinely violent session - failures we cannot anticipate individually.
    """
    if state.day_pnl_pct <= -risk_params.daily_loss_limit:
        return RiskDecision(
            False,
            f"daily loss limit hit: {state.day_pnl_pct:.2%} <= -{risk_params.daily_loss_limit:.2%}",
        )
    return RiskDecision(True)


def can_open(
    instrument: str,
    side: str,
    trade_risk: float,
    state: PortfolioState,
    risk_params: RiskParams,
) -> RiskDecision:
    """Gate every new entry against the portfolio limits.

    Checks run cheapest-and-most-fatal first so the logged reason is the most
    informative one.
    """
    if state.halted:
        return RiskDecision(False, f"trading halted: {state.halt_reason}")

    kill = check_kill_switch(state, risk_params)
    if not kill:
        return kill

    if instrument in state.open_risk:
        return RiskDecision(False, f"already holding {instrument}")

    if state.open_count >= risk_params.max_open_positions:
        return RiskDecision(
            False,
            f"at position cap ({state.open_count}/{risk_params.max_open_positions})",
        )

    projected = state.total_open_risk + trade_risk
    if projected > risk_params.max_portfolio_risk:
        return RiskDecision(
            False,
            f"portfolio risk would reach {projected:.2%} "
            f"(cap {risk_params.max_portfolio_risk:.2%})",
        )

    exposure = state.currency_exposure()
    base, quote = split_pair(instrument)
    for ccy in (base, quote):
        if exposure.get(ccy, 0) >= risk_params.max_per_currency:
            return RiskDecision(
                False,
                f"{ccy} exposure at cap ({exposure[ccy]}/{risk_params.max_per_currency})",
            )

    return RiskDecision(True)
