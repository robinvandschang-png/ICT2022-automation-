"""Draw on liquidity, v1: the target comes from the setup.

The setup decides the direction (e.g. sell-side sweep + bullish CHoCH = long).
The target is the nearest untapped pool on the opposite side that is at
least `min_rr` times the risk away from the entry. Closer pools that were
skipped are counted (`pools_between`) so the backtest can compare this with
the strict version ("the nearest pool itself must be >= min R").

No target within reach = no trade: this is the bot's version of
"no clear draw, no trade".

A separate higher-timeframe draw model (structure, premium/discount) is a
later filter, to be tested in the backtest rather than assumed.
"""
from __future__ import annotations

import pandas as pd

from ict.liquidity import BUY, SELL
from ict.structure import UP


def pools_as_of(pools: pd.DataFrame, t: int) -> pd.DataFrame:
    """Pools that are active and untapped at the close of bar t.

    `pools` must carry `taken_bar` (see ict.liquidity.pool_takes).
    """
    active = pools["active_from"] <= t
    untapped = pools["taken_bar"].isna() | (pools["taken_bar"] > t)
    alive = pools["expires"].isna() | (pools["expires"] >= t)
    return pools[(active & untapped & alive).fillna(False).astype(bool)]


def find_target(pools_now: pd.DataFrame, direction: str, entry: float, stop: float,
                min_rr: float = 2.0) -> dict | None:
    """Nearest opposite pool at least `min_rr` x risk from the entry, or None."""
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    if direction == UP:
        side = pools_now[(pools_now["side"] == BUY) & (pools_now["price"] > entry)]
        dist = side["price"] - entry
    else:
        side = pools_now[(pools_now["side"] == SELL) & (pools_now["price"] < entry)]
        dist = entry - side["price"]
    if side.empty:
        return None
    side = side.assign(rr=dist / risk).sort_values("rr")
    far_enough = side[side["rr"] >= min_rr]
    if far_enough.empty:
        return None
    t = far_enough.iloc[0]
    return {
        "target_name": t["name"],
        "target_price": float(t["price"]),
        "target_rr": float(t["rr"]),
        "pools_between": int((side["rr"] < min_rr).sum()),
        "nearest_rr": float(side["rr"].iloc[0]),
    }
