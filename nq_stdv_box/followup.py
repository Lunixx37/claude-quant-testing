"""
Follow-up study on the NQ Stdv Box.

  A) Tiny-box filter      : box range / ATR14 (daily ETH range, previous 14 days) >= threshold
  B) Entries x targets    : aggressive limit at level (stop 0.25h / 0.5h beyond) or momentum entry,
                            targets 2R/3R/5R/8R or structural (mid / box edge on that side)
  C) Box direction        : bearish box = 00:00 open ABOVE 08:30 open; win-rate by (box dir, trade side)
  D) First reaction       : first level event of the day (opposite box edge or first 2.0 level beyond the
                            08:30 edge) -> rejection vs break; do later setups aligned with that bias do better?
  E) Old levels as POI    : box edges / mid / stdv levels from the previous 1-3 days, reaction vs fake levels

NQ 2023-2025 = discovery, NAS100 CFD 2016-2022 = out-of-sample check.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import stdv_box as m        # noqa: E402
import confluence as cf     # noqa: E402

OUT = Path(__file__).parent / "results" / "followup"
LEVELS = m.STDV_LEVELS
BOX_FILTERS = [0.0, 0.10, 0.20, 0.30]
ENTRIES = ["limit_0.25h", "limit_0.5h", "momentum"]
TARGETS = ["2R", "3R", "5R", "8R", "mid", "edge"]
COST = {"limit_0.25h": 0.5, "limit_0.5h": 0.5, "momentum": 1.0}
TICK = 0.25


# ----------------------------------------------------------------------------- data
def daily_atr(bars):
    key = (bars.index + pd.Timedelta("6h")).normalize()
    g = bars.groupby(key)
    rng = g.high.max() - g.low.min()
    return rng.rolling(14).mean().shift(1)


def prepare(kind, start, end):
    bars = cf.load(kind)
    bars = bars[(bars.index >= start) & (bars.index < end)]
    box = m.build_boxes(bars[["open", "high", "low", "close"]])
    box["atr"] = daily_atr(bars).reindex(box.index)
    box["rel"] = 2 * box.h / box.atr
    box = box.dropna(subset=["atr"])
    sess = m.session_slices(bars, box)
    days = []
    for day, b, s in sess:
        days.append({"day": day, "b": b, "O": s.open.values, "H": s.high.values, "L": s.low.values,
                     "C": s.close.values})
    return days, box


# ----------------------------------------------------------------------------- trade engine
def first_idx(mask, offset=0):
    i = np.flatnonzero(mask)
    return i[0] + offset if len(i) else 10**9


def candidates(d, entry):
    """All setups of one day for an entry type: list of dicts sorted by entry bar."""
    b, O, H, L, C = d["b"], d["O"], d["H"], d["L"], d["C"]
    out = []
    for k in LEVELS:
        for side, lvl in ((-1, b.mid + k * b.h), (1, b.mid - k * b.h)):
            i0 = first_idx(H >= lvl) if side == -1 else first_idx(L <= lvl)
            if i0 >= 10**9:
                continue
            if entry.startswith("limit"):
                frac = float(entry.split("_")[1][:-1])
                out.append({"j": i0, "side": side, "k": k, "level": lvl, "entry": lvl,
                            "stop": lvl - side * frac * b.h, "limit": True})
            else:
                j = cf.momentum_trigger(O, H, L, C, i0, lvl, side)
                if j is None:
                    continue
                ext = H[i0:j + 1].max() if side == -1 else L[i0:j + 1].min()
                out.append({"j": j, "side": side, "k": k, "level": lvl, "entry": C[j],
                            "stop": ext - side * TICK, "limit": False, "i0": i0})
    return sorted(out, key=lambda e: e["j"])


def target_price(c, b, target):
    risk = abs(c["entry"] - c["stop"])
    if target.endswith("R"):
        return c["entry"] + c["side"] * float(target[:-1]) * risk
    if target == "mid":
        return b.mid
    if target == "edge":                       # box edge on the side of the trade's level
        return b.mid - c["side"] * b.h
    raise ValueError(target)


def simulate(d, cands, target, cost):
    H, L, C, b = d["H"], d["L"], d["C"], d["b"]
    trades, busy = [], -1
    for c in cands:
        j, side = c["j"], c["side"]
        if j <= busy:
            continue
        risk = abs(c["entry"] - c["stop"])
        if risk < TICK or risk > 0.25 * b.atr:           # absurdly wide stops are skipped
            continue
        tp = target_price(c, b, target)
        if (tp - c["entry"]) * side <= 0:
            continue
        s0 = j if c["limit"] else j + 1                    # limit: stop may already hit on the fill bar
        js = first_idx((H[s0:] >= c["stop"]) if side == -1 else (L[s0:] <= c["stop"]), s0)
        jt = first_idx((L[j + 1:] <= tp) if side == -1 else (H[j + 1:] >= tp), j + 1)
        if js == jt == 10**9:
            k_exit, px, why = len(C) - 1, C[-1], "time"
        elif js <= jt:
            k_exit, px, why = js, c["stop"], "stop"
        else:
            k_exit, px, why = jt, tp, "target"
        pnl = side * (px - c["entry"]) - cost
        trades.append({**c, "day": d["day"], "exit": px, "why": why, "pts": pnl, "R": pnl / risk,
                       "risk": risk, "rr": abs(tp - c["entry"]) / risk, "box_dir": b.dir,
                       "rel": b.rel, "exit_j": k_exit})
        busy = k_exit
    return trades


def summarize(tr, n_days=None):
    if len(tr) == 0:
        return {"n": 0}
    r = tr.R
    gp, gl = tr.pts[tr.pts > 0].sum(), -tr.pts[tr.pts < 0].sum()
    eq = r.cumsum()
    res = {"n": len(tr), "Win %": round((tr.pts > 0).mean() * 100, 1), "Ø R": round(r.mean(), 3),
           "t": round(r.mean() / r.std(ddof=1) * np.sqrt(len(r)), 2) if len(r) > 2 else np.nan,
           "Σ R": round(r.sum(), 1), "PF": round(gp / gl, 2) if gl else np.inf,
           "MaxDD R": round((eq - eq.cummax()).min(), 1)}
    if n_days:
        res["Tage"] = n_days
    return res


def run_grid(days, name):
    rows, all_tr = [], {}
    cache = {e: [candidates(d, e) for d in days] for e in ENTRIES}
    for f in BOX_FILTERS:
        sel = [i for i, d in enumerate(days) if d["b"].rel >= f]
        for e in ENTRIES:
            for t in TARGETS:
                tr = []
                for i in sel:
                    tr += simulate(days[i], cache[e][i], t, COST[e])
                tr = pd.DataFrame(tr)
                all_tr[(f, e, t)] = tr
                rows.append({"Daten": name, "Box ≥ ATR×": f, "Entry": e, "Target": t,
                             **summarize(tr, len(sel))})
    return pd.DataFrame(rows), all_tr, cache


# ----------------------------------------------------------------------------- C) box direction
def by_box_direction(tr):
    t = tr[tr.box_dir != 0].copy()
    t["Box"] = np.where(t.box_dir < 0, "bearish (00:00 über 08:30)", "bullish (00:00 unter 08:30)")
    t["Trade"] = np.where(t.side > 0, "Long", "Short")
    g = t.groupby(["Box", "Trade"]).apply(lambda x: pd.Series(summarize(x)), include_groups=False)
    return g[["n", "Win %", "Ø R", "t"]]


# ----------------------------------------------------------------------------- D) first reaction
def first_reaction(d, thr=0.5):
    """Return (bias, resolve_bar, info). bias +1 bullish / -1 bearish / 0 none."""
    b, H, L = d["b"], d["H"], d["L"]
    if b.dir == 0:
        return 0, None, None
    # candidate first events: opposite box edge (o0) and 2.0 level beyond the 08:30 edge
    opp = b.o0
    opp_side = 1 if opp < b.o830 else -1               # +1: level is BELOW price (support) -> touch from above
    beyond = b.mid + b.dir * 2.0 * b.h
    beyond_side = -b.dir                                # level above price -> resistance (-1)
    evs = []
    for lvl, s, name in ((opp, opp_side, "Box-Kante (00:00 Open)"), (beyond, beyond_side, "2.0 hinter 08:30-Kante")):
        i0 = first_idx(L <= lvl) if s == 1 else first_idx(H >= lvl)
        evs.append((i0, lvl, s, name))
    i0, lvl, s, name = min(evs)
    if i0 >= 10**9:
        return 0, None, None
    # first passage after touch: back by thr*h (rejection) or beyond by thr*h (break)
    d_ = thr * b.h
    if s == 1:      # support from above
        jr = first_idx(H[i0:] >= lvl + d_, i0)
        jb = first_idx(L[i0:] <= lvl - d_, i0)
    else:
        jr = first_idx(L[i0:] <= lvl - d_, i0)
        jb = first_idx(H[i0:] >= lvl + d_, i0)
    if jr == jb == 10**9:
        return 0, None, None
    if jr < jb:
        return s, jr, (name, "Rejection")          # support rejected -> bullish, resistance rejected -> bearish
    if jb < jr:
        return -s, jb, (name, "Break")
    return 0, None, None                            # both in the same bar: ambiguous


def reaction_study(days, cache, entry, target, box_filter):
    rows = []
    for i, d in enumerate(days):
        if d["b"].rel < box_filter:
            continue
        bias, jres, info = first_reaction(d)
        if bias == 0:
            continue
        later = [c for c in cache[entry][i] if c["j"] > jres]
        for t in simulate(d, later, target, COST[entry]):
            t["bias"] = bias
            t["event"], t["reaction"] = info
            rows.append(t)
    tr = pd.DataFrame(rows)
    if tr.empty:
        return tr, pd.DataFrame()
    tr["Ausrichtung"] = np.where(tr.side == tr.bias, "mit Bias", "gegen Bias")
    g = tr.groupby(["event", "reaction", "Ausrichtung"]).apply(lambda x: pd.Series(summarize(x)), include_groups=False)
    g_all = tr.groupby("Ausrichtung").apply(lambda x: pd.Series(summarize(x)), include_groups=False)
    g_all.index = pd.MultiIndex.from_tuples([("ALLE", "", a) for a in g_all.index])
    return tr, pd.concat([g_all, g])[["n", "Win %", "Ø R", "t"]]


def reaction_day_stats(days, box_filter):
    """Simple outcome: where does the session close relative to the box, given the first reaction?"""
    rows = []
    for d in days:
        if d["b"].rel < box_filter:
            continue
        bias, jres, info = first_reaction(d)
        if bias == 0:
            continue
        b = d["b"]
        rows.append({"event": info[0], "reaction": info[1], "bias": bias,
                     "close_with_bias": (d["C"][-1] - d["C"][jres]) * bias > 0,
                     "move_R": (d["C"][-1] - d["C"][jres]) * bias / b.h})
    t = pd.DataFrame(rows)
    return t.groupby(["event", "reaction"]).agg(Tage=("bias", "size"),
                                                **{"Close in Bias-Richtung %": ("close_with_bias", lambda x: round(x.mean() * 100, 1))},
                                                **{"Ø Move bis Close (h)": ("move_R", lambda x: round(x.mean(), 2))})


# ----------------------------------------------------------------------------- E) old levels as POI
def old_levels(box, day, lookback, box_filter):
    prev = box[box.index < day].tail(lookback)
    lv = []
    for age, (_, b) in enumerate(prev[::-1].iterrows(), start=1):
        if b.rel < box_filter or b.h <= 0:
            continue
        lv += [(b.top, "Box-Kante", age), (b.bot, "Box-Kante", age), (b.mid, "Mitte", age)]
        for k in LEVELS:
            lv += [(b.mid + k * b.h, "Stdv", age), (b.mid - k * b.h, "Stdv", age)]
    return lv


def poi_study(days, box, lookback=3, box_filter=0.10, n_fake=5, seed=1):
    """
    For each old level (and fake levels = old level shifted by +/- U(0.03,0.08)*ATR): first touch
    in today's 08:30-16:00 session, approached from the side of the 08:30 open.
    Reaction = first passage: rejection by X before break by X (X = 0.05*ATR, also 0.1*ATR).
    Fade trade = limit at level, stop X beyond, target 2R / 3R.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for d in days:
        b, O, H, L, C = d["b"], d["O"], d["H"], d["L"], d["C"]
        atr = b.atr
        lv = old_levels(box, d["day"], lookback, box_filter)
        lv_f = []
        for p, typ, age in lv:
            for _ in range(n_fake):
                lv_f.append((p + rng.choice([-1, 1]) * rng.uniform(0.03, 0.08) * atr, typ, age))
        for real, levels in ((True, lv), (False, lv_f)):
            for p, typ, age in levels:
                if abs(p - O[0]) < 0.02 * atr:          # level sits right at the 08:30 price -> skip
                    continue
                side = 1 if p < O[0] else -1             # +1: support (long fade), -1: resistance
                i0 = first_idx(L <= p) if side == 1 else first_idx(H >= p)
                if i0 >= 10**9:
                    continue
                r = {"real": real, "type": typ, "age": age}
                for xf in (0.05, 0.10):
                    x = xf * atr
                    if side == 1:
                        jr, jb = first_idx(H[i0:] >= p + x, i0), first_idx(L[i0:] <= p - x, i0)
                    else:
                        jr, jb = first_idx(L[i0:] <= p - x, i0), first_idx(H[i0:] >= p + x, i0)
                    r[f"rej_{xf}"] = np.nan if jr == jb else float(jr < jb)
                # fade trade, limit at level, stop 0.05 ATR
                x = 0.05 * atr
                stop = p - side * x
                js = first_idx((L[i0:] <= stop) if side == 1 else (H[i0:] >= stop), i0)
                for rr in (2, 3):
                    tp = p + side * rr * x
                    jt = first_idx((H[i0 + 1:] >= tp) if side == 1 else (L[i0 + 1:] <= tp), i0 + 1)
                    if js == jt == 10**9:
                        px = C[-1]
                    elif js <= jt:
                        px = stop
                    else:
                        px = tp
                    r[f"R_{rr}"] = (side * (px - p) - 0.5) / x
                rows.append(r)
    t = pd.DataFrame(rows)

    def agg(g):
        return pd.Series({"Touches": len(g),
                          "Rejection % (0.05 ATR)": round(g["rej_0.05"].mean() * 100, 1),
                          "Rejection % (0.10 ATR)": round(g["rej_0.1"].mean() * 100, 1),
                          "Fade 2R Ø R": round(g.R_2.mean(), 3), "Fade 3R Ø R": round(g.R_3.mean(), 3)})

    t["Level"] = np.where(t.real, "echt", "fake")
    res = t.groupby(["type", "Level"]).apply(agg, include_groups=False)
    res_age = t.groupby(["age", "Level"]).apply(agg, include_groups=False)
    return res, res_age


