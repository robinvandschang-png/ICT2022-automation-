import numpy as np
import pandas as pd
import pytest

from ict.structure import DOWN, UP, structure_breaks
from ict.swings import SwingParams, detect_swings
from tests.test_swings import candles

FAST = SwingParams(atr_period=3, min_move_atr=0, vol_method="atr")


def test_breaks_and_leg_starts():
    df = candles([110, 100, 120, 105, 130, 90, 95])
    b = structure_breaks(df, detect_swings(df, FAST))
    got = list(zip(b["direction"], b["swing_price"], b["leg_start_price"]))
    assert got == [(UP, 120, 105), (DOWN, 105, 130)]


def test_each_swing_breaks_once_and_after_confirmation():
    df = candles([110, 100, 120, 105, 130, 90, 95])
    swings = detect_swings(df, FAST)
    b = structure_breaks(df, swings)
    assert b["swing_bar"].is_unique
    conf = swings.set_index("bar")["confirmed"]
    assert (b["bar"] > conf.loc[b["swing_bar"]].to_numpy()).all()


@pytest.mark.parametrize("seed", [4, 5])
def test_breaks_no_lookahead(seed):
    rng = np.random.default_rng(seed)
    n = 1200
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    wick = np.abs(rng.normal(0, 0.0015, (2, n))) * close
    df = pd.DataFrame(
        {"open": open_, "high": np.maximum(open_, close) + wick[0],
         "low": np.minimum(open_, close) - wick[1], "close": close},
        index=pd.date_range("2026-01-01", periods=n, freq="5min"),
    )
    full = structure_breaks(df, detect_swings(df))
    for t in range(100, n, 97):
        part_df = df.iloc[: t + 1]
        part = structure_breaks(part_df, detect_swings(part_df))
        a = full[full["bar"] <= t].drop(columns="time").reset_index(drop=True)
        b = part.drop(columns="time").reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b)
