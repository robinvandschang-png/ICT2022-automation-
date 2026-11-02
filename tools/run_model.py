"""Run the v1 model as decided (ict/config.py) plus a few variants. NOT a validated backtest.

Prints the gate funnel for the decided model, a variant comparison, and writes
the decided model's trades to CSV.

Usage:
    python -m tools.run_model "data/nq/NQ_5min*.csv" --out out/model_v1_trades.csv
"""
from __future__ import annotations

import argparse
import dataclasses
import glob

import pandas as pd

from ict.data import load_csv
from ict.model import ModelParams, build_context, build_trades, summarize, sweep_choch_sequences

TZ = "America/New_York"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default="out/model_v1_trades.csv")
    ap.add_argument("--warmup-days", type=int, default=20)
    a = ap.parse_args()

    df = load_csv(glob.glob(a.csv)[0])
    ctx = build_context(df)
    seqs = sweep_choch_sequences(ctx)
    warm = df.index.searchsorted(df.index[0] + pd.Timedelta(days=a.warmup_days))
    seqs = seqs[seqs["sweep_bar"] >= warm].reset_index(drop=True)

    v1 = ModelParams.from_config()
    variants = {
        "v1 as decided (London + NY AM)": v1,
        "v1, all hours": dataclasses.replace(v1, killzones=None),
        "v1, all hours, no P/D gate": dataclasses.replace(v1, killzones=None, pd_gate=None),
        "v1, all hours, fixed 1R target": dataclasses.replace(v1, killzones=None, target_rule="fixed", fixed_rr=1.0),
        "v1, London + NY AM, fixed 1R target": dataclasses.replace(v1, target_rule="fixed", fixed_rr=1.0),
    }

    period = f"{df.index[warm].tz_convert(TZ):%d %b %Y} – {df.index[-1].tz_convert(TZ):%d %b %Y}"
    print(f"NQ 5m, {period}: {len(seqs)} sweep -> CHoCH sequences\n")

    trades = build_trades(ctx, v1, seqs)
    order = ["outside kill zones", "no array", "entry beyond stop", "wrong half", "no target", "order"]
    funnel = trades["status"].value_counts().reindex(order, fill_value=0)
    print("Gate funnel, v1 as decided:")
    remaining = len(trades)
    for status, n in funnel.items():
        if status == "order":
            print(f"  -> orders placed: {n}")
        else:
            remaining -= n
            print(f"  dropped: {status:<20} {n:>3}   (left {remaining})")

    rows = {name: summarize(build_trades(ctx, p, seqs)) for name, p in variants.items()}
    print("\nVariants:")
    print(pd.DataFrame(rows).T.drop(columns=["sequences"]).to_string())

    out = trades[trades["status"] == "order"].copy()
    out["time"] = pd.DatetimeIndex(out["time"]).tz_convert(TZ).strftime("%Y-%m-%d %H:%M")
    out.to_csv(a.out, index=False)
    cols = ["time", "killzone", "swept", "direction", "entry", "stop", "target_name", "target_rr", "outcome", "r"]
    print("\nv1 trades:")
    print(out[cols].round(2).to_string(index=False))
    plot_trades(ctx, trades[trades["status"] == "order"], seqs, a.out.rsplit(".", 1)[0] + ".png")


def plot_trades(ctx, orders: pd.DataFrame, seqs: pd.DataFrame, path: str, max_n: int = 4) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from ict.model import entry_options
    from ict.premium_discount import dealing_range
    from tools.plot_swings import draw_candles

    orders = orders.head(max_n)
    if orders.empty:
        return
    df = ctx.df
    local = df.index.tz_convert(TZ)
    fig, axes = plt.subplots(1, len(orders), figsize=(8 * len(orders), 6), dpi=110, squeeze=False)
    for (_, r), ax in zip(orders.iterrows(), axes[0]):
        seq = seqs[seqs["sweep_bar"] == r.sweep_bar].iloc[0]
        _, meta = entry_options(ctx, seq)
        end_bar = int(r.exit_bar) if not pd.isna(r.exit_bar) else int(r.place_bar) + 12
        lo, hi = max(0, int(seq.sweep_bar) - 30), min(len(df), end_bar + 10)
        draw_candles(ax, df, lo, hi)
        for g in meta["gaps"]:
            ax.fill_between([g["middle_bar"] - 1, hi], g["bottom"], g["top"], color="#7F77DD", alpha=0.15, linewidth=0)
        dr = dealing_range(df, ctx.swings, int(seq.sweep_bar), int(r.place_bar))
        if dr:
            for y, ls in ((dr[0], ":"), (dr[1], ":"), ((dr[0] + dr[1]) / 2, "--")):
                ax.axhline(y, color="#888780", linestyle=ls, linewidth=1)
            ax.text(lo, (dr[0] + dr[1]) / 2, " dealing range 50%", fontsize=8, color="#5F5E5A", va="bottom")
        x0 = int(r.place_bar)
        ax.hlines(r.entry, x0, end_bar, color="#185FA5", linewidth=1.6)
        ax.hlines(r.stop, x0, end_bar, color="#A32D2D", linewidth=1.6)
        ax.hlines(r.target, x0, end_bar, color="#0F6E56", linewidth=1.6)
        ax.text(end_bar, r.target, f" {r.target_name} {r.target_rr:.1f}R", fontsize=8, color="#0F6E56", va="center")
        ax.axvspan(int(seq.sweep_bar) - 0.5, int(seq.sweep_bar) + 0.5, color="#EF9F27", alpha=0.25)
        ax.axvspan(int(seq.break_bar) - 0.5, int(seq.break_bar) + 0.5, color="#534AB7", alpha=0.15)
        ticks = list(range(lo, hi, max(1, (hi - lo) // 6)))
        ax.set_xticks(ticks)
        ax.set_xticklabels([local[k].strftime("%H:%M") for k in ticks], fontsize=8)
        ax.set_xlim(lo - 1, hi + 8)
        ax.grid(alpha=0.12)
        ax.set_title(f"{local[int(seq.sweep_bar)].strftime('%a %d %b %H:%M')} ET ({r.killzone})  swept {r.swept}  "
                     f"{'long' if r.direction == 'up' else 'short'} → {r.outcome} ({r.r:+.1f}R)", fontsize=10, loc="left")
    fig.text(0.01, 0.01, "Orange = sweep candle · purple band = CHoCH · purple boxes = FVGs · blue = entry (FVG near edge) · "
             "red = stop · green = target · grey = dealing range and its 50%. 5m NQ, ET.", fontsize=9, color="#5F5E5A")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path)


if __name__ == "__main__":
    main()
