"""Trading cost model.

Backtests flatter strategies by default. Every cost left out shows up as profit
that does not exist. This module makes the three that matter explicit:

  spread     - you buy at ask and sell at bid, always
  slippage   - market orders fill slightly worse than the price you saw
  financing  - holding overnight earns or pays the interest rate differential

For a trend system on daily bars these are a modest drag. For anything trading
intraday they are frequently the entire difference between profit and loss,
which is exactly why they are modelled rather than assumed away.
"""
from __future__ import annotations

from dataclasses import dataclass


def pip_size(instrument: str) -> float:
    """Value of one pip in quote currency, per unit of base."""
    return 0.01 if instrument.upper().endswith("_JPY") else 0.0001


@dataclass(frozen=True)
class CostModel:
    """Per-instrument costs, in pips.

    Defaults are deliberately PESSIMISTIC - roughly OANDA retail spreads on
    majors, widened a little. Underestimating costs is the expensive mistake;
    overestimating them only means the live result beats the backtest.
    """

    spread_pips: float = 1.5
    slippage_pips: float = 0.5
    stop_slippage_pips: float = 1.5  # stops fill WORSE than limit/market orders
    financing_bps_per_day: float = 0.0  # annualised carry, as bps of notional/day

    def __post_init__(self) -> None:
        if min(self.spread_pips, self.slippage_pips, self.stop_slippage_pips) < 0:
            raise ValueError("costs cannot be negative")

    def entry_fill(self, instrument: str, price: float, side: str) -> float:
        """Realistic fill price for an entry, adverse by half-spread + slippage."""
        adverse = (self.spread_pips / 2 + self.slippage_pips) * pip_size(instrument)
        return price + adverse if side == "long" else price - adverse

    def exit_fill(self, instrument: str, price: float, side: str) -> float:
        """Realistic fill price for an exit. Exiting a long means selling at bid."""
        adverse = (self.spread_pips / 2 + self.slippage_pips) * pip_size(instrument)
        return price - adverse if side == "long" else price + adverse

    def stop_fill(self, instrument: str, price: float, side: str) -> float:
        """Fill price for a STOP exit, which is worse than an ordinary exit.

        A stop becomes a market order the moment it triggers, and it triggers
        precisely when price is moving against you - so it fills into a falling
        (or rising) market, not at the quiet level you chose. This is modelled
        separately because backtests on bar data are structurally optimistic here:
        the bar only tells us the stop level was touched, and assuming a fill
        exactly there is the single largest source of false profit in a
        stop-based system. Widening the stop fill is the honest correction.
        """
        adverse = (self.spread_pips / 2 + self.stop_slippage_pips) * pip_size(instrument)
        return price - adverse if side == "long" else price + adverse

    def financing_cost(self, notional: float, days_held: int) -> float:
        """Overnight financing. Positive result = a cost."""
        if self.financing_bps_per_day == 0 or days_held <= 0:
            return 0.0
        return abs(notional) * (self.financing_bps_per_day / 10_000.0) * days_held


# Per-instrument overrides. Majors are tight; crosses and JPY pairs less so.
DEFAULT_COSTS: dict[str, CostModel] = {
    "EUR_USD": CostModel(spread_pips=1.2, slippage_pips=0.3, stop_slippage_pips=1.0),
    "GBP_USD": CostModel(spread_pips=1.6, slippage_pips=0.4, stop_slippage_pips=1.4),
    "USD_JPY": CostModel(spread_pips=1.3, slippage_pips=0.3, stop_slippage_pips=1.1),
    "AUD_USD": CostModel(spread_pips=1.4, slippage_pips=0.4, stop_slippage_pips=1.3),
    "USD_CAD": CostModel(spread_pips=1.8, slippage_pips=0.4, stop_slippage_pips=1.6),
    "USD_CHF": CostModel(spread_pips=1.8, slippage_pips=0.4, stop_slippage_pips=1.6),
    "NZD_USD": CostModel(spread_pips=2.0, slippage_pips=0.5, stop_slippage_pips=1.8),
}


def cost_for(instrument: str) -> CostModel:
    """Cost model for an instrument, falling back to a conservative default."""
    return DEFAULT_COSTS.get(instrument.upper(), CostModel())


def quote_to_account_rate(
    instrument: str,
    price: float,
    account_currency: str = "USD",
    rates=None,
    when=None,
) -> float:
    """Convert a P&L amount in the pair's QUOTE currency into account currency.

    EUR_USD on a USD account: profit is already USD           -> 1.0
    USD_JPY on a USD account: profit is in JPY, convert back  -> 1/price

    A cross with neither leg in the account currency (EUR_GBP on a USD account)
    needs a third rate. Pass `rates` - a RateBook for backtests or a
    BrokerRateBook for live - and it resolves GBP->USD from the GBP_USD series.
    Without one, this raises rather than guessing: a silently wrong conversion
    rate misprices every position in that pair.

    `when` pins a historical lookup to a timestamp so a backtest converts at
    rates that were knowable at the time.
    """
    base, quote = instrument.upper().replace("/", "_").split("_")
    account_currency = account_currency.upper()

    if quote == account_currency:
        return 1.0
    if base == account_currency:
        if price <= 0:
            raise ValueError(f"cannot convert at non-positive price {price}")
        return 1.0 / price

    if rates is None:
        raise ValueError(
            f"{instrument} has neither leg in account currency {account_currency} "
            "and no rate provider was supplied. Pass a RateBook (backtest) or "
            "BrokerRateBook (live), or restrict the universe to "
            f"{account_currency}-crossed pairs."
        )
    return rates.rate(quote, account_currency, when)
