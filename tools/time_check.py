"""Kill-zone checks on NQ.

1. Premise test: in which hour (ET) does each trading day's high and low form?
   Uses hourly bars (longest history) and 5m bars (window-level detail).
2. Setups by window: sweep -> CHoCH sequences and FVG near-edge results at a
   fixed 1R, split by the kill zone of the sweep (NOT a backtest).

Usage:
    python -m tools.time_check --h1 "data/nq/NQ_1h*.csv" --m5 "data/nq/NQ_5min*.csv" --out out/killzones.png
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
from ict.liquidity import trading_day
from ict.model import build_context, sweep_choch_sequences
from ict.timewindows import KILLZONES, TZ, window_label
from tools.entry_check import fixed_rr

HOURS = list(range(18, 24)) + list(range(0, 17))   # trading-day order, 18:00 -> 16:00 ET


def daily_extremes(df: pd.DataFrame) -> pd.DataFrame:
    day = trading_day(df.index).to_numpy()
    rows = []
    for d in pd.unique(day):
        sel = np.flatnonzero(day == d)
        if len(sel) < 0.8 * np.median(np.bincount(pd.factorize(day)[0])):
            continue                                  # skip half days / partial days
        hi = sel[np.argmax(df["high"].to_numpy()[sel])]
        lo = sel[np.argmin(df["low"].to_numpy()[sel])]
        rows += [{"day": d, "kind": "high", "bar": hi}, {"day": d, "kind": "low", "bar": lo}]
    out = pd.DataFrame(rows)
    out["time"] = df.index[out["bar"].to_numpy()]
    return out


def hourly_profile(df_h1: pd.DataFrame) -> pd.Series:
    ex = daily_extremes(df_h1)
    hours = ex["time"].dt.tz_convert(TZ).dt.hour
    return hours.value_counts(normalize=True).reindex(HOURS, fill_value=0) * 100, ex["day"].nunique()


def window_share(df_m5: pd.DataFrame) -> pd.DataFrame:
    ex = daily_extremes(df_m5)
    lab = window_label(pd.DatetimeIndex(ex["time"])).replace("", "outside")
    share = lab.value_counts(normalize=True) * 100
    all_lab = window_label(df_m5.index).replace("", "outside")
    time_share = all_lab.value_counts(normalize=True) * 100
    t = pd.DataFrame({"share of daily highs/lows": share, "share of trading time": time_share}).fillna(0)
    return t.loc[[k for k in list(KILLZONES) + ["outside"] if k in t.index]].round(0), ex["day"].nunique()


def plot_profile(prof: pd.Series, n_days: int, out: str) -> None:
    fig, ax = plt.subplots(figsize=(13, 5), dpi=120)
    x = np.arange(len(HOURS))
    ax.bar(x, prof.to_numpy(), color="#378ADD", width=0.75)
    ax.axhline(100 / len(HOURS), color="#5F5E5A", linestyle="--", linewidth=1)
    ax.text(len(HOURS) - 0.5, 100 / len(HOURS) + 0.3, "if spread evenly", ha="right", fontsize=9, color="#5F5E5A")
    def xpos(hour: float) -> float:
        """x coordinate of a clock time: bar k spans [k - 0.5, k + 0.5) for hour HOURS[k]."""
        h = int(hour) % 24
        return HOURS.index(h) - 0.5 + (hour - int(hour))

    colors = {"Asia": "#B4B2A9", "London": "#EF9F27", "NY AM": "#1D9E75", "NY PM": "#7F77DD"}
    for name, (s, e) in KILLZONES.items():
        hs = int(s[:2]) + int(s[3:]) / 60
        he = (int(e[:2]) + int(e[3:]) / 60) or 24.0
        x0, x1 = xpos(hs), xpos(he) if he < 24 else xpos(0)
        ax.axvspan(x0, x1, color=colors[name], alpha=0.15, zorder=0)
        ax.text((x0 + x1) / 2, prof.max() * 1.05, f"{name}\n{s}–{e}", ha="center", fontsize=8.5, color=colors[name])
    ax.set_xticks(x)
    ax.set_xticklabels([f"{h:02d}" for h in HOURS], fontsize=9)
    ax.set_xlabel("Hour of the trading day, ET (bar start)")
    ax.set_ylabel("% of daily highs and lows")
    ax.set_ylim(0, prof.max() * 1.15)
    ax.set_title(f"NQ: when the trading day's high and low form ({n_days} days, hourly bars)", loc="left", fontsize=11)
    ax.grid(axis="y", alpha=0.15)
    fig.tight_layout()
    fig.savefig(out)


def setups_by_window(df_m5: pd.DataFrame) -> pd.DataFrame:
    ctx = build_context(df_m5)
    seqs = sweep_choch_sequences(ctx)
    warm = df_m5.index.searchsorted(df_m5.index[0] + pd.Timedelta(days=20))
    seqs = seqs[seqs["sweep_bar"] >= warm].reset_index(drop=True)
    t = fixed_rr(ctx, seqs, [1.0])
    seqs["window"] = window_label(df_m5.index).iloc[seqs["sweep_bar"].to_numpy()].replace("", "outside").to_numpy()
    t = t.merge(seqs[["sweep_bar", "window"]], on="sweep_bar")
    rows = []
    for w in list(KILLZONES) + ["outside"]:
        s = seqs[seqs["window"] == w]
        f = t[(t["window"] == w) & t["fill_bar"].notna()]
        wins, losses = (f["outcome"] == "target").sum(), (f["outcome"] == "stop").sum()
        rows.append({"window (sweep time)": w, "sequences": len(s), "filled at 1R": len(f),
                     "wins / losses": f"{wins} / {losses}", "total R": round(float(f["r"].sum()), 1)})
    return pd.DataFrame(rows).set_index("window (sweep time)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--h1", required=True)
    ap.add_argument("--m5", required=True)
    ap.add_argument("--out", default="out/killzones.png")
    a = ap.parse_args()
    h1 = load_csv(glob.glob(a.h1)[0])
    m5 = load_csv(glob.glob(a.m5)[0])

    prof, n = hourly_profile(h1)
    plot_profile(prof, n, a.out)
    print(f"Daily high/low by hour (ET), {n} full trading days of hourly bars, top hours:")
    print(prof.sort_values(ascending=False).head(6).round(1).to_string())
    ws, n5 = window_share(m5)
    print(f"\nDaily highs/lows by kill zone, {n5} days of 5m bars:")
    print(ws.to_string())
    print("\nSweep -> CHoCH sequences by kill zone (FVG near edge, fixed 1R):")
    print(setups_by_window(m5).to_string())


if __name__ == "__main__":
    main()
