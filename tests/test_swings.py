import numpy as np
import pandas as pd
import pytest

from ict.swings import HIGH, LOW, SwingParams, detect_swings, raw_pivots, swings_as_of


def candles(points, bars_per_leg=5):
    """Piecewise-linear closes through `points`; open = previous close."""
    closes = [points[0]]
    for a, b in zip(points[:-1], points[1:]):
        closes += list(np.linspace(a, b, bars_per_leg + 1)[1:])
    closes = np.array(closes, dtype=float)
    opens = np.concatenate([[closes[0]], closes[:-1]])
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="5min")
    return pd.DataFrame(
        {"open": opens, "high": np.maximum(opens, closes),
         "low": np.minimum(opens, closes), "close": closes},
        index=idx,
    )


def active(swings):
    s = swings[swings["cancelled"].isna()]
    return list(zip(s["kind"], s["price"].round(6)))


def test_raw_pivots_mark_turning_points():
    df = candles([110, 100, 120, 95, 105])
    p = raw_pivots(df, 2)
    assert list(zip(p["kind"], p["price"])) == [(LOW, 100), (HIGH, 120), (LOW, 95)]
    assert (p["confirmed"] == p["bar"] + 2).all()


def test_atr_filter_removes_small_wiggle_and_higher_high_replaces():
    # Lead-in leg gives the 14-bar ATR time to warm up before the low at 100.
    df = candles([100, 130, 100, 120, 119, 125, 95, 105], bars_per_leg=8)
    unfiltered = detect_swings(df, SwingParams(min_move_atr=0))
    assert active(unfiltered) == [(LOW, 100), (HIGH, 120), (LOW, 119), (HIGH, 125), (LOW, 95)]

    filtered = detect_swings(df, SwingParams(min_move_atr=1.0))
    assert active(filtered) == [(LOW, 100), (HIGH, 125), (LOW, 95)]
    replaced = filtered[filtered["cancelled"].notna()]
    assert list(zip(replaced["kind"], replaced["price"])) == [(HIGH, 120)]


def test_intermediate_high_needs_lower_highs_on_both_sides():
    df = candles([110, 100, 110, 102, 120, 105, 112, 98, 104])
    s = detect_swings(df, SwingParams(atr_period=3, min_move_atr=0))
    tier2 = s[s["tier"] >= 2]
    assert list(zip(tier2["kind"], tier2["price"])) == [(HIGH, 120)]
    # Known only once the lower high at 112 is locked in by the low at 98.
    low_98 = s[(s["kind"] == LOW) & (s["price"] == 98)].iloc[0]
    assert tier2.iloc[0]["t2_confirmed"] == low_98["confirmed"]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_no_lookahead(seed):
    """What the bot knows at bar t must not change when future bars are added."""
    rng = np.random.default_rng(seed)
    n = 1500
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    wick = np.abs(rng.normal(0, 0.0015, (2, n))) * close
    df = pd.DataFrame(
        {"open": open_, "high": np.maximum(open_, close) + wick[0],
         "low": np.minimum(open_, close) - wick[1], "close": close},
        index=pd.date_range("2026-01-01", periods=n, freq="5min"),
    )
    params = SwingParams()
    full = detect_swings(df, params)
    cols = ["bar", "kind", "price"]
    for t in range(60, n, 53):
        part = detect_swings(df.iloc[: t + 1], params)
        for tier in (1, 2, 3):
            a = swings_as_of(full, t, tier)[cols].reset_index(drop=True)
            b = swings_as_of(part, t, tier)[cols].reset_index(drop=True)
            pd.testing.assert_frame_equal(a, b)
