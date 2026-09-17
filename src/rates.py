"""Currency conversion for P&L that lands in a third currency.

THE PROBLEM
-----------
A trade's profit arrives in the pair's QUOTE currency. Trading EUR_GBP on a USD
account earns or loses GBP, and GBP is not USD. To size the position correctly -
and to book the P&L correctly - the bot needs a GBP->USD rate.

For a universe where every pair touches the account currency (EUR_USD, USD_JPY,
... on a USD account) this never comes up, which is why the first version of this
bot simply refused any other pair. That restriction had a cost: with every pair
sharing USD, the per-currency risk cap allowed only two concurrent positions and
silently discarded most valid signals.

This module lifts the restriction. Rates are resolved from ordinary candle series
the bot already knows how to fetch:

    direct   GBP->USD  from GBP_USD
    inverse  JPY->USD  from USD_JPY, as 1/price

Triangulation through a third currency is deliberately NOT implemented. Chained
rates compound their errors and silently produce plausible-looking nonsense.
When a rate cannot be resolved the code raises and names the exact series it
needs, so the fix is obvious rather than hidden.
"""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)


# Standard FX quoting precedence: the currency earlier in this list is the base.
# EUR/USD is never quoted USD/EUR, USD/JPY never JPY/USD. Brokers list the
# conventional side only, so a conversion pair has to be named the way the market
# names it or the fetch will 404.
QUOTE_PRECEDENCE = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "NOK", "SEK", "JPY"]


def canonical_pair(a: str, b: str) -> str:
    """Name a currency pair the way the market quotes it.

    >>> canonical_pair("JPY", "USD")
    'USD_JPY'
    >>> canonical_pair("USD", "EUR")
    'EUR_USD'
    """
    a, b = a.upper(), b.upper()
    if a == b:
        raise ValueError(f"cannot form a pair from {a} and itself")

    def rank(ccy: str) -> int:
        return QUOTE_PRECEDENCE.index(ccy) if ccy in QUOTE_PRECEDENCE else len(QUOTE_PRECEDENCE)

    return f"{a}_{b}" if rank(a) <= rank(b) else f"{b}_{a}"


def split_pair(instrument: str) -> tuple[str, str]:
    """'EUR_USD' or 'eur/usd' -> ('EUR', 'USD')."""
    parts = instrument.replace("/", "_").upper().split("_")
    if len(parts) != 2 or not all(len(p) == 3 for p in parts):
        raise ValueError(f"cannot parse instrument {instrument!r}, expected e.g. EUR_USD")
    return parts[0], parts[1]


class MissingRateError(ValueError):
    """A needed conversion rate is not available. Names what to supply."""


def required_conversion_pairs(
    instruments: list[str], account_currency: str = "USD"
) -> list[str]:
    """Extra series needed to convert every instrument's P&L into the account currency.

    Returns instrument names to fetch ALONGSIDE the traded universe, named the
    way the market quotes them, and excluding anything the universe already
    covers. A pair whose quote or base currency is the account currency needs
    nothing extra - its own price does the conversion.

    >>> required_conversion_pairs(["EUR_USD", "EUR_GBP"], "USD")
    ['GBP_USD']
    >>> required_conversion_pairs(["USD_JPY"], "EUR")
    ['EUR_JPY']
    """
    account_currency = account_currency.upper()
    have = {i.replace("/", "_").upper() for i in instruments}
    needed: list[str] = []

    for instrument in instruments:
        base, quote = split_pair(instrument)
        if quote == account_currency or base == account_currency:
            continue  # convertible from the instrument's own price
        pair = canonical_pair(quote, account_currency)
        if pair not in have and pair not in needed:
            needed.append(pair)

    return needed


class RateBook:
    """Resolves FROM->TO conversion rates from candle close series.

    Built from {instrument: close_series}. Both the traded universe and any
    auxiliary conversion series can be thrown in; the book works out which of
    them answers a given request.
    """

    def __init__(self, closes: dict[str, pd.Series] | None = None) -> None:
        self._by_ccy: dict[tuple[str, str], pd.Series] = {}
        for instrument, series in (closes or {}).items():
            base, quote = split_pair(instrument)
            self._by_ccy[(base, quote)] = series

    @classmethod
    def from_candles(cls, data: dict[str, pd.DataFrame]) -> RateBook:
        """Build from OHLC frames, using each one's close column."""
        return cls({inst: df["close"] for inst, df in data.items()})

    def add(self, instrument: str, closes: pd.Series) -> None:
        base, quote = split_pair(instrument)
        self._by_ccy[(base, quote)] = closes

    @property
    def available(self) -> list[str]:
        return [f"{b}_{q}" for b, q in sorted(self._by_ccy)]

    def rate(
        self, from_ccy: str, to_ccy: str, when: pd.Timestamp | None = None
    ) -> float:
        """Units of `to_ccy` per unit of `from_ccy`.

        `when` selects the last observation at or before that timestamp, so a
        backtest converts using rates that were knowable at the time. Omit it to
        use the most recent observation.
        """
        from_ccy, to_ccy = from_ccy.upper(), to_ccy.upper()
        if from_ccy == to_ccy:
            return 1.0

        direct = self._by_ccy.get((from_ccy, to_ccy))
        if direct is not None:
            return self._observe(direct, when, f"{from_ccy}_{to_ccy}")

        inverse = self._by_ccy.get((to_ccy, from_ccy))
        if inverse is not None:
            price = self._observe(inverse, when, f"{to_ccy}_{from_ccy}")
            if price <= 0:
                raise MissingRateError(f"non-positive price in {to_ccy}_{from_ccy}")
            return 1.0 / price

        raise MissingRateError(
            f"no rate for {from_ccy}->{to_ccy}. Supply candles for "
            f"{from_ccy}_{to_ccy} or {to_ccy}_{from_ccy}. "
            f"Available: {', '.join(self.available) or 'none'}"
        )

    @staticmethod
    def _observe(series: pd.Series, when: pd.Timestamp | None, label: str) -> float:
        if when is None:
            value = series.iloc[-1] if len(series) else float("nan")
        else:
            value = series.asof(when)  # last value at or before `when`
        if pd.isna(value):
            raise MissingRateError(
                f"{label} has no observation at or before {when}; "
                "the conversion series probably starts later than the traded data"
            )
        return float(value)


class BrokerRateBook:
    """Live rates, read from the broker on demand and cached for one cycle.

    Caching matters: a cycle may convert several instruments through the same
    currency, and each uncached lookup is a network round trip inside the
    trading loop.
    """

    def __init__(self, broker) -> None:
        self._broker = broker
        self._cache: dict[tuple[str, str], float] = {}

    def clear(self) -> None:
        """Drop cached rates. Call once per cycle so prices stay fresh."""
        self._cache.clear()

    def rate(
        self, from_ccy: str, to_ccy: str, when: pd.Timestamp | None = None
    ) -> float:
        from_ccy, to_ccy = from_ccy.upper(), to_ccy.upper()
        if from_ccy == to_ccy:
            return 1.0

        key = (from_ccy, to_ccy)
        if key in self._cache:
            return self._cache[key]

        for instrument, invert in (
            (f"{from_ccy}_{to_ccy}", False),
            (f"{to_ccy}_{from_ccy}", True),
        ):
            try:
                price = self._broker.get_price(instrument).mid
            except Exception:  # not offered by this broker, or not tradeable now
                continue
            if price <= 0:
                continue
            value = 1.0 / price if invert else price
            self._cache[key] = value
            return value

        raise MissingRateError(
            f"broker could not price {from_ccy}_{to_ccy} or {to_ccy}_{from_ccy}"
        )
