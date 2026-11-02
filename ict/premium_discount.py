"""Premium / discount: where an entry sits inside a range (0 = range low, 1 = range high).

Longs must enter in discount (< 0.5), shorts in premium (> 0.5) — Robin's rule.
Two candidate ranges, both measured with only the information known at the bar:

- Setup range: from the sweep extreme to the furthest price reached since
  (the move the setup produced). For a long: sweep low -> highest high so far.
- Dealing range: the latest known tier-2 swing high and swing low, widened to
  include the sweep extreme if price went beyond them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ict.structure import UP
from ict.swings import HIGH, LOW, swings_as_of


def position(price: float, low: float, high: float) -> float:
    return float((price - low) / (high - low)) if high > low else np.nan


def in_correct_half(pos: float, direction: str) -> bool:
    """Discount (< 0.5) for longs, premium (> 0.5) for shorts."""
    return bool(pos < 0.5) if direction == UP else bool(pos > 0.5)


def setup_range(df: pd.DataFrame, sweep_bar: int, upto: int, direction: str) -> tuple[float, float]:
    h = df["high"].to_numpy()[sweep_bar:upto + 1]
    lo = df["low"].to_numpy()[sweep_bar:upto + 1]
    return (float(lo.min()), float(h.max()))


def dealing_range(df: pd.DataFrame, swings: pd.DataFrame, sweep_bar: int, upto: int,
                  min_tier: int = 2) -> tuple[float, float] | None:
    known = swings_as_of(swings, upto, min_tier)
    known = known[known["bar"] <= upto]
    if known[known["kind"] == HIGH].empty or known[known["kind"] == LOW].empty:
        return None
    hi = float(known[known["kind"] == HIGH].sort_values("bar")["price"].iloc[-1])
    lo = float(known[known["kind"] == LOW].sort_values("bar")["price"].iloc[-1])
    s_lo, s_hi = setup_range(df, sweep_bar, upto, UP)
    return (min(lo, s_lo), max(hi, s_hi))
