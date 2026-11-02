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

## Open
- Concept 4 — sweep vs run: the book's single-candle close test vs "reclaims
  the level within N candles" (NQ 2 Apr 2026 09:30 ET closed below the low,
  then reversed — a sweep by intent, a run by the close test).
