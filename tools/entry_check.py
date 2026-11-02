"""Compare entry options on sweep -> CHoCH sequences. NOT a backtest.

Options (all with stop beyond the sweep extreme and the strict target rule):
  CHoCH close       market entry at the close of the CHoCH / sweep-verdict candle
  FVG edge (latest) limit at the near edge of the FVG closest to the break
  FVG CE (latest)   limit at the midpoint of that FVG
  FVG edge (first)  limit at the near edge of the first (deepest) FVG in the leg
  Order block       limit at the near edge of the order block
Limit orders wait up to `wait` candles (default 12 = 1 hour on 5m), same trading day.
No time-window filter, no premium/discount filter, no costs.

Usage:
    python -m tools.entry_check "data/nq/NQ_5min*.csv" --out out/entries.png
"""
from __future__ import annotations

import argparse
import glob

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ict.data import load_csv
from ict.draw import find_target, pools_as_of
from ict.model import build_context, entry_options, simulate_trade, sweep_choch_sequences
from ict.structure import UP
from tools.plot_swings import draw_candles

TZ = "America/New_York"
OPTIONS = ["CHoCH close", "FVG edge (latest)", "FVG CE (latest)", "FVG edge (first)", "Order block"]


entries_for = entry_options   # moved into ict.model


def run(ctx, seqs: pd.DataFrame, wait: int = 12, min_rr: float = 2.0) -> pd.DataFrame:
    close = ctx.df["close"].to_numpy()
    rows = []
    for seq in seqs.itertuples(index=False):
        opts, meta = entries_for(ctx, seq)
        for name in OPTIONS:
            row = {"sweep_bar": seq.sweep_bar, "option": name, "direction": seq.direction,
                   "ob_fvg_overlap": meta["ob_fvg_overlap"]}
            if name not in opts:
                rows.append({**row, "status": "no array"})
                continue
            entry, place, immediate = opts[name]
            up = seq.direction == UP
            if not immediate and ((close[place] <= entry) if up else (close[place] >= entry)):
                entry, immediate = close[place], True       # price already inside: take it now
            if (up and entry <= seq.stop) or (not up and entry >= seq.stop):
                rows.append({**row, "status": "invalid (entry beyond stop)"})
                continue
            tgt = find_target(pools_as_of(ctx.pools, place), seq.direction, entry, seq.stop, min_rr)
            if tgt is None:
                rows.append({**row, "status": "no target >= 2R"})
                continue
            res = simulate_trade(ctx, seq.direction, entry, seq.stop, tgt["target_price"], place, wait, immediate)
            rows.append({**row, "status": "order", "entry": entry, "stop": seq.stop, "place_bar": place,
                         "target": tgt["target_price"], "target_name": tgt["target_name"],
                         "target_rr": tgt["target_rr"], **res})
    return pd.DataFrame(rows)


def report(res: pd.DataFrame, n_seq: int) -> pd.DataFrame:
    out = []
    for name in OPTIONS:
        r = res[res["option"] == name]
        orders = r[r["status"] == "order"]
        filled = orders[orders["fill_bar"].notna()]
        out.append({
            "entry option": name,
            "array found": int((r["status"] != "no array").sum()),
            "target >= 2R": len(orders),
            "filled": len(filled),
            "target hit": int((filled["outcome"] == "target").sum()),
            "stopped": int((filled["outcome"] == "stop").sum()),
            "open at day end": int((filled["outcome"] == "open at day end").sum()),
            "median target R": round(float(orders["target_rr"].median()), 1) if len(orders) else np.nan,
            "total R": round(float(filled["r"].sum()), 1),
            "avg R per fill": round(float(filled["r"].mean()), 2) if len(filled) else np.nan,
        })
    t = pd.DataFrame(out).set_index("entry option")
    print(f"{n_seq} sweep -> CHoCH sequences\n")
    print(t.to_string())
    return t


