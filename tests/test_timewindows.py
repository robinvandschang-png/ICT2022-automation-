import pandas as pd

from ict.timewindows import KILLZONES, in_windows, window_label, window_mask


def idx(*times_et):
    return pd.DatetimeIndex(list(times_et), tz="America/New_York").tz_convert("UTC")


def test_window_edges_and_midnight():
    i = idx("2026-03-02 08:25", "2026-03-02 08:30", "2026-03-02 10:55", "2026-03-02 11:00",
            "2026-03-02 23:55", "2026-03-03 00:00")
    assert list(window_mask(i, "08:30", "11:00")) == [False, True, True, False, False, False]
    assert list(window_mask(i, "20:00", "00:00")) == [False, False, False, False, True, False]


def test_labels_follow_exchange_time_across_dst():
    # 09:30 ET is 14:30 UTC in winter and 13:30 UTC in summer; both must be NY AM.
    i = pd.DatetimeIndex(["2026-02-02 14:30", "2026-04-01 13:30"], tz="UTC")
    assert list(window_label(i)) == ["NY AM", "NY AM"]


def test_in_windows_union():
    i = idx("2026-03-02 03:00", "2026-03-02 06:00", "2026-03-02 14:00")
    assert list(in_windows(i, ["London", "NY PM"], KILLZONES)) == [True, False, True]
