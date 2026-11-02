"""Loading candle data."""
from __future__ import annotations

import pandas as pd

SESSIONS_ET = {
    "Asia": ("20:00", "00:00"),
    "London": ("02:00", "05:00"),
    "NY open": ("09:30", "10:00"),
    "NY AM": ("10:00", "11:00"),
    "NY PM": ("13:30", "16:00"),
}


def load_csv(path: str, source_tz: str = "UTC") -> pd.DataFrame:
    """CSV with a time column first, then open/high/low/close[/volume].

    Returns a tz-aware index (timestamps are interpreted in `source_tz`).
    """
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    time_col = df.columns[0]
    idx = pd.DatetimeIndex(pd.to_datetime(df.pop(time_col)))
    if idx.tz is None:
        idx = idx.tz_localize(source_tz)
    df.index = idx
    return df.sort_index()


def session_of(index: pd.DatetimeIndex, tz: str = "America/New_York") -> pd.Series:
    """Label each bar with its session (ET windows above), or 'other'."""
    local = index.tz_convert(tz)
    minutes = local.hour * 60 + local.minute
    labels = pd.Series("other", index=index)
    for name, (start, end) in SESSIONS_ET.items():
        s = int(start[:2]) * 60 + int(start[3:])
        e = int(end[:2]) * 60 + int(end[3:]) or 24 * 60
        labels[(minutes >= s) & (minutes < e)] = name
    return labels
