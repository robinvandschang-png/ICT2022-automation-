"""Displacement: was the move that broke structure strong and one-sided?

Measured on one leg: from the extreme where the move started (`leg_start`)
to the candle that closed beyond the swing (`end`). All sizes are expressed
in yardstick units (see ict.volatility), so the same thresholds work across
markets and timeframes.

Measures
- leg:        net move from the leg extreme to the breaking close
- big_body:   largest candle body in the leg
- efficiency: net move / sum of candle ranges (1.0 = no overlap at all)
- body_range: average body / range (closes near the extremes)
- fvg_count:  fair value gaps in the leg's direction of at least `min_fvg`
- max_fvg:    largest such gap

Timing: the gates use candles up to `end`, so the decision is known at the
close of the breaking candle. An FVG whose middle candle is the breaking
candle is only known one candle later (`fvg_known_at`).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ict.structure import UP


@dataclass(frozen=True)
class DisplacementParams:
    min_leg: float = 1.5         # net move, in yardsticks
    min_big_body: float = 1.0    # largest body, in yardsticks
    min_efficiency: float = 0.5  # net move / sum of ranges
    min_fvg: float = 0.3         # smallest FVG that counts, in yardsticks
    require_fvg: bool = False    # True: no FVG, no displacement


def measure_leg(df: pd.DataFrame, vol: pd.Series, start: int, end: int, direction: str,
                min_fvg: float = 0.3) -> dict:
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    c = df["close"].to_numpy()
    v = vol.to_numpy()
    seg = slice(start, end + 1)

    net = c[end] - lo[start] if direction == UP else h[start] - c[end]
    unit = float(np.mean(v[seg]))
    body = np.abs(c[seg] - o[seg])
    rng = h[seg] - lo[seg]
    with np.errstate(divide="ignore", invalid="ignore"):
        body_range = float(np.nanmean(np.where(rng > 0, body / rng, np.nan)))

    gaps = []
    last_fvg_bar = None
    for j in range(start + 1, end + 1):
        if j + 1 >= len(df):
            break
        gap = lo[j + 1] - h[j - 1] if direction == UP else lo[j - 1] - h[j + 1]
        size = gap / v[j]
        if size >= min_fvg:
            gaps.append(size)
            last_fvg_bar = j + 1

    return {
        "n_bars": end - start + 1,
        "leg": net / unit,
        "big_body": float(np.max(body / v[seg])),
        "efficiency": net / float(np.sum(rng)) if np.sum(rng) > 0 else 0.0,
        "body_range": body_range,
        "fvg_count": len(gaps),
        "max_fvg": max(gaps) if gaps else 0.0,
        "fvg_known_at": last_fvg_bar,
    }


def passes(m: dict, p: DisplacementParams) -> bool:
    ok = m["leg"] >= p.min_leg and m["big_body"] >= p.min_big_body and m["efficiency"] >= p.min_efficiency
    return bool(ok and (m["fvg_count"] > 0 or not p.require_fvg))


def evaluate_breaks(df: pd.DataFrame, breaks: pd.DataFrame, vol: pd.Series,
                    params: DisplacementParams = DisplacementParams()) -> pd.DataFrame:
    """Add displacement measures and a `displacement` flag to each structure break."""
    rows = []
    for b in breaks.itertuples(index=False):
        m = measure_leg(df, vol, int(b.leg_start), int(b.bar), b.direction, params.min_fvg)
        m["displacement"] = passes(m, params)
        rows.append(m)
    return pd.concat([breaks.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
