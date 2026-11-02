import pandas as pd

from ict.draw import find_target, pools_as_of
from ict.liquidity import BUY, SELL
from ict.structure import DOWN, UP


def pools():
    return pd.DataFrame({
        "name": ["Asia H", "PDH", "PWH", "PDL", "old high"],
        "side": [BUY, BUY, BUY, SELL, BUY],
        "price": [105.0, 112.0, 130.0, 90.0, 120.0],
        "formed_bar": [0, 0, 0, 0, 0],
        "active_from": [5, 5, 5, 5, 50],          # "old high" not active yet at t=20
        "expires": pd.array([30, pd.NA, pd.NA, pd.NA, pd.NA], dtype="Int64"),
        "taken_bar": pd.array([pd.NA, pd.NA, 15, pd.NA, pd.NA], dtype="Int64"),  # PWH taken at 15
    })


def test_pools_as_of():
    now = pools_as_of(pools(), 20)
    assert set(now["name"]) == {"Asia H", "PDH", "PDL"}
    assert "Asia H" not in set(pools_as_of(pools(), 31)["name"])  # expired


def test_nearest_pool_beyond_min_rr_and_skipped_count():
    now = pools_as_of(pools(), 20)
    t = find_target(now, UP, entry=100.0, stop=97.0, min_rr=2.0)   # risk 3
    assert t["target_name"] == "PDH" and t["target_rr"] == 4.0
    assert t["pools_between"] == 1 and round(t["nearest_rr"], 2) == 1.67  # Asia H skipped


def test_no_target_means_no_trade():
    now = pools_as_of(pools(), 20)
    assert find_target(now, UP, entry=100.0, stop=90.0, min_rr=2.0) is None  # PDH only 1.2R
    assert find_target(now, DOWN, entry=100.0, stop=103.0, min_rr=4.0) is None  # PDL 3.3R
    assert find_target(now, DOWN, entry=100.0, stop=103.0, min_rr=2.0)["target_name"] == "PDL"
