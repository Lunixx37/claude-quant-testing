"""
K2 optimisation: tighter stops, larger targets, and filters that keep aggressive variants valid.

Population: K2 entries (reclaim of the 3.5 level with momentum candle, prior opposite reclaim), up to 6 touches
per level and day ("K2+"; ord < 3 = K2 base). For every entry the net R is computed for every stop model x exit
model (conservative fills, costs as before).

  stops : struct_min (sweep extreme, >= 0.02 ATR = current K2) | struct | half_struct (half the sweep distance)
          bar (extreme of the reclaim candle) | fixed 0.010 / 0.015 / 0.020 / 0.030 / 0.060 ATR
  exits : 2R 3R 5R 8R 12R | mid (current K2) | far box edge | opposite 2.0 level | opposite 3.5 level | EOD
          be_* : target as named, stop to break-even once the box mid is reached
          half_*: half the position out at the mid, rest as be_*
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, str(Path(__file__).parent))
import search_events as sev    # noqa: E402
import ict                     # noqa: E402

TICK = 0.25
STOPS = ["struct_min", "struct", "half_struct", "bar", "fix0.010", "fix0.015", "fix0.020", "fix0.030", "fix0.060"]
BASE_EXITS = ["2R", "3R", "5R", "8R", "12R", "mid", "far_edge", "opp2", "opp35", "EOD", "be_far_edge", "be_opp2", "be_opp35", "be_EOD"]
EXITS = BASE_EXITS + ["half_far_edge", "half_opp2", "half_opp35", "half_EOD"]


@njit(cache=True)
def sim2(H, L, C, j, side, entry, stop0, tp, be_px):
    """Market entry at close of bar j. tp nan = no target. be_px nan = no break-even rule."""
    stop = stop0
    n = len(C)
    for i in range(j + 1, n):
        if side == 1:
            if L[i] <= stop:
                return stop, i
            if not np.isnan(tp) and H[i] >= tp:
                return tp, i
            if not np.isnan(be_px) and stop < entry and H[i] >= be_px:
                stop = entry
                if L[i] <= stop:
                    return stop, i
        else:
            if H[i] >= stop:
                return stop, i
            if not np.isnan(tp) and L[i] <= tp:
                return tp, i
            if not np.isnan(be_px) and stop > entry and L[i] <= be_px:
                stop = entry
                if H[i] >= stop:
                    return stop, i
    return C[n - 1], n - 1


def build(kind, start, end, first_day, shift=0.0):
    days, zones = sev.prepare(kind, start, end, first_day)
    rows = []
    for di, d in enumerate(days):
        b, O, H, L, C, T, V = d["b"], d["O"], d["H"], d["L"], d["C"], d["T"], d["V"]
        atr, h, mid = b.atr, b.h, b.mid
        cost = 1.0 if kind == "NQ" else 0.0032 * atr
        thr = TICK if kind == "NQ" else 0.0008 * atr
        zd = ict.day_zones(zones, d)
        z_av, z_inv, z_lo, z_hi, z_pol = (zd[c].values for c in ("avail", "inv", "lo", "hi", "pol"))
        evs = []
        for name, lvl, grp in sev.levels_of(b, shift):
            for side in (1, -1):
                S, R, E = sev.find_events(O, H, L, C, lvl, side, sev.REARM * atr, 10, 6, thr)
                for k in range(6):
                    if S[k] < 0:
                        break
                    evs.append((name, lvl, grp, side, k, int(S[k]), int(R[k]), E[k]))
        recl = [(e[6], e[3]) for e in evs if e[6] >= 0]
        for name, lvl, grp, side, k, s, r, ext in evs:
            if grp != "l35" or r < 1 or r >= len(C) - 1:
                continue
            if not ((C[r] > H[r - 1] and C[r] > O[r]) if side == 1 else (C[r] < L[r - 1] and C[r] < O[r])):
                continue
            n_opp = sum(1 for rr, sd in recl if rr < s and sd == -side)
            if n_opp == 0:
                continue
            entry = C[r]
            if (mid - entry) * side <= 0:
                continue
            p = max(s - 1, 0)
            sdv = d["sd"][p]
            zm = (z_pol == side) & (z_av <= T[s]) & (z_inv > T[s]) & (z_lo - ict.ZONE_TOL <= lvl) & (z_hi + ict.ZONE_TOL >= lvl)
            vol_base = V[max(r - 20, 0):r].mean() if r > 0 else np.nan
            sstruct = ext - side * TICK
            barx = (L[r] if side == 1 else H[r]) - side * TICK
            rec = {"di": di, "day": d["day"], "bar": r, "side": side, "ord": k, "atr": atr, "rel": b.rel,
                   "with_dir": side == b.dir, "ict": bool(zm.any()),
                   "z": (lvl - d["vw"][p]) / sdv * side if sdv > 0 else 0.0,
                   "depth": abs(lvl - ext) / atr, "reclaim_bars": r - s,
                   "body": abs(C[r] - O[r]) / atr, "close_dist": abs(entry - lvl) / atr,
                   "vol_ratio": V[r] / vol_base if vol_base and vol_base > 0 else np.nan,
                   "n_opp": n_opp, "n_same": sum(1 for rr, sd in recl if rr < s and sd == side),
                   "rr_mid_struct": abs(mid - entry) / abs(entry - sstruct)}
            stops = {"struct_min": (min(sstruct, entry - 0.02 * atr) if side == 1 else max(sstruct, entry + 0.02 * atr)),
                     "struct": sstruct, "half_struct": entry - 0.5 * (entry - sstruct), "bar": barx}
            for f in (0.010, 0.015, 0.020, 0.030, 0.060):
                stops[f"fix{f:.3f}"] = entry - side * f * atr
            tps = {"mid": mid, "far_edge": mid + side * h, "opp2": mid + side * 2 * h, "opp35": mid + side * 3.5 * h, "EOD": np.nan}
            for si, sn in enumerate(STOPS):
                stop = stops[sn]
                risk = abs(entry - stop)
                rec[f"risk_{si}"] = risk / atr
                res = {}
                if risk < TICK:
                    for xn in EXITS:
                        rec[f"o_{si}_{xn}"] = np.nan
                        rec[f"x_{si}_{xn}"] = -1
                    continue
                for xn in BASE_EXITS:
                    if xn.endswith("R") and xn[0].isdigit():
                        px, xb = sim2(H, L, C, r, side, entry, stop, entry + side * float(xn[:-1]) * risk, np.nan)
                    elif xn.startswith("be_"):
                        px, xb = sim2(H, L, C, r, side, entry, stop, tps[xn[3:]], mid)
                    else:
                        px, xb = sim2(H, L, C, r, side, entry, stop, tps[xn], np.nan)
                    res[xn] = ((side * (px - entry) - cost) / risk, xb)
                for xn in ("far_edge", "opp2", "opp35", "EOD"):
                    res["half_" + xn] = (0.5 * res["mid"][0] + 0.5 * res["be_" + xn][0], res["be_" + xn][1])
                for xn in EXITS:
                    rec[f"o_{si}_{xn}"], rec[f"x_{si}_{xn}"] = res[xn]
            rows.append(rec)
    ev = pd.DataFrame(rows).sort_values(["di", "bar"]).reset_index(drop=True)
    return ev, len(days)


def take(ev, si, xn, mask=None, maxord=6):
    """Trades of one stop/exit combination, one position at a time."""
    m = (ev.ord.values < maxord) & ~np.isnan(ev[f"o_{si}_{xn}"].values)
    if mask is not None:
        m &= mask
    t = ev[m]
    keep, cur, busy = [], -1, -1
    for i, (di, bar, xb) in enumerate(zip(t.di.values, t.bar.values, t[f"x_{si}_{xn}"].values)):
        if di != cur:
            cur, busy = di, -1
        if bar > busy:
            keep.append(i)
            busy = xb
    t = t.iloc[keep]
    return t, t[f"o_{si}_{xn}"].values


def stat(t, r, nd):
    if len(r) == 0:
        return {"n": 0}
    d = np.zeros(nd)
    np.add.at(d, t.di.values, r)
    return {"n": len(r), "Tr/Wo": round(len(r) / nd * 5, 2), "Win %": round((r > 0).mean() * 100, 1),
            "Ø R": round(r.mean(), 3), "R/Wo": round(r.sum() / nd * 5, 3),
            "t": round(d.mean() / d.std(ddof=1) * np.sqrt(nd), 2) if d.std() > 0 else 0.0}


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    sets = {"CFD": ("CFD", "2016-11-01", "2023-01-01", "2016-11-16"), "NQ": ("NQ", "2022-12-01", "2026-01-01", "2023-01-01")}
    for shift in (0.0, 0.07, -0.07):
        for name, a in sets.items():
            ev, nd = build(*a, shift=shift)
            suf = "" if shift == 0 else f"_fake{shift:+.2f}"
            ev.attrs["nd"] = nd
            ev.to_pickle(out / f"k2ev_{name}{suf}.pkl")
            pd.Series({"nd": nd}).to_pickle(out / f"k2nd_{name}.pkl")
            print(name, suf, len(ev), "Events,", nd, "Tage", flush=True)
