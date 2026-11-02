"""PD arrays left by a displacement leg: fair value gaps and the order block.

The leg runs from `start` (the extreme where the move began, e.g. the sweep
low) to `end` (the candle that closed beyond the swing).

Fair value gap (bullish): candle j+1's low above candle j-1's high, with the
middle candle j inside the leg. Zone = [high[j-1], low[j+1]].
  proximal = the edge price meets first on a retrace (top for bullish)
  ce       = consequent encroachment, the zone's midpoint
  known_at = j + 1 (the gap only exists once candle j+1 has printed)

Order block (bullish): the last down-close candle before the leg's first
large-bodied candle, searched from `lookback` candles before the leg start.
  zone = that candle's low..high, proximal = its high (bullish) / low (bearish)
  mean = midpoint of its body (ICT's "mean threshold")
Mirror everything for bearish legs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ict.structure import UP


def leg_fvgs(df: pd.DataFrame, vol: pd.Series, start: int, end: int, direction: str,
             min_size: float = 0.3) -> list[dict]:
    """FVGs in the leg's direction, oldest first. Only gaps >= `min_size` yardsticks."""
    h = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    v = vol.to_numpy()
    out = []
    for j in range(max(start, 1), end + 1):
        if j + 1 >= len(df):
            break
        if direction == UP:
            bottom, top = h[j - 1], lo[j + 1]
        else:
            bottom, top = h[j + 1], lo[j - 1]
        size = (top - bottom) / v[j]
        if size < min_size:
            continue
        out.append({
            "middle_bar": j, "known_at": j + 1, "bottom": bottom, "top": top,
            "proximal": top if direction == UP else bottom,
            "distal": bottom if direction == UP else top,
            "ce": (top + bottom) / 2, "size": size,
        })
    return out


def leg_order_block(df: pd.DataFrame, vol: pd.Series, start: int, end: int, direction: str,
                    big_body: float = 1.0, lookback: int = 3) -> dict | None:
    """Last opposing candle before the leg's first candle with body >= `big_body` yardsticks."""
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    c = df["close"].to_numpy()
    v = vol.to_numpy()
    body = np.abs(c - o) / v
    with_dir = (c > o) if direction == UP else (c < o)
    first_big = next((k for k in range(start, end + 1) if with_dir[k] and body[k] >= big_body), end)
    opposing = (c < o) if direction == UP else (c > o)
    for k in range(first_big - 1, max(start - lookback, 0) - 1, -1):
        if opposing[k]:
            return {
                "bar": k, "high": h[k], "low": lo[k],
                "proximal": h[k] if direction == UP else lo[k],
                "distal": lo[k] if direction == UP else h[k],
                "mean": (o[k] + c[k]) / 2,
            }
    return None


def overlaps(fvg: dict, ob: dict | None) -> bool:
    """Do the FVG zone and the order block zone share any price?"""
    if ob is None:
        return False
    return max(fvg["bottom"], ob["low"]) <= min(fvg["top"], ob["high"])
