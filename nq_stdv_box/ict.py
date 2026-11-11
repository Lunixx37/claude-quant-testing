"""
ICT confluence + "only 4.5 Stdv" study.

ICT zones (detected on 5-min bars built from the 1-min data, usable once the pattern's last candle closed):
  FVG  bull: low[i]  > high[i-2]  -> zone [high[i-2], low[i]]     bear: high[i] < low[i-2] -> [high[i], low[i-2]]
  OB   bull: last bearish candle i, followed by a bullish candle closing above high[i] and a bullish FVG
            (low[i+2] > high[i])  -> zone [low[i], high[i]]           bear: mirror
  RB   bull: swing low (2 bars each side) with lower wick >= 50 % of range -> zone [low, min(open,close)]
       bear: swing high with upper wick >= 50 % -> zone [max(open,close), high]
  A zone stays valid until a 5-min close beyond its far edge, at most 48 h.
  Confluence: level L touched and a valid zone of the right polarity (bearish for shorts at resistance,
  bullish for longs at support) contains L (+/- ZONE_TOL points).

Levels: box borders (00:00-open edge from inside, 08:30-open edge on the first retest after price moved
0.5 h away) and the stdv levels. Part B trades only the 4.5 levels and compares fixed vs trailing exits.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import confluence as cf     # noqa: E402
import followup as fu       # noqa: E402
import stdv_box as m        # noqa: E402

OUT = Path(__file__).parent / "results" / "ict"
ZONE_TOL = 2.5
MAX_AGE = 48 * 60           # minutes
TICK = 0.25
COST = {"limit_0.25h": 0.5, "limit_0.5h": 0.5, "momentum": 1.0}


# ----------------------------------------------------------------------------- data
def prepare(kind, start, end, first_day):
    bars = cf.load(kind)[["open", "high", "low", "close", "volume"]]
    bars = bars[(bars.index >= start) & (bars.index < end)]
    box = m.build_boxes(bars[["open", "high", "low", "close"]])
    box["atr"] = fu.daily_atr(bars).reindex(box.index)
    box["rel"] = 2 * box.h / box.atr
    box = box.dropna(subset=["atr"])
    days = []
    for day, b, s in m.session_slices(bars, box):
        if day < pd.Timestamp(first_day):
            continue
        days.append({"day": day, "b": b, "O": s.open.values, "H": s.high.values, "L": s.low.values,
                     "C": s.close.values, "T": s.index.values.astype("datetime64[m]").astype(np.int64)})
    zones = detect_zones(bars)
    return days, zones


# ----------------------------------------------------------------------------- ICT zones
def detect_zones(bars):
    b5 = bars.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    o, h, l, c = (b5[x].values for x in ("open", "high", "low", "close"))
    t = b5.index.values.astype("datetime64[m]").astype(np.int64)
    n = len(c)
    z = []   # (avail_t, lo, hi, polarity(+1 bull/-1 bear), type, last_idx)
    for i in range(2, n):
        if t[i] - t[i - 2] > 15:          # skip patterns across session breaks
            continue
        if l[i] > h[i - 2]:
            z.append((t[i] + 5, h[i - 2], l[i], 1, "FVG", i))
        if h[i] < l[i - 2]:
            z.append((t[i] + 5, h[i], l[i - 2], -1, "FVG", i))
        k = i - 2      # order block candle
        if c[k] < o[k] and c[k + 1] > o[k + 1] and c[k + 1] > h[k] and l[i] > h[k]:
            z.append((t[i] + 5, l[k], h[k], 1, "OB", i))
        if c[k] > o[k] and c[k + 1] < o[k + 1] and c[k + 1] < l[k] and h[i] < l[k]:
            z.append((t[i] + 5, l[k], h[k], -1, "OB", i))
    for i in range(2, n - 2):
        if t[i + 2] - t[i - 2] > 25:
            continue
        rng = h[i] - l[i]
        if rng <= 0:
            continue
        if h[i] > max(h[i - 1], h[i - 2], h[i + 1], h[i + 2]) and (h[i] - max(o[i], c[i])) >= 0.5 * rng:
            z.append((t[i + 2] + 5, max(o[i], c[i]), h[i], -1, "RB", i + 2))
        if l[i] < min(l[i - 1], l[i - 2], l[i + 1], l[i + 2]) and (min(o[i], c[i]) - l[i]) >= 0.5 * rng:
            z.append((t[i + 2] + 5, l[i], min(o[i], c[i]), 1, "RB", i + 2))
    zd = pd.DataFrame(z, columns=["avail", "lo", "hi", "pol", "type", "idx"])
    # invalidation: first 5-min close beyond the far edge (bear: close > hi, bull: close < lo)
    inv = np.empty(len(zd), dtype=np.int64)
    for r, (idx, lo, hi, pol, av) in enumerate(zip(zd.idx.values, zd.lo.values, zd.hi.values, zd.pol.values, zd.avail.values)):
        seg = c[idx + 1: idx + 1 + 600]
        hit = np.flatnonzero(seg > hi) if pol == -1 else np.flatnonzero(seg < lo)
        inv[r] = t[idx + 1 + hit[0]] + 5 if len(hit) else av + MAX_AGE
    zd["inv"] = np.minimum(inv, zd.avail.values + MAX_AGE)
    return zd.sort_values("avail").reset_index(drop=True)


def day_zones(zones, d):
    t0, t1 = d["T"][0] - MAX_AGE, d["T"][-1]
    a = zones.avail.values
    sl = zones.iloc[np.searchsorted(a, t0): np.searchsorted(a, t1, side="right")]
    return sl[sl.inv > d["T"][0]]


def ict_match(zd, t, level, side, kinds):
    """side -1 (short at resistance) needs bearish zone, +1 needs bullish zone."""
    pol = -1 if side == -1 else 1
    q = zd[(zd.pol == pol) & (zd.avail <= t) & (zd.inv > t) & (zd.lo - ZONE_TOL <= level) & (zd.hi + ZONE_TOL >= level)]
    if kinds != "ANY":
        q = q[q.type == kinds]
    return len(q) > 0


# ----------------------------------------------------------------------------- setups
def first_idx(mask, off=0):
    i = np.flatnonzero(mask)
    return int(i[0]) + off if len(i) else 10**9


def raw_levels(d, which):
    """list of (i0, side, level, tag)."""
    b, H, L = d["b"], d["H"], d["L"]
    out = []
    if which in ("stdv", "stdv45"):
        ks = [4.5] if which == "stdv45" else m.STDV_LEVELS
        for k in ks:
            for side, lvl in ((-1, b.mid + k * b.h), (1, b.mid - k * b.h)):
                i0 = first_idx(H >= lvl) if side == -1 else first_idx(L <= lvl)
                if i0 < 10**9:
                    out.append((i0, side, lvl, f"k{k}"))
    elif which == "box":
        if b.dir == 0:
            return out
        # opposite edge (00:00 open), approached from inside the box
        side = 1 if b.o0 < b.o830 else -1
        i0 = first_idx(L <= b.o0) if side == 1 else first_idx(H >= b.o0)
        if i0 < 10**9:
            out.append((i0, side, b.o0, "edge00"))
        # 08:30 edge: first retest after price moved 0.5h away
        e = b.o830
        up = first_idx(H >= e + 0.5 * b.h)
        dn = first_idx(L <= e - 0.5 * b.h)
        if min(up, dn) < 10**9:
            if up < dn:     # moved above -> retest from above = support
                i0 = first_idx(L[up + 1:] <= e, up + 1); side = 1
            else:
                i0 = first_idx(H[dn + 1:] >= e, dn + 1); side = -1
            if i0 < 10**9:
                out.append((i0, side, e, "edge830"))
    return out


def build_candidates(d, which, entry, conf, zd):
    O, H, L, C, T, b = d["O"], d["H"], d["L"], d["C"], d["T"], d["b"]
    out = []
    for i0, side, lvl, tag in raw_levels(d, which):
        if conf != "none" and not ict_match(zd, T[i0], lvl, side, conf):
            continue
        if entry.startswith("limit"):
            frac = float(entry.split("_")[1][:-1])
            out.append({"j": i0, "side": side, "level": lvl, "tag": tag, "entry": lvl,
                        "stop": lvl - side * frac * b.h, "limit": True})
        else:
            j = cf.momentum_trigger(O, H, L, C, i0, lvl, side)
            if j is None:
                continue
            ext = H[i0:j + 1].max() if side == -1 else L[i0:j + 1].min()
            out.append({"j": j, "side": side, "level": lvl, "tag": tag, "entry": C[j],
                        "stop": ext - side * TICK, "limit": False})
    return sorted(out, key=lambda e: e["j"])


# ----------------------------------------------------------------------------- exits (fixed + trailing)
def run_trade(d, c, exit_mode):
    H, L, C, b = d["H"], d["L"], d["C"], d["b"]
    side, entry, j = c["side"], c["entry"], c["j"]
    risk = abs(entry - c["stop"])
    stop = c["stop"]
    tp = None
    if exit_mode.endswith("R") and exit_mode[0].isdigit():
        tp = entry + side * float(exit_mode[:-1]) * risk
    elif exit_mode in ("mid", "be_mid"):
        tp = b.mid
        if (tp - entry) * side <= 0:
            return None
    best = entry
    for i in range(j, len(C)):
        if i == j and not c["limit"]:
            continue                                  # market entry at close of bar j
        if (H[i] >= stop) if side == -1 else (L[i] <= stop):
            return stop, "stop", i
        if i > j and tp is not None and ((L[i] <= tp) if side == -1 else (H[i] >= tp)):
            return tp, "target", i
        if i == j:
            continue                                  # fill bar: no trailing update (unknown order)
        best = min(best, L[i]) if side == -1 else max(best, H[i])
        fav = (entry - best) / risk if side == -1 else (best - entry) / risk
        new = None
        if exit_mode == "trail1R" and fav >= 1:
            new = best + risk if side == -1 else best - risk
        elif exit_mode == "trail2R" and fav >= 2:
            new = best + 2 * risk if side == -1 else best - 2 * risk
        elif exit_mode == "be_mid" and fav >= 1:
            new = entry
        if new is not None:
            stop = min(stop, new) if side == -1 else max(stop, new)
    return C[-1], "time", len(C) - 1


def simulate(d, cands, exit_mode, cost):
    trades, busy = [], -1
    b = d["b"]
    for c in cands:
        if c["j"] <= busy:
            continue
        risk = abs(c["entry"] - c["stop"])
        if risk < TICK or risk > 0.25 * b.atr:
            continue
        r = run_trade(d, c, exit_mode)
        if r is None:
            continue
        px, why, k = r
        pnl = c["side"] * (px - c["entry"]) - cost
        trades.append({**c, "day": d["day"], "exit": px, "why": why, "pts": pnl, "R": pnl / risk})
        busy = k
    return trades


# ----------------------------------------------------------------------------- main
def grid(days, zones, name, which_list, filters, entries, exits, confs):
    rows = []
    zcache = {i: day_zones(zones, d) for i, d in enumerate(days)}
    for which in which_list:
        for conf in confs:
            for e in entries:
                cands = {i: build_candidates(d, which, e, conf, zcache[i]) for i, d in enumerate(days)}
                for f in filters:
                    sel = [i for i, d in enumerate(days) if d["b"].rel >= f]
                    for x in exits:
                        tr = []
                        for i in sel:
                            tr += simulate(days[i], cands[i], x, COST[e])
                        tr = pd.DataFrame(tr)
                        rows.append({"Daten": name, "Level": which, "ICT": conf, "Entry": e,
                                     "Box ≥ ATR×": f, "Exit": x, **fu.summarize(tr, len(sel))})
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sets = {"NQ_2023_2025": ("NQ", "2022-12-01", "2026-01-01", "2023-01-01"),
            "CFD_2016_2022": ("CFD", "2016-11-01", "2023-01-01", "2016-11-16")}
    res = []
    for name, (kind, a, z, fd) in sets.items():
        days, zones = prepare(kind, a, z, fd)
        print(f"\n######## {name}: {len(days)} Tage, Zonen:", zones.type.value_counts().to_dict(), flush=True)
        # A) ICT confluence on box borders and stdv levels
        ga = grid(days, zones, name, ["box", "stdv"], [0.0, 0.2],
                  ["limit_0.25h", "limit_0.5h", "momentum"], ["mid", "3R"],
                  ["none", "FVG", "OB", "RB", "ANY"])
        ga["Teil"] = "A_ICT"
        print(ga.to_string(index=False), flush=True)
        # B) only 4.5 levels, fixed vs trailing exits
        gb = grid(days, zones, name, ["stdv45"], [0.0, 0.2, 0.3],
                  ["limit_0.25h", "limit_0.5h", "momentum"],
                  ["2R", "3R", "5R", "mid", "trail1R", "trail2R", "be_mid"], ["none", "ANY"])
        gb["Teil"] = "B_45"
        print(gb.to_string(index=False), flush=True)
        res += [ga, gb]
    out = pd.concat(res)
    out.to_csv(OUT / "ict_and_45_grid.csv", index=False)


if __name__ == "__main__":
    main()
