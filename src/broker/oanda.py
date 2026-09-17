"""OANDA v20 REST implementation of the Broker interface.

Docs: https://developer.oanda.com/rest-live-v20/introduction/

Credentials come from the environment, never from source. See .env.example.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import requests

from .base import (
    Account,
    Broker,
    BrokerError,
    OpenPosition,
    OrderResult,
    Price,
)

log = logging.getLogger(__name__)

PRACTICE_HOST = "https://api-fxpractice.oanda.com"
LIVE_HOST = "https://api-fxtrade.oanda.com"

# OANDA rejects prices with more decimals than the instrument supports. JPY
# crosses quote to 3 places, almost everything else to 5.
JPY_PRECISION = 3
DEFAULT_PRECISION = 5


def price_precision(instrument: str) -> int:
    return JPY_PRECISION if instrument.upper().endswith("_JPY") else DEFAULT_PRECISION


def format_price(instrument: str, price: float) -> str:
    return f"{price:.{price_precision(instrument)}f}"


class OandaBroker(Broker):
    """Talks to OANDA over HTTPS.

    Retries are deliberately narrow: only idempotent GETs and only on network
    errors or 5xx. An order POST is never retried automatically, because a
    request that timed out may well have been filled, and a blind retry is how
    you end up with two positions where you wanted one.
    """

    def __init__(
        self,
        api_token: str,
        account_id: str,
        environment: str = "practice",
        timeout: int = 20,
        max_retries: int = 3,
    ) -> None:
        if not api_token:
            raise ValueError("api_token is required (set OANDA_API_TOKEN in .env)")
        if not account_id:
            raise ValueError("account_id is required (set OANDA_ACCOUNT_ID in .env)")
        if environment not in ("practice", "live"):
            raise ValueError(f"environment must be 'practice' or 'live', got {environment!r}")

        self.account_id = account_id
        self.environment = environment
        self.host = PRACTICE_HOST if environment == "practice" else LIVE_HOST
        self.timeout = timeout
        self.max_retries = max_retries

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
                "Accept-Datetime-Format": "RFC3339",
            }
        )

        if environment == "live":
            log.warning("OANDA broker is pointed at LIVE - orders will use real money")

    # ---------------------------------------------------------------- plumbing

    def _request(self, method: str, path: str, *, retry: bool = False, **kwargs):
        url = f"{self.host}{path}"
        attempts = self.max_retries if retry else 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                resp = self._session.request(method, url, timeout=self.timeout, **kwargs)
                if resp.status_code >= 500 and retry and attempt < attempts - 1:
                    last_error = BrokerError(f"{resp.status_code} from {path}")
                    time.sleep(2**attempt)
                    continue
                if not resp.ok:
                    raise BrokerError(
                        f"OANDA {method} {path} -> {resp.status_code}: {resp.text[:400]}"
                    )
                return resp.json()
            except requests.RequestException as exc:
                last_error = exc
                if retry and attempt < attempts - 1:
                    log.warning("network error on %s (attempt %d): %s", path, attempt + 1, exc)
                    time.sleep(2**attempt)
                    continue
                raise BrokerError(f"network failure calling {path}: {exc}") from exc

        raise BrokerError(f"exhausted retries on {path}: {last_error}")

    def _get(self, path: str, **kwargs):
        return self._request("GET", path, retry=True, **kwargs)

    # ------------------------------------------------------------------ reads

    def get_account(self) -> Account:
        data = self._get(f"/v3/accounts/{self.account_id}/summary")["account"]
        return Account(
            account_id=data["id"],
            currency=data["currency"],
            balance=float(data["balance"]),
            equity=float(data["NAV"]),  # NAV = balance + unrealised P&L
            margin_available=float(data.get("marginAvailable", 0.0)),
            open_position_count=int(data.get("openPositionCount", 0)),
        )

    def get_candles(
        self, instrument: str, granularity: str = "D", count: int = 500
    ) -> pd.DataFrame:
        params = {
            "granularity": granularity,
            "count": min(count, 5000),  # API hard limit
            "price": "M",               # midpoint; spread is applied at execution
        }
        data = self._get(f"/v3/instruments/{instrument}/candles", params=params)

        rows = []
        for candle in data.get("candles", []):
            # Incomplete bars are still forming. Acting on one means acting on a
            # signal that can disappear before the bar closes.
            if not candle.get("complete", False):
                continue
            mid = candle["mid"]
            rows.append(
                {
                    "time": pd.Timestamp(candle["time"]),
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "volume": int(candle.get("volume", 0)),
                }
            )

        if not rows:
            raise BrokerError(f"no complete candles returned for {instrument}")

        return pd.DataFrame(rows).set_index("time").sort_index()

    def get_price(self, instrument: str) -> Price:
        data = self._get(
            f"/v3/accounts/{self.account_id}/pricing",
            params={"instruments": instrument},
        )
        prices = data.get("prices", [])
        if not prices:
            raise BrokerError(f"no price available for {instrument}")

        quote = prices[0]
        if quote.get("tradeable") is False:
            raise BrokerError(f"{instrument} is not currently tradeable (market closed?)")

        return Price(
            instrument=instrument,
            bid=float(quote["bids"][0]["price"]),
            ask=float(quote["asks"][0]["price"]),
            time=pd.Timestamp(quote["time"]),
        )

    def get_open_positions(self) -> list[OpenPosition]:
        data = self._get(f"/v3/accounts/{self.account_id}/openPositions")
        positions: list[OpenPosition] = []

        for pos in data.get("positions", []):
            long_units = float(pos["long"]["units"])
            short_units = float(pos["short"]["units"])

            if long_units > 0:
                leg, side, units = pos["long"], "long", long_units
            elif short_units < 0:
                leg, side, units = pos["short"], "short", short_units
            else:
                continue

            positions.append(
                OpenPosition(
                    instrument=pos["instrument"],
                    side=side,
                    units=units,
                    entry_price=float(leg.get("averagePrice", 0.0)),
                    unrealised_pnl=float(leg.get("unrealizedPL", 0.0)),
                )
            )
        return positions

    def _find_trade_id(self, instrument: str) -> str | None:
        """Open trade id for an instrument, needed to modify its stop."""
        data = self._get(
            f"/v3/accounts/{self.account_id}/openTrades",
        )
        for trade in data.get("trades", []):
            if trade["instrument"] == instrument:
                return trade["id"]
        return None

    # ----------------------------------------------------------------- writes

    def market_order(
        self,
        instrument: str,
        units: int,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        if units == 0:
            raise ValueError("refusing to submit an order for 0 units")

        order: dict = {
            "type": "MARKET",
            "instrument": instrument,
            "units": str(int(units)),
            "timeInForce": "FOK",  # fill completely or not at all; no partials
            "positionFill": "DEFAULT",
        }

        # Attached on fill, so the position is never naked even for a moment.
        if stop_loss is not None:
            order["stopLossOnFill"] = {
                "price": format_price(instrument, stop_loss),
                "timeInForce": "GTC",
            }
        if take_profit is not None:
            order["takeProfitOnFill"] = {
                "price": format_price(instrument, take_profit),
                "timeInForce": "GTC",
            }

        # Note: no retry. See class docstring.
        data = self._request(
            "POST",
            f"/v3/accounts/{self.account_id}/orders",
            json={"order": order},
        )

        fill = data.get("orderFillTransaction")
        if fill is None:
            reason = data.get("orderRejectTransaction", {}).get("rejectReason", "unknown")
            raise BrokerError(f"order for {instrument} was not filled: {reason}")

        return OrderResult(
            order_id=fill["id"],
            instrument=instrument,
            units=float(fill["units"]),
            fill_price=float(fill["price"]),
            time=pd.Timestamp(fill["time"]),
        )

    def close_position(self, instrument: str) -> OrderResult | None:
        positions = {p.instrument: p for p in self.get_open_positions()}
        pos = positions.get(instrument)
        if pos is None:
            log.info("close_position: nothing open on %s", instrument)
            return None

        payload = {"longUnits": "ALL"} if pos.side == "long" else {"shortUnits": "ALL"}
        data = self._request(
            "PUT",
            f"/v3/accounts/{self.account_id}/positions/{instrument}/close",
            json=payload,
        )

        fill = data.get("longOrderFillTransaction") or data.get("shortOrderFillTransaction")
        if fill is None:
            raise BrokerError(f"close of {instrument} returned no fill: {str(data)[:300]}")

        return OrderResult(
            order_id=fill["id"],
            instrument=instrument,
            units=float(fill["units"]),
            fill_price=float(fill["price"]),
            time=pd.Timestamp(fill["time"]),
        )

    def update_stop_loss(self, instrument: str, stop_price: float) -> bool:
        trade_id = self._find_trade_id(instrument)
        if trade_id is None:
            log.warning("update_stop_loss: no open trade on %s", instrument)
            return False

        self._request(
            "PUT",
            f"/v3/accounts/{self.account_id}/trades/{trade_id}/orders",
            json={
                "stopLoss": {
                    "price": format_price(instrument, stop_price),
                    "timeInForce": "GTC",
                }
            },
        )
        log.info("moved stop on %s to %s", instrument, format_price(instrument, stop_price))
        return True
