# ICT 2022 Automation

A screener that scans markets for ICT 2022 trade setups. Each ICT concept is
turned into a precise, testable rule, checked against hand-marked charts, and
finally validated by backtest before any live scanning.

> Status: early build. Detectors are being built concept by concept.
> There is no live scanning or order execution yet.

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
| 4. Liquidity pools and sweeps | — | Next |
| 2. Draw on liquidity | — | Planned |
| PD arrays: FVG, order block | — | Planned |
| Premium / discount, dealing range | — | Planned |
| Time windows (kill zones, Silver Bullet) | — | Planned |
| Model assembly (gated sequence) | — | Planned |
| Backtest (results in R, out-of-sample) | — | Planned |
| Screener and alerts | — | Planned |

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
tools/
  plot_swings.py     chart raw pivots vs swing tiers
  plot_structure.py  chart structure breaks with displacement verdicts
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

Data used so far: NQ (E-mini Nasdaq-100) 1m–1h from the TopstepX API via the
public repo `axb0306/cme-futures-ohlc` (third-party, not official CME data),
and EUR/USD 1h sample data from the `backtesting` package.

## Disclaimer

Research and education tool. Not financial advice. Nothing here has a proven
edge until the backtest says so.
