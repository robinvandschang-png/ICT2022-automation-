import numpy as np
import pandas as pd

from ict.liquidity import BUY, SELL, classify_takes, fixed_pools, pool_takes, take_features, trading_day


def three_days(seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-03-02 18:00", "2026-03-05 16:55", freq="5min", tz="America/New_York")
    idx = idx[~((idx.hour == 17))]  # CME maintenance hour
    close = 20000 + np.cumsum(rng.normal(0, 5, len(idx)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    df = pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + 2,
                       "low": np.minimum(open_, close) - 2, "close": close}, index=idx)
    return df.tz_convert("UTC")


def test_trading_day_starts_at_18_et():
    idx = pd.DatetimeIndex(["2026-03-02 17:55", "2026-03-02 18:00"], tz="America/New_York")
    d = trading_day(idx)
    assert str(d.iloc[0].date()) == "2026-03-02" and str(d.iloc[1].date()) == "2026-03-03"


def test_previous_day_high_low():
    df = three_days()
    pools = fixed_pools(df)
    day = trading_day(df.index)
    first = day.unique()[0]
    pdh = pools[pools["name"] == "PDH"].iloc[0]
    assert pdh["price"] == df["high"][(day == first).to_numpy()].max()
    assert day.iloc[pdh["active_from"]] != first          # active only from the next day
    assert day.iloc[pdh["active_from"] - 1] == first


def test_session_pool_expires_end_of_day():
    df = three_days()
    asia = fixed_pools(df).query("name == 'Asia H'").iloc[0]
    local = df.index.tz_convert("America/New_York")
    assert local[asia["active_from"]].hour == 0
    assert trading_day(df.index).iloc[asia["expires"]] == trading_day(df.index).iloc[asia["active_from"]]


def bars(rows):
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                      index=pd.date_range("2026-01-01", periods=len(rows), freq="5min", tz="UTC"))
    return df, pd.Series(1.0, index=df.index)


def test_take_and_features_close_back_same_candle():
    df, vol = bars([(9, 9.5, 8.5, 9), (9, 10.6, 8.8, 9.6), (9.6, 9.8, 9.0, 9.2)])
    pools = pd.DataFrame({"name": ["X"], "side": [BUY], "price": [10.0], "formed_bar": [0],
                          "active_from": [0], "expires": pd.array([pd.NA], dtype="Int64")})
    f = take_features(df, pool_takes(df, pools), vol).iloc[0]
    assert f["taken_bar"] == 1 and not f["closed_beyond"]
    assert f["reclaim_bars"] == 0 and abs(f["depth"] - 0.6) < 1e-9


def test_features_closed_beyond_then_reclaimed():
    df, vol = bars([(11, 11.2, 10.5, 10.8), (10.8, 10.9, 9.2, 9.4),   # closes below 10
                    (9.4, 9.6, 8.9, 9.5), (9.5, 10.6, 9.4, 10.4)])    # back above on candle 2 after
    pools = pd.DataFrame({"name": ["Y"], "side": [SELL], "price": [10.0], "formed_bar": [0],
                          "active_from": [1], "expires": pd.array([pd.NA], dtype="Int64")})
    f = take_features(df, pool_takes(df, pools), vol).iloc[0]
    assert f["closed_beyond"] and f["reclaim_bars"] == 2
    assert abs(f["depth"] - 1.1) < 1e-9


def test_classify_takes():
    f = pd.DataFrame({
        "taken_bar": pd.array([10, 20, 30, 40], dtype="Int64"),
        "reclaim_bars": pd.array([0, 2, 5, pd.NA], dtype="Int64"),
        "depth": [0.2, 0.7, 0.5, 3.0],
    })
    c = classify_takes(f)
    assert list(c["sweep"]) == [True, True, False, False]
    assert list(c["decided_at"]) == [10, 22, 33, 43]
    deep = classify_takes(pd.DataFrame({"taken_bar": pd.array([5], dtype="Int64"),
                                        "reclaim_bars": pd.array([1], dtype="Int64"), "depth": [1.4]}))
    assert not deep["sweep"].iloc[0]


def test_extreme_is_furthest_price_beyond_level():
    df, vol = bars([(11, 11.2, 10.5, 10.8), (10.8, 10.9, 9.2, 9.4),
                    (9.4, 9.6, 8.9, 9.5), (9.5, 10.6, 9.4, 10.4)])
    pools = pd.DataFrame({"name": ["Y"], "side": [SELL], "price": [10.0], "formed_bar": [0],
                          "active_from": [1], "expires": pd.array([pd.NA], dtype="Int64")})
    f = take_features(df, pool_takes(df, pools), vol).iloc[0]
    assert abs(f["extreme"] - 8.9) < 1e-9
