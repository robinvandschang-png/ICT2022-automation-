# Design decisions

Running log of how each ICT concept is quantified. "Provisional" values are
starting points; final values come from the backtest, not from eyeballing.

## Scope (Phase 0)
- Market: NQ (E-mini Nasdaq-100) only, for now (Robin, 2026-11-02).
- Sweep detection: 5-minute chart (Robin, 2026-11-02).
- Open: entry timeframe; whether swing pools also come from a higher
  timeframe (15m / 1H). Default until decided: fixed levels (PDH/PDL,
  PWH/PWL, Asia/London H/L) + 5m tier-2 swings.

## Yardstick for "big"
- Time-of-day range: average true range at the same exchange clock time over
  the previous 20 sessions (`ict/volatility.py`). Falls back to ATR(14) during
  warm-up.
- Why: on NQ 5m, plain ATR(14) flagged 43% of NY-open candles as large vs 8%
  in Asia; time-of-day normalization gives 8–11% in every session.

## Concept 1 — Significant swings (settled)
- Raw pivot: high/low beyond 2 candles on each side (provisional: 2).
- Tier 1: alternating highs/lows at least 1.0 yardstick from the previous
  opposite swing; a more extreme swing replaces the previous one
  (provisional: 1.0).
- Tier 2 / tier 3: nesting — a swing with less extreme same-kind neighbours
  in the tier below. No extra parameters.
- Every swing records when it became known / was replaced / was promoted.
  No-lookahead is tested.
- Roles:
  - CHoCH / structure-break trigger: tier 1 (confirmed by Robin, 2026-11-02).
  - Liquidity pools: tier 2 + fixed levels (concept 4).
  - Dealing range and draw: tier 2 / tier 3.
- Checked: tier-2 swings match hand-marked structure (EUR/USD H1).

## Concept 3 — Displacement (built, thresholds provisional)
- Measured on the leg from the extreme where the move started to the candle
  that closes beyond the tier-1 swing.
- Gates: net move >= 1.5, largest body >= 1.0 (yardsticks), net move / sum of
  ranges >= 0.5.
- FVG (>= 0.3 yardstick): recorded as a score, not required — open question;
  the backtest compares both.
- NQ (Jan–Apr 2026): ~26–29% of breaks pass on 1m, 5m and 15m alike.

## Concept 4 — Liquidity pools and sweeps (done, rule provisional)
- Pools (provisional set):
  - PDH / PDL, PWH / PWL: valid until taken. CME trading day starts 18:00 ET.
  - Asia (20:00–24:00 ET) and London (02:00–05:00 ET) high / low: valid for
    the rest of that trading day.
  - Tier-2 swing highs / lows: valid from promotion until taken.
  - Equal highs / lows: not yet included.
- Taken = first candle after the pool is active that trades through it.
- Facts recorded per take: closed beyond the level?, candles until the first
  close back inside, deepest trade beyond the level (yardsticks).
- Sweep vs run: candidate rules are (A) the book's single-candle close test,
  (B) back inside within N candles, (C) B plus a depth cap. Robin called NQ
  2 Apr 2026 09:30 ET a sweep although that candle closed beyond the low
  (fails A). Being calibrated against Robin's blind labels of 12 NQ 5m takes
  (`tools/sweep_gallery.py`, seed 7).
- NQ 5m London + NY hours (Feb–Apr 2026): of 197 takes, 93 closed back on the
  taking candle, 47 within 1–3 candles, 12 within 4–12, 45 not within 12.
