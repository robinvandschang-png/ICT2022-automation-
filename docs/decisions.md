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
  gate (`sweep_choch_sequences(killzones=[...])`) stays off until the
  backtest on longer data compares all hours vs NY AM vs London + NY.
