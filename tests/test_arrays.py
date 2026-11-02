import pandas as pd
import pytest

from ict.arrays import leg_fvgs, leg_order_block, overlaps
from ict.structure import DOWN, UP


def bars(rows):
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                      index=pd.date_range("2026-01-01", periods=len(rows), freq="5min", tz="UTC"))
    return df, pd.Series(1.0, index=df.index)


BULL = [
    (10.0, 10.1, 9.4, 9.6),   # 0 down candle, before the leg
    (9.6, 9.7, 9.0, 9.2),     # 1 down candle at the sweep low  -> order block
    (9.2, 10.6, 9.1, 10.5),   # 2 first big up candle; candle 3 low 10.4 > candle 1 high 9.7 -> FVG 0.7
    (10.5, 12.1, 10.4, 12.0), # 3 big up; candle 4 low 11.9 > candle 2 high 10.6 -> FVG 1.3
    (12.0, 13.6, 11.9, 13.5), # 4 breaking candle; candle 5 low 13.2 > 12.1 -> FVG 1.1
    (13.5, 13.7, 13.2, 13.4), # 5
]


def test_bullish_fvgs_and_order_block():
    df, vol = bars(BULL)
    gaps = leg_fvgs(df, vol, start=1, end=4, direction=UP)
    assert [g["middle_bar"] for g in gaps] == [2, 3, 4]
    g = gaps[1]
    assert (g["bottom"], g["top"], g["proximal"]) == (10.6, 11.9, 11.9)
    assert g["ce"] == pytest.approx(11.25) and g["known_at"] == 4
    ob = leg_order_block(df, vol, start=1, end=4, direction=UP)
    assert ob["bar"] == 1 and ob["proximal"] == 9.7 and ob["mean"] == pytest.approx(9.4)
    assert overlaps(gaps[0], ob) and not overlaps(g, ob)   # first gap starts at the OB high


def test_bearish_mirror():
    df, vol = bars([(o * -1, l * -1, h * -1, c * -1) for o, h, l, c in BULL])
    gaps = leg_fvgs(df, vol, start=1, end=4, direction=DOWN)
    assert [g["middle_bar"] for g in gaps] == [2, 3, 4]
    assert gaps[1]["proximal"] == -11.9          # bottom edge is met first on a retrace up
    ob = leg_order_block(df, vol, start=1, end=4, direction=DOWN)
    assert ob["bar"] == 1 and ob["proximal"] == -9.7


def test_small_gaps_ignored_and_no_ob_when_no_opposing_candle():
    df, vol = bars([(9.0, 9.6, 8.9, 9.5), (9.5, 10.6, 9.4, 10.5), (10.5, 10.9, 9.5, 10.8)])   # candle 2 dips back below candle 0's high
    assert leg_fvgs(df, vol, start=0, end=1, direction=UP, min_size=0.3) == []
    assert leg_order_block(df, vol, start=0, end=1, direction=UP) is None