# ----------------------------------------------------------------------------- main
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sets = {"NQ_2023_2025": ("NQ", "2022-12-01", "2026-01-01"),
            "CFD_2016_2022": ("CFD", "2016-11-01", "2023-01-01")}
    grids = []
    for name, (kind, a, z) in sets.items():
        days, box = prepare(kind, a, z)
        days = [d for d in days if d["day"] >= (pd.Timestamp("2023-01-01") if kind == "NQ" else pd.Timestamp("2016-11-16"))]
        print(f"\n################ {name}: {len(days)} Tage")

        # A + B
        g, all_tr, cache = run_grid(days, name)
        grids.append(g)
        g.to_csv(OUT / f"{name}_grid.csv", index=False)
        print(g.sort_values("Ø R", ascending=False).head(12).to_string(index=False))

        # C box direction (several configs)
        cdir = []
        for key in [(0.2, "limit_0.25h", "mid"), (0.2, "limit_0.5h", "3R"), (0.2, "momentum", "3R"),
                    (0.0, "limit_0.25h", "mid"), (0.0, "momentum", "2R")]:
            x = by_box_direction(all_tr[key])
            x.insert(0, "Config", f"Box≥{key[0]} {key[1]} {key[2]}")
            cdir.append(x)
        cdir = pd.concat(cdir)
        cdir.to_csv(OUT / f"{name}_box_direction.csv")
        print(cdir.to_string())

        # D first reaction
        dstat = reaction_day_stats(days, 0.10)
        dstat.to_csv(OUT / f"{name}_first_reaction_days.csv")
        print(dstat.to_string())
        dd = []
        for e, t in (("limit_0.25h", "mid"), ("limit_0.5h", "3R"), ("momentum", "3R")):
            _, x = reaction_study(days, cache, e, t, 0.10)
            x.insert(0, "Config", f"Box≥0.1 {e} {t}")
            dd.append(x)
        dd = pd.concat(dd)
        dd.to_csv(OUT / f"{name}_first_reaction_trades.csv")
        print(dd.to_string())

        # E old levels
        for lb, bf in ((3, 0.10), (1, 0.10)):
            r1, r2 = poi_study(days, box, lookback=lb, box_filter=bf)
            r1.to_csv(OUT / f"{name}_poi_lb{lb}_by_type.csv")
            r2.to_csv(OUT / f"{name}_poi_lb{lb}_by_age.csv")
            print(f"POI lookback={lb}"); print(r1.to_string()); print(r2.to_string())

    pd.concat(grids).to_csv(OUT / "grid_all.csv", index=False)


if __name__ == "__main__":
    main()
