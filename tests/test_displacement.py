import pandas as pd
import pytest

from ict.displacement import DisplacementParams, measure_leg, passes
from ict.structure import DOWN, UP


def bars(rows):
    """rows of (open, high, low, close); yardstick fixed at 1.0."""
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                      index=pd.date_range("2026-01-01", periods=len(rows), freq="5min"))
    return df, pd.Series(1.0, index=df.index)


def test_clean_impulse_passes_with_fvg():
    df, vol = bars([
        (10.0, 10.2, 9.0, 9.1),   # leg extreme (low 9.0)
        (9.1, 10.6, 9.0, 10.5),   # strong candle
        (10.5, 12.1, 10.4, 12.0), # strong candle; low 10.4 > high 10.2 two back = FVG 0.2 (too small)
        (12.0, 13.6, 11.9, 13.5), # breaking candle; low 11.9 > 10.6 = FVG 1.3
        (13.5, 13.7, 13.2, 13.4), # low 13.2 > 12.1 = FVG 1.1 around the breaking candle
    ])
    m = measure_leg(df, vol, start=0, end=3, direction=UP)
    assert m["leg"] == pytest.approx(13.5 - 9.0)
    assert m["big_body"] == pytest.approx(1.5)
    assert m["efficiency"] == pytest.approx(4.5 / (1.2 + 1.6 + 1.7 + 1.7))
    assert m["fvg_count"] == 2 and m["max_fvg"] == pytest.approx(1.3)
    assert m["fvg_known_at"] == 4  # the gap around the breaking candle needs the next candle
    assert passes(m, DisplacementParams())


def test_choppy_leg_fails_on_overlap():
    df, vol = bars([
        (10.0, 10.1, 9.0, 9.2),
        (9.2, 10.4, 9.1, 10.2),
        (10.2, 10.3, 9.3, 9.5),
        (9.5, 10.6, 9.4, 10.4),
        (10.4, 10.5, 9.6, 9.8),
        (9.8, 11.0, 9.7, 10.9),
    ])
    m = measure_leg(df, vol, start=0, end=5, direction=UP)
    assert m["leg"] >= 1.5 and m["big_body"] >= 1.0
    assert m["efficiency"] < 0.5
    assert not passes(m, DisplacementParams())


def test_require_fvg_switch():
    df, vol = bars([
        (13.0, 13.1, 11.9, 12.0),
        (12.0, 12.1, 10.4, 10.5),
        (10.5, 12.0, 9.4, 9.5),   # overlaps candle 0's low -> no bearish FVG
        (9.5, 10.5, 9.3, 9.4),    # reaches back above candle 1's low -> no gap either
    ])
    m = measure_leg(df, vol, start=0, end=2, direction=DOWN)
    assert m["fvg_count"] == 0
    assert passes(m, DisplacementParams())
    assert not passes(m, DisplacementParams(require_fvg=True))
