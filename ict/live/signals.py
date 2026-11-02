"""Turn the latest closed candles of one market into trade signals.

`scan` runs exactly the backtest pipeline (ict.model.build_trades) on the
candles available now and keeps the orders whose placement bar is the latest
closed candle. Because every detector is causal, a live signal is identical to
the order the backtest records at that bar (tested in tests/test_live.py).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from ict.contracts import TICK, cost_in_r, position_size
from ict.model import ModelParams, build_context, build_trades, sweep_choch_sequences
from ict.structure import UP

TZ = "America/New_York"


@dataclass
class Signal:
    sym: str
    direction: str            # "up" (long) / "down" (short)
    killzone: str
    swept: str                # pool that was swept, e.g. "Asia L"
    sweep_time: pd.Timestamp
    signal_time: pd.Timestamp  # close of the candle the signal is based on
    entry: float
    stop: float
    target: float
    target_name: str
    target_rr: float
    expires: pd.Timestamp     # cancel the limit order if not filled by then
    at_market: bool           # price already inside the FVG: enter now
    bias_1h: str
    pos_dealing: float
    cost_r: float
    size: dict

    @property
    def key(self) -> str:
        return f"{self.sym}|{self.sweep_time.isoformat()}|{self.direction}"

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("sweep_time", "signal_time", "expires"):
            d[k] = d[k].isoformat()
        return d


def scan(df: pd.DataFrame, sym: str, params: ModelParams | None = None, recent_bars: int = 1,
         account: float = 50_000, risk_pct: float = 1.0, lookback_seq: int = 60) -> list[Signal]:
    """Signals whose order is placed at one of the last `recent_bars` closed candles of `df`."""
    params = params or ModelParams.from_config()
    if len(df) < 500:
        return []
    ctx = build_context(df)
    last = len(df) - 1
    seqs = sweep_choch_sequences(ctx)
    if seqs.empty:
        return []
    seqs = seqs[seqs["setup_bar"] >= last - lookback_seq].reset_index(drop=True)
    if seqs.empty:
        return []
    trades = build_trades(ctx, params, seqs)
    if trades.empty or "place_bar" not in trades:
        return []
    new = trades[(trades["status"] == "order") & (trades["place_bar"] >= last - recent_bars + 1)]
    step = df.index[-1] - df.index[-2]
    out = []
    for r in new.itertuples(index=False):
        place = int(r.place_bar)
        at_market = r.fill_bar is not None and not pd.isna(r.fill_bar) and int(r.fill_bar) == place
        risk = abs(r.entry - r.stop)
        out.append(Signal(
            sym=sym, direction=r.direction, killzone=r.killzone, swept=r.swept,
            sweep_time=pd.Timestamp(r.time), signal_time=df.index[place] + step,
            entry=float(r.entry), stop=float(r.stop), target=float(r.target), target_name=r.target_name,
            target_rr=float(r.target_rr), expires=df.index[place] + step * (1 + params.wait),
            at_market=bool(at_market), bias_1h=r.bias_1h, pos_dealing=float(r.pos_dealing),
            cost_r=float(cost_in_r(sym, risk)) if sym in TICK else float("nan"),
            size=position_size(sym, risk, account * risk_pct / 100) if sym in TICK else {},
        ))
    return out


def _px(sym: str, x: float) -> str:
    tick = TICK.get(sym, (0.01, 0))[0]
    decimals = max(0, min(7, len(f"{tick:.10f}".rstrip("0").split(".")[1]) if tick < 1 else 0))
    return f"{round(x / tick) * tick:,.{decimals}f}"


def format_signal(s: Signal, max_cost_r: float = 0.10) -> str:
    side = "LONG" if s.direction == UP else "SHORT"
    t = lambda ts: ts.tz_convert(TZ).strftime("%H:%M")
    risk = abs(s.entry - s.stop)
    tick = TICK.get(s.sym, (1, 0))[0]
    entry_line = (f"Entry: MARKET ~{_px(s.sym, s.entry)} (price already in the FVG)" if s.at_market else
                  f"Entry: limit {_px(s.sym, s.entry)} (FVG near edge), cancel if not filled by {t(s.expires)} ET")
    lines = [
        f"{side} {s.sym} — {s.killzone} kill zone",
        f"Swept {s.swept} at {t(s.sweep_time)} ET, CHoCH on displacement, signal at {t(s.signal_time)} ET",
        entry_line,
        f"Stop: {_px(s.sym, s.stop)} ({risk / tick:,.0f} ticks)",
        f"Target: {s.target_name} {_px(s.sym, s.target)} ({s.target_rr:.1f}R)",
    ]
    if s.size:
        lines.append(f"Size: {s.size['contracts']} {s.size['symbol']} "
                     f"(risk ${s.size['risk_usd']:,.0f}; ${s.size['risk_per_contract']:,.0f} per contract)")
    zone = "discount" if s.pos_dealing < 0.5 else "premium"
    lines.append(f"1H trend: {s.bias_1h or 'n/a'} · dealing range: {s.pos_dealing * 100:.0f}% ({zone})")
    if s.cost_r == s.cost_r:
        lines.append(f"Costs ≈ {s.cost_r:.2f}R" + ("  ⚠ above limit — consider skipping" if s.cost_r > max_cost_r else ""))
    return "\n".join(lines)
