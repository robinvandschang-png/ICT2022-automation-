"""Sanity check for target selection (draw v1). NOT a backtest.

Pairs each sweep with the first displacement break in the reversal direction
within `window` candles, then:
  entry  = close of the later of (break candle, sweep verdict candle)  [placeholder:
           the real model enters on the retrace into the OB/FVG]
  stop   = beyond the furthest price since the take, plus 0.1 yardstick
  target = nearest untapped opposite pool >= min R (ict.draw.find_target)
and follows price until stop, target, or the end of the trading day.
No costs or slippage; same-candle stop+target counts as a loss.

Usage:
    python -m tools.draw_check "data/nq/NQ_5min*.csv" --out out/draw_examples.png
"""
from __future__ import annotations

import argparse
import glob

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ict.data import load_csv, session_of
from ict.displacement import evaluate_breaks
from ict.draw import find_target, pools_as_of
from ict.liquidity import SELL, classify_takes, fixed_pools, pool_takes, swing_pools, take_features, trading_day
from ict.structure import DOWN, UP, structure_breaks
from ict.swings import SwingParams, detect_swings
from ict.volatility import volatility
from tools.plot_swings import draw_candles

TZ = "America/New_York"


def build(df: pd.DataFrame, window: int = 12, min_rr: float = 2.0, buffer: float = 0.1) -> pd.DataFrame:
    vol = volatility(df, "tod")
    swings = detect_swings(df, SwingParams())
    breaks = evaluate_breaks(df, structure_breaks(df, swings), vol)
    disp = breaks[breaks["displacement"]]
    pools = pool_takes(df, pd.concat([fixed_pools(df), swing_pools(swings)], ignore_index=True))
    takes = classify_takes(take_features(df, pools, vol))
    sweeps = takes[takes["sweep"]].sort_values("taken_bar")

    high, low, close = (df[c].to_numpy() for c in ("high", "low", "close"))
    v = vol.to_numpy()
    day = trading_day(df.index).to_numpy()
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
        entry = close[t]
        if direction == UP:
            stop = low[i:t + 1].min() - buffer * v[i]
        else:
            stop = high[i:t + 1].max() + buffer * v[i]
        if (direction == UP and stop >= entry) or (direction == DOWN and stop <= entry):
            continue
        tgt = find_target(pools_as_of(pools, t), direction, entry, stop, min_rr)
        row = {"sweep_bar": i, "swept": s.name, "direction": direction, "break_bar": int(brk["bar"]),
               "setup_bar": t, "entry": entry, "stop": stop, "has_target": tgt is not None}
        if tgt:
            row.update(tgt)
            end = t + 1
            while end < len(df) and day[end] == day[t]:
                end += 1
            hit_stop = (low[t + 1:end] <= stop) if direction == UP else (high[t + 1:end] >= stop)
            hit_tgt = (high[t + 1:end] >= tgt["target_price"]) if direction == UP else (low[t + 1:end] <= tgt["target_price"])
            first_stop = int(np.argmax(hit_stop)) if hit_stop.any() else None
            first_tgt = int(np.argmax(hit_tgt)) if hit_tgt.any() else None
            risk = abs(entry - stop)
            if first_stop is not None and (first_tgt is None or first_stop <= first_tgt):
                row.update(outcome="stop", r=-1.0, exit_bar=t + 1 + first_stop)
            elif first_tgt is not None:
                row.update(outcome="target", r=tgt["target_rr"], exit_bar=t + 1 + first_tgt)
            else:
                last = close[end - 1]
                row.update(outcome="open at day end", r=((last - entry) if direction == UP else (entry - last)) / risk,
                           exit_bar=end - 1)
        rows.append(row)
    out = pd.DataFrame(rows)
    out["session"] = session_of(df.index).iloc[out["sweep_bar"].to_numpy()].to_numpy()
    return out


