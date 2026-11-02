"""Liquidity pools: where resting orders sit, and when price takes them.

Pools
- Fixed, time-based levels:
  PDH / PDL   previous trading day high / low (valid until taken)
  PWH / PWL   previous week high / low (valid until taken)
  Asia H / L  20:00-24:00 ET range, valid for the rest of that trading day
  London H / L 02:00-05:00 ET range, valid for the rest of that trading day
- Swing pools: tier-2 swing highs / lows, valid from promotion until taken.

Buy-side pools sit above highs, sell-side pools below lows. A pool is taken
by the first candle that trades through it after it becomes active.

Whether a take was a sweep (reversal) or a run (continuation) is decided
separately; `take_features` records the facts a rule can use:
- closed_beyond: did the taking candle close beyond the level?
- reclaim_bars:  candles until the first close back inside (0 = same candle)
- depth:         furthest trade beyond the level before the reclaim (or
                 within `max_bars`), in yardsticks
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ict.swings import HIGH

BUY, SELL = "buy-side", "sell-side"
DEFAULT_TZ = "America/New_York"


def trading_day(index: pd.DatetimeIndex, tz: str = DEFAULT_TZ, day_start_hour: int = 18) -> pd.Series:
    """Trading-day label per bar. CME days start at 18:00 ET (the bar at 18:00 belongs to the next day)."""
    local = index.tz_convert(tz)
    shifted = local + pd.Timedelta(hours=24 - day_start_hour)
    return pd.Series(shifted.normalize().tz_localize(None), index=index)


def _window_mask(local: pd.DatetimeIndex, start: str, end: str) -> np.ndarray:
    m = local.hour * 60 + local.minute
    s = int(start[:2]) * 60 + int(start[3:])
    e = int(end[:2]) * 60 + int(end[3:]) or 24 * 60
    return (m >= s) & (m < e)


def fixed_pools(df: pd.DataFrame, tz: str = DEFAULT_TZ) -> pd.DataFrame:
    """Time-based pools. Bar columns are integer positions into df."""
    local = df.index.tz_convert(tz)
    day = trading_day(df.index, tz).to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    pos = np.arange(len(df))
    rows = []

    days = pd.unique(day)
    first_bar = {d: int(pos[day == d][0]) for d in days}
    last_bar = {d: int(pos[day == d][-1]) for d in days}

    # Previous day high / low
    for prev, cur in zip(days[:-1], days[1:]):
        sel = day == prev
        rows.append(("PDH", BUY, high[sel].max(), last_bar[prev], first_bar[cur], None))
        rows.append(("PDL", SELL, low[sel].min(), last_bar[prev], first_bar[cur], None))

    # Previous week high / low (week of the trading day, Mon-Fri)
    week = pd.DatetimeIndex(day).to_period("W-SUN").to_numpy()
    weeks = pd.unique(week)
    for prev, cur in zip(weeks[:-1], weeks[1:]):
        sel = week == prev
        nxt = int(pos[week == cur][0])
        rows.append(("PWH", BUY, high[sel].max(), int(pos[sel][-1]), nxt, None))
        rows.append(("PWL", SELL, low[sel].min(), int(pos[sel][-1]), nxt, None))

    # Session ranges, valid for the rest of their trading day
    for name, (start, end) in {"Asia": ("20:00", "00:00"), "London": ("02:00", "05:00")}.items():
        in_win = _window_mask(local, start, end)
        for d in days:
            sel = (day == d) & in_win
            if not sel.any():
                continue
            done = int(pos[sel][-1])
            after = pos[(day == d) & (pos > done)]
            if len(after) == 0:
                continue
            rows.append((f"{name} H", BUY, high[sel].max(), done, int(after[0]), last_bar[d]))
            rows.append((f"{name} L", SELL, low[sel].min(), done, int(after[0]), last_bar[d]))

    out = pd.DataFrame(rows, columns=["name", "side", "price", "formed_bar", "active_from", "expires"])
    out["expires"] = out["expires"].astype("Int64")
    return out


def swing_pools(swings: pd.DataFrame, min_tier: int = 2) -> pd.DataFrame:
    """Swing highs / lows of at least `min_tier`, active once promoted."""
    col = "t2_confirmed" if min_tier == 2 else "t3_confirmed"
    s = swings[swings[col].notna()]
    return pd.DataFrame({
        "name": [f"T{min_tier} {'high' if k == HIGH else 'low'}" for k in s["kind"]],
        "side": [BUY if k == HIGH else SELL for k in s["kind"]],
        "price": s["price"].to_numpy(),
        "formed_bar": s["bar"].to_numpy(),
        "active_from": (s[col] + 1).astype(int).to_numpy(),
        "expires": pd.array([pd.NA] * len(s), dtype="Int64"),
    })


def pool_takes(df: pd.DataFrame, pools: pd.DataFrame) -> pd.DataFrame:
    """Add `taken_bar`: first bar at or after `active_from` that trades through the pool."""
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    taken = []
    for p in pools.itertuples(index=False):
        a = int(p.active_from)
        b = len(df) if pd.isna(p.expires) else int(p.expires) + 1
        if a >= b:
            taken.append(pd.NA)
            continue
        hit = high[a:b] > p.price if p.side == BUY else low[a:b] < p.price
        taken.append(a + int(np.argmax(hit)) if hit.any() else pd.NA)
    out = pools.copy()
    out["taken_bar"] = pd.array(taken, dtype="Int64")
    return out


def take_features(df: pd.DataFrame, takes: pd.DataFrame, vol: pd.Series, max_bars: int = 12) -> pd.DataFrame:
    """Facts about each take that a sweep/run rule can use (see module docstring)."""
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    v = vol.to_numpy()
    t = takes[takes["taken_bar"].notna()].copy()
    closed, reclaim, depth = [], [], []
    for p in t.itertuples(index=False):
        i = int(p.taken_bar)
        j_end = min(len(df), i + max_bars + 1)
        if p.side == BUY:
            inside = close[i:j_end] < p.price
            beyond = high[i:j_end] - p.price
        else:
            inside = close[i:j_end] > p.price
            beyond = p.price - low[i:j_end]
        k = int(np.argmax(inside)) if inside.any() else None
        closed.append(not inside[0])
        reclaim.append(k)
        upto = (k + 1) if k is not None else len(beyond)
        depth.append(float(beyond[:upto].max() / v[i]))
    t["closed_beyond"] = closed
    t["reclaim_bars"] = pd.array(reclaim, dtype="Int64")
    t["depth"] = depth
    return t.reset_index(drop=True)
