import numpy as np
import pandas as pd
import pytest

from ict.htf import htf_bias, resample


def five_min(days=40, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-04 18:00", periods=days * 276, freq="5min", tz="America/New_York")
    close = 20000 + np.cumsum(rng.standard_t(3, len(idx)) * 4.0)
    open_ = np.concatenate([[close[0]], close[:-1]])
    wick = np.abs(rng.normal(0, 3, (2, len(idx))))
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + wick[0],
                         "low": np.minimum(open_, close) - wick[1], "close": close,
                         "volume": 1.0}, index=idx).tz_convert("UTC")


def test_resample_aligns_4h_to_cme_day_and_maps_last_bar():
    df = five_min(days=3)
    h4, last = resample(df, "4h")
    starts = set(h4.index.tz_convert("America/New_York").hour)
    assert starts <= {18, 22, 2, 6, 10, 14}
    k = 0
    span = df.loc[h4.index[k]: h4.index[k] + pd.Timedelta("4h") - pd.Timedelta("1ns")]
    assert h4["high"].iloc[k] == span["high"].max()
    assert df.index[last[k]] == span.index[-1]


def test_incomplete_last_candle_is_dropped():
    df = five_min(days=2)
    cut = df.iloc[: len(df) - 5]                      # ends mid-hour
    h1_full, _ = resample(df, "1h")
    h1_cut, _ = resample(cut, "1h")
    assert len(h1_cut) == len(h1_full) - 1
    assert h1_cut.index[-1] == h1_full.index[-2]


@pytest.mark.parametrize("rule", ["1h", "4h"])
def test_bias_no_lookahead(rule):
    df = five_min(days=40)
    full = htf_bias(df, rule)
    assert set(full.unique()) <= {"", "up", "down"} and (full != "").any()
    for t in range(3000, len(df), 1777):
        part = htf_bias(df.iloc[: t + 1], rule)
        pd.testing.assert_series_equal(full.iloc[: t + 1], part, check_names=False)
