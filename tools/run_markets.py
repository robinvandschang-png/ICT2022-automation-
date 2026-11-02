"""Run the v1 model (unchanged rules) across many CME futures. NOT a validated backtest.

Data: one 5m CSV per market, named <SYMBOL>_5min.csv in --root.
Each market is trimmed to its actively traded days (daily volume >= `min_vol_share`
of its median day), because some files come from a single contract that becomes
illiquid near expiry. Markets with fewer than `min_days` active days are skipped.

Usage:
    python -m tools.run_markets --root data/cme --out out/markets
"""
from __future__ import annotations

import argparse
import dataclasses
import glob
import os
from multiprocessing import Pool

import numpy as np
import pandas as pd

from ict.data import load_csv
from ict.model import ModelParams, build_context, build_trades, summarize, sweep_choch_sequences

TZ = "America/New_York"
ASSET_CLASS = {
    **{s: "Equity indices" for s in ["NQ", "ES", "YM", "RTY", "NKD"]},
    **{s: "Metals" for s in ["GC", "SI", "HG", "PL"]},
    **{s: "Energy" for s in ["CL", "NG", "HO", "RB"]},
    **{s: "Currencies" for s in ["6E", "6B", "6J", "6A", "6C", "6S", "6N", "6M"]},
    **{s: "Rates" for s in ["ZB", "ZN", "ZF", "ZT", "TN", "UB"]},
    **{s: "Agriculture" for s in ["ZC", "ZS", "ZW", "ZL", "ZM", "HE", "LE"]},
    **{s: "Crypto" for s in ["MBT", "MET"]},
}


def active_window(df: pd.DataFrame, min_vol_share: float = 0.2) -> pd.DataFrame:
    """Trim to the first..last day whose volume is >= min_vol_share x the median day."""
    day = df.index.tz_convert(TZ).normalize()
    vol = df["volume"].groupby(day).sum()
    vol = vol[vol > 0]
    active = vol[vol >= min_vol_share * vol.median()].index
    if len(active) == 0:
        return df.iloc[:0]
    keep = (day >= active[0]) & (day <= active[-1])
    out = df[keep]
    # drop leading bars with no range (no trading yet)
    first = np.argmax((out["high"] > out["low"]).to_numpy())
    return out.iloc[first:]


def variants(v1: ModelParams) -> dict:
    return {
        "v1 (London + NY AM)": v1,
        "v1 all hours": dataclasses.replace(v1, killzones=None),
        "v1 all hours, 1R target": dataclasses.replace(v1, killzones=None, target_rule="fixed", fixed_rr=1.0),
    }


