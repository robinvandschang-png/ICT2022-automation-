"""Check the Interactive Brokers connection before running the screener.

Run on the computer where TWS or IB Gateway is running and logged in:
    pip install ib_async
    python -m ict.live.check_ibkr                 # uses host/port from ict/config.py
    python -m ict.live.check_ibkr --port 4001     # e.g. IB Gateway, live account

For each market it prints the contract IB resolved, how many 5m candles came
back, the last closed candle and how old it is. Real-time data shows an age of
a few minutes at most; ~10+ minutes means delayed data (no subscription).
Paste the output back into the chat if anything looks wrong.
"""
from __future__ import annotations

import argparse

import pandas as pd

from ict import config
from ict.live.feeds import IB_CONTRACTS, IBKRFeed

TZ = "America/New_York"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=config.IBKR_HOST)
    ap.add_argument("--port", type=int, default=config.IBKR_PORT)
    ap.add_argument("--client-id", type=int, default=config.IBKR_CLIENT_ID + 1)
    ap.add_argument("--markets", nargs="*", default=list(config.SCREENER_MARKETS))
    a = ap.parse_args()

    try:
        feed = IBKRFeed(a.markets, a.host, a.port, a.client_id, days=5)
    except Exception as e:
        print(f"Could not connect to {a.host}:{a.port} — {type(e).__name__}: {e}")
        print("Check: TWS / IB Gateway is running and logged in; API enabled "
              "(Configure > API > Settings > 'Enable ActiveX and Socket Clients'); the port matches.")
        return
    print(f"Connected to {a.host}:{a.port}\n")
    now = pd.Timestamp.now(tz="UTC")
    print(f"{'market':<7}{'IB contract':<14}{'candles':>8}  {'last closed candle (ET)':<24}{'age':>8}  note")
    for sym in a.markets:
        if sym not in IB_CONTRACTS:
            print(f"{sym:<7}{'—':<14}{'':>8}  {'':<24}{'':>8}  no IB mapping in feeds.IB_CONTRACTS")
            continue
        try:
            df = feed.candles(sym, now)
            c = feed.contract(sym)
            local = getattr(c, "localSymbol", "") or getattr(c, "symbol", "")
            if df.empty:
                print(f"{sym:<7}{local:<14}{0:>8}  {'':<24}{'':>8}  no data — market-data subscription or permissions?")
                continue
            last = df.index[-1]
            age = (now - (last + pd.Timedelta('5min'))).total_seconds() / 60
            note = "real-time" if age < 6 else ("delayed?" if age < 30 else "stale — market closed or no live data")
            print(f"{sym:<7}{local:<14}{len(df):>8}  {last.tz_convert(TZ):%Y-%m-%d %H:%M}        {age:>6.1f}m  {note}")
        except Exception as e:
            print(f"{sym:<7}{'':<14}{'':>8}  {'':<24}{'':>8}  error: {type(e).__name__}: {e}")
    feed.ib.disconnect()


if __name__ == "__main__":
    main()
