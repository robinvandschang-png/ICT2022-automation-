"""Defaults decided so far (see docs/decisions.md). One place to change them.

Backtests should vary these explicitly; the live screener uses them as-is.
"""
MARKET = "NQ"                      # E-mini Nasdaq-100 only, for now
SWEEP_TIMEFRAME = "5min"           # sweeps detected on the 5-minute chart

ENTRY = "FVG edge (latest)"        # limit at the near edge of the FVG closest to the break
ENTRY_WAIT_CANDLES = 12            # cancel an unfilled entry after 1 hour on 5m

TARGET_RULE = "strict"             # nearest opposite pool, only if >= MIN_RR away
MIN_RR = 2.0

# Robin trades London open and NY AM most of the time (2026-11-02).
# The screener alerts only in these windows; the backtest compares them with all hours.
SCREENER_KILLZONES = ["London", "NY AM"]

# Robin: a long's entry must be in discount, a short's in premium, of the bigger
# dealing range (latest significant swing high/low), 2026-11-02.
PD_RANGE = "dealing"               # "dealing" | "setup" | None

# Robin reads the trend from 1H structure (2026-11-02): the screener only takes
# setups in the direction of the latest 1H structure break. Research runs keep
# comparing with / without it (no measurable effect on Jan–Apr 2026 yet).
HTF_GATE = "1h"                    # "1h" | "4h" | None

# --- Live screener -------------------------------------------------------------
SCREENER_FEED = "ibkr"             # "ibkr" (real-time via TWS / IB Gateway) | "yahoo" (free, delayed)
IBKR_HOST = "127.0.0.1"
IBKR_PORT = 7497                   # TWS: 7497 paper / 7496 live; IB Gateway: 4002 paper / 4001 live
IBKR_CLIENT_ID = 17

# Markets to scan: symbol -> Yahoo Finance ticker (used by the Yahoo feed;
# the IBKR feed maps the same symbols in ict/live/feeds.py:IB_CONTRACTS).
SCREENER_MARKETS = {
    "NQ": "NQ=F", "ES": "ES=F", "YM": "YM=F", "RTY": "RTY=F",
    "CL": "CL=F", "GC": "GC=F",
    "6E": "6E=F", "6B": "6B=F", "6J": "6J=F",
    "ZN": "ZN=F", "ZB": "ZB=F",
}
ACCOUNT_SIZE = 50_000              # USD, for position sizing in alerts
RISK_PCT = 1.0                     # % of the account risked per trade (book ch. 27)
MAX_COST_R = 0.10                  # flag a signal whose costs exceed this share of 1R
SCAN_AFTER_KILLZONE_MIN = 75       # keep scanning this long after a kill zone ends (CHoCH + FVG can come later)
