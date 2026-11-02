import pandas as pd
import pytest

from ict.contracts import position_size
from ict.live.signals import format_signal, scan
from ict.model import ModelParams, build_context, build_trades
from tests.test_model import ctx  # noqa: F401  (shared synthetic market fixture)

PARAMS = ModelParams(pd_gate=None, killzones=None, htf_gate=None)   # loose, so the fixture yields trades


def test_live_signal_equals_backtest_order(ctx):  # noqa: F811
    """Replaying candles one by one must produce each backtest order exactly at its bar."""
    df = ctx.df
    orders = build_trades(ctx, PARAMS)
    orders = orders[orders["status"] == "order"]
    assert len(orders) >= 3
    for r in orders.head(6).itertuples(index=False):
        p = int(r.place_bar)
        live = scan(df.iloc[: p + 1], "NQ", PARAMS, lookback_seq=200)
        match = [s for s in live if s.sweep_time == pd.Timestamp(r.time)]
        assert len(match) == 1, f"order at bar {p} not reproduced live"
        s = match[0]
        assert s.direction == r.direction
        assert (s.entry, s.stop, s.target) == pytest.approx((r.entry, r.stop, r.target))
        before = scan(df.iloc[:p], "NQ", PARAMS, lookback_seq=200)
        assert not [x for x in before if x.sweep_time == pd.Timestamp(r.time)], "signal appeared too early"


def test_position_size_full_and_micro():
    big = position_size("NQ", risk_pts=20, risk_usd=1000)        # $400 per NQ
    assert big == {"symbol": "NQ", "contracts": 2, "risk_usd": 800.0, "risk_per_contract": 400.0}
    small = position_size("NQ", risk_pts=100, risk_usd=500)      # $2,000 per NQ -> micros at $200
    assert small["symbol"] == "MNQ" and small["contracts"] == 2


def test_message_has_the_trade(ctx):  # noqa: F811
    orders = build_trades(ctx, PARAMS)
    p = int(orders[orders["status"] == "order"].iloc[0]["place_bar"])
    s = scan(ctx.df.iloc[: p + 1], "NQ", PARAMS, lookback_seq=200)[0]
    msg = format_signal(s)
    for part in ("NQ", "Entry", "Stop", "Target", "Size", "1H trend"):
        assert part in msg


def test_scanning_window_covers_killzones_plus_grace():
    from ict.live.screener import scanning_now
    et = lambda s: pd.Timestamp(s, tz="America/New_York").tz_convert("UTC")
    assert scanning_now(et("2026-04-10 02:00"), ["London"], 75)
    assert scanning_now(et("2026-04-10 06:10"), ["London"], 75)      # within 75 min after 05:00
    assert not scanning_now(et("2026-04-10 06:20"), ["London"], 75)
    assert scanning_now(et("2026-04-10 09:00"), ["NY AM"], 75)
    assert not scanning_now(et("2026-04-10 13:00"), ["London", "NY AM"], 75)


def test_closed_only_drops_forming_candle():
    from ict.live.feeds import closed_only
    idx = pd.date_range("2026-04-10 08:00", periods=3, freq="5min", tz="UTC")
    df = pd.DataFrame({"close": [1, 2, 3]}, index=idx)
    assert len(closed_only(df, pd.Timestamp("2026-04-10 08:12", tz="UTC"))) == 2


class FakeIB:
    """Stands in for ib_async.IB: serves 5m bars from a frame, as of a moving 'now'."""

    def __init__(self, df):
        self.df, self.now, self.requests = df, None, []

    def qualifyContracts(self, *c):
        return c

    def reqHistoricalData(self, contract, endDateTime, durationStr, barSizeSetting, whatToShow, useRTH, formatDate):
        from types import SimpleNamespace
        self.requests.append(durationStr)
        days = int(durationStr.split()[0])
        part = self.df[(self.df.index >= self.now - pd.Timedelta(days=days)) & (self.df.index < self.now)]
        return [SimpleNamespace(date=t.to_pydatetime(), open=r.open, high=r.high, low=r.low, close=r.close,
                                volume=r.volume) for t, r in part.iterrows()]


def test_ibkr_feed_loads_history_then_merges_updates(ctx, monkeypatch):  # noqa: F811
    import sys
    from types import SimpleNamespace
    from ict.live.feeds import IB_CONTRACTS, IBKRFeed
    monkeypatch.setitem(sys.modules, "ib_async", SimpleNamespace(ContFuture=lambda **k: SimpleNamespace(**k)))
    df = ctx.df.assign(volume=1.0)
    ib = FakeIB(df)
    feed = IBKRFeed(["NQ"], client=ib, days=10)
    ib.now = df.index[4000] + pd.Timedelta("2min")              # mid-candle: last candle still forming
    first = feed.candles("NQ", ib.now)
    assert first.index[-1] == df.index[3999] and ib.requests == ["10 D"]
    ib.now = df.index[4100] + pd.Timedelta("1min")
    later = feed.candles("NQ", ib.now)
    assert ib.requests[-1] == "2 D"
    expected = df[(df.index >= later.index[0]) & (df.index <= df.index[4099])]
    pd.testing.assert_frame_equal(later[["open", "high", "low", "close"]], expected[["open", "high", "low", "close"]],
                                  check_freq=False)
    assert set(IB_CONTRACTS) >= {"NQ", "ES", "YM", "RTY", "CL", "GC", "6E", "6B", "6J", "ZN", "ZB"}
