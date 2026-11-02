"""Model assembly (work in progress): sweep -> CHoCH on displacement -> entry -> trade.

Built so far
- `build_context`: every detector run once over a candle series.
- `sweep_choch_sequences`: each sweep followed by a displacement break in the
  reversal direction within `window` candles. Stop = beyond the furthest
  price since the take, plus `buffer` yardsticks.
- `simulate_trade`: limit order at `entry`, then stop vs target, within the
  trading day. Conservative on ambiguity: a candle that touches both the stop
  and the target counts as a stop; the fill candle cannot also hit the target.

Not yet included: time windows (kill zones), premium/discount, costs.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ict.displacement import DisplacementParams, evaluate_breaks
from ict.liquidity import SELL, classify_takes, fixed_pools, pool_takes, swing_pools, take_features, trading_day
from ict.structure import DOWN, UP, structure_breaks
from ict.swings import SwingParams, detect_swings
from ict.volatility import volatility


@dataclass
class Context:
    df: pd.DataFrame
    vol: pd.Series
    swings: pd.DataFrame
    breaks: pd.DataFrame   # with displacement measures
    pools: pd.DataFrame    # with taken_bar
    takes: pd.DataFrame    # with sweep classification
    day: np.ndarray        # trading-day label per bar


def build_context(df: pd.DataFrame, swing_params: SwingParams = SwingParams(),
                  disp_params: DisplacementParams = DisplacementParams()) -> Context:
    vol = volatility(df, swing_params.vol_method, swing_params.atr_period,
                     swing_params.tod_lookback, swing_params.tz)
    swings = detect_swings(df, swing_params)
    breaks = evaluate_breaks(df, structure_breaks(df, swings), vol, disp_params)
    pools = pool_takes(df, pd.concat([fixed_pools(df), swing_pools(swings)], ignore_index=True))
    takes = classify_takes(take_features(df, pools, vol))
    return Context(df, vol, swings, breaks, pools, takes, trading_day(df.index).to_numpy())


def sweep_choch_sequences(ctx: Context, window: int = 12, buffer: float = 0.1) -> pd.DataFrame:
    df = ctx.df
    high, low = df["high"].to_numpy(), df["low"].to_numpy()
    v = ctx.vol.to_numpy()
    disp = ctx.breaks[ctx.breaks["displacement"]]
    sweeps = ctx.takes[ctx.takes["sweep"]].sort_values("taken_bar")
    rows, used = [], set()
    for s in sweeps.itertuples(index=False):
        direction = UP if s.side == SELL else DOWN
        i = int(s.taken_bar)
        b = disp[(disp["direction"] == direction) & (disp["bar"] >= i) & (disp["bar"] <= i + window)]
        if b.empty or int(b["bar"].iloc[0]) in used:
            continue
        brk = b.iloc[0]
        used.add(int(brk["bar"]))
        t = max(int(brk["bar"]), int(s.decided_at))
        stop = low[i:t + 1].min() - buffer * v[i] if direction == UP else high[i:t + 1].max() + buffer * v[i]
        rows.append({"sweep_bar": i, "swept": s.name, "direction": direction,
                     "leg_start": int(brk["leg_start"]), "break_bar": int(brk["bar"]),
                     "setup_bar": t, "stop": stop})
    return pd.DataFrame(rows)


def simulate_trade(ctx: Context, direction: str, entry: float, stop: float, target: float,
                   place_bar: int, wait: int = 12, immediate: bool = False) -> dict:
    """Outcome of a limit order placed at the close of `place_bar` (or filled there if `immediate`)."""
    df = ctx.df
    high, low, close = (df[c].to_numpy() for c in ("high", "low", "close"))
    n, day = len(df), ctx.day
    up = direction == UP
    risk = abs(entry - stop)

    end = place_bar + 1
    while end < n and day[end] == day[place_bar]:
        end += 1                                  # first bar of the next trading day

    fill = place_bar if immediate else None
    if fill is None:
        for k in range(place_bar + 1, min(place_bar + 1 + wait, end)):
            touched = low[k] <= entry if up else high[k] >= entry
            if touched:
                fill = k
                if (low[k] <= stop) if up else (high[k] >= stop):
                    return {"outcome": "stop", "r": -1.0, "fill_bar": k, "exit_bar": k}
                break
            if (high[k] >= target) if up else (low[k] <= target):
                return {"outcome": "missed (target first)", "r": 0.0, "fill_bar": None, "exit_bar": k}
        if fill is None:
            return {"outcome": "not filled", "r": 0.0, "fill_bar": None, "exit_bar": None}

    for m in range(fill + 1, end):
        if (low[m] <= stop) if up else (high[m] >= stop):
            return {"outcome": "stop", "r": -1.0, "fill_bar": fill, "exit_bar": m}
        if (high[m] >= target) if up else (low[m] <= target):
            return {"outcome": "target", "r": abs(target - entry) / risk, "fill_bar": fill, "exit_bar": m}
    last = close[end - 1]
    return {"outcome": "open at day end", "r": ((last - entry) if up else (entry - last)) / risk,
            "fill_bar": fill, "exit_bar": end - 1}
