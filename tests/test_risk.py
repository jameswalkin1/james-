import pytest

from src.risk import (
    PortfolioState,
    RiskParams,
    can_open,
    check_kill_switch,
    position_size,
    split_pair,
)


def test_position_size_risks_exactly_the_configured_fraction():
    rp = RiskParams(risk_per_trade=0.01)
    units = position_size(equity=10_000, entry_price=1.1000, stop_price=1.0900, risk_params=rp)
    loss_if_stopped = units * (1.1000 - 1.0900)
    assert loss_if_stopped == pytest.approx(100.0, abs=1.0)  # 1% of 10k


def test_wider_stop_gives_smaller_position():
    rp = RiskParams()
    tight = position_size(10_000, 1.10, 1.095, rp)   # 50 pip stop
    wide = position_size(10_000, 1.10, 1.090, rp)    # 100 pip stop
    assert wide == pytest.approx(tight / 2, rel=0.01)


def test_quote_conversion_changes_size():
    """USD_JPY P&L lands in yen, so the same risk buys far more units."""
    rp = RiskParams()
    no_conv = position_size(10_000, 157.00, 155.00, rp, quote_to_account_rate=1.0)
    with_conv = position_size(10_000, 157.00, 155.00, rp, quote_to_account_rate=1 / 157.0)
    assert with_conv > no_conv * 100


def test_zero_or_inverted_stop_returns_no_position():
    rp = RiskParams()
    assert position_size(10_000, 1.10, 1.10, rp) == 0
    assert position_size(0, 1.10, 1.09, rp) == 0


def test_absurd_risk_per_trade_is_rejected():
    with pytest.raises(ValueError, match="risk_per_trade"):
        RiskParams(risk_per_trade=0.5)


def test_kill_switch_trips_at_daily_limit():
    rp = RiskParams(daily_loss_limit=0.03)
    state = PortfolioState(equity=9_700, day_start_equity=10_000)  # exactly -3%
    assert not check_kill_switch(state, rp)
    assert "daily loss limit" in check_kill_switch(state, rp).reason


def test_kill_switch_allows_smaller_loss():
    rp = RiskParams(daily_loss_limit=0.03)
    assert check_kill_switch(PortfolioState(equity=9_800, day_start_equity=10_000), rp)


def test_position_cap_blocks_extra_entries():
    rp = RiskParams(max_open_positions=2, max_per_currency=9)
    state = PortfolioState(equity=10_000, day_start_equity=10_000)
    state.open_risk = {"EUR_USD": 0.005, "GBP_JPY": 0.005}
    assert not can_open("AUD_NZD", "long", 0.005, state, rp)


def test_portfolio_risk_cap():
    rp = RiskParams(max_portfolio_risk=0.01, max_open_positions=9, max_per_currency=9)
    state = PortfolioState(equity=10_000, day_start_equity=10_000)
    state.open_risk = {"EUR_USD": 0.008}
    assert not can_open("GBP_JPY", "long", 0.005, state, rp)
    assert can_open("GBP_JPY", "long", 0.001, state, rp)


def test_currency_cap_prevents_stacking_the_same_bet():
    """Long EUR_USD + long GBP_USD + long AUD_USD is one big short-USD bet."""
    rp = RiskParams(max_per_currency=2, max_open_positions=9)
    state = PortfolioState(equity=10_000, day_start_equity=10_000)
    state.open_risk = {"EUR_USD": 0.005, "GBP_USD": 0.005}
    verdict = can_open("AUD_USD", "long", 0.005, state, rp)
    assert not verdict
    assert "USD" in verdict.reason


def test_cannot_double_up_on_one_instrument():
    rp = RiskParams()
    state = PortfolioState(equity=10_000, day_start_equity=10_000)
    state.open_risk = {"EUR_USD": 0.005}
    assert not can_open("EUR_USD", "long", 0.005, state, rp)


def test_halt_blocks_everything():
    rp = RiskParams()
    state = PortfolioState(equity=10_000, day_start_equity=10_000, halted=True, halt_reason="manual")
    assert not can_open("EUR_USD", "long", 0.001, state, rp)


@pytest.mark.parametrize("raw,expected", [("EUR_USD", ("EUR", "USD")), ("gbp/jpy", ("GBP", "JPY"))])
def test_split_pair(raw, expected):
    assert split_pair(raw) == expected


def test_split_pair_rejects_junk():
    with pytest.raises(ValueError):
        split_pair("NOTAPAIR")
