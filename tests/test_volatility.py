import numpy as np
import pandas as pd

from ict.volatility import atr, tod_range, volatility


def intraday(days=30, seed=0):
    """5m bars, 24h a day, with a volatile 09:30-10:00 ET window."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-05", periods=days * 288, freq="5min", tz="America/New_York")
    hot = (idx.hour == 9) & (idx.minute >= 30)
    step = rng.normal(0, 1, len(idx)) * np.where(hot, 5.0, 1.0)
    close = 1000 + np.cumsum(step)
    open_ = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame(
        {"open": open_, "high": np.maximum(open_, close) + 0.1,
         "low": np.minimum(open_, close) - 0.1, "close": close},
        index=idx,
    )


def test_tod_range_uses_only_previous_sessions():
    df = intraday()
    full = tod_range(df)
    for t in [3000, 5000, 8000]:
        part = tod_range(df.iloc[: t + 1])
        pd.testing.assert_series_equal(full.iloc[: t + 1], part, check_names=False)


def test_tod_range_matches_same_clock_time():
    df = intraday()
    v = tod_range(df)
    last_day = v.loc["2026-02-03"]
    open_window = last_day.between_time("09:30", "09:55")
    quiet = last_day.between_time("03:00", "04:00")
    # The open is ~5x more volatile in the data; the yardstick should know that.
    assert open_window.mean() > 3 * quiet.mean()
    # Plain ATR at the first open candle still reflects the quiet pre-market.
    a = atr(df).loc["2026-02-03 09:30"]
    assert a < 0.5 * open_window.iloc[0]


def test_volatility_falls_back_to_atr_during_warmup():
    df = intraday(days=12)
    v = volatility(df, "tod")
    assert v.iloc[20:].notna().all()
