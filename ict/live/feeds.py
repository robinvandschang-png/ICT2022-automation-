"""Candle sources for the screener. Each returns only CLOSED 5m candles, UTC index.

- ReplayFeed: historical CSVs revealed up to a simulated "now" (testing, demos).
- YahooFeed:  free Yahoo Finance futures data via `yfinance` (pip install yfinance).
              CME data on free sources is delayed by at least 10 minutes, and
              Yahoo keeps only recent intraday history. Good for paper alerts;
              swap in a real-time feed (broker / data vendor) before trading live.

A new feed only needs: candles(sym, now) -> DataFrame[open, high, low, close, volume].
"""
from __future__ import annotations

import pandas as pd

from ict.data import load_csv

STEP = pd.Timedelta("5min")


def closed_only(df: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """Drop candles that have not closed yet at `now` (bar start + 5 min > now)."""
    return df[df.index + STEP <= now]


class ReplayFeed:
    def __init__(self, files: dict[str, str]):
        self.data = {sym: load_csv(path) for sym, path in files.items()}

    def candles(self, sym: str, now: pd.Timestamp, days: int = 45) -> pd.DataFrame:
        df = self.data[sym]
        df = df[df.index >= now - pd.Timedelta(days=days)]
        return closed_only(df, now)


class YahooFeed:
    def __init__(self, tickers: dict[str, str], days: int = 45):
        self.tickers, self.days = tickers, days

    def candles(self, sym: str, now: pd.Timestamp | None = None) -> pd.DataFrame:
        import yfinance as yf

        raw = yf.download(self.tickers[sym], period=f"{self.days}d", interval="5m",
                          progress=False, auto_adjust=False, prepost=True, threads=False)
        if raw is None or raw.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = raw.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
        idx = pd.DatetimeIndex(df.index)
        df.index = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        return closed_only(df, now or pd.Timestamp.now(tz="UTC"))
