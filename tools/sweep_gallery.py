"""Blind labelling gallery: real pool takes, numbered, no verdicts shown.

Samples takes during London (02:00-05:00 ET) and NY (08:30-11:30 ET) across
the cases that separate the candidate sweep rules:
  wick    - closed back inside on the taking candle
  quick   - closed beyond, back inside within 1-3 candles
  slow    - back inside after 4-12 candles
  hold    - not back inside within 12 candles
The answer key (features per example) is written next to the chart so the
human labels can be compared with each rule afterwards.

Usage:
    python -m tools.sweep_gallery "data/nq/NQ_5min*.csv" --out out/sweeps.png --seed 7
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
from ict.liquidity import BUY, fixed_pools, pool_takes, swing_pools, take_features
from ict.swings import SwingParams, detect_swings
from ict.volatility import volatility
from tools.plot_swings import draw_candles

TZ = "America/New_York"
PRIORITY = {"PWH": 0, "PWL": 0, "PDH": 1, "PDL": 1, "London H": 2, "London L": 2,
            "Asia H": 3, "Asia L": 3, "T2 high": 4, "T2 low": 4}
QUOTAS = {
    # first pass: spread across the whole range
    "spread": {"wick": 3, "quick": 4, "slow": 2, "hold": 3},
    # second pass: only the cases that decide N and the depth cap
    "boundary": {"quick-deep": 4, "quick-mid": 4, "medium": 3, "wick-deep": 1},
}


def category(r) -> str:
    if pd.isna(r.reclaim_bars):
        return "hold"
    if r.reclaim_bars == 0:
        return "wick"
    return "quick" if r.reclaim_bars <= 3 else "slow"


def boundary_category(r) -> str:
    rb = None if pd.isna(r.reclaim_bars) else int(r.reclaim_bars)
    if rb is not None and 1 <= rb <= 3 and r.depth >= 1.0:
        return "quick-deep"
    if rb is not None and 2 <= rb <= 3 and 0.5 <= r.depth < 1.0:
        return "quick-mid"
    if rb is not None and 4 <= rb <= 6:
        return "medium"
    if rb == 0 and r.depth >= 0.8:
        return "wick-deep"
    return "other"


def all_takes(df: pd.DataFrame) -> pd.DataFrame:
    vol = volatility(df, "tod")
    swings = detect_swings(df, SwingParams())
    pools = pd.concat([fixed_pools(df), swing_pools(swings)], ignore_index=True)
    f = take_features(df, pool_takes(df, pools), vol)
    f["priority"] = f["name"].map(PRIORITY)
    f = f.sort_values(["taken_bar", "priority"]).drop_duplicates(["taken_bar", "side"])
    f["category"] = [category(r) for r in f.itertuples(index=False)]
    return f.reset_index(drop=True)


def in_killzone(df: pd.DataFrame, bars: pd.Series) -> np.ndarray:
    local = df.index.tz_convert(TZ)[bars.astype(int).to_numpy()]
    m = local.hour * 60 + local.minute
    return ((m >= 120) & (m < 300)) | ((m >= 510) & (m < 690))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default="out/sweeps.png")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--before", type=int, default=30)
    ap.add_argument("--after", type=int, default=24)
    ap.add_argument("--mode", choices=list(QUOTAS), default="spread")
    ap.add_argument("--exclude", nargs="*", default=[], help="answer keys of galleries already shown")
    a = ap.parse_args()

    df = load_csv(glob.glob(a.csv)[0])
    takes = all_takes(df)
    if a.mode == "boundary":
        takes["category"] = [boundary_category(r) for r in takes.itertuples(index=False)]
    warm = df.index.searchsorted(df.index[0] + pd.Timedelta(days=20))
    ok = (takes["taken_bar"] >= warm) & (takes["taken_bar"] + a.after < len(df))
    ok &= in_killzone(df, takes["taken_bar"])
    for key_file in a.exclude:
        ok &= ~takes["taken_bar"].isin(pd.read_csv(key_file)["taken_bar"])
    pool = takes[ok]
    print("available:", pool["category"].value_counts().to_dict())

    rng = np.random.default_rng(a.seed)
    picks = []
    for cat, n in QUOTAS[a.mode].items():
        c = pool[pool["category"] == cat]
        picks.append(c.iloc[rng.choice(len(c), size=min(n, len(c)), replace=False)])
    sample = pd.concat(picks).sample(frac=1, random_state=a.seed).reset_index(drop=True)
    sample.index = sample.index + 1

    local = df.index.tz_convert(TZ)
    fig, axes = plt.subplots(4, 3, figsize=(18, 19), dpi=110)
    for (num, r), ax in zip(sample.iterrows(), axes.flat):
        i = int(r.taken_bar)
        lo, hi = max(0, i - a.before), min(len(df), i + a.after + 1)
        draw_candles(ax, df, lo, hi)
        ax.axhline(r.price, color="#534AB7", linestyle="--", linewidth=1.1)
        ax.axvspan(i - 0.5, i + 0.5, color="#EF9F27", alpha=0.18, zorder=0)
        ax.text(lo, r.price, f" {r['name']}", color="#534AB7", fontsize=9,
                va="bottom" if r.side == BUY else "top")
        ticks = list(range(lo, hi, 12))
        ax.set_xticks(ticks)
        ax.set_xticklabels([local[t].strftime("%H:%M") for t in ticks], fontsize=8)
        ax.set_xlim(lo - 1, hi)
        ax.grid(alpha=0.12)
        ax.set_title(f"#{num}   {local[i].strftime('%a %d %b  %H:%M')} ET   {r['name']} ({r.side})",
                     fontsize=11, loc="left")
    fig.text(0.01, 0.004, "Dashed line = liquidity level · orange band = candle that first trades through it · "
             "5-minute NQ, times ET", fontsize=9, color="#5F5E5A")
    fig.tight_layout(rect=(0, 0.01, 1, 1))
    fig.savefig(a.out)

    key = sample[["name", "side", "price", "taken_bar", "closed_beyond", "reclaim_bars", "depth", "category"]].copy()
    key.insert(0, "time_et", local[key["taken_bar"].astype(int).to_numpy()].strftime("%Y-%m-%d %H:%M"))
    key.to_csv(a.out.rsplit(".", 1)[0] + "_key.csv")
    print(f"wrote {a.out} and answer key")


if __name__ == "__main__":
    main()
