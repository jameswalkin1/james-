"""Configuration loading.

Secrets come from the environment (.env, gitignored). Everything else comes from
config.yaml, which is safe to commit. The split is deliberate: nothing that could
move money should ever be capable of being pushed to a repository.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .risk import RiskParams
from .strategy import StrategyParams

DEFAULT_UNIVERSE = [
    # USD majors
    "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "USD_CHF", "NZD_USD",
    # non-USD crosses, so the per-currency risk cap does not bind on USD alone
    "EUR_GBP", "EUR_JPY", "GBP_JPY", "AUD_JPY", "AUD_NZD", "EUR_AUD", "CAD_JPY",
]


@dataclass
class Config:
    """Everything the bot needs to run."""

    instruments: list[str] = field(default_factory=lambda: list(DEFAULT_UNIVERSE))
    granularity: str = "D"
    account_currency: str = "USD"
    starting_equity: float = 10_000.0
    strategy: StrategyParams = field(default_factory=StrategyParams)
    risk: RiskParams = field(default_factory=RiskParams)

    # Execution mode. "signal" only notifies; "auto" actually places orders.
    mode: str = "signal"

    # Credentials, from environment only.
    oanda_token: str = ""
    oanda_account: str = ""
    oanda_env: str = "practice"
    telegram_token: str = ""
    telegram_chat: str = ""

    def __post_init__(self) -> None:
        if self.mode not in ("signal", "auto"):
            raise ValueError(f"mode must be 'signal' or 'auto', got {self.mode!r}")

    @property
    def is_live_money(self) -> bool:
        return self.oanda_env == "live" and self.mode == "auto"

    def validate_for_trading(self) -> None:
        """Fail fast before the first cycle rather than mid-session."""
        missing = []
        if not self.oanda_token:
            missing.append("OANDA_API_TOKEN")
        if not self.oanda_account:
            missing.append("OANDA_ACCOUNT_ID")
        if missing:
            raise ValueError(
                f"missing required environment variables: {', '.join(missing)}. "
                "Copy .env.example to .env and fill it in."
            )
        if not self.instruments:
            raise ValueError("no instruments configured")


def load_config(path: str | Path = "config.yaml") -> Config:
    """Read config.yaml plus environment secrets."""
    load_dotenv()

    raw: dict = {}
    path = Path(path)
    if path.exists():
        raw = yaml.safe_load(path.read_text()) or {}

    strategy = StrategyParams(**(raw.get("strategy") or {}))
    risk = RiskParams(**(raw.get("risk") or {}))

    return Config(
        instruments=raw.get("instruments") or list(DEFAULT_UNIVERSE),
        granularity=raw.get("granularity", "D"),
        account_currency=raw.get("account_currency", "USD"),
        starting_equity=float(raw.get("starting_equity", 10_000.0)),
        strategy=strategy,
        risk=risk,
        mode=raw.get("mode", "signal"),
        oanda_token=os.getenv("OANDA_API_TOKEN", ""),
        oanda_account=os.getenv("OANDA_ACCOUNT_ID", ""),
        oanda_env=os.getenv("OANDA_ENVIRONMENT", "practice"),
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat=os.getenv("TELEGRAM_CHAT_ID", ""),
    )
