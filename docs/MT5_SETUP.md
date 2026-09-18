# MetaTrader 5 setup

For brokers that offer MT5 rather than a REST API — Vantage, OANDA's EU
entities, IC Markets, Pepperstone and most MiFID-regulated brokers.

> **Confirmed for this project:** OANDA's EU hub (`hub.oanda.com`, `OANDATMS-MT5`)
> has no "Manage API Access" option at all. Its account settings contain only
> Profile settings. The v20 REST path is unavailable there — use MT5.

---

## 1. The Windows requirement

The `MetaTrader5` Python package talks to a running MT5 terminal over local IPC
on **Windows only**. There is no Linux or macOS build. You need one of:

| Option | Cost | Notes |
|---|---|---|
| A Windows PC you already own | free | Must stay on and awake 24/5 |
| Windows VPS | ~$15–30/mo | Correct answer for unattended running |
| MT5's built-in VPS | ~$15/mo | Rented inside the terminal; only hosts EAs, **not** this Python bot |

Note the third row. MT5's own VPS hosting runs MQL5 Expert Advisors, not Python
scripts. If you want that route the strategy has to be rewritten in MQL5 — a
separate job, not a config change.

**Mac or Linux only?** Wine or Parallels can work but adds a failure mode to
something meant to run unattended for months. A Windows VPS is the honest answer.

Providers that work fine: Contabo, Vultr, Hetzner (Windows images), or a
forex-specific VPS. Pick one physically near your broker's servers if offered —
it shaves latency, though on daily bars this barely matters.

---

## 2. Open an MT5 **demo** account

Do not point this at a live account until it has run on demo for weeks.

**Vantage:** sign up, choose MT5, choose **demo**. Instant, no verification.

**Two things to ask for:**

1. **A micro or cent account.** This is not optional on a small balance — see
   the minimum-lot section below.
2. **Raw/ECN vs Standard.** Raw has tighter spreads plus commission. On daily
   bars with ~130-pip stops the difference is minor; take whichever is simpler.

Write down: **login number, password, server name** (e.g. `VantageInternational-Demo`).

---

## 3. Minimum lot — check this before anything else

MT5 brokers enforce a minimum trade size, and it sets a floor under your risk
per trade:

| Account type | Min lot | Risk on a 130-pip stop | Balance needed at 0.5% risk |
|---|---|---|---|
| Standard | 0.01 | €13.00 | **€2,600** |
| Micro | 0.001 | €1.30 | **€260** |
| Cent / nano | 0.0001 | €0.13 | **€26** |

On a **standard** account with €100, the bot's correct size is 0.0004 lots. The
minimum is 0.01 — **25x larger**. The bot will size to zero and place nothing.

That is deliberate. Rounding up to the minimum would risk €13 on a €100 account:
**13% per trade**, 26 times the configured 0.5%. A normal losing streak at that
size ends the account. Placing no trade is the safe reading of an impossible
request.

`python -m src.cli doctor` computes this against your real account and tells you
the balance to fund or to switch account type.

---

## 4. Install MT5 and the bot

On the Windows machine:

1. Install **MetaTrader 5** from your broker (use their download link, not
   MetaQuotes' generic one — it pre-configures the server list).
2. Log in with your demo credentials.
3. **Enable algorithmic trading**: the `Algo Trading` button in the toolbar must
   be lit. Also Tools → Options → Expert Advisors → allow automated trading.
   Without this every order is rejected.
4. Install **Python 3.11+** from python.org — tick *Add Python to PATH*.
5. Then:

```cmd
git clone https://github.com/jameswalkin1/james-.git
cd james-
git checkout claude/forex-trading-bot-gv76xg
pip install -r requirements.txt
pip install MetaTrader5
```

`MetaTrader5` is in neither `requirements.txt` nor CI, because it cannot install
anywhere but Windows.

---

## 5. Configure

In `config.yaml`:

```yaml
broker: mt5
mode: signal
account_currency: EUR    # must match the account
```

Copy `.env.example` to `.env` and fill the MT5 block:

```
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=VantageInternational-Demo
```

Leave all three blank to attach to whatever account the terminal is already
logged into — often simpler on a dedicated VPS.

`.env` is gitignored. It never reaches GitHub.

---

## 6. Run

**Leave the MT5 terminal running.** The bot drives it; if it closes, the bot goes
deaf mid-position.

```cmd
python -m src.cli doctor
python -m src.cli fetch
python -m src.cli backtest
```

`doctor` verifies the terminal connection, that Algo Trading is on, that every
instrument exists at your broker, that the account currency matches, and that
your balance can actually size a trade.

Daily run, after the 5pm New York close:

```cmd
python -m src.cli run --new-day
```

Schedule it with Windows Task Scheduler. Set it to *Run whether user is logged on
or not*.

---

## 7. Symbol names

Brokers name symbols differently: `EURUSD`, `EURUSD.a`, `EURUSD-ECN`, `EURUSDm`.
The adapter **auto-detects the suffix** from the broker's own symbol list, so
normally you do nothing.

If `doctor` reports a missing instrument, open Market Watch in MT5, right-click →
*Show All*, and check the exact spelling. Anything your broker does not offer,
delete from `instruments:` in `config.yaml`.

---

## 8. What MT5 costs you versus a REST API

Worth knowing what you are accepting:

- **A GUI app in the loop.** The terminal can crash, hang, or log out. A REST API
  reconnects; a dead terminal just stops.
- **Windows hosting**, at roughly 3–6x the price of a Linux box.
- **Updates restart the terminal**, sometimes mid-session.
- **No native paper mode** — a demo account is the substitute.

And what you gain:

- **The Strategy Tester** backtests against your broker's own tick data, so
  spreads and fills reflect what you would really get. That is better evidence
  than this project's own backtester, which works on daily bars.

---

## 9. Manual trades are safe

The adapter tags its orders with a magic number and ignores every position
carrying a different one. Trade by hand in the same account and the bot will not
touch, close, or move stops on your positions.

It also means the bot ignores its **own** positions if you change the magic
number. Don't, while trades are open.
