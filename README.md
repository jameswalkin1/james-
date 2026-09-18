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
| **Universe** | 14 pairs across 8 currencies — see below |

Signals are computed on **closed bars only** and acted on at the next bar's open.

### Why 14 pairs across 8 currencies

The first version traded 7 all-USD-crossed pairs, chosen so P&L converted
exactly. That had a cost I did not anticipate: with USD on every pair, the
`max_per_currency` cap bound on USD permanently and throttled the system to
**~32 trades/year while discarding ~1,300 valid signals**. The cap meant to stop
correlated bets was acting as a blanket position limit.

Spreading across 8 currencies roughly **doubled trade frequency** at identical
edge per trade, on matched synthetic data with realistic cross-pair correlation:

| | Narrow (7 pairs, all USD) | Wide (14 pairs, 8 ccy) |
|---|---|---|
| Trades/year | 31.8 | **62.0** |
| CAGR | +4.67% | +8.23% |
| Max drawdown | 7.04% | 12.05% |
| Sharpe | 0.90 | **1.06** |
| Blocked by USD cap | **1,299** | 399 |

More trades came with more drawdown — that is the honest trade-off, and it is
what taking more positions buys you. Risk-adjusted return improved. The
bottleneck also moved from an accidental cap to the deliberate one (position
count), which is where it belongs.

Trade count scales with **edge per trade**, not with risk per trade. Widening the
currency spread is the one lever that adds trades without touching either.

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
- **6 concurrent positions** maximum
- **3% total open risk** across the portfolio — note these two are **coupled**:
  every position spends `risk_per_trade` of the budget, so
  `max_portfolio_risk / risk_per_trade` is its own position limit. Raising the
  position cap alone is a silent no-op; the bot warns when the config is
  incoherent (`effective_max_positions`)
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

### 4. Cross-pair conversion is resolved, never guessed

A pair with neither leg in your account currency (EUR_GBP on a USD account)
earns P&L in a third currency. `src/rates.py` resolves the rate from ordinary
candle series — directly (GBP→USD from `GBP_USD`) or inverted (JPY→USD from
`USD_JPY`).

**Triangulation through a third currency is deliberately not implemented.**
Chained rates compound their errors and produce plausible-looking nonsense. When
a rate cannot be resolved the code raises and names the exact series to fetch.

This matters more than it sounds: returning `1.0` for a JPY cross would size the
position **~157x too large**, and every downstream risk cap would wave it
through, because they all work in account currency. There is a test for
precisely that.

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

**Account currency:** set `account_currency` in `config.yaml` to match your
broker account. `fetch` works out which extra conversion series it needs and
downloads them automatically — a USD account needs none with the default
universe; a EUR account also pulls `EUR_CAD`, `EUR_CHF`, `EUR_NZD`.

```bash
python -m src.cli doctor              # checks everything, names any problem
python -m src.cli fetch               # download ~10 years of daily candles
python -m src.cli backtest            # see the numbers
```

Run `doctor` first. It verifies packages, config coherence, credentials, the
broker connection, that your account currency matches `config.yaml`, and that
your broker actually offers every instrument in the universe — and prints the
specific fix for whatever fails, instead of a traceback.

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
  rates.py         cross-currency conversion (RateBook, BrokerRateBook)
  backtest.py      event-driven portfolio backtester
  engine.py        live trading loop
  config.py        config.yaml + .env
  notify.py        Telegram alerts
  cli.py           command line
  broker/
    base.py        broker interface
    oanda.py       OANDA v20 REST
    mt5.py         MetaTrader 5 (Vantage, OANDA MT5, ...)
    paper.py       simulated, for tests and dry runs
tests/             100 tests
```

Strategy and risk logic never import a broker SDK. Both the backtester and the
live engine drive the same strategy functions through the same interface, so the
system you test is the system you trade.

### Brokers

Set `broker:` in `config.yaml`:

| | `oanda` | `mt5` |
|---|---|---|
| Needs | fxTrade (v20) account, id like `101-004-12345678-001` | MT5 terminal running and logged in |
| Runs on | anything, incl. a €5 Linux VPS | **Windows only** |
| Works with | OANDA fxTrade | Vantage, OANDA MT5, IC Markets, most EU brokers |

**An OANDA MetaTrader 5 account is not an fxTrade account.** They are separate
platforms with separate account numbers (`221230` vs `101-004-…`). An MT5 account
has no v20 API token — use `broker: mt5`. Some OANDA entities (notably the EU
ones on `hub.oanda.com`) offer MT5 only.

The MT5 adapter auto-detects the broker's symbol suffix (`.a`, `-ECN`, `m`), and
tags its orders with a magic number so it never touches positions you opened by
hand.

### Minimum account size

MT5 brokers enforce a **minimum lot**, and it sets a floor on what you can risk:

| Account type | Min lot | Risk on a 130-pip stop | Account needed at 0.5% risk |
|---|---|---|---|
| Standard | 0.01 | €13.00 | **€2,600** |
| Micro | 0.001 | €1.30 | **€260** |
| Cent / nano | 0.0001 | €0.13 | **€26** |

Below that floor the bot sizes to zero and places nothing — which is correct.
Rounding *up* to the minimum instead would risk many times the configured amount,
and on a small account that is the difference between 0.5% and 13% per trade.

`doctor` checks this against your actual account and tells you the number to
fund, or to open a micro/cent account instead.

## Tests

```bash
python -m pytest tests/ -v
```
