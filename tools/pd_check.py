"""Premium/discount check: where do FVG near-edge entries sit, and does the half matter?

Two range definitions (see ict/premium_discount.py); results at a fixed 1R
and with the strict pool target. NOT a backtest.

Usage:
    python -m tools.pd_check "data/nq/NQ_5min*.csv"
"""
import glob, sys
import numpy as np, pandas as pd
from ict.data import load_csv
from ict.draw import find_target, pools_as_of
from ict.model import build_context, simulate_trade, sweep_choch_sequences
from ict.premium_discount import dealing_range, in_correct_half, position, setup_range
from ict.structure import UP
from tools.entry_check import entries_for

df = load_csv(glob.glob(sys.argv[1] if len(sys.argv) > 1 else "data/nq/NQ_5min*.csv")[0])
ctx = build_context(df)
seqs = sweep_choch_sequences(ctx)
warm = df.index.searchsorted(df.index[0] + pd.Timedelta(days=20))
seqs = seqs[seqs.sweep_bar >= warm].reset_index(drop=True)
close = df.close.to_numpy()
rows = []
for s in seqs.itertuples(index=False):
    opts, _ = entries_for(ctx, s)
    if "FVG edge (latest)" not in opts:
        continue
    entry, place, imm = opts["FVG edge (latest)"]
    up = s.direction == UP
    if not imm and ((close[place] <= entry) if up else (close[place] >= entry)):
        entry, imm = close[place], True
    lo, hi = setup_range(df, s.sweep_bar, place, s.direction)
    pos_b = position(entry, lo, hi)
    dr = dealing_range(df, ctx.swings, s.sweep_bar, place)
    pos_a = position(entry, *dr) if dr else np.nan
    risk = abs(entry - s.stop)
    t1 = entry + risk if up else entry - risk
    r1 = simulate_trade(ctx, s.direction, entry, s.stop, t1, place, 12, imm)
    tg = find_target(pools_as_of(ctx.pools, place), s.direction, entry, s.stop, 2.0)
    rp = simulate_trade(ctx, s.direction, entry, s.stop, tg["target_price"], place, 12, imm) if tg else None
    rows.append(dict(sweep_bar=s.sweep_bar, direction=s.direction, killzone=s.killzone,
                     pos_setup=pos_b, pos_dealing=pos_a,
                     ok_setup=in_correct_half(pos_b, s.direction),
                     ok_dealing=(in_correct_half(pos_a, s.direction) if not np.isnan(pos_a) else None),
                     r1=r1["r"] if r1["fill_bar"] is not None else np.nan, out1=r1["outcome"],
                     rpool=(rp["r"] if rp and rp["fill_bar"] is not None else np.nan)))
t = pd.DataFrame(rows)
# express position from the trade's side: 0 = deepest discount for longs / premium for shorts
t["depth_setup"] = np.where(t.direction == UP, t.pos_setup, 1 - t.pos_setup)
t["depth_dealing"] = np.where(t.direction == UP, t.pos_dealing, 1 - t.pos_dealing)
print(f"{len(t)} setups with an FVG near-edge entry\n")
print("Entry position in range, from the trade's side (0 = best price, 0.5 = middle, 1 = worst):")
print(t[["depth_setup", "depth_dealing"]].describe(percentiles=[.25, .5, .75]).loc[["count", "25%", "50%", "75%"]].round(2).to_string())
for col, name in [("ok_setup", "Setup move (sweep extreme -> furthest price since)"), ("ok_dealing", "Dealing range (latest tier-2 swing high/low)")]:
    print(f"\n{name}")
    for ok, g in t.groupby(col):
        f1 = g[g.r1.notna()]; w = (f1.out1 == "target").sum(); l = (f1.out1 == "stop").sum()
        fp = g[g.rpool.notna()]
        print(f"  {'correct half' if ok else 'wrong half':<13} setups {len(g):>2} | 1R: filled {len(f1):>2}, {w}/{l} W/L, total {f1.r1.sum():+.1f}R"
              f" | pool target >=2R: filled {len(fp):>2}, total {fp.rpool.sum():+.1f}R")
