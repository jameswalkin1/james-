"""MetaTrader 5 implementation of the Broker interface.

Works with any MT5 broker - Vantage, OANDA's MT5 entity, IC Markets, Pepperstone.
Only the login credentials and the symbol names change.

RUNNING THIS
------------
The `MetaTrader5` package is WINDOWS-ONLY and talks to a running MT5 terminal
over local IPC. That means:

  - a Windows machine (or Windows VPS) with MT5 installed and LOGGED IN
  - the terminal must stay running; if it closes, the bot goes deaf mid-position
  - "Algo Trading" must be enabled in the terminal toolbar, or every order is
    rejected with AutoTrading disabled

This is strictly worse operationally than a REST API, and it is why v20 was the
first choice. It is, however, the only route most EU-regulated brokers offer.

SYMBOL NAMES
------------
MT5 brokers use their own symbol strings: "EURUSD", "EURUSD.a", "EURUSD-ECN",
"EURUSDm" all exist in the wild. The rest of this codebase speaks OANDA-style
"EUR_USD", so translation happens here and nowhere else. `discover_symbol_suffix`
works the broker's convention out at startup rather than making you configure it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from .base import (
    Account,
    Broker,
    BrokerError,
    OpenPosition,
    OrderResult,
    Price,
)

log = logging.getLogger(__name__)

# Granularity strings shared with the rest of the bot -> MT5 timeframe constants.
# Resolved lazily because the mt5 module only imports on Windows.
_TIMEFRAME_NAMES = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D": "TIMEFRAME_D1",
    "D1": "TIMEFRAME_D1",
    "W": "TIMEFRAME_W1",
}


def _import_mt5():
    """Import the MetaTrader5 package with an actionable error if unavailable."""
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError as exc:
        raise BrokerError(
            "the MetaTrader5 package is not installed or not importable. It is "
            "Windows-only: pip install MetaTrader5, on a Windows machine with the "
            "MT5 terminal installed. On Linux or macOS use a Windows VPS."
        ) from exc
    return mt5


def to_mt5_symbol(instrument: str, suffix: str = "") -> str:
    """'EUR_USD' -> 'EURUSD' plus whatever the broker appends."""
    return instrument.replace("_", "").replace("/", "").upper() + suffix


def from_mt5_symbol(symbol: str, suffix: str = "") -> str:
    """'EURUSD.a' -> 'EUR_USD'. Inverse of to_mt5_symbol."""
    name = symbol.upper()
    if suffix and name.endswith(suffix.upper()):
        name = name[: -len(suffix)]
    if len(name) != 6:
        raise ValueError(f"cannot parse MT5 symbol {symbol!r} into a currency pair")
    return f"{name[:3]}_{name[3:]}"


class MT5Broker(Broker):
    """Drives a running MetaTrader 5 terminal.

    Deliberately mirrors OandaBroker's semantics so the engine cannot tell them
    apart: stops are attached to the entry order, candles exclude the forming
    bar, and positions are read back from the terminal rather than remembered.
    """

    def __init__(
        self,
        login: int | None = None,
        password: str = "",
        server: str = "",
        terminal_path: str | None = None,
        symbol_suffix: str | None = None,
        magic: int = 20240917,
        deviation: int = 20,
        mt5_module=None,
    ) -> None:
        """
        Args:
            login/password/server: MT5 account credentials. Omit them all to
                attach to a terminal that is already logged in.
            terminal_path: path to terminal64.exe, if it is not auto-detected.
            symbol_suffix: broker suffix such as ".a". None means auto-detect.
            magic: identifies this bot's orders, so manual trades stay distinct.
            deviation: maximum slippage in points the terminal may accept.
            mt5_module: injected for testing. Production leaves it None.
        """
        self._mt5 = mt5_module or _import_mt5()
        self.magic = magic
        self.deviation = deviation

        kwargs: dict = {}
        if terminal_path:
            kwargs["path"] = terminal_path
        if login:
            kwargs.update(login=int(login), password=password, server=server)

        if not self._mt5.initialize(**kwargs):
            raise BrokerError(
                f"could not connect to the MT5 terminal: {self._last_error()}. "
                "Check the terminal is running and logged in, and that "
                "Tools -> Options -> Expert Advisors allows algorithmic trading."
            )

        info = self._mt5.terminal_info()
        if info is not None and not getattr(info, "trade_allowed", True):
            log.warning(
                "MT5 reports trading is NOT allowed. Enable the 'Algo Trading' "
                "button in the terminal toolbar or every order will be rejected."
            )

        self.symbol_suffix = (
            symbol_suffix if symbol_suffix is not None else self.discover_symbol_suffix()
        )
        log.info("connected to MT5; symbol suffix %r", self.symbol_suffix)

    # ---------------------------------------------------------------- helpers

    def _last_error(self) -> str:
        try:
            code, text = self._mt5.last_error()
            return f"{code}: {text}"
        except Exception:
            return "unknown error"

    def discover_symbol_suffix(self) -> str:
        """Work out the broker's symbol convention from its own symbol list.

        Brokers append arbitrary suffixes (".a", "-ECN", "m", ".raw"). Rather
        than make the user find out by trial and error, look for something that
        starts with a known major and take whatever trails it.
        """
        try:
            symbols = self._mt5.symbols_get()
        except Exception as exc:
            log.warning("could not list MT5 symbols (%s); assuming no suffix", exc)
            return ""

        if not symbols:
            return ""

        names = [s.name for s in symbols]
        for probe in ("EURUSD", "GBPUSD", "USDJPY"):
            for name in names:
                upper = name.upper()
                if upper.startswith(probe):
                    return name[len(probe):]
        log.warning("no major found in the broker's symbol list; assuming no suffix")
        return ""

    def _symbol(self, instrument: str) -> str:
        """Translate and make sure the symbol is selected in Market Watch.

        An unselected symbol returns no ticks and no history, which otherwise
        looks like a dead market rather than a configuration problem.
        """
        symbol = to_mt5_symbol(instrument, self.symbol_suffix)
        if not self._mt5.symbol_select(symbol, True):
            raise BrokerError(
                f"{symbol} is not available at this broker ({self._last_error()}). "
                "Check the instrument list in config.yaml against the broker's "
                "Market Watch."
            )
        return symbol

    def _timeframe(self, granularity: str):
        name = _TIMEFRAME_NAMES.get(granularity.upper())
        if name is None:
            raise ValueError(
                f"unsupported granularity {granularity!r}; "
                f"expected one of {sorted(_TIMEFRAME_NAMES)}"
            )
        return getattr(self._mt5, name)

    # ------------------------------------------------------------------ reads

    def get_account(self) -> Account:
        info = self._mt5.account_info()
        if info is None:
            raise BrokerError(f"could not read account info: {self._last_error()}")
        return Account(
            account_id=str(info.login),
            currency=info.currency,
            balance=float(info.balance),
            equity=float(info.equity),  # balance + floating P&L
            margin_available=float(getattr(info, "margin_free", 0.0)),
            open_position_count=len(self._mt5.positions_get() or []),
        )

    def get_candles(
        self, instrument: str, granularity: str = "D", count: int = 500
    ) -> pd.DataFrame:
        symbol = self._symbol(instrument)
        # Ask for one extra bar, then drop the newest: bar 0 in MT5 is the bar
        # still forming, and acting on it produces signals that vanish.
        rates = self._mt5.copy_rates_from_pos(
            symbol, self._timeframe(granularity), 0, count + 1
        )
        if rates is None or len(rates) == 0:
            raise BrokerError(
                f"no candles returned for {symbol}: {self._last_error()}"
            )

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time").sort_index()
        df = df.rename(columns={"tick_volume": "volume"})

        if len(df) > 1:
            df = df.iloc[:-1]  # discard the forming bar

        return df[["open", "high", "low", "close", "volume"]]

    def get_price(self, instrument: str) -> Price:
        symbol = self._symbol(instrument)
        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None or (tick.bid == 0 and tick.ask == 0):
            raise BrokerError(
                f"no live price for {symbol} - market closed? ({self._last_error()})"
            )
        return Price(
            instrument=instrument,
            bid=float(tick.bid),
            ask=float(tick.ask),
            time=pd.Timestamp(datetime.fromtimestamp(tick.time, tz=timezone.utc)),
        )

    def get_open_positions(self) -> list[OpenPosition]:
        """Only positions this bot opened, identified by magic number.

        Manual trades are excluded on purpose: the bot must never move a stop on
        or close a position a human placed by hand.
        """
        positions = self._mt5.positions_get() or []
        out: list[OpenPosition] = []

        for pos in positions:
            if pos.magic != self.magic:
                continue
            try:
                instrument = from_mt5_symbol(pos.symbol, self.symbol_suffix)
            except ValueError:
                log.warning("skipping unrecognised symbol %s", pos.symbol)
                continue

            is_long = pos.type == self._mt5.POSITION_TYPE_BUY
            out.append(
                OpenPosition(
                    instrument=instrument,
                    side="long" if is_long else "short",
                    units=float(pos.volume) if is_long else -float(pos.volume),
                    entry_price=float(pos.price_open),
                    unrealised_pnl=float(pos.profit),
                )
            )
        return out

    def _find_position(self, instrument: str):
        symbol = to_mt5_symbol(instrument, self.symbol_suffix)
        for pos in self._mt5.positions_get(symbol=symbol) or []:
            if pos.magic == self.magic:
                return pos
        return None

    # ----------------------------------------------------------------- writes

    def units_to_lots(self, instrument: str, units: float) -> float:
        """Convert base-currency units into MT5 lots, respecting broker limits.

        One standard lot is 100,000 units of base currency. Brokers impose a
        minimum, a maximum and a step; a volume off the step is rejected
        outright, so it is rounded here rather than discovered at order time.
        """
        symbol = self._symbol(instrument)
        info = self._mt5.symbol_info(symbol)
        if info is None:
            raise BrokerError(f"no symbol info for {symbol}")

        lots = abs(units) / 100_000.0
        step = float(getattr(info, "volume_step", 0.01)) or 0.01
        lots = round(round(lots / step) * step, 8)

        min_lot = float(getattr(info, "volume_min", 0.01))
        max_lot = float(getattr(info, "volume_max", 100.0))

        if lots < min_lot:
            log.info(
                "%s: %.0f units is %.4f lots, below the broker minimum of %.2f - skipping",
                instrument, abs(units), lots, min_lot,
            )
            return 0.0
        return min(lots, max_lot)

    def market_order(
        self,
        instrument: str,
        units: int,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        if units == 0:
            raise ValueError("refusing to submit an order for 0 units")

        symbol = self._symbol(instrument)
        lots = self.units_to_lots(instrument, units)
        if lots <= 0:
            raise BrokerError(
                f"{instrument}: position size rounds to 0 lots. The account is "
                "probably too small for this stop distance at the configured risk."
            )

        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None:
            raise BrokerError(f"no tick for {symbol}: {self._last_error()}")

        is_buy = units > 0
        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lots,
            "type": self._mt5.ORDER_TYPE_BUY if is_buy else self._mt5.ORDER_TYPE_SELL,
            "price": float(tick.ask if is_buy else tick.bid),
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": "trend-bot",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        }
        # Attached to the order itself, so the position is never unprotected.
        if stop_loss is not None:
            request["sl"] = float(stop_loss)
        if take_profit is not None:
            request["tp"] = float(take_profit)

        result = self._mt5.order_send(request)
        if result is None:
            raise BrokerError(f"order_send returned nothing: {self._last_error()}")
        if result.retcode != self._mt5.TRADE_RETCODE_DONE:
            raise BrokerError(
                f"{instrument} order rejected, retcode {result.retcode}: "
                f"{getattr(result, 'comment', '')}"
            )

        return OrderResult(
            order_id=str(result.order),
            instrument=instrument,
            units=float(units),
            fill_price=float(result.price),
            time=pd.Timestamp.now(tz="UTC"),
        )

    def close_position(self, instrument: str) -> OrderResult | None:
        pos = self._find_position(instrument)
        if pos is None:
            log.info("close_position: nothing open on %s", instrument)
            return None

        symbol = pos.symbol
        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None:
            raise BrokerError(f"no tick for {symbol}: {self._last_error()}")

        was_long = pos.type == self._mt5.POSITION_TYPE_BUY
        result = self._mt5.order_send({
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(pos.volume),
            # Closing is an opposite-side deal against the same position ticket.
            "type": self._mt5.ORDER_TYPE_SELL if was_long else self._mt5.ORDER_TYPE_BUY,
            "position": pos.ticket,
            "price": float(tick.bid if was_long else tick.ask),
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": "trend-bot close",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        })

        if result is None or result.retcode != self._mt5.TRADE_RETCODE_DONE:
            raise BrokerError(
                f"could not close {instrument}: "
                f"{getattr(result, 'retcode', 'no result')} {self._last_error()}"
            )

        return OrderResult(
            order_id=str(result.order),
            instrument=instrument,
            units=-float(pos.volume) * 100_000 * (1 if was_long else -1),
            fill_price=float(result.price),
            time=pd.Timestamp.now(tz="UTC"),
        )

    def update_stop_loss(self, instrument: str, stop_price: float) -> bool:
        pos = self._find_position(instrument)
        if pos is None:
            log.warning("update_stop_loss: no open position on %s", instrument)
            return False

        result = self._mt5.order_send({
            "action": self._mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": pos.ticket,
            "sl": float(stop_price),
            "tp": float(pos.tp),  # preserve any existing take-profit
        })

        if result is None or result.retcode != self._mt5.TRADE_RETCODE_DONE:
            log.error(
                "could not move stop on %s: %s",
                instrument, getattr(result, "retcode", self._last_error()),
            )
            return False

        log.info("moved stop on %s to %.5f", instrument, stop_price)
        return True

    def shutdown(self) -> None:
        """Release the terminal connection."""
        try:
            self._mt5.shutdown()
        except Exception:
            pass