- Batch 1 (12 takes, Robin's labels: 4 sweep, 6 run, 2 unsure):
  - (A) close test: 7/10 — misses 3 of the 4 sweeps (they closed beyond first).
  - (B) back inside within 1–3 candles: 9/10.
  - The one miss can't be fixed by any take-time rule: #4 (sweep) and #10
    (run) both reclaimed after 2 candles at depth 0.71. What separated them
    was the follow-through — the job of the next gate (CHoCH on
    displacement), not of the sweep rule.
- Objective check (all 197 takes): a displacement break in the reversal
  direction followed within 12 candles for 11% of same-candle reclaims, 17%
  of 1–3-candle reclaims, 0% of 4–12-candle reclaims (n=12), 2% of takes not
  reclaimed within 12 (n=45). 1–3-candle reclaims deeper than 1 yardstick:
  0 of 4.
- Adopted rule (`classify_takes`): sweep candidate = back inside within 3
  candles (5m: 15 min) and no deeper than 1 yardstick beyond the level;
  confirmation comes from the CHoCH gate. The furthest price beyond the level
  is stored as `extreme` (stop placement).
- Provisional: the depth cap rests on few cases. Batch 2 (boundary cases,
  seed 11) was generated but left unlabelled when we moved on; the backtest
  will compare max reclaim 1–3 and depth caps 0.75–1.5.

## Concept 2 — Draw on liquidity (v1 built)
- Version B (Robin, 2026-11-02): the setup decides direction (sell-side
  sweep + bullish CHoCH = long); target = nearest untapped opposite pool at
  least 2R from the entry; no such pool = no trade. A higher-timeframe draw
  model (structure, premium/discount) comes later as a filter tested in the
  backtest. Code: `ict/draw.py`.
- Sanity check, NOT a backtest (`tools/draw_check.py`; NQ 5m Feb–Apr 2026,
  44 sweep -> displacement-CHoCH sequences; placeholder entry at the CHoCH
  close, stop beyond the sweep extreme, no costs):
  - 98% had a pool >= 2R, but 88% of those skipped at least one closer pool.
  - Target before stop 14%, stop 51%, still open at day end 35%;
    average +0.04R gross.
  - Nearest opposite pool reached before the stop: 52% (median 1.0R away);
    2nd nearest 40% (1.4R); 3rd nearest 26% (1.6R).
- Reading: the nearest pool works as a magnet; pools further out are
  reached much less often. R:R has to come from a better entry (retrace into
  the FVG / order block shrinks the risk), not from reaching for farther
  pools.
- Decided (Robin, 2026-11-02): strict rule is the default — target = the
  nearest opposite pool, trade only if it is >= 2R from the actual entry.
  The skip-closer variant stays available (`skip_closer=True`) for the
  backtest comparison.
- Data (Robin, 2026-11-02): keep building on the free NQ data we have
  (Jan–Apr 2026). Longer history (e.g. Databento NQ 1m from 2023) later.
- Data limit: 3 months of 5m data gives ~44 sequences. The backtest needs
  at least 2 years of NQ 5m history.

## PD arrays — FVG and order block (built, default entry open)
- FVG: 3-candle gap in the leg's direction, middle candle inside the
  displacement leg, at least 0.3 yardsticks. Near edge = first price met on a
  retrace; CE = midpoint; known one candle after the middle candle.
- Order block: last opposing candle before the leg's first large-bodied
  candle (searched from 3 candles before the leg start). Near edge = its high
  (bullish) / low (bearish).
- Entry comparison, NOT a backtest (`tools/entry_check.py`; same 44 NQ 5m
  sequences, stop beyond the sweep extreme, strict target >= 2R, limit
  orders wait 12 candles, no session filter, no costs):

  | Entry | Qualify (target >= 2R) | Filled | Target / stop | Total R |
  |---|---|---|---|---|
  | CHoCH close | 5 | 5 | 2 / 3 | +1.4 |
  | FVG near edge (latest gap) | 12 | 9 | 5 / 4 | +9.5 |
  | FVG midpoint (latest gap) | 15 | 6 | 2 / 4 | +2.7 |
  | FVG near edge (first gap) | 16 | 8 | 4 / 4 | +7.0 |
  | Order block near edge | 35 | 13 | 4 / 8 (+1 open) | +10.4 |

- Reading: retrace entries are what make the strict 2R rule workable
  (5 -> 12–35 qualifying setups). Deeper entries qualify more often but fill
  less (order block 13/35, FVG midpoint 6/15 vs FVG near edge 9/12).
  5–13 filled trades per option: one trade changes the ranking, so no
  conclusion on which entry is best or whether any has an edge.
- Robin trades the FVG near edge most (2026-11-02) -> default entry.
- Fixed-R targets with the FVG near-edge entry (latest gap), same 35
  sequences with an FVG, all hours, no costs (`entry_check --fixed-rr`):

  | Target | Filled | Wins / losses / open | Win rate | Break-even | Total R |
  |---|---|---|---|---|---|
  | 1R | 29 | 17 / 9 / 3 | 65% | 50% | +8.0 |
  | 1.5R | 30 | 13 / 12 / 5 | 52% | 40% | +8.4 |
  | 2R | 30 | 11 / 14 / 5 | 44% | 33% | +8.9 |
  | 3R | 30 | 7 / 16 / 7 | 30% | 25% | +8.7 |

  London + NY AM only: 11 filled; 1R win rate 56% (5/9), +1.2R.
  Median risk 86 NQ points. Expectancy is ~+0.3R per trade at every target
  in this sample; 26 decided trades at 1R give a win-rate range of roughly
  47–83% (95%), so not distinguishable from break-even yet.

## Time windows — kill zones (built, gate off for now)
- Windows (ET, ICT conventions; the course gives no times): Asia 20:00–00:00,
  London 02:00–05:00, NY AM 08:30–11:00, NY PM 13:30–16:00. Silver Bullet
  03–04, 10–11, 14–15. Code: `ict/timewindows.py`.
- Premise test, 273 full NQ trading days of hourly bars (`tools/time_check.py`):
  share of daily highs/lows forming in each hour (even spread = 4.3%/hour):
  18:00 (Globex open) 12.3%, 09:00 9.3%, 10:00 9.9%, 11:00 6.0%,
  15:00 10.8%, 16:00 9.0%; London hours 02–04: 2.2–3.5%; Asia 0.7–3.3%.
- 5m, 60 days: NY AM holds 18% of daily highs/lows in 11% of the time,
  NY PM 18% in 11%, London 9% in 13%, Asia 7% in 17%.
- Reading: for NQ the New York open and the close are where the day's
  extremes form; London is not special (below an even spread). The Globex
  open hour is often one end of the day.
- Setups by sweep window (44 sequences, FVG near edge, fixed 1R): outside
  any kill zone 26 sequences, 13 wins / 5 losses, +7.7R; London 6 (2/2, 0R);
  NY AM 8 (2/2, +0.5R); NY PM 3 (0/0); Asia 1. At <= 5 trades per window this
  is noise, but a hard gate would have discarded most of the sample.
- Decision: every sequence records its kill zone (`killzone` column); the
  gate (`sweep_choch_sequences(killzones=[...])`) stays off in research until
  the backtest on longer data compares all hours vs NY AM vs London + NY AM.
- Robin trades London open and NY AM most of the time (2026-11-02): the live
  screener alerts only in London + NY AM (`ict/config.py`). In this sample
  those two windows had 14 sequences, 4 wins / 4 losses at 1R, +0.5R.

## Premium / discount (done)
- Robin's rule (2026-11-02): a long's entry must be in discount of the
  dealing range, a short's in premium.
- Two range definitions measured (`ict/premium_discount.py`, `tools/pd_check.py`):
  - Setup move: sweep extreme -> furthest price reached since.
  - Dealing range: latest known tier-2 swing high and low, widened to the
    sweep extreme.
- 35 setups with an FVG near-edge entry (latest gap), NQ 5m Feb–Apr 2026:
  - Setup move: the entry sits at a median 71% of the move from the trade's
    side — in the wrong half for 31 of 35. This range is nearly incompatible
    with the latest-FVG entry; it would need a deeper FVG or the order block.
  - Dealing range: median 48%; 18 correct half / 17 wrong half.
    Correct half: 1R 10 W / 4 L, +6.0R; pool target 8 fills, +10.5R.
    Wrong half: 1R 7 W / 5 L, +2.0R; pool target 1 fill, -1.0R.
- Reading: with the dealing range, the rule is compatible with the entry
  and points the right way (tiny sample).
- Decided (Robin, 2026-11-02): the bigger dealing range — latest significant
  (tier-2) swing high and low, widened to the sweep extreme. Gate: longs in
  discount (< 50%), shorts in premium (> 50%). `config.PD_RANGE = "dealing"`.

## v1 model assembled (`ict/model.py: build_trades`, `tools/run_model.py`)
- Gates in order: kill zone (London + NY AM) -> FVG in the displacement leg
  -> entry beyond stop? -> dealing-range half -> strict target >= 2R ->
  limit order at the FVG near edge (1 h) -> stop / target / day end.
- NQ 5m, 9 Feb – 15 Apr 2026 (after warm-up), NOT a validated backtest:
  44 sequences -> 14 in London/NY AM -> 11 with an FVG -> 3 in the correct
  half -> 2 with a target >= 2R -> 2 trades: 1 win (+3.2R), 1 loss.
- Variants: all hours 8 fills, 5 W / 3 L, +10.5R; all hours without the P/D
  gate 9 fills, +9.5R; all hours with a fixed 1R target 14 fills, 10 W / 4 L,
  +6.0R; London + NY AM with 1R 3 fills, 2 W / 1 L, +1.0R.
- Reading: as decided, v1 produces about one NQ trade a month. The biggest
  filters are the kill-zone gate (30 of 44) and the P/D gate (8 of 11).
  Too few trades to judge the rules on NQ alone, even with years of data.

## Multi-market run (rules unchanged, 2026-11-02)
- Data: 36 full-size CME futures (micros and mini duplicates excluded), 5m,
  Jan–Apr 2026, from the same free TopstepX dataset. Each file is one fixed
  contract; gold and platinum turn illiquid near expiry, FX / rates / NKD /
  crypto cover only 5–7 weeks. Each market is trimmed to days with volume
  >= 20% of its median day; 10-day warm-up.
- Rules were designed on NQ only, so the other 35 markets are out-of-sample
  for the rule design (same calendar period, though).
- Costs: $4.50 commission per round trip ($1 for micro crypto) + 1 tick
  slippage on every trade (`ict/contracts.py`). 95% ranges come from
  resampling whole trading days.

  | Variant | Trades | Avg R gross | Avg cost | Avg R net | Net 95% range |
  |---|---|---|---|---|---|
  | v1 as decided (London + NY AM) | 37 | +0.11 | 0.09 | +0.02 | -0.70 to +0.72 |
  | v1, all hours | 159 | +0.24 | 0.11 | +0.13 | -0.17 to +0.45 |
  | v1, all hours, fixed 1R | 276 | +0.16 | 0.09 | +0.06 | -0.04 to +0.17 |

- Net R by class (all hours, pool target): equity indices +24.4 (34 trades,
  cost 0.03R), energy +5.6, crypto +5.7 (5 trades), currencies +2.5;
  agriculture -3.2, rates -6.8, metals -7.4. Costs are 0.15–0.26R per trade
  in agriculture, rates and currencies, where stops are only a few ticks wide.
- Equity-index trades rarely coincide: 31 trades at 29 distinct times.
- Reading: nothing is statistically conclusive after costs. Equity indices
  are the strongest class; the kill-zone gate still shows no benefit; costs
  call for a minimum-risk (maximum cost) rule.

## Hard part #6 — Higher-timeframe bias (built, gate off)
- Definition: 5m data resampled to 1H and 4H candles (4H aligned to the CME
  day: 18, 22, 02, 06, 10, 14 ET); the same swing + structure detectors run
  on them; bias = direction of the latest HTF structure break. An HTF candle
  is used only once closed (tested: no lookahead). Code: `ict/htf.py`.
- Every setup records bias_1h and bias_4h; `ModelParams(htf_gate="1h"|"4h")`
  trades only with the bias. `config.HTF_GATE = None` for now.
- Test, 36 markets, same trades split by bias (net of costs; differences
  with a 95% range from resampling days):

  | Target | Bias | With bias | Against / none | Difference range |
  |---|---|---|---|---|
  | Pool (>= 2R) | 1H | 60 trades, +0.06R | 99, +0.17R | -0.67 to +0.43 |
  | Pool (>= 2R) | 4H | 77, +0.11R | 82, +0.15R | -0.59 to +0.54 |
  | Pool (>= 2R) | 1H and 4H agree | 38, +0.01R | 121, +0.17R | -0.76 to +0.46 |
  | Fixed 1R | 1H | 89, +0.11R | 187, +0.04R | -0.19 to +0.31 |
  | Fixed 1R | 4H | 127, +0.08R | 149, +0.05R | -0.18 to +0.24 |
  | Fixed 1R | 1H and 4H agree | 58, +0.16R | 218, +0.04R | -0.17 to +0.39 |

- Reading: no consistent effect — the sign flips with the target rule and
  every range spans zero. Not evidence against bias in general; evidence
  that this structure-based bias adds nothing visible on 3 months.
- Not built: a daily-draw bias (e.g. which of PDH / PDL is the day's draw).
- Decided (Robin, 2026-11-02): he reads the trend from 1H structure, so the
  screener only takes setups in the direction of the latest 1H structure
  break (`config.HTF_GATE = "1h"`). Research variants run without it.
- The full rule set as decided (London + NY AM, FVG near edge, dealing-range
  half, 1H trend, strict target >= 2R), 36 markets, 13 Feb – 10 Apr 2026:
  13 trades (about 1.6 a week), 6 targets / 7 stops, +7.5R gross, net
  +0.46R a trade with a 95% range of -0.61 to +1.63. NQ alone: 2 trades.

## Live screener v0 (2026-11-02)
- Robin chose the live screener before the longer-history backtest.
- `ict/live/`: each 5-minute candle close during London / NY AM (+75 min),
  every market in `config.SCREENER_MARKETS` is scanned with exactly the
  backtest pipeline; an order placed at the latest closed candle becomes an
  alert. Sent alerts are remembered (no duplicates) and logged to JSONL.
- Proven: replaying candles one by one reproduces each backtest order at its
  bar and never earlier (`tests/test_live.py`). Replay of 10 Apr 2026
  02:00–06:20 ET over the 11 default markets produced exactly the two
  decided-model trades (NQ and ES longs, signals at 05:25 ET).
- Alerts include position size at `RISK_PCT` of `ACCOUNT_SIZE` (full-size
  contract, or the micro when one full contract risks too much) and costs in
  R, flagged above `MAX_COST_R`.
- Data: free Yahoo Finance via yfinance, delayed >= 10 minutes (CME rule for
  free data). Fine for paper alerts; a real-time feed is needed to trade the
  5m entries live. Runs on Robin's machine; this workspace cannot reach it.
- Robin has an Interactive Brokers account (2026-11-02): IBKR is the default
  screener feed (`ict/live/feeds.py:IBKRFeed`, via `ib_async`, read-only).
  It reads continuous front-month 5m candles from TWS / IB Gateway on
  Robin's computer: 30 days of history at start, then the last 2 days each
  cycle (one request per market per 5 minutes). `python -m
  ict.live.check_ibkr` verifies contracts, candle counts and data delay.
  Needs IB's non-professional futures data bundle for real-time candles.
- Connection verified on Robin's laptop (2026-11-03): TWS live, port 7496,
  all 11 markets resolve to the Dec-2026 contracts, 1,272 candles each, but
  candles arrive 10 minutes late (no futures data subscription yet).
- IB showed only "(P)" bundles: the account is set as a professional
  market-data subscriber, and the $10 futures bundle is offered to
  non-professionals only. Either fix the status (if it was set by mistake) or,
  if professional is correct, subscribe to CME Real-Time (P) only (covers NQ,
  ES, RTY, 6E/6B/6J).
- Until then the screener runs on the delayed candles as a paper forward-test:
  signals are identical to real-time ones, only later, so they still count as
  out-of-sample evidence for the model.
- The screener now re-checks the last 3 candles each cycle (was 1): a candle
  that arrives after its cycle (delayed or slow feed) no longer loses its
  signal; the state file prevents repeats (test added).
