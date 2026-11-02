import pandas as pd

from ict.premium_discount import in_correct_half, position, setup_range
from ict.structure import DOWN, UP


def test_position_and_halves():
    assert position(25, 0, 100) == 0.25
    assert in_correct_half(0.25, UP) and not in_correct_half(0.25, DOWN)
    assert in_correct_half(0.75, DOWN) and not in_correct_half(0.75, UP)


def test_setup_range_uses_bars_from_sweep_to_now():
    df = pd.DataFrame({"high": [10, 12, 9, 15, 20], "low": [8, 7, 6, 11, 14],
                       "open": 0, "close": 0})
    assert setup_range(df, sweep_bar=1, upto=3, direction=UP) == (6, 15)   # bar 4 not yet known
