import numpy as np
import pandas as pd
import pytest

from ict.model import ModelParams, build_context, build_trades, summarize
from ict.premium_discount import in_correct_half
from ict.structure import UP


@pytest.fixture(scope="module")
def ctx():
    """30 days of 24h 5m bars with fat-tailed moves, so sweeps and breaks occur."""
    rng = np.random.default_rng(42)
    idx = pd.date_range("2026-01-05 00:00", periods=30 * 288, freq="5min", tz="America/New_York")
    step = rng.standard_t(3, len(idx)) * 4.0
    close = 20000 + np.cumsum(step)
    open_ = np.concatenate([[close[0]], close[:-1]])
    wick = np.abs(rng.normal(0, 3, (2, len(idx))))
    df = pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + wick[0],
                       "low": np.minimum(open_, close) - wick[1], "close": close}, index=idx)
    return build_context(df.tz_convert("UTC"))


def test_trades_have_valid_geometry(ctx):
    t = build_trades(ctx, ModelParams(pd_gate=None))
    assert len(t) > 0
    o = t[t["status"] == "order"]
    assert len(o) > 0
    up = o["direction"] == UP
    assert (o.loc[up, "entry"] > o.loc[up, "stop"]).all() and (o.loc[up, "target"] > o.loc[up, "entry"]).all()
    assert (o.loc[~up, "entry"] < o.loc[~up, "stop"]).all() and (o.loc[~up, "target"] < o.loc[~up, "entry"]).all()
    assert (o["target_rr"] >= 2.0).all()


def test_pd_gate_only_passes_correct_half(ctx):
    t = build_trades(ctx, ModelParams(pd_gate="dealing"))
    o = t[t["status"] == "order"]
    assert all(in_correct_half(p, d) for p, d in zip(o["pos_dealing"], o["direction"]))
    w = t[t["status"] == "wrong half"]
    assert not any(in_correct_half(p, d) for p, d in zip(w["pos_dealing"], w["direction"]))


def test_killzone_gate_and_summary(ctx):
    t = build_trades(ctx, ModelParams(killzones=("NY AM",), pd_gate=None))
    assert set(t.loc[t["status"] != "outside kill zones", "killzone"]) <= {"NY AM"}
    s = summarize(t)
    assert s["sequences"] == len(t) and s["filled"] <= s["orders"]


def test_from_config_matches_decisions():
    p = ModelParams.from_config()
    assert p.entry == "FVG edge (latest)" and p.target_rule == "strict" and p.min_rr == 2.0
    assert p.pd_gate == "dealing" and p.killzones == ("London", "NY AM")
