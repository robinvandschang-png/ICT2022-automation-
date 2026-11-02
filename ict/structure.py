"""Structure breaks: the first candle that closes beyond the latest tier-1 swing.

This is the raw event behind both BOS and CHoCH; classifying a break as one
or the other (with vs against the trend) comes later.

For each break we also record where the move that produced it started: the
most extreme price between the broken swing and the breaking candle. That
leg is what displacement is measured on.

Causal: at bar t only swings already confirmed (and not replaced) by the
close of bar t-1 can be broken.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ict.swings import HIGH, LOW

UP, DOWN = "up", "down"


def structure_breaks(df: pd.DataFrame, swings: pd.DataFrame) -> pd.DataFrame:
    """Return one row per break.

    Columns: bar, time, direction, swing_bar, swing_price, leg_start, leg_start_price
    """
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()

    confirms: dict[int, list] = {}
    cancels: dict[int, list] = {}
    for row in swings.itertuples(index=False):
        confirms.setdefault(int(row.confirmed), []).append(row)
        if not pd.isna(row.cancelled):
            cancels.setdefault(int(row.cancelled), []).append(row.bar)

    target = {HIGH: None, LOW: None}  # latest known, unbroken tier-1 swing of each kind
    rows = []
    for t in range(len(df)):
        # 1) breaks, using what was known at the close of t-1
        for kind, direction in ((HIGH, UP), (LOW, DOWN)):
            s = target[kind]
            if s is None:
                continue
            broke = close[t] > s.price if kind == HIGH else close[t] < s.price
            if broke:
                seg = slice(s.bar + 1, t + 1)
                if kind == HIGH:
                    start = s.bar + 1 + int(np.argmin(low[seg]))
                    start_price = low[start]
                else:
                    start = s.bar + 1 + int(np.argmax(high[seg]))
                    start_price = high[start]
                rows.append((t, direction, s.bar, s.price, start, start_price))
                target[kind] = None

        # 2) update targets with what becomes known at the close of t
        for bar in cancels.get(t, []):
            for kind in (HIGH, LOW):
                if target[kind] is not None and target[kind].bar == bar:
                    target[kind] = None
        for s in confirms.get(t, []):
            if pd.isna(s.cancelled) or s.cancelled > t:
                if target[s.kind] is None or s.bar > target[s.kind].bar:
                    target[s.kind] = s

    out = pd.DataFrame(rows, columns=["bar", "direction", "swing_bar", "swing_price",
                                      "leg_start", "leg_start_price"])
    out.insert(1, "time", df.index[out["bar"].to_numpy()] if len(out) else pd.Series(dtype=object))
    return out
