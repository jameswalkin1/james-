# Forex Trend-Following Bot

An automated forex trading system: strategy, backtester, risk manager, and live
execution against OANDA's v20 API.

**It cannot promise you money.** No strategy can, and anything that tells you
otherwise is selling something. What this gives you is a real edge candidate
implemented carefully, costs modelled honestly, and numbers you can check
yourself before risking anything.

---

## The strategy

Multi-pair **time-series momentum** (trend following) on daily bars.

Chosen because it is the most durably documented return premium in currency
markets — Moskowitz, Ooi & Pedersen (2012) found it across 58 futures markets
including FX over ~25 years, and it is the core of what managed-futures funds
actually trade. It is not a secret, which is the point: an edge that survives
being public has a better claim to being real than one that only exists inside a
curve-fitted backtest.

| | Rule |
|---|---|
| **Entry long** | Close breaks above the 20-bar high **and** close is above the 100-EMA |
| **Entry short** | Close breaks below the 20-bar low **and** close is below the 100-EMA |
| **Initial stop** | 2 × ATR(20) from entry |
| **Trailing stop** | Chandelier: highest high since entry − 3 × ATR, ratcheting only |
| **Channel exit** | Opposite 10-bar channel breaks |
| **Size** | 0.5% of equity risked between entry and stop |

Signals are computed on **closed bars only** and acted on at the next bar's open.

### What to expect

Trend systems win **30–45%** of trades. They make money because winners run
several times the size of losers. Long flat and losing stretches are normal, not
a sign something broke. If you cannot sit through a 20%+ drawdown without
switching it off, this approach is not for you — turning it off during the
drawdown is how you keep the losses and miss the recovery.

---

## Risk controls

Every one of these is a brake:

- **0.5% risk per trade**, sized from the stop distance, so volatile pairs get
  smaller positions rather than bigger risk
- **4 concurrent positions** maximum
- **2% total open risk** across the portfolio
- **2 positions per currency** — long EUR/USD + long GBP/USD + long AUD/USD is
  one big short-USD bet, not three independent ones
- **−3% daily loss limit** → flatten everything, stop trading until tomorrow
- Stops are **attached to the entry order**, so a position is never naked, even
  for the moment between fill and stop placement

---

## Honest limitations

Read this section before you believe any backtest number.

### 1. Bar-data backtests flatter stop-based exits

A daily bar tells you the stop level was *touched*, so the engine fills there.
But the bar's real information content is its close, and price that touched your
stop usually closed past it. Measured against a no-edge control, this artifact
alone is worth roughly **+0.2% per year** in this system.

This is not a bug. It was verified by writing an independent reference
implementation of the same trailing-stop rule, which reproduces the effect
exactly on a synthetic martingale. It is a property of testing on bars rather
than tick data, and it inflates *every* bar-based backtest with stop exits —
including every one you have ever been shown by someone selling a system.

Mitigations in place: stop exits are charged extra slippage
(`stop_slippage_pips`), separately from ordinary exits. **Subtract ~0.2%/year
from any backtested return before drawing conclusions.**

### 2. The test suite proves honesty, not profitability

`tests/test_backtest.py` checks that the strategy does **not** beat random
entries on a random walk — that there is no lookahead bias. That is a test of the
*engine*, not evidence the strategy makes money. Only out-of-sample results and
live forward-testing can speak to that.

### 3. Costs are modelled but approximate

Spread, slippage and stop slippage are included at pessimistic defaults.
Overnight financing (swap) is supported but **defaults to zero** — set it if you
hold positions for days, which this system does. Real spreads widen around news
and at the daily roll.

### 4. Cross pairs are refused, not guessed

A pair with neither leg in your account currency (EUR_GBP on a USD account)
needs a third exchange rate this bot does not fetch. It raises rather than
silently returning a wrong position size. Keep the universe USD-crossed.

### 5. Parameters are conventional, not optimised

The defaults are close to the original Turtle system and were **not** tuned
against any history. If you tune them until the equity curve looks beautiful,
you will have curve-fitted it and it will die live. That is the single most
common way these systems fail.

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env     # then fill it in
```

Get an OANDA **demo** account (free, instant, no deposit — full API access
identical to live). In the account portal: *Manage API Access* → generate a
token. Put the token and account ID in `.env`. Never commit `.env`.

```bash
python -m src.cli status              # confirm the connection works
python -m src.cli fetch               # download ~10 years of daily candles
python -m src.cli backtest            # see the numbers
```

## Running it

The bot runs **one cycle per completed bar**. On daily bars, that means once a
day shortly after the 5pm New York close.

```bash
python -m src.cli run --new-day       # first run of the day
python -m src.cli run                 # subsequent runs
```

Via cron on a small Linux VPS (~$5/month):

```cron
5 22 * * 1-5 cd /path/to/bot && /usr/bin/python3 -m src.cli run --new-day >> logs/bot.log 2>&1
```

### Modes

`config.yaml` → `mode`:

- **`signal`** (default) — analyses and notifies you, places no orders. Start here.
- **`auto`** — places and manages orders itself.

Going to `auto` on a **live** account requires typing `LIVE` at a confirmation
prompt. That friction is deliberate.

---

## Suggested path

1. **Backtest** on cached history. Look at max drawdown first, not return.
2. **Signal mode on demo** for a few weeks. Check its calls look sane to you.
3. **Auto mode on demo** for at least a month. This is the real test — it catches
   the bugs backtests cannot.
4. **Live, minimum size**, only if steps 1–3 hold up.
5. **Scale slowly**, and only on evidence.

Skipping to step 5 is how accounts get emptied.

---

## Layout

```
src/
  strategy.py      entry/exit rules          (pure, no I/O)
  indicators.py    ATR, EMA, Donchian        (pure)
  risk.py          sizing, limits, kill switch
  costs.py         spread, slippage, conversion
  backtest.py      event-driven portfolio backtester
  engine.py        live trading loop
  config.py        config.yaml + .env
  notify.py        Telegram alerts
  cli.py           command line
  broker/
    base.py        broker interface  <-- port to MT5/Vantage here
    oanda.py       OANDA v20
    paper.py       simulated, for tests and dry runs
tests/             41 tests
```

Strategy and risk logic never import a broker SDK. Both the backtester and the
live engine drive the same strategy functions through the same interface, so the
system you test is the system you trade.

### Moving to a different broker

Implement `src/broker/base.py` for the new venue and change one line of wiring.
For Vantage that means an MT5 adapter — the `MetaTrader5` Python package is
Windows-only, so it needs a Windows VPS with the terminal permanently logged in.
Nothing in the strategy, risk or backtest code changes.

## Tests

```bash
python -m pytest tests/ -v
```
