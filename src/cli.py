"""Command line entry points.

    python -m src.cli backtest            # run the strategy over history
    python -m src.cli fetch               # download and cache candles
    python -m src.cli run                 # one live cycle
    python -m src.cli status              # account and open positions
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from .backtest import Backtester
from .broker.oanda import OandaBroker
from .config import load_config
from .engine import TradingEngine
from .notify import Notifier

CACHE = Path("data/cache")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _broker(cfg):
    cfg.validate_for_trading()
    return OandaBroker(cfg.oanda_token, cfg.oanda_account, cfg.oanda_env)


def cmd_fetch(args) -> int:
    """Download candles and cache them so backtests do not re-hit the API."""
    cfg = load_config(args.config)
    broker = _broker(cfg)
    CACHE.mkdir(parents=True, exist_ok=True)

    for instrument in cfg.instruments:
        df = broker.get_candles(instrument, cfg.granularity, count=args.count)
        path = CACHE / f"{instrument}_{cfg.granularity}.csv"
        df.to_csv(path)
        print(f"{instrument:10s} {len(df):5d} bars  {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}")
    return 0


def cmd_backtest(args) -> int:
    cfg = load_config(args.config)
    data: dict[str, pd.DataFrame] = {}

    for instrument in cfg.instruments:
        path = CACHE / f"{instrument}_{cfg.granularity}.csv"
        if not path.exists():
            print(f"missing {path} - run 'fetch' first", file=sys.stderr)
            continue
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        data[instrument] = df

    if not data:
        print("no cached data found. Run: python -m src.cli fetch", file=sys.stderr)
        return 1

    result = Backtester(
        strategy_params=cfg.strategy,
        risk_params=cfg.risk,
        starting_equity=cfg.starting_equity,
        account_currency=cfg.account_currency,
    ).run(data)

    print(result.summary())
    print()
    print("READ THIS BEFORE BELIEVING THE NUMBER ABOVE")
    print("  Backtests on bar data are structurally optimistic about stop exits:")
    print("  a bar shows the stop level was touched, so the engine fills there.")
    print("  Measured against a no-edge control, that is worth roughly +0.2%/year.")
    print("  Subtract it before drawing conclusions, and treat the max drawdown")
    print("  as the honest number - it is the one you will actually have to sit through.")

    if args.save:
        result.equity_curve.to_csv(args.save)
        print(f"\nequity curve written to {args.save}")
    return 0


def cmd_run(args) -> int:
    cfg = load_config(args.config)
    broker = _broker(cfg)
    engine = TradingEngine(broker, cfg, Notifier(cfg.telegram_token, cfg.telegram_chat))

    if cfg.is_live_money:
        print("*** LIVE MONEY, AUTO EXECUTION ***")
        if not args.yes and input("type LIVE to continue: ").strip() != "LIVE":
            print("aborted")
            return 1

    if args.new_day:
        engine.start_new_day()

    engine.run_cycle()
    print("cycle complete")
    return 0


def cmd_status(args) -> int:
    cfg = load_config(args.config)
    broker = _broker(cfg)
    account = broker.get_account()

    print(f"account   {account.account_id} ({cfg.oanda_env})")
    print(f"currency  {account.currency}")
    print(f"balance   {account.balance:,.2f}")
    print(f"equity    {account.equity:,.2f}")
    print(f"margin    {account.margin_available:,.2f}")

    positions = broker.get_open_positions()
    print(f"\nopen positions: {len(positions)}")
    for p in positions:
        print(f"  {p.instrument:10s} {p.side:5s} {p.units:>12,.0f} @ {p.entry_price:.5f}  "
              f"P&L {p.unrealised_pnl:>+10,.2f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forex-bot", description="Trend-following forex bot")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch", help="download and cache candles")
    p.add_argument("--count", type=int, default=2500)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("backtest", help="run the strategy over cached history")
    p.add_argument("--save", help="write the equity curve to this CSV")
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("run", help="execute one live cycle")
    p.add_argument("--new-day", action="store_true", help="reset the daily loss counter first")
    p.add_argument("--yes", action="store_true", help="skip the live-money confirmation")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("status", help="show account and positions")
    p.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    try:
        return args.func(args)
    except Exception as exc:
        logging.getLogger("cli").error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
