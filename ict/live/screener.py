"""The live screener: every 5 minutes, scan each market and alert on new signals.

Live (free Yahoo data, ~10+ min delayed):
    pip install yfinance
    python -m ict.live.screener

Replay a past period with local CSVs (no network):
    python -m ict.live.screener --replay data/cme --start "2026-04-10 01:30" --end "2026-04-10 12:30"

Scanning runs only during the kill zones (config.SCREENER_KILLZONES) and up to
config.SCAN_AFTER_KILLZONE_MIN minutes after each ends, because the CHoCH and
FVG can form after the sweep. Sent signals are remembered in a state file so
nothing is alerted twice.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import time
import traceback

import pandas as pd

from ict import config
from ict.live.feeds import ReplayFeed, YahooFeed
from ict.live.notify import from_env
from ict.live.signals import format_signal, scan
from ict.model import ModelParams
from ict.timewindows import KILLZONES

TZ = "America/New_York"
STEP = pd.Timedelta("5min")


def scanning_now(now: pd.Timestamp, killzones=None, after_min: int | None = None) -> bool:
    killzones = killzones or config.SCREENER_KILLZONES
    after = pd.Timedelta(minutes=config.SCAN_AFTER_KILLZONE_MIN if after_min is None else after_min)
    local = now.tz_convert(TZ)
    for name in killzones:
        s, e = KILLZONES[name]
        day = local.normalize()
        start = day + pd.Timedelta(hours=int(s[:2]), minutes=int(s[3:]))
        end = day + pd.Timedelta(hours=int(e[:2]), minutes=int(e[3:]))
        if end <= start:
            end += pd.Timedelta(days=1)
        for shift in (pd.Timedelta(0), pd.Timedelta(days=-1)):
            if start + shift <= local < end + shift + after:
                return True
    return False


class State:
    def __init__(self, path: str):
        self.path = path
        self.sent = set(json.load(open(path))) if os.path.exists(path) else set()

    def add(self, key: str) -> None:
        self.sent.add(key)
        with open(self.path, "w") as f:
            json.dump(sorted(self.sent), f)


def scan_once(feed, markets, now, params, notifiers, state, log=None) -> list:
    sent = []
    for sym in markets:
        try:
            df = feed.candles(sym, now)
            for s in scan(df, sym, params, recent_bars=1, account=config.ACCOUNT_SIZE, risk_pct=config.RISK_PCT):
                if s.key in state.sent:
                    continue
                text = format_signal(s, config.MAX_COST_R)
                for n in notifiers:
                    n.send(text)
                state.add(s.key)
                sent.append(s)
                if log:
                    with open(log, "a") as f:
                        f.write(json.dumps(s.to_dict()) + "\n")
        except Exception:  # one bad market must not stop the others
            traceback.print_exc()
    return sent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", help="folder of <SYM>_5min.csv files to replay instead of live data")
    ap.add_argument("--start", help="replay start, ET (e.g. '2026-04-10 01:30')")
    ap.add_argument("--end", help="replay end, ET")
    ap.add_argument("--markets", nargs="*", help="symbols to scan (default: config.SCREENER_MARKETS)")
    ap.add_argument("--state", default="out/screener_state.json")
    ap.add_argument("--log", default="out/signals.jsonl")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.state) or ".", exist_ok=True)

    params = ModelParams.from_config()
    markets = a.markets or list(config.SCREENER_MARKETS)
    notifiers = from_env()

    if a.replay:
        files = {s: f for s in markets for f in glob.glob(f"{a.replay}/{s}_5min*.csv")[:1]}
        feed = ReplayFeed(files)
        state = State(a.state + ".replay")
        state.sent.clear()
        now = pd.Timestamp(a.start, tz=TZ).tz_convert("UTC")
        end = pd.Timestamp(a.end, tz=TZ).tz_convert("UTC")
        n = 0
        while now <= end:
            if scanning_now(now):
                n += len(scan_once(feed, list(files), now, params, notifiers, state, log=a.log + ".replay"))
            now += STEP
        print(f"Replay done: {n} signals.")
        return

    feed = YahooFeed(config.SCREENER_MARKETS)
    state = State(a.state)
    print(f"Screener running on {len(markets)} markets; kill zones {config.SCREENER_KILLZONES}. Ctrl+C to stop.")
    while True:
        now = pd.Timestamp.now(tz="UTC")
        if scanning_now(now):
            scan_once(feed, markets, now, params, notifiers, state, log=a.log)
        nxt = now.floor("5min") + STEP + pd.Timedelta(seconds=20)   # just after the next candle close
        time.sleep(max(5.0, (nxt - pd.Timestamp.now(tz="UTC")).total_seconds()))


if __name__ == "__main__":
    main()
