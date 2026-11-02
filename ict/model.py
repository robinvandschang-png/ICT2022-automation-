"""The v1 model: sweep -> CHoCH on displacement -> FVG entry -> P/D gate -> target -> trade.

- `build_context`: every detector run once over a candle series.
- `sweep_choch_sequences`: each sweep followed by a displacement break in the
  reversal direction within `window` candles. Stop = beyond the furthest
  price since the take, plus `buffer` yardsticks. Records the sweep's kill zone.
- `entry_options`: entry price and placement bar for each entry style.
- `build_trades`: applies the gates in order and simulates each trade
  (`ModelParams`, defaults from ict/config.py).
- `simulate_trade`: limit order at `entry`, then stop vs target, within the
  trading day. Conservative on ambiguity: a candle that touches both the stop
  and the target counts as a stop; the fill candle cannot also hit the target.

Costs are applied in the research tools (ict/contracts.py). A daily-draw bias is not built.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ict.displacement import DisplacementParams, evaluate_breaks
from ict.liquidity import SELL, classify_takes, fixed_pools, pool_takes, swing_pools, take_features, trading_day
from ict.structure import DOWN, UP, structure_breaks
from ict.swings import SwingParams, detect_swings
from ict.timewindows import window_label
from ict.volatility import volatility


@dataclass
class Context:
    df: pd.DataFrame
    vol: pd.Series
    swings: pd.DataFrame
    breaks: pd.DataFrame   # with displacement measures
    pools: pd.DataFrame    # with taken_bar
    takes: pd.DataFrame    # with sweep classification
    day: np.ndarray        # trading-day label per bar
    cache: dict = field(default_factory=dict)   # lazily computed extras (e.g. HTF bias)


def get_htf_bias(ctx: Context, rule: str) -> np.ndarray:
    """'up' / 'down' / '' per bar from the higher timeframe `rule` (cached)."""
    key = f"htf_bias_{rule}"
    if key not in ctx.cache:
        from ict.htf import htf_bias
        ctx.cache[key] = htf_bias(ctx.df, rule).to_numpy()
    return ctx.cache[key]


def build_context(df: pd.DataFrame, swing_params: SwingParams = SwingParams(),
                  disp_params: DisplacementParams = DisplacementParams()) -> Context:
    vol = volatility(df, swing_params.vol_method, swing_params.atr_period,
                     swing_params.tod_lookback, swing_params.tz)
    swings = detect_swings(df, swing_params)
    breaks = evaluate_breaks(df, structure_breaks(df, swings), vol, disp_params)
    pools = pool_takes(df, pd.concat([fixed_pools(df), swing_pools(swings)], ignore_index=True))
    takes = classify_takes(take_features(df, pools, vol))
    return Context(df, vol, swings, breaks, pools, takes, trading_day(df.index).to_numpy())


def sweep_choch_sequences(ctx: Context, window: int = 12, buffer: float = 0.1,
                          killzones: list[str] | None = None) -> pd.DataFrame:
    """Sweep -> displacement CHoCH sequences.

    Every row records the kill zone of its sweep (`killzone`, '' if none).
    `killzones`: if given, keep only sequences whose sweep happened inside one
    of these windows (see ict.timewindows.KILLZONES). None = all hours.
    """
    df = ctx.df
    zone = window_label(df.index).to_numpy()
    high, low = df["high"].to_numpy(), df["low"].to_numpy()
    v = ctx.vol.to_numpy()
    disp = ctx.breaks[ctx.breaks["displacement"]]
    sweeps = ctx.takes[ctx.takes["sweep"]].sort_values("taken_bar")
    rows, used = [], set()
    for s in sweeps.itertuples(index=False):
        direction = UP if s.side == SELL else DOWN
        i = int(s.taken_bar)
        b = disp[(disp["direction"] == direction) & (disp["bar"] >= i) & (disp["bar"] <= i + window)]
        if b.empty or int(b["bar"].iloc[0]) in used:
            continue
        brk = b.iloc[0]
        used.add(int(brk["bar"]))
        t = max(int(brk["bar"]), int(s.decided_at))
        stop = low[i:t + 1].min() - buffer * v[i] if direction == UP else high[i:t + 1].max() + buffer * v[i]
        rows.append({"sweep_bar": i, "swept": s.name, "direction": direction,
                     "leg_start": int(brk["leg_start"]), "break_bar": int(brk["bar"]),
                     "setup_bar": t, "stop": stop, "killzone": zone[i]})
    out = pd.DataFrame(rows)
    if killzones is not None and len(out):
        out = out[out["killzone"].isin(killzones)].reset_index(drop=True)
    return out


def simulate_trade(ctx: Context, direction: str, entry: float, stop: float, target: float,
                   place_bar: int, wait: int = 12, immediate: bool = False) -> dict:
    """Outcome of a limit order placed at the close of `place_bar` (or filled there if `immediate`)."""
    df = ctx.df
    high, low, close = (df[c].to_numpy() for c in ("high", "low", "close"))
    n, day = len(df), ctx.day
    up = direction == UP
    risk = abs(entry - stop)

    end = place_bar + 1
    while end < n and day[end] == day[place_bar]:
        end += 1                                  # first bar of the next trading day

    fill = place_bar if immediate else None
    if fill is None:
        for k in range(place_bar + 1, min(place_bar + 1 + wait, end)):
            touched = low[k] <= entry if up else high[k] >= entry
            if touched:
                fill = k
                if (low[k] <= stop) if up else (high[k] >= stop):
                    return {"outcome": "stop", "r": -1.0, "fill_bar": k, "exit_bar": k}
                break
            if (high[k] >= target) if up else (low[k] <= target):
                return {"outcome": "missed (target first)", "r": 0.0, "fill_bar": None, "exit_bar": k}
        if fill is None:
            return {"outcome": "not filled", "r": 0.0, "fill_bar": None, "exit_bar": None}

    for m in range(fill + 1, end):
        if (low[m] <= stop) if up else (high[m] >= stop):
            return {"outcome": "stop", "r": -1.0, "fill_bar": fill, "exit_bar": m}
        if (high[m] >= target) if up else (low[m] <= target):
            return {"outcome": "target", "r": abs(target - entry) / risk, "fill_bar": fill, "exit_bar": m}
    last = close[end - 1]
    return {"outcome": "open at day end", "r": ((last - entry) if up else (entry - last)) / risk,
            "fill_bar": fill, "exit_bar": end - 1}


ENTRY_STYLES = ["CHoCH close", "FVG edge (latest)", "FVG CE (latest)", "FVG edge (first)", "Order block"]


def entry_options(ctx: Context, seq) -> tuple[dict, dict]:
    """{style: (entry price, placement bar, immediate fill?)} and array details for one sequence."""
    from ict.arrays import leg_fvgs, leg_order_block, overlaps

    close = ctx.df["close"].to_numpy()
    s, e, d = int(seq.leg_start), int(seq.break_bar), seq.direction
    gaps = leg_fvgs(ctx.df, ctx.vol, s, e, d)
    ob = leg_order_block(ctx.df, ctx.vol, s, e, d)
    out = {"CHoCH close": (close[seq.setup_bar], int(seq.setup_bar), True)}
    if gaps:
        last, first = gaps[-1], gaps[0]
        out["FVG edge (latest)"] = (last["proximal"], max(int(seq.setup_bar), last["known_at"]), False)
        out["FVG CE (latest)"] = (last["ce"], max(int(seq.setup_bar), last["known_at"]), False)
        out["FVG edge (first)"] = (first["proximal"], max(int(seq.setup_bar), first["known_at"]), False)
    if ob:
        out["Order block"] = (ob["proximal"], int(seq.setup_bar), False)
    meta = {"n_fvg": len(gaps), "has_ob": ob is not None,
            "ob_fvg_overlap": any(overlaps(g, ob) for g in gaps), "gaps": gaps, "ob": ob}
    return out, meta


@dataclass(frozen=True)
class ModelParams:
    entry: str = "FVG edge (latest)"
    wait: int = 12                       # candles an unfilled entry stays live
    target_rule: str = "strict"          # "strict" | "skip_closer" | "fixed"
    min_rr: float = 2.0                  # pool targets must be at least this far
    fixed_rr: float = 1.0                # used when target_rule == "fixed"
    pd_gate: str | None = "dealing"      # "dealing" | "setup" | None (off)
    killzones: tuple | None = None       # e.g. ("London", "NY AM"); None = all hours
    htf_gate: str | None = None          # "1h" | "4h": trade only with that timeframe's bias

    @classmethod
    def from_config(cls) -> "ModelParams":
        from ict import config
        return cls(entry=config.ENTRY, wait=config.ENTRY_WAIT_CANDLES, target_rule=config.TARGET_RULE,
                   min_rr=config.MIN_RR, pd_gate=config.PD_RANGE,
                   killzones=tuple(config.SCREENER_KILLZONES), htf_gate=config.HTF_GATE)


def build_trades(ctx: Context, params: ModelParams = ModelParams(), seqs: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per sweep -> CHoCH sequence: which gate stopped it, or the simulated trade.

    status: "outside kill zones" | "no array" | "entry beyond stop" | "wrong half" |
            "against HTF bias" | "no target" | "order"
    Every row records the 1H and 4H bias at the setup bar (bias_1h, bias_4h).
    """
    from ict.draw import find_target, pools_as_of
    from ict.premium_discount import dealing_range, in_correct_half, position, setup_range

    if seqs is None:
        seqs = sweep_choch_sequences(ctx)
    close = ctx.df["close"].to_numpy()
    bias = {r: get_htf_bias(ctx, r) for r in ("1h", "4h")}
    rows = []
    for seq in seqs.itertuples(index=False):
        row = {"sweep_bar": seq.sweep_bar, "time": ctx.df.index[seq.sweep_bar], "swept": seq.swept,
               "direction": seq.direction, "killzone": seq.killzone, "stop": seq.stop,
               "bias_1h": bias["1h"][seq.setup_bar], "bias_4h": bias["4h"][seq.setup_bar]}
        if params.killzones is not None and seq.killzone not in params.killzones:
            rows.append({**row, "status": "outside kill zones"})
            continue
        opts, _ = entry_options(ctx, seq)
        if params.entry not in opts:
            rows.append({**row, "status": "no array"})
            continue
        entry, place, immediate = opts[params.entry]
        up = seq.direction == UP
        if not immediate and ((close[place] <= entry) if up else (close[place] >= entry)):
            entry, immediate = close[place], True        # price already inside: take it now
        if (up and entry <= seq.stop) or (not up and entry >= seq.stop):
            rows.append({**row, "status": "entry beyond stop"})
            continue

        dr = dealing_range(ctx.df, ctx.swings, int(seq.sweep_bar), place)
        pos_dealing = position(entry, *dr) if dr else np.nan
        pos_setup = position(entry, *setup_range(ctx.df, int(seq.sweep_bar), place, seq.direction))
        row.update(entry=entry, place_bar=place, pos_dealing=pos_dealing, pos_setup=pos_setup)
        pos = {"dealing": pos_dealing, "setup": pos_setup}.get(params.pd_gate)
        if params.pd_gate and (np.isnan(pos) or not in_correct_half(pos, seq.direction)):
            rows.append({**row, "status": "wrong half"})
            continue

        if params.htf_gate and row[f"bias_{params.htf_gate}"] != seq.direction:
            rows.append({**row, "status": "against HTF bias"})
            continue

        risk = abs(entry - seq.stop)
        if params.target_rule == "fixed":
            target = entry + params.fixed_rr * risk if up else entry - params.fixed_rr * risk
            tgt = {"target_name": f"{params.fixed_rr:g}R", "target_price": target, "target_rr": params.fixed_rr}
        else:
            tgt = find_target(pools_as_of(ctx.pools, place), seq.direction, entry, seq.stop,
                              params.min_rr, skip_closer=params.target_rule == "skip_closer")
            if tgt is None:
                rows.append({**row, "status": "no target"})
                continue
        res = simulate_trade(ctx, seq.direction, entry, seq.stop, tgt["target_price"], place, params.wait, immediate)
        rows.append({**row, "status": "order", "risk_pts": risk, "target": tgt["target_price"],
                     "target_name": tgt["target_name"], "target_rr": tgt["target_rr"], **res})
    return pd.DataFrame(rows)


def summarize(trades: pd.DataFrame) -> dict:
    """Counts and R for one run of build_trades."""
    orders = trades[trades["status"] == "order"] if len(trades) else trades
    filled = orders[orders["fill_bar"].notna()] if len(orders) else orders
    wins = int((filled["outcome"] == "target").sum()) if len(filled) else 0
    losses = int((filled["outcome"] == "stop").sum()) if len(filled) else 0
    return {"sequences": len(trades), "orders": len(orders), "filled": len(filled),
            "wins": wins, "losses": losses,
            "open at day end": int((filled["outcome"] == "open at day end").sum()) if len(filled) else 0,
            "win rate": round(wins / max(wins + losses, 1) * 100),
            "total R": round(float(filled["r"].sum()), 1) if len(filled) else 0.0,
            "avg R": round(float(filled["r"].mean()), 2) if len(filled) else float("nan")}
