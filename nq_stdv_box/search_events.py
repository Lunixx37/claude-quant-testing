"""
Builds the event table for the systematic strategy search (see search.py).

For every day (08:30-16:00 ET) and every level x side (box top/bottom, stdv +/-2..4.5; each as support AND
resistance) we record up to 3 "touch" events (re-armed after price closed >= 0.02 ATR away again):

  T  = limit entry at the level on the touch bar
  R  = reclaim entry: price traded through the level and a 1-min candle closes back within 10 bars
       (entry = that close)

For each event we store features known at entry time and the net R outcome for every stop model x exit model.

  stops T : 0.25h | 0.5h | 0.03 ATR | 0.06 ATR beyond the level
  stops R : struct (sweep extreme + 1 tick) | struct_min (>= 0.02 ATR) | 0.03 ATR | 0.06 ATR from entry
  exits   : 1R 1.5R 2R 3R 5R | mid | trail1R | trail2R | BE@1R->3R | BE@1R->mid      (all flat at 15:59)

Conservative fills: a limit order only fills if price trades one tick THROUGH the level; stop wins if stop
and target are inside one bar; a trailing / break-even stop that is moved inside a bar is assumed to be hit
in that same bar if the bar's opposite extreme reaches it (1-min data cannot resolve the order).

Costs: NQ futures 0.5 pt (limit) / 1.0 pt (market entry) round turn.
       CFD (lower price level 2016-2022): same cost relative to volatility = 0.0016 / 0.0032 x ATR14.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, str(Path(__file__).parent))
import confluence as cf     # noqa: E402
import followup as fu       # noqa: E402
import ict                  # noqa: E402
import stdv_box as m        # noqa: E402

TICK = 0.25
REARM = 0.02        # x ATR
NREC = 10
MAXEV = 3
STOPS_T = ["0.25h", "0.5h", "0.03atr", "0.06atr"]
STOPS_R = ["struct", "struct_min", "0.03atr", "0.06atr"]
EXITS = ["1R", "1.5R", "2R", "3R", "5R", "mid", "trail1R", "trail2R", "be_3R", "be_mid"]
#          mode, rmult
EXIT_DEF = [(0, 1.0), (0, 1.5), (0, 2.0), (0, 3.0), (0, 5.0), (1, 0.0), (2, 1.0), (2, 2.0), (3, 3.0), (4, 0.0)]


@njit(cache=True)
def find_events(O, H, L, C, lvl, side, rearm, nrec, maxev, thr):
    """side +1: support (touched from above). Returns touch bar s, reclaim bar r (-1), extreme."""
    n = len(C)
    S = np.full(maxev, -1, np.int64)
    R = np.full(maxev, -1, np.int64)
    E = np.full(maxev, np.nan)
    k = 0
    armed = (O[0] - lvl) * side >= rearm
    i = 0
    while i < n and k < maxev:
        if armed:
            touched = (L[i] <= lvl - thr) if side == 1 else (H[i] >= lvl + thr)
            if touched:
                S[k] = i
                # reclaim?
                ext = L[i] if side == 1 else H[i]
                r = -1
                through = False
                for q in range(i, min(i + nrec + 1, n)):
                    if side == 1:
                        ext = min(ext, L[q])
                        through = through or (L[q] < lvl)
                        if through and C[q] > lvl:
                            r = q
                            break
                    else:
                        ext = max(ext, H[q])
                        through = through or (H[q] > lvl)
                        if through and C[q] < lvl:
                            r = q
                            break
                R[k] = r
                E[k] = ext
                k += 1
                armed = False
        if not armed and (C[i] - lvl) * side >= rearm:
            armed = True
        i += 1
    return S, R, E


@njit(cache=True)
def sim(H, L, C, j, side, entry, stop0, mode, rmult, mid, is_limit):
    """Returns (exit price, exit bar); price nan = invalid setup."""
    risk = abs(entry - stop0)
    if risk <= 0:
        return np.nan, -1
    tp = np.nan
    if mode == 0 or mode == 3:
        tp = entry + side * rmult * risk
    elif mode == 1 or mode == 4:
        tp = mid
        if (tp - entry) * side <= 0:
            return np.nan, -1
    stop = stop0
    best = entry
    n = len(C)
    start = j if is_limit else j + 1
    for i in range(start, n):
        if side == 1:
            if L[i] <= stop:
                return stop, i
            if i > j and not np.isnan(tp) and H[i] >= tp:
                return tp, i
            if i == j:
                continue
            if H[i] > best:
                best = H[i]
            fav = (best - entry) / risk
            new = stop
            if mode == 2 and fav >= rmult:
                new = max(stop, best - rmult * risk)
            elif (mode == 3 or mode == 4) and fav >= 1.0:
                new = max(stop, entry)
            if new > stop:
                stop = new
                if L[i] <= stop:          # pessimistic: high first, then the low of the same bar hits the moved stop
                    return stop, i
        else:
            if H[i] >= stop:
                return stop, i
            if i > j and not np.isnan(tp) and L[i] <= tp:
                return tp, i
            if i == j:
                continue
            if L[i] < best:
                best = L[i]
            fav = (entry - best) / risk
            new = stop
            if mode == 2 and fav >= rmult:
                new = min(stop, best + rmult * risk)
            elif (mode == 3 or mode == 4) and fav >= 1.0:
                new = min(stop, entry)
            if new < stop:
                stop = new
                if H[i] >= stop:
                    return stop, i
    return C[n - 1], n - 1


def prepare(kind, start, end, first_day):
    bars = cf.load(kind)
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
                     "C": s.close.values, "T": s.index.values.astype("datetime64[m]").astype(np.int64),
                     "vw": s.vw_eth.values, "sd": s.sd_eth.values, "V": s.volume.values.astype(float)})
    zones = ict.detect_zones(bars[["open", "high", "low", "close"]])
    return days, zones


def levels_of(b, shift=0.0):
    """shift != 0 moves ALL levels by shift x ATR (fake-level control)."""
    out = [("edge00", b.o0, "edge00"), ("edge830", b.o830, "edge830")]
    for k in m.STDV_LEVELS:
        g = "c2" if k <= 2.5 else ("l35" if k == 3.5 else "c4")
        out.append((f"+{k}", b.mid + k * b.h, g))
        out.append((f"-{k}", b.mid - k * b.h, g))
    return [(n, p + shift * b.atr, g) for n, p, g in out]


def build(kind, start, end, first_day, shift=0.0):
    days, zones = prepare(kind, start, end, first_day)
    rows = []
    for di, d in enumerate(days):
        b, O, H, L, C, T = d["b"], d["O"], d["H"], d["L"], d["C"], d["T"]
        atr, h, mid = b.atr, b.h, b.mid
        cost_l, cost_m = (0.5, 1.0) if kind == "NQ" else (0.0016 * atr, 0.0032 * atr)
        thr = TICK if kind == "NQ" else 0.0008 * atr      # limit fills only if price trades 1 tick through
        zd = ict.day_zones(zones, d)
        z_av, z_inv, z_lo, z_hi, z_pol = (zd[c].values for c in ("avail", "inv", "lo", "hi", "pol"))
        ev_day = []
        for name, lvl, grp in levels_of(b, shift):
            for side in (1, -1):
                S, R, E = find_events(O, H, L, C, lvl, side, REARM * atr, NREC, MAXEV, thr)
                for k in range(MAXEV):
                    if S[k] < 0:
                        break
                    ev_day.append((name, lvl, grp, side, k, int(S[k]), int(R[k]), E[k]))
        # prior reaction bookkeeping: completed reclaims (bar r, side, level, qualifies as "first reaction")
        recl = [(e[6], e[3], e[0], e[0] in ("edge00", "edge830", "+2.5", "-2.5", "+3.5", "-3.5", "+4.5", "-4.5"))
                for e in ev_day if e[6] >= 0]
        for name, lvl, grp, side, k, s, r, ext in ev_day:
            ps = any(rr < s and sd == side and nm != name for rr, sd, nm, q in recl)
            psq = any(rr < s and sd == side and nm != name and q for rr, sd, nm, q in recl)
            po = any(rr < s and sd == -side for rr, sd, nm, q in recl)
            t = T[s]
            zm = (z_pol == side) & (z_av <= t) & (z_inv > t) & (z_lo - ict.ZONE_TOL <= lvl) & (z_hi + ict.ZONE_TOL >= lvl)
            p = max(s - 1, 0)
            sdv = d["sd"][p]
            zv = (lvl - d["vw"][p]) / sdv * side if sdv > 0 else 0.0
            natural = ((lvl < mid) == (side == 1)) if grp not in ("edge00", "edge830") else \
                ((lvl <= mid) == (side == 1))
            base = {"di": di, "day": d["day"], "level": name, "grp": grp, "side": side, "ord": k,
                    "rel": b.rel, "with_dir": side == b.dir, "natural": natural, "ict": bool(zm.any()),
                    "z": zv, "psych": abs(lvl - round(lvl / 50) * 50) <= 0.015 * atr,
                    "prior_same": ps, "prior_same_q": psq, "prior_opp": po, "atr": atr}
            # ---- T: limit at level
            rec = dict(base, kind="T", bar=s, mom=False)
            for si, sm in enumerate(STOPS_T):
                dist = float(sm[:-1]) * h if sm.endswith("h") else float(sm[:-3]) * atr
                stop = lvl - side * dist
                rec[f"risk{si}"] = dist / atr
                for xi, (mode, rm) in enumerate(EXIT_DEF):
                    px, xb = sim(H, L, C, s, side, lvl, stop, mode, rm, mid, True)
                    rec[f"x{si}_{xi}"] = xb
                    rec[f"o{si}_{xi}"] = (side * (px - lvl) - cost_l) / dist if dist > 0 and not np.isnan(px) else np.nan
            rows.append(rec)
            # ---- R: reclaim close
            if r >= 0 and r < len(C) - 1:
                entry = C[r]
                rec = dict(base, kind="R", bar=r,
                           mom=bool((C[r] > H[r - 1] and C[r] > O[r]) if side == 1 else (C[r] < L[r - 1] and C[r] < O[r])) if r > 0 else False,
                           mom_ext=bool((C[r] > H[r - 1]) if side == 1 else (C[r] < L[r - 1])) if r > 0 else False,
                           mom_body=bool((C[r] > O[r]) if side == 1 else (C[r] < O[r])), reclaim_bars=r - s)
                sstruct = ext - side * TICK
                for si, sm in enumerate(STOPS_R):
                    if sm == "struct":
                        stop = sstruct
                    elif sm == "struct_min":
                        stop = min(sstruct, entry - 0.02 * atr) if side == 1 else max(sstruct, entry + 0.02 * atr)
                    else:
                        stop = entry - side * float(sm[:-3]) * atr
                    dist = abs(entry - stop)
                    rec[f"risk{si}"] = dist / atr
                    for xi, (mode, rm) in enumerate(EXIT_DEF):
                        px, xb = sim(H, L, C, r, side, entry, stop, mode, rm, mid, False)
                        rec[f"x{si}_{xi}"] = xb
                        rec[f"o{si}_{xi}"] = (side * (px - entry) - cost_m) / dist if dist > 0 and not np.isnan(px) else np.nan
                rows.append(rec)
    ev = pd.DataFrame(rows)
    ev["year"] = ev.day.dt.year
    daylist = pd.DataFrame({"di": range(len(days)), "day": [d["day"] for d in days],
                            "rel": [d["b"].rel for d in days]})
    return ev, daylist


if __name__ == "__main__":
    out = Path(sys.argv[1])
    shift = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    suffix = "" if shift == 0 else f"_fake{shift:+.2f}"
    out.mkdir(parents=True, exist_ok=True)
    for name, args in {"CFD": ("CFD", "2016-11-01", "2023-01-01", "2016-11-16"),
                       "NQ": ("NQ", "2022-12-01", "2026-01-01", "2023-01-01")}.items():
        ev, dl = build(*args, shift=shift)
        ev.to_pickle(out / f"events_{name}{suffix}.pkl")
        dl.to_pickle(out / f"days_{name}.pkl")
        print(name, len(dl), "Tage", len(ev), "Events", ev.kind.value_counts().to_dict(), flush=True)
