"""Currency conversion tests.

A wrong conversion rate is one of the most dangerous bugs possible here: it
misprices position size silently. Sizing a JPY cross as if the rate were 1.0
would open a position ~150x too large, and every risk cap downstream would
happily wave it through because they all work in account currency.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.costs import quote_to_account_rate
from src.rates import (
    BrokerRateBook,
    MissingRateError,
    RateBook,
    canonical_pair,
    required_conversion_pairs,
    split_pair,
)


@pytest.fixture
def book():
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    return RateBook({
        "GBP_USD": pd.Series([1.26, 1.27, 1.28], index=idx),
        "USD_JPY": pd.Series([155.0, 156.0, 157.0], index=idx),
        "AUD_USD": pd.Series([0.65, 0.66, 0.67], index=idx),
    })


# ------------------------------------------------------------------- naming

@pytest.mark.parametrize("a,b,expected", [
    ("JPY", "USD", "USD_JPY"),   # never quoted JPY_USD
    ("USD", "EUR", "EUR_USD"),   # never quoted USD_EUR
    ("GBP", "JPY", "GBP_JPY"),
    ("CAD", "CHF", "CAD_CHF"),
])
def test_canonical_pair_follows_market_convention(a, b, expected):
    assert canonical_pair(a, b) == expected


def test_canonical_pair_rejects_same_currency():
    with pytest.raises(ValueError):
        canonical_pair("USD", "USD")


def test_split_pair_rejects_junk():
    with pytest.raises(ValueError):
        split_pair("NOTAPAIR")


# -------------------------------------------------------- required extras

def test_usd_crossed_universe_needs_nothing_extra():
    assert required_conversion_pairs(["EUR_USD", "USD_JPY", "AUD_USD"], "USD") == []


def test_cross_pair_requires_its_quote_leg():
    assert required_conversion_pairs(["EUR_GBP"], "USD") == ["GBP_USD"]


def test_already_traded_pairs_are_not_duplicated():
    """GBP_USD is in the universe, so it must not be listed as an extra fetch."""
    assert required_conversion_pairs(["EUR_GBP", "GBP_USD"], "USD") == []


def test_eur_account_needs_eur_legs():
    needed = required_conversion_pairs(["USD_CAD", "USD_CHF"], "EUR")
    assert needed == ["EUR_CAD", "EUR_CHF"]


# ---------------------------------------------------------------- lookups

def test_same_currency_is_identity(book):
    assert book.rate("USD", "USD") == 1.0


def test_direct_rate(book):
    assert book.rate("GBP", "USD") == pytest.approx(1.28)  # latest observation


def test_inverse_rate(book):
    """JPY->USD comes from USD_JPY, inverted."""
    assert book.rate("JPY", "USD") == pytest.approx(1 / 157.0)


def test_historical_lookup_uses_the_rate_of_the_day(book):
    """A backtest must convert at a rate that was knowable at the time."""
    when = pd.Timestamp("2024-01-02")
    assert book.rate("GBP", "USD", when) == pytest.approx(1.27)


def test_lookup_before_series_starts_raises(book):
    with pytest.raises(MissingRateError, match="no observation"):
        book.rate("GBP", "USD", pd.Timestamp("2020-01-01"))


def test_unresolvable_rate_names_what_is_needed(book):
    with pytest.raises(MissingRateError) as exc:
        book.rate("CAD", "USD")
    assert "CAD_USD" in str(exc.value) and "USD_CAD" in str(exc.value)


def test_no_triangulation_is_attempted(book):
    """GBP->JPY is derivable via USD, but chained rates compound error.

    The book must refuse rather than quietly triangulate.
    """
    with pytest.raises(MissingRateError):
        book.rate("GBP", "JPY")


# ------------------------------------------- integration with sizing costs

def test_quote_conversion_for_a_true_cross(book):
    """EUR_GBP on a USD account: P&L is in GBP, so the rate is GBP->USD."""
    assert quote_to_account_rate("EUR_GBP", 0.85, "USD", rates=book) == pytest.approx(1.28)


def test_jpy_cross_conversion_is_not_one(book):
    """The dangerous case: AUD_JPY P&L is in yen, ~157x smaller per unit.

    If this ever returned 1.0 the bot would size positions ~157x too big.
    """
    rate = quote_to_account_rate("AUD_JPY", 95.0, "USD", rates=book)
    assert rate == pytest.approx(1 / 157.0)
    assert rate < 0.01


def test_cross_without_a_provider_still_refuses():
    with pytest.raises(ValueError, match="no rate provider"):
        quote_to_account_rate("EUR_GBP", 0.85, "USD")


def test_direct_legs_never_consult_the_provider():
    """EUR_USD and USD_JPY on a USD account need no external rate at all."""
    assert quote_to_account_rate("EUR_USD", 1.10, "USD") == 1.0
    assert quote_to_account_rate("USD_JPY", 157.0, "USD") == pytest.approx(1 / 157.0)


# --------------------------------------------------------- live rate book

class FakeBroker:
    """Prices only the pairs it lists, and counts calls."""

    def __init__(self, prices: dict[str, float]):
        self.prices = prices
        self.calls = 0

    def get_price(self, instrument):
        self.calls += 1
        if instrument not in self.prices:
            raise RuntimeError(f"{instrument} not offered")
        from src.broker.base import Price

        p = self.prices[instrument]
        return Price(instrument=instrument, bid=p - 0.0001, ask=p + 0.0001, time=None)


def test_broker_book_resolves_direct_and_inverse():
    broker = FakeBroker({"GBP_USD": 1.28, "USD_JPY": 157.0})
    rates = BrokerRateBook(broker)
    assert rates.rate("GBP", "USD") == pytest.approx(1.28, abs=1e-4)
    assert rates.rate("JPY", "USD") == pytest.approx(1 / 157.0, abs=1e-6)


def test_broker_book_caches_within_a_cycle():
    """Each uncached lookup is a network call inside the trading loop."""
    broker = FakeBroker({"GBP_USD": 1.28})
    rates = BrokerRateBook(broker)
    rates.rate("GBP", "USD")
    calls_after_first = broker.calls
    rates.rate("GBP", "USD")
    assert broker.calls == calls_after_first, "second lookup hit the network"

    rates.clear()
    rates.rate("GBP", "USD")
    assert broker.calls > calls_after_first, "clear() did not invalidate the cache"


def test_broker_book_raises_when_nothing_prices_it():
    rates = BrokerRateBook(FakeBroker({}))
    with pytest.raises(MissingRateError):
        rates.rate("CAD", "USD")
