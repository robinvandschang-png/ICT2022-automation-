"""Significant swing detection for the ICT screener.

Three layers, all causal (no future candles are ever used):

1. Raw pivots: a candle whose high (low) is beyond the `pivot_bars` candles
   on each side. Known `pivot_bars` candles after it forms.
2. Tier 1 (short-term swings): raw pivots that alternate high/low and sit at
   least `min_move_atr` x ATR away from the previous opposite swing. A higher
   high (lower low) before that move happens replaces the previous swing.
3. Tier 2 (intermediate-term) and tier 3 (long-term): a swing whose
   neighbours of the same kind in the tier below are both less extreme.

Every swing records the bar at which each fact became known, so a backtest or
live scan can ask "what did the bot know at bar t?" via `swings_as_of`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ict.volatility import DEFAULT_TZ, atr, volatility  # noqa: F401  (atr re-exported)

HIGH, LOW = "high", "low"


@dataclass(frozen=True)
class SwingParams:
    pivot_bars: int = 2        # candles required on each side of a raw pivot
    atr_period: int = 14       # ATR length (also the fallback for "tod")
    min_move_atr: float = 1.0  # opposite swing must be >= this many yardsticks away
    vol_method: str = "tod"    # yardstick: "tod" (time-of-day range) or "atr"
    tod_lookback: int = 20     # sessions averaged for "tod"
    tz: str = DEFAULT_TZ       # exchange clock for "tod"


def raw_pivots(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Fractal pivots: strictly beyond the n candles before, at least equal to the n after.

    The asymmetric tie rule marks only the first candle of an equal-high pair.
    """
    high = pd.Series(df["high"].to_numpy())
    low = pd.Series(df["low"].to_numpy())

    left_high = high.shift(1).rolling(n).max()
    right_high = high.iloc[::-1].shift(1).rolling(n).max().iloc[::-1]
    left_low = low.shift(1).rolling(n).min()
    right_low = low.iloc[::-1].shift(1).rolling(n).min().iloc[::-1]

    is_high = (high > left_high) & (high >= right_high)
    is_low = (low < left_low) & (low <= right_low)

    rows = [(i, HIGH, high[i], i + n) for i in np.flatnonzero(is_high)]
    rows += [(i, LOW, low[i], i + n) for i in np.flatnonzero(is_low)]
    out = pd.DataFrame(rows, columns=["bar", "kind", "price", "confirmed"])
    return out.sort_values(["confirmed", "bar"], kind="stable").reset_index(drop=True)


def _beyond(price: float, other: float, kind: str) -> bool:
    return price > other if kind == HIGH else price < other


def _tier1(pivots: pd.DataFrame, atr_values: np.ndarray, k: float) -> list[dict]:
    """ATR-filtered zigzag over raw pivots, processed in the order they become known."""
    records: list[dict] = []
    active: list[dict] = []  # current alternating sequence (no cancelled swings)

    for p in pivots.itertuples(index=False):
        a = atr_values[p.bar]
        if np.isnan(a):
            continue
        new = {"bar": int(p.bar), "kind": p.kind, "price": float(p.price),
               "confirmed": int(p.confirmed), "final": None, "cancelled": None}

        if not active:
            active.append(new)
            records.append(new)
            continue

        last = active[-1]
        if p.kind == last["kind"]:
            if _beyond(new["price"], last["price"], p.kind):
                last["cancelled"] = new["confirmed"]  # replaced by a more extreme swing
                active[-1] = new
                records.append(new)
        elif abs(new["price"] - last["price"]) >= k * a:
            last["final"] = new["confirmed"]  # opposite swing locks the previous one
            active.append(new)
            records.append(new)

    return records


def _promote(seq: list[dict], known_key: str, out_key: str) -> None:
    """Mark swings whose same-kind neighbours are both less extreme.

    Strictly beyond the left neighbour, at least equal to the right one.
    Promotion is known when the right neighbour's own status is known.
    """
    for j in range(1, len(seq) - 1):
        cur, left, right = seq[j], seq[j - 1], seq[j + 1]
        if right[known_key] is None:
            continue
        kind = cur["kind"]
        right_ok = cur["price"] >= right["price"] if kind == HIGH else cur["price"] <= right["price"]
        if _beyond(cur["price"], left["price"], kind) and right_ok:
            cur[out_key] = right[known_key]


def detect_swings(df: pd.DataFrame, params: SwingParams = SwingParams()) -> pd.DataFrame:
    """Return every tier-1 swing (including cancelled ones) with tier and timing columns.

    Columns: bar, time, kind, price, confirmed, final, cancelled,
             t2_confirmed, t3_confirmed, tier
    All bar columns are integer positions into `df`; NaN means "not (yet) known".
    """
    pivots = raw_pivots(df, params.pivot_bars)
    yardstick = volatility(df, params.vol_method, params.atr_period,
                           params.tod_lookback, params.tz).to_numpy()
    records = _tier1(pivots, yardstick, params.min_move_atr)

    for r in records:
        r["t2_confirmed"] = None
        r["t3_confirmed"] = None

    for kind in (HIGH, LOW):
        tier1 = [r for r in records if r["kind"] == kind and r["cancelled"] is None]
        _promote(tier1, "final", "t2_confirmed")
        tier2 = [r for r in tier1 if r["t2_confirmed"] is not None]
        _promote(tier2, "t2_confirmed", "t3_confirmed")

    cols = ["bar", "kind", "price", "confirmed", "final", "cancelled", "t2_confirmed", "t3_confirmed"]
    out = pd.DataFrame(records, columns=cols)
    if out.empty:
        out["time"] = pd.Series(dtype=object)
        out["tier"] = pd.Series(dtype=int)
        return out
    for c in ["final", "cancelled", "t2_confirmed", "t3_confirmed"]:
        out[c] = out[c].astype("Float64").astype("Int64")
    out.insert(1, "time", df.index[out["bar"].to_numpy()])
    out["tier"] = 1 + out["t2_confirmed"].notna().astype(int) + out["t3_confirmed"].notna().astype(int)
    return out.sort_values("bar", kind="stable").reset_index(drop=True)


def swings_as_of(swings: pd.DataFrame, t: int, min_tier: int = 1) -> pd.DataFrame:
    """Swings the bot knew about at the close of bar t, at or above `min_tier`."""
    if min_tier <= 1:
        cancelled = swings["cancelled"]
        known = (swings["confirmed"] <= t) & (cancelled.isna() | (cancelled > t))
    elif min_tier == 2:
        known = swings["t2_confirmed"].notna() & (swings["t2_confirmed"] <= t)
    else:
        known = swings["t3_confirmed"].notna() & (swings["t3_confirmed"] <= t)
    return swings[known.fillna(False).astype(bool)]