def report(s: pd.DataFrame, label: str) -> None:
    t = s[s["has_target"]]
    print(f"\n== {label}: {len(s)} sweep+CHoCH sequences, {len(t)} with a target >= 2R ({len(t)/max(len(s),1)*100:.0f}%)")
    if t.empty:
        return
    print("  target pools:", t["target_name"].value_counts().to_dict())
    print(f"  R to target: median {t['target_rr'].median():.1f} (25-75%: {t['target_rr'].quantile(.25):.1f}-{t['target_rr'].quantile(.75):.1f})"
          f" | closer pools skipped: none {(t['pools_between']==0).mean()*100:.0f}%, 1+ {(t['pools_between']>0).mean()*100:.0f}%")
    o = t["outcome"].value_counts(normalize=True).mul(100).round(0).to_dict()
    print(f"  outcome: {o} | avg R per trade {t['r'].mean():+.2f} (gross, placeholder entry)")
    strict = t[t["pools_between"] == 0]
    if len(strict):
        print(f"  strict variant (nearest pool itself >= 2R): {len(strict)} trades, avg R {strict['r'].mean():+.2f}")


def plot_examples(df: pd.DataFrame, s: pd.DataFrame, out: str, n: int = 6, seed: int = 3) -> None:
    t = s[s["has_target"]]
    rng = np.random.default_rng(seed)
    pick = t.iloc[np.sort(rng.choice(len(t), size=min(n, len(t)), replace=False))]
    local = df.index.tz_convert(TZ)
    fig, axes = plt.subplots(2, 3, figsize=(18, 10), dpi=110)
    pick = pick.astype({c: int for c in ("sweep_bar", "setup_bar", "break_bar", "exit_bar")})
    for (_, r), ax in zip(pick.iterrows(), axes.flat):
        lo = max(0, r.sweep_bar - 24)
        hi = min(len(df), max(r.exit_bar + 6, r.setup_bar + 30))
        draw_candles(ax, df, lo, hi)
        ax.hlines(r.entry, r.setup_bar, r.exit_bar, color="#185FA5", linewidth=1.4)
        ax.hlines(r.stop, r.setup_bar, r.exit_bar, color="#A32D2D", linewidth=1.4)
        ax.hlines(r.target_price, r.setup_bar, r.exit_bar, color="#0F6E56", linewidth=1.4)
        ax.axvspan(r.sweep_bar - 0.5, r.sweep_bar + 0.5, color="#EF9F27", alpha=0.2)
        ax.axvspan(r.break_bar - 0.5, r.break_bar + 0.5, color="#534AB7", alpha=0.15)
        ax.text(r.exit_bar, r.target_price, f" {r.target_name} {r.target_rr:.1f}R", fontsize=8, color="#0F6E56", va="center")
        ticks = list(range(lo, hi, max(1, (hi - lo) // 6)))
        ax.set_xticks(ticks)
        ax.set_xticklabels([local[k].strftime("%H:%M") for k in ticks], fontsize=8)
        ax.set_xlim(lo - 1, hi + 8)
        ax.grid(alpha=0.12)
        ax.set_title(f"{local[r.sweep_bar].strftime('%a %d %b')}  swept {r.swept}  {'long' if r.direction == UP else 'short'}"
                     f"  → {r.outcome} ({r.r:+.1f}R)", fontsize=10, loc="left")
    fig.text(0.01, 0.005, "Orange band = sweep candle · purple band = CHoCH on displacement · blue = placeholder entry · "
             "red = stop · green = target pool. 5-minute NQ, ET.", fontsize=9, color="#5F5E5A")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default="out/draw_examples.png")
    a = ap.parse_args()
    df = load_csv(glob.glob(a.csv)[0])
    s = build(df)
    warm = df.index.searchsorted(df.index[0] + pd.Timedelta(days=20))
    s = s[s["sweep_bar"] >= warm]
    report(s, "All hours")
    report(s[s["session"].isin(["London", "NY open", "NY AM"])], "London + NY open/AM")
    plot_examples(df, s, a.out)
    s.to_csv(a.out.rsplit(".", 1)[0] + ".csv", index=False)


if __name__ == "__main__":
    main()
