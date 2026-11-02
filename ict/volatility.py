"""Volatility yardsticks: what counts as a "big" candle or move.

Two options:
- `atr`: Wilder's ATR over the last N candles. Simple, but on intraday
  charts it lags session changes (e.g. the quiet pre-market makes every
  NY-open candle look huge).
- `tod_range`: average true range at the same clock time over the previous
  N sessions. A 09:35 candle is judged against earlier 09:35 candles, so
  "big" means "unusual for this moment of the day".

Both are causal: the value at bar t uses only bars before or at t
(`tod_range` excludes bar t itself).
"""
from __future__ import annotations

import pandas as pd

DEFAULT_TZ = "America/New_York"


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift()
    return pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's Average True Range."""
    return true_range(df).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _clock_key(index: pd.Index, tz: str) -> pd.Index:
    """Clock time used to match bars across sessions (exchange time, so DST is handled)."""
    if isinstance(index, pd.DatetimeIndex) and index.tz is not None:
        index = index.tz_convert(tz)
    return pd.Index(index.strftime("%H:%M"))


def tod_range(df: pd.DataFrame, lookback: int = 20, tz: str = DEFAULT_TZ,
              min_sessions: int = 10) -> pd.Series:
    """Average true range at the same clock time over the previous `lookback` sessions."""
    tr = true_range(df)
    key = _clock_key(df.index, tz)
    return tr.groupby(key.to_numpy()).transform(
        lambda s: s.shift(1).rolling(lookback, min_periods=min_sessions).mean()
    )


def volatility(df: pd.DataFrame, method: str = "tod", atr_period: int = 14,
               lookback: int = 20, tz: str = DEFAULT_TZ) -> pd.Series:
    """Yardstick series. For "tod", bars without enough history fall back to ATR."""
    if method == "atr":
        return atr(df, atr_period)
    if method == "tod":
        return tod_range(df, lookback, tz).fillna(atr(df, atr_period))
    raise ValueError(f"unknown volatility method: {method!r}")
