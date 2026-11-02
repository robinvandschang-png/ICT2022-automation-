"""Candle sources for the screener. Each returns only CLOSED 5m candles, UTC index.

- ReplayFeed: historical CSVs revealed up to a simulated "now" (testing, demos).
- IBKRFeed:   Interactive Brokers via `ib_async` (pip install ib_async), reading from
              TWS or IB Gateway running on the same computer. Real-time with a
              futures market-data subscription.
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


# Interactive Brokers contract per screener symbol: (IB symbol, exchange, trading class)
IB_CONTRACTS = {
    "NQ": ("NQ", "CME", "NQ"), "ES": ("ES", "CME", "ES"), "YM": ("YM", "CBOT", "YM"),
    "RTY": ("RTY", "CME", "RTY"), "CL": ("CL", "NYMEX", "CL"), "GC": ("GC", "COMEX", "GC"),
    "6E": ("EUR", "CME", "6E"), "6B": ("GBP", "CME", "6B"), "6J": ("JPY", "CME", "6J"),
    "ZN": ("ZN", "CBOT", "ZN"), "ZB": ("ZB", "CBOT", "ZB"),
}


def bars_to_frame(bars) -> pd.DataFrame:
    """ib_async BarData list -> OHLCV frame with a UTC index (bar start times)."""
    rows = [(b.date, b.open, b.high, b.low, b.close, b.volume) for b in bars]
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    if df.empty:
        return df.set_index("time")
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("time"), utc=True)).rename(None)
    return df[~df.index.duplicated(keep="last")].sort_index()


class IBKRFeed:
    """Continuous front-month futures from Interactive Brokers.

    First call per market loads `days` of 5m history; later calls fetch the
    last 2 days and merge, so each 5-minute cycle costs one small request per
    market. Connects read-only: this feed never places orders.
    """

    def __init__(self, markets, host: str = "127.0.0.1", port: int = 7497, client_id: int = 17,
                 days: int = 30, client=None):
        if client is None:
            from ib_async import IB
            client = IB()
            client.connect(host, port, clientId=client_id, readonly=True)
        self.ib, self.days = client, days
        self.markets = list(markets)
        self.cache: dict[str, pd.DataFrame] = {}
        self.contracts: dict = {}

    def contract(self, sym: str):
        if sym not in self.contracts:
            from ib_async import ContFuture
            symbol, exchange, trading_class = IB_CONTRACTS[sym]
            c = ContFuture(symbol=symbol, exchange=exchange, tradingClass=trading_class)
            self.ib.qualifyContracts(c)
            self.contracts[sym] = c
        return self.contracts[sym]

    def _fetch(self, sym: str, duration: str) -> pd.DataFrame:
        bars = self.ib.reqHistoricalData(self.contract(sym), endDateTime="", durationStr=duration,
                                         barSizeSetting="5 mins", whatToShow="TRADES", useRTH=False,
                                         formatDate=2)
        return bars_to_frame(bars or [])

    def candles(self, sym: str, now: pd.Timestamp | None = None) -> pd.DataFrame:
        now = now or pd.Timestamp.now(tz="UTC")
        if sym not in self.cache or self.cache[sym].empty:
            df = pd.DataFrame()
            for duration in (f"{self.days} D", "10 D", "5 D"):   # fall back if a long request is refused
                df = self._fetch(sym, duration)
                if len(df):
                    break
            self.cache[sym] = df
        else:
            new = self._fetch(sym, "2 D")
            if len(new):
                old = self.cache[sym]
                df = pd.concat([old[old.index < new.index[0]], new])
                self.cache[sym] = df[df.index >= now - pd.Timedelta(days=self.days + 5)]
        return closed_only(self.cache[sym], now)
