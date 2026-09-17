"""Telegram notifications.

Optional. If no token is configured the notifier degrades to logging, so the bot
never fails to trade because a message could not be delivered.
"""
from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)


class Notifier:
    """Sends short operational messages. Never raises into the trading loop."""

    def __init__(self, bot_token: str = "", chat_id: str = "", timeout: int = 10) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout
        self.enabled = bool(bot_token and chat_id)
        if not self.enabled:
            log.info("Telegram not configured; notifications will be logged only")

    def send(self, message: str) -> bool:
        """Deliver a message. Returns False on failure, never raises.

        A notification failure must not be able to kill a running bot or, worse,
        leave a position half-managed.
        """
        log.info("NOTIFY: %s", message)
        if not self.enabled:
            return False
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"},
                timeout=self.timeout,
            )
            return resp.ok
        except requests.RequestException as exc:
            log.warning("could not send Telegram message: %s", exc)
            return False

    def trade_opened(self, instrument: str, side: str, units: float,
                     price: float, stop: float) -> None:
        risk_pips = abs(price - stop) / (0.01 if instrument.endswith("_JPY") else 0.0001)
        self.send(
            f"<b>OPENED {side.upper()} {instrument}</b>\n"
            f"units {units:,.0f} @ {price:.5f}\n"
            f"stop {stop:.5f}  ({risk_pips:.0f} pips)"
        )

    def trade_closed(self, instrument: str, side: str, price: float, reason: str) -> None:
        self.send(f"<b>CLOSED {side.upper()} {instrument}</b> @ {price:.5f} ({reason})")

    def signal_only(self, instrument: str, side: str, price: float, stop: float) -> None:
        self.send(
            f"<b>SIGNAL {side.upper()} {instrument}</b>\n"
            f"entry ~{price:.5f}  stop {stop:.5f}\n"
            f"<i>signal mode - no order placed</i>"
        )

    def alert(self, message: str) -> None:
        self.send(f"WARNING: {message}")
