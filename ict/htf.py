"""Higher-timeframe (HTF) bias for a lower-timeframe (LTF) chart.

The same detectors run on HTF candles built from the LTF data:
  5m -> 1H / 4H candles (aligned to the CME day: 4H candles start 18:00, 22:00,
  02:00, 06:00, 10:00, 14:00 ET) -> tier-1 swings -> structure breaks.
Bias at an LTF bar = direction of the latest HTF structure break that was
known by then ("up" / "down", "" before the first break).

Timing: an HTF candle is only used once it has closed, i.e. from the last LTF
bar inside it. The last HTF candle is dropped if the LTF data does not cover
its full span (a candle still forming must not be read as closed).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ict.structure import structure_breaks
from ict.swings import SwingParams, detect_swings

TZ = "America/New_York"
ORIGIN = pd.Timestamp("2000-01-02 18:00", tz=TZ)   # Sunday 18:00 ET: CME day start


def resample(df: pd.DataFrame, rule: str, tz: str = TZ) -> tuple[pd.DataFrame, np.ndarray]:
    """HTF candles plus, for each, the position of the last LTF bar inside it.

    Incomplete trailing candles are dropped.
    """
    local = df.tz_convert(tz)
    pos = pd.Series(np.arange(len(df)), index=local.index)
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df:
        agg["volume"] = "sum"
    htf = local.resample(rule, origin=ORIGIN, label="left", closed="left").agg(agg).dropna(subset=["open"])
    last_pos = pos.resample(rule, origin=ORIGIN, label="left", closed="left").max().dropna().astype(int)
    last_pos = last_pos.reindex(htf.index)

    # drop a trailing candle whose span the data does not fully cover
    step = df.index[1] - df.index[0] if len(df) > 1 else pd.Timedelta(0)
    if len(htf):
        end = htf.index[-1] + pd.Timedelta(rule)
        if local.index[-1] + step < end:
            htf, last_pos = htf.iloc[:-1], last_pos.iloc[:-1]
    htf.index = htf.index.tz_convert(df.index.tz)
    return htf, last_pos.to_numpy()


def htf_bias(df: pd.DataFrame, rule: str = "1h", params: SwingParams = SwingParams()) -> pd.Series:
    """'up' / 'down' / '' per LTF bar: direction of the latest closed-candle HTF break."""
    htf, last_pos = resample(df, rule)
    bias = pd.Series("", index=df.index, dtype=object)
    if len(htf) < 10:
        return bias
    breaks = structure_breaks(htf, detect_swings(htf, params))
    if breaks.empty:
        return bias
    known_at = last_pos[breaks["bar"].to_numpy()]
    events = pd.Series(breaks["direction"].to_numpy(), index=known_at)
    events = events[~events.index.duplicated(keep="last")]
    arr = np.full(len(df), "", dtype=object)
    arr[events.index.to_numpy()] = events.to_numpy()
    return pd.Series(arr, index=df.index).replace("", np.nan).ffill().fillna("")