def run_market(args) -> dict:
    path, warmup_days, min_days = args
    sym = os.path.basename(path).split("_")[0]
    df = active_window(load_csv(path))
    days = df.index.tz_convert(TZ).normalize().nunique() if len(df) else 0
    if days < min_days:
        return {"sym": sym, "skipped": f"only {days} active days"}
    ctx = build_context(df)
    seqs = sweep_choch_sequences(ctx)
    warm = df.index.searchsorted(df.index[0] + pd.Timedelta(days=warmup_days))
    seqs = seqs[seqs["sweep_bar"] >= warm].reset_index(drop=True)
    out = {"sym": sym, "days": days - warmup_days * 5 // 7, "sequences": len(seqs), "results": {}, "trades": []}
    for name, p in variants(ModelParams.from_config()).items():
        t = build_trades(ctx, p, seqs) if len(seqs) else pd.DataFrame()
        out["results"][name] = summarize(t) if len(t) else summarize(pd.DataFrame({"status": []}))
        if len(t):
            o = t[t["status"] == "order"].copy()
            o["sym"], o["variant"] = sym, name
            out["trades"].append(o)
    return out


def bias_report(f: pd.DataFrame, rng, n_boot: int = 5000) -> None:
    """Same trades split by whether they went with the 1H / 4H bias (gate off when the trades were made)."""
    print("\nBy higher-timeframe bias at the setup (net of costs; 95% range of the with-minus-against "
          "difference from resampling days):")
    rows = []
    for v in ["v1 all hours", "v1 all hours, 1R target"]:
        g = f[f["variant"] == v]
        for rule in ["1h", "4h", "both"]:
            if rule == "both":
                with_ = (g["bias_1h"] == g["direction"]) & (g["bias_4h"] == g["direction"])
            else:
                with_ = g[f"bias_{rule}"] == g["direction"]
            a, b = g[with_], g[~with_]
            days = sorted(set(g["day"]))
            idx = {d: i for i, d in enumerate(days)}
            def by_day(x):
                s = np.zeros(len(days)); c = np.zeros(len(days))
                np.add.at(s, x["day"].map(idx).to_numpy(), x["net_r"].to_numpy())
                np.add.at(c, x["day"].map(idx).to_numpy(), 1)
                return s, c
            sa, ca = by_day(a); sb, cb = by_day(b)
            pick = rng.integers(0, len(days), (n_boot, len(days)))
            diff = sa[pick].sum(1) / np.maximum(ca[pick].sum(1), 1) - sb[pick].sum(1) / np.maximum(cb[pick].sum(1), 1)
            lo, hi = np.percentile(diff, [2.5, 97.5])
            rows.append({"variant": v, "bias": rule, "with: trades": len(a), "with: avg R net": round(a["net_r"].mean(), 2),
                         "against/none: trades": len(b), "against/none: avg R net": round(b["net_r"].mean(), 2),
                         "difference 95% range": f"{lo:+.2f} to {hi:+.2f}", "with better in": f"{(diff > 0).mean() * 100:.0f}%"})
    print(pd.DataFrame(rows).set_index(["variant", "bias"]).to_string())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/cme")
    ap.add_argument("--out", default="out/markets")
    ap.add_argument("--warmup-days", type=int, default=10)
    ap.add_argument("--min-days", type=int, default=25)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()

    files = sorted(glob.glob(f"{a.root}/*_5min.csv"))
    with Pool(a.workers) as pool:
        results = pool.map(run_market, [(f, a.warmup_days, a.min_days) for f in files])

    skipped = [r for r in results if "skipped" in r]
    done = [r for r in results if "skipped" not in r]
    rows = []
    for r in done:
        for name, s in r["results"].items():
            rows.append({"sym": r["sym"], "class": ASSET_CLASS.get(r["sym"], "Other"), "days": r["days"],
                         "sequences": r["sequences"], "variant": name, **s})
    t = pd.DataFrame(rows)
    trades = pd.concat([x for r in done for x in r["trades"]], ignore_index=True) if done else pd.DataFrame()
    t.to_csv(f"{a.out}_summary.csv", index=False)
    if len(trades):
        trades["time"] = pd.DatetimeIndex(trades["time"]).tz_convert(TZ).strftime("%Y-%m-%d %H:%M")
        trades.to_csv(f"{a.out}_trades.csv", index=False)

    print(f"Markets run: {len(done)}; skipped: " + ", ".join(f"{r['sym']} ({r['skipped']})" for r in skipped))
    for name in variants(ModelParams()).keys():
        v = t[t["variant"] == name]
        tot = v[["sequences", "orders", "filled", "wins", "losses", "open at day end", "total R"]].sum()
        wr = tot["wins"] / max(tot["wins"] + tot["losses"], 1) * 100
        print(f"\n== {name}: {int(tot['filled'])} trades, {int(tot['wins'])} W / {int(tot['losses'])} L "
              f"({wr:.0f}%), total {tot['total R']:+.1f}R, avg {tot['total R'] / max(tot['filled'], 1):+.2f}R")
        by_class = v.groupby("class")[["days", "sequences", "filled", "wins", "losses", "total R"]].sum()
        print(by_class.to_string())
    v1 = t[t["variant"] == "v1 (London + NY AM)"].set_index("sym")
    print("\nv1 per market:")
    print(v1[["class", "days", "sequences", "orders", "filled", "wins", "losses", "total R"]].to_string())
    if len(trades):
        net_report(trades, a.out)


def net_report(trades: pd.DataFrame, out: str, commission: float = 4.5, micro_commission: float = 1.0,
               slippage_ticks: float = 1.0, n_boot: int = 5000) -> None:
    """Gross vs net of costs, with a 95% range from resampling whole trading days."""
    from ict.contracts import cost_in_r

    f = trades[trades["fill_bar"].notna()].copy()
    f["cost_r"] = [cost_in_r(s, r, micro_commission if s in ("MBT", "MET") else commission, slippage_ticks)
                   for s, r in zip(f["sym"], f["risk_pts"])]
    f["net_r"] = f["r"] - f["cost_r"]
    f["day"] = f["time"].str[:10]
    f.to_csv(f"{out}_trades_net.csv", index=False)
    rng = np.random.default_rng(0)
    print(f"\nNet of costs (${commission} commission + {slippage_ticks:g} tick slippage per trade); "
          "95% range from resampling trading days:")
    rows = []
    for v, g in f.groupby("variant", sort=False):
        days = g.groupby("day")["net_r"].agg(["sum", "count"])
        idx = rng.integers(0, len(days), (n_boot, len(days)))
        means = days["sum"].to_numpy()[idx].sum(1) / days["count"].to_numpy()[idx].sum(1)
        lo, hi = np.percentile(means, [2.5, 97.5])
        rows.append({"variant": v, "trades": len(g), "avg R gross": round(g["r"].mean(), 2),
                     "avg cost R": round(g["cost_r"].mean(), 2), "avg R net": round(g["net_r"].mean(), 2),
                     "net 95% range": f"{lo:+.2f} to {hi:+.2f}", "share > 0": f"{(means > 0).mean() * 100:.0f}%"})
    print(pd.DataFrame(rows).set_index("variant").to_string())
    bias_report(f, rng, n_boot)
    by = f.assign(cls=f["sym"].map(ASSET_CLASS)).groupby(["variant", "cls"]).agg(
        trades=("net_r", "size"), avg_cost_R=("cost_r", "mean"), net_R=("net_r", "sum")).round(2)
    print("\nNet R by asset class:")
    print(by.unstack(0).to_string())


if __name__ == "__main__":
    main()
