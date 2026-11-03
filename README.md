# ICT 2022 Automation

A screener that scans markets for ICT 2022 trade setups. Each ICT concept is
turned into a precise, testable rule, checked against hand-marked charts, and
finally validated by backtest before any live scanning.

> Status: early build. Detectors are being built concept by concept.
> There is no live scanning or order execution yet.

**Current scope:** NQ (E-mini Nasdaq-100) only; liquidity sweeps detected on
the 5-minute chart; entries at the FVG near edge; screener windows London
open and NY AM; only in the direction of the 1H trend. Defaults live in `ict/config.py`. Other markets come after
the model is validated on NQ.

## The model being automated

In a high-probability time window, price sweeps liquidity against the intended
direction, shifts structure on displacement, and retraces into the PD array
(order block / fair value gap) that move left, in the correct premium/discount
half. Stop beyond the sweep, target the draw on liquidity, minimum R:R.

1. Context: structure, draw on liquidity, premium/discount
2. Time: kill zone / macro
3. Sweep of liquidity against the intended direction
4. Shift: structure break (CHoCH) on displacement
5. Entry: retrace into the OB / FVG
6. Stop beyond the sweep, target the draw

## Progress

| Concept | Module | Status |
|---|---|---|
| Volatility yardstick ("what counts as big") | `ict/volatility.py` | Done |
| 1. Significant swings (tiers 1–3) | `ict/swings.py` | Done — parameters provisional |
| Structure breaks (raw BOS/CHoCH event) | `ict/structure.py` | Done — BOS vs CHoCH labelling pending |
| 3. Displacement | `ict/displacement.py` | Built — thresholds provisional, FVG requirement open |
| 4. Liquidity pools and sweeps | `ict/liquidity.py` | Done — sweep rule provisional (back inside within 3 candles, ≤ 1 yardstick deep); equal highs/lows pending |
| 2. Draw on liquidity | `ict/draw.py` | Done (v1) — strict: target = nearest untapped opposite pool, trade only if ≥ 2R away; higher-timeframe draw later as a tested filter |
| PD arrays: FVG, order block (entry) | `ict/arrays.py` | Built — default entry option still open (FVG edge / FVG midpoint / order block) |
| Premium / discount, dealing range | `ict/premium_discount.py` | Done — gate: entry in discount (longs) / premium (shorts) of the bigger dealing range |
| Time windows (kill zones, Silver Bullet) | `ict/timewindows.py` | Built — every setup records its kill zone; gate available, off until the backtest shows it helps |
| Model assembly (gated sequence) | `ict/model.py` | Done (v1) — all gates in one pipeline (`build_trades`); run with `tools/run_model.py` |
| Higher-timeframe bias (1H / 4H structure) | `ict/htf.py` | Done — screener trades only with the 1H trend (Robin's practice); research compares with / without |
| Multi-market research run (36 CME futures, same rules) | `tools/run_markets.py` | Done — results net of costs in `docs/decisions.md` |
| Backtest (results in R, out-of-sample) | — | Next — needs longer history |
| Live screener and alerts | `ict/live/` | Built (v0) — Interactive Brokers real-time feed (default) or free delayed Yahoo feed, console + Telegram alerts, replay mode; live signals = backtest orders (tested) |

Every definition, threshold and the reason behind it is logged in
[`docs/decisions.md`](docs/decisions.md).

## Design principles

- **No lookahead.** Every detected fact records the bar at which it became
  known (confirmed, replaced, promoted). Tests check that adding future candles
  never changes a past decision.
- **One yardstick for "big".** Sizes are measured against the average range at
  the same exchange clock time over the previous 20 sessions, so a 09:35 candle
  is compared with earlier 09:35 candles. This keeps thresholds stable across
  markets, timeframes and sessions.
- **Gates vs scores.** Model steps are pass/fail gates; confluence quality is
  recorded as scores. Weights come from the backtest, not intuition.
- **Provisional until backtested.** Thresholds are set by eye first and tuned
  only on in-sample data, with a held-out period for validation.

## Layout

```
ict/
  data.py          CSV loading (UTC -> tz-aware), ET session labels
  volatility.py    ATR and time-of-day range
  swings.py        raw pivots -> tier 1 (yardstick filter) -> tiers 2/3 (nesting)
  structure.py     first close beyond the latest tier-1 swing, with leg start
  displacement.py  leg size, largest body, overlap, FVGs; displacement gates
  liquidity.py     pools (PDH/PDL, PWH/PWL, Asia/London H/L, tier-2 swings),
                   when each is taken, facts about the take, sweep rule
  draw.py          untapped pools at a bar; target = nearest opposite pool (strict, >= min R)
  arrays.py        FVGs and the order block left by a displacement leg
  model.py         context build, sweep -> CHoCH sequences, trade simulation
  timewindows.py   kill zones and Silver Bullet hours (ET), labels and gate
  config.py        defaults decided so far (market, entry, target rule, windows)
  premium_discount.py  entry position in the setup move or the dealing range
  contracts.py     tick size / tick value per contract; trading costs in R
  htf.py           1H / 4H candles from 5m, structure bias per 5m bar (closed candles only)
  live/signals.py  scan the latest closed candles -> signals (entry, stop, target, size, costs)
  live/feeds.py    replay (CSV), Interactive Brokers and Yahoo candle feeds, closed candles only
  live/check_ibkr.py  connection check for Interactive Brokers
  live/notify.py   console and Telegram alerts
  live/screener.py the 5-minute loop during the kill zones; replay mode
tools/
  plot_swings.py     chart raw pivots vs swing tiers
  plot_structure.py  chart structure breaks with displacement verdicts
  sweep_gallery.py   blind gallery of real pool takes for hand labelling
  draw_check.py      sanity check of target selection on sweep + CHoCH sequences
  entry_check.py     compare entry options (FVG edge / CE / order block) on the sequences
  time_check.py      when NQ's daily high/low forms; setups and results by kill zone
  pd_check.py        premium/discount position of entries and results by half
  run_model.py       run the decided v1 model + variants; gate funnel, trades CSV and chart
  run_markets.py     same model across many futures; liquidity trim, costs, day-resampled ranges
tests/             unit tests incl. no-lookahead checks
docs/decisions.md  design decision log
```

## Quick start

```bash
pip install -r requirements.txt
python -m pytest -q
```

Data: CSV files with a time column first, then `open, high, low, close`
(volume optional). Timestamps are read as UTC. Put files under `data/`
(git-ignored).

```bash
# Swing tiers for one NY morning (times are exchange time, America/New_York)
python -m tools.plot_swings data/nq/NQ_5min.csv --start "2026-04-02 08:00" --end "2026-04-02 12:30" --out out/swings.png

# Structure breaks and displacement verdicts, one panel per window
python -m tools.plot_structure "data/nq/NQ_5min*.csv" \
    --windows "2026-03-23 08:00/2026-03-23 12:30" "2026-04-02 08:00/2026-04-02 12:30" \
    --out out/displacement.png
```

## Live screener

Runs on your own computer (or a small server) during the kill zones and sends
an alert for every new signal: market, direction, limit entry (FVG near edge)
and when to cancel it, stop, target, position size for your account, 1H trend,
dealing-range position and estimated costs.

```bash
pip install -r requirements.txt
python -m ict.live.screener                # Ctrl+C to stop
```

**Phone alerts via Telegram** (optional; console alerts always stay on). The
token is a password: keep it in an environment variable, never in the code.

1. In Telegram, message **@BotFather** → `/newbot` → pick a name → copy the token.
2. Windows cmd: `setx TELEGRAM_BOT_TOKEN "<token>"` (macOS/Linux: `export ...`),
   then open a **new** terminal (and re-activate the venv).
3. Open your new bot in Telegram, press Start and send it any message.
4. `python -m ict.live.notify` → prints your chat id →
   `setx TELEGRAM_CHAT_ID "<chat id>"` → new terminal again.
5. `python -m ict.live.notify` → sends a test message.
6. Start the screener; its first line says `alerts: console + Telegram`.

A Telegram outage never blocks the console alert or the log; replays never
message the phone.

- Markets, account size, risk % and the cost limit are in `ict/config.py`.
- Scans London 02:00–05:00 and NY AM 08:30–11:00 ET, plus 75 minutes after
  each, on every 5-minute candle close.
- **Data delay:** the free Yahoo feed is delayed by at least 10 minutes (CME
  rule for free data), so a limit entry may already have filled or run by the
  time an alert arrives. Use it for paper-trading the signals; plug in a
  real-time feed (broker or data vendor) before trading them live — a feed is
  one class with a `candles(sym, now)` method (`ict/live/feeds.py`).
### Real-time data via Interactive Brokers (default feed)

The screener reads candles from TWS or IB Gateway running on the same
computer. It connects read-only and never places orders; your IB login stays
in TWS / Gateway.

1. **Market data:** in IBKR Client Portal → Settings → Market Data
   Subscriptions, subscribe to the *US Securities Snapshot and Futures Value
   Bundle* (covers CME, CBOT, NYMEX, COMEX; non-professional). For a paper
   account, also enable sharing your live market data with it.
   If every bundle is marked **(P)**, the account is set as a *professional*
   subscriber and this bundle is not offered: check Market Data Subscriber
   Status (answer truthfully), or, if professional is correct, subscribe to
   *CME Real-Time (P)* only (covers NQ, ES, RTY, 6E, 6B, 6J).
   Without a subscription the candles arrive about 10 minutes late; the
   screener still works and gives the same signals, only later (fine for
   paper forward-testing).
2. **Run TWS or IB Gateway** and log in.
3. **Enable the API:** Configure → API → Settings → tick *Enable ActiveX and
   Socket Clients*, keep *Read-Only API* ticked, note the socket port
   (TWS 7497 paper / 7496 live; IB Gateway 4002 paper / 4001 live), allow
   127.0.0.1.
4. `pip install -r requirements.txt` (includes `ib_async`; Python 3.10+).
5. Check the connection: `python -m ict.live.check_ibkr` (port from
   `ict/config.py`, currently 7496; override with `--port`). With real-time data
   every market shows a last candle under 6 minutes old.
6. Run: `python -m ict.live.screener`

Use `--feed yahoo` for the free, delayed feed instead.

- Replay any past period from local CSVs, exactly as it would have alerted:
  `python -m ict.live.screener --replay data/cme --start "2026-04-10 02:00" --end "2026-04-10 06:20"`

Data used so far: NQ (E-mini Nasdaq-100) 1m–1h from the TopstepX API via the
public repo `axb0306/cme-futures-ohlc` (third-party, not official CME data),
and EUR/USD 1h sample data from the `backtesting` package.

## Disclaimer

Research and education tool. Not financial advice. Nothing here has a proven
edge until the backtest says so.
