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
