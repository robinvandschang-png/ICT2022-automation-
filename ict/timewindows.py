"""ICT time windows, in exchange time (America/New_York).

The course text gives no clock times ("confirm them for your instrument"), so
these are the commonly used ICT conventions, kept configurable:

Kill zones
  Asia     20:00-00:00  quiet, usually sets the range
  London   02:00-05:00  first real volume, often the day's manipulation
  NY AM    08:30-11:00  index futures: 08:30 data + 09:30 cash open
  NY PM    13:30-16:00  secondary window

Silver Bullet hours: 03:00-04:00, 10:00-11:00, 14:00-15:00.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TZ = "America/New_York"

KILLZONES = {
    "Asia": ("20:00", "00:00"),
    "London": ("02:00", "05:00"),
    "NY AM": ("08:30", "11:00"),
    "NY PM": ("13:30", "16:00"),
}

SILVER_BULLET = {
    "London SB": ("03:00", "04:00"),
    "NY AM SB": ("10:00", "11:00"),
    "NY PM SB": ("14:00", "15:00"),
}


def _minutes(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def window_mask(index: pd.DatetimeIndex, start: str, end: str, tz: str = TZ) -> np.ndarray:
    """True for bars whose start time is in [start, end). '00:00' as end means midnight."""
    local = index.tz_convert(tz)
    m = local.hour * 60 + local.minute
    s, e = _minutes(start), _minutes(end) or 24 * 60
    return np.asarray((m >= s) & (m < e)) if s < e else np.asarray((m >= s) | (m < e))


def window_label(index: pd.DatetimeIndex, windows: dict = KILLZONES, tz: str = TZ) -> pd.Series:
    """Name of the window each bar falls in ('' if none). Later windows win on overlap."""
    labels = np.full(len(index), "", dtype=object)
    for name, (s, e) in windows.items():
        labels[window_mask(index, s, e, tz)] = name
    return pd.Series(labels, index=index)


def in_windows(index: pd.DatetimeIndex, names, windows: dict = KILLZONES, tz: str = TZ) -> np.ndarray:
    """True for bars inside any of the named windows."""
    mask = np.zeros(len(index), dtype=bool)
    for name in names:
        s, e = windows[name]
        mask |= window_mask(index, s, e, tz)
    return mask
