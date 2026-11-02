# Design decisions

Running log of how each ICT concept is quantified. "Provisional" values are
starting points; final values come from the backtest, not from eyeballing.

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

## Concept 4 — Liquidity pools and sweeps (in progress)
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