def plot_examples(ctx, seqs, res, out, n=4, seed=5):
    df = ctx.df
    local = df.index.tz_convert(TZ)
    pick_from = res[(res["option"] == "FVG edge (latest)") & (res["status"] == "order")]
    if pick_from.empty:
        return
    rng = np.random.default_rng(seed)
    picks = pick_from.iloc[np.sort(rng.choice(len(pick_from), size=min(n, len(pick_from)), replace=False))]
    fig, axes = plt.subplots(2, 2, figsize=(16, 10), dpi=110)
    for (_, r), ax in zip(picks.iterrows(), axes.flat):
        seq = seqs[seqs["sweep_bar"] == r.sweep_bar].iloc[0]
        _, meta = entries_for(ctx, seq)
        end_bar = int(r.exit_bar) if not pd.isna(r.exit_bar) else int(r.place_bar) + 12
        lo, hi = max(0, int(seq.sweep_bar) - 20), min(len(df), end_bar + 8)
        draw_candles(ax, df, lo, hi)
        for g in meta["gaps"]:
            ax.fill_between([g["middle_bar"] - 1, hi], g["bottom"], g["top"], color="#7F77DD", alpha=0.15, linewidth=0)
        if meta["ob"]:
            ob = meta["ob"]
            ax.fill_between([ob["bar"] - 0.4, hi], ob["low"], ob["high"], color="#EF9F27", alpha=0.18, linewidth=0)
        x0 = int(r.place_bar)
        ax.hlines(r.entry, x0, end_bar, color="#185FA5", linewidth=1.4)
        ax.hlines(r.stop, x0, end_bar, color="#A32D2D", linewidth=1.4)
        ax.hlines(r.target, x0, end_bar, color="#0F6E56", linewidth=1.4)
        ax.text(end_bar, r.target, f" {r.target_name} {r.target_rr:.1f}R", fontsize=8, color="#0F6E56", va="center")
        if not pd.isna(r.fill_bar):
            ax.plot(int(r.fill_bar), r.entry, marker="o", color="#185FA5")
        ticks = list(range(lo, hi, max(1, (hi - lo) // 6)))
        ax.set_xticks(ticks)
        ax.set_xticklabels([local[k].strftime("%H:%M") for k in ticks], fontsize=8)
        ax.set_xlim(lo - 1, hi + 6)
        ax.grid(alpha=0.12)
        ax.set_title(f"{local[int(seq.sweep_bar)].strftime('%a %d %b %H:%M')} ET  swept {seq.swept}  "
                     f"{'long' if seq.direction == UP else 'short'} → {r.outcome} ({r.r:+.1f}R)", fontsize=10, loc="left")
    fig.text(0.01, 0.005, "Purple boxes = FVGs in the displacement leg · orange box = order block · blue = entry at the "
             "latest FVG's near edge (dot = filled) · red = stop · green = target. 5m NQ, ET.", fontsize=9, color="#5F5E5A")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(out)


def fixed_rr(ctx, seqs: pd.DataFrame, rrs, option: str = "FVG edge (latest)", wait: int = 12) -> pd.DataFrame:
    """Same entry and stop, but the target is a fixed multiple of the risk instead of a pool."""
    close = ctx.df["close"].to_numpy()
    rows = []
    for seq in seqs.itertuples(index=False):
        opts, _ = entries_for(ctx, seq)
        if option not in opts:
            continue
        entry, place, immediate = opts[option]
        up = seq.direction == UP
        if not immediate and ((close[place] <= entry) if up else (close[place] >= entry)):
            entry, immediate = close[place], True
        risk = abs(entry - seq.stop)
        if (up and entry <= seq.stop) or (not up and entry >= seq.stop):
            continue
        for k in rrs:
            target = entry + k * risk if up else entry - k * risk
            res = simulate_trade(ctx, seq.direction, entry, seq.stop, target, place, wait, immediate)
            rows.append({"sweep_bar": seq.sweep_bar, "rr": k, "risk_pts": risk, **res})
    return pd.DataFrame(rows)


def fixed_rr_report(t: pd.DataFrame, label: str) -> None:
    print(f"\n{label}")
    out = []
    for k, g in t.groupby("rr"):
        f = g[g["fill_bar"].notna()]
        wins, losses = (f["outcome"] == "target").sum(), (f["outcome"] == "stop").sum()
        out.append({"target": f"{k:g}R", "orders": len(g), "filled": len(f), "wins": int(wins),
                    "losses": int(losses), "open at day end": int((f["outcome"] == "open at day end").sum()),
                    "win rate": f"{wins / max(wins + losses, 1) * 100:.0f}%",
                    "break-even win rate": f"{100 / (1 + k):.0f}%",
                    "total R": round(float(f["r"].sum()), 1), "avg R": round(float(f["r"].mean()), 2)})
    print(pd.DataFrame(out).set_index("target").to_string())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default="out/entries.png")
    ap.add_argument("--wait", type=int, default=12)
    ap.add_argument("--fixed-rr", type=float, nargs="*", help="also test fixed R targets, e.g. 1 1.5 2 3")
    a = ap.parse_args()
    df = load_csv(glob.glob(a.csv)[0])
    ctx = build_context(df)
    seqs = sweep_choch_sequences(ctx)
    warm = df.index.searchsorted(df.index[0] + pd.Timedelta(days=20))
    seqs = seqs[seqs["sweep_bar"] >= warm].reset_index(drop=True)
    if a.fixed_rr:
        t = fixed_rr(ctx, seqs, a.fixed_rr, wait=a.wait)
        fixed_rr_report(t, "FVG near edge (latest gap), fixed R targets — all hours")
        local = df.index.tz_convert(TZ)[t["sweep_bar"].to_numpy()]
        m = local.hour * 60 + local.minute
        kz = ((m >= 120) & (m < 300)) | ((m >= 510) & (m < 690))
        fixed_rr_report(t[kz], "Same, London 02:00-05:00 + NY 08:30-11:30 ET only")
        print(f"\nmedian risk: {t['risk_pts'].median():.1f} NQ points")
        return
    res = run(ctx, seqs, a.wait)
    report(res, len(seqs))
    res.to_csv(a.out.rsplit(".", 1)[0] + ".csv", index=False)
    plot_examples(ctx, seqs, res, a.out)


if __name__ == "__main__":
    main()
