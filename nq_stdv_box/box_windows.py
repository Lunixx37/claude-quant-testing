"""
Alternative box definitions: the box is drawn between the OPEN at the start and the OPEN at the end of a
time window (same construction as the original 00:00 -> 08:30 box), mid = 50 %, stdv levels = mid +/- k*h.

Session times (New-York time, ICT-style, non-overlapping; change SESS to test others):
    Asia 20:00-00:00 | London 02:00-05:00 | New York 09:30-16:00

Boxes (relative to trading date D):
    Original          00:00 -> 08:30
    Asien             20:00 (previous evening) -> 00:00
    Asien->London     00:00 -> 02:00
    London            02:00 -> 05:00
    London->NY        05:00 -> 09:30
    New York          09:30 -> 16:00
    NY->Asien         16:00 -> 20:00

Each box is evaluated in two trading windows:
    "danach" : the 7.5 hours directly after the box is complete
    "NY"     : the next New-York session 09:30-16:00 after the box is complete (same window for all boxes)

Measured: how often the levels are reached, reaction vs fake levels (+/-0.07 ATR), and the K2 entry
(reclaim of the 3.5 level with momentum candle and prior opposite reclaim; stop behind the sweep >= 0.02 ATR)
with target mid (K2) or opposite 2.0 level (V2).

Usage: python box_windows.py build <dir> ; python box_windows.py report <dir>
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import confluence as cf        # noqa: E402
import followup as fu          # noqa: E402
import k2_optimize as ko       # noqa: E402
import search_events as sev    # noqa: E402
import session_study as ss     # noqa: E402

TICK = 0.25
H = pd.Timedelta("1h")
# name: (box start, box end) as offsets from midnight of the trading date D
BOXES = {
    "Original 00:00→08:30": (0 * H, 8.5 * H),
    "Asien 20:00→00:00": (-4 * H, 0 * H),
    "Asien→London 00:00→02:00": (0 * H, 2 * H),
    "London 02:00→05:00": (2 * H, 5 * H),
    "London→NY 05:00→09:30": (5 * H, 9.5 * H),
    "New York 09:30→16:00": (9.5 * H, 16 * H),
    "NY→Asien 16:00→20:00": (16 * H, 20 * H),
}
WINDOWS = ["danach", "NY"]
OUT = Path(__file__).parent / "results" / "box_windows"


def build(kind, start, end, first_day, shift=0.0):
    bars = cf.load(kind)[["open", "high", "low", "close"]]
    bars = bars[(bars.index >= start) & (bars.index < end)]
    atr_s = fu.daily_atr(bars)
    tv = bars.index.values
    O_, H_, L_, C_ = (bars[c].values for c in ("open", "high", "low", "close"))
    # trading dates = weekdays that have a 09:30 bar
    d930 = bars.index[(bars.index.hour == 9) & (bars.index.minute == 30)].normalize()
    dates = [d for d in d930 if d.dayofweek < 5 and d >= pd.Timestamp(first_day)]
    nxt = {dates[i]: dates[i + 1] for i in range(len(dates) - 1)}

    def open_at(ts):
        i = np.searchsorted(tv, np.datetime64(ts))
        return (O_[i], i) if i < len(tv) and tv[i] == np.datetime64(ts) else (np.nan, -1)

    rows, lv_rows = [], []
    for bi, (bname, (o_a, o_b)) in enumerate(BOXES.items()):
        for di, day in enumerate(dates):
            atr = atr_s.get(day, np.nan)
            pa, _ = open_at(day + o_a)
            pb, ib = open_at(day + o_b)
            if np.isnan(atr) or np.isnan(pa) or np.isnan(pb) or pa == pb:
                continue
            top, bot = max(pa, pb), min(pa, pb)
            b = SimpleNamespace(o0=pa, o830=pb, mid=(top + bot) / 2, h=(top - bot) / 2, atr=atr,
                                rel=(top - bot) / atr, dir=np.sign(pb - pa))
            cost = 1.0 if kind == "NQ" else 0.0032 * atr
            thr = TICK if kind == "NQ" else 0.0008 * atr
            t_end = day + o_b
            for w in WINDOWS:
                if w == "danach":
                    w0, w1 = t_end, t_end + 7.5 * H
                else:
                    nyday = day if o_b <= 9.5 * H else nxt.get(day)
                    if nyday is None or (nyday - day).days > 4:
                        continue
                    w0, w1 = nyday + 9.5 * H, nyday + 16 * H
                a, e = np.searchsorted(tv, np.datetime64(w0)), np.searchsorted(tv, np.datetime64(w1))
                if e - a < 200:
                    continue
                O, Hh, L, C = O_[a:e], H_[a:e], L_[a:e], C_[a:e]
                evs = []
                for name, lvl, grp in sev.levels_of(b, shift):
                    for side in (1, -1):
                        S, R, E = sev.find_events(O, Hh, L, C, lvl, side, sev.REARM * atr, 10, 6, thr)
                        for k in range(6):
                            if S[k] < 0:
                                break
                            evs.append((name, lvl, grp, side, k, int(S[k]), int(R[k]), E[k]))
                            if k == 0:
                                lv_rows.append((bi, w, di, grp, ss.first_passage(Hh, L, int(S[k]), lvl, side, ss.REACT_X * atr), R[k] >= 0))
                recl = [(x[6], x[3]) for x in evs if x[6] >= 0]
                for name, lvl, grp, side, k, s, r, ext in evs:
                    if grp != "l35" or r < 1 or r >= len(C) - 1:
                        continue
                    if not ((C[r] > Hh[r - 1] and C[r] > O[r]) if side == 1 else (C[r] < L[r - 1] and C[r] < O[r])):
                        continue
                    if not any(rr < s and sd == -side for rr, sd in recl):
                        continue
                    entry = C[r]
                    if (b.mid - entry) * side <= 0:
                        continue
                    sstruct = ext - side * TICK
                    stop = min(sstruct, entry - 0.02 * atr) if side == 1 else max(sstruct, entry + 0.02 * atr)
                    risk = abs(entry - stop)
                    rec = {"box": bi, "win": w, "di": di, "day": day, "bar": r, "side": side, "ord": k, "rel": b.rel}
                    for xn, tp in (("mid", b.mid), ("opp2", b.mid + side * 2 * b.h)):
                        px, xb = ko.sim2(Hh, L, C, r, side, entry, stop, tp, np.nan)
                        rec[f"o_{xn}"] = (side * (px - entry) - cost) / risk
                        rec[f"x_{xn}"] = xb
                    rows.append(rec)
            rows.append({"box": bi, "win": "_box", "di": di, "day": day, "bar": -1, "side": 0, "ord": 0, "rel": b.rel})
    ev = pd.DataFrame(rows)
    lv = pd.DataFrame(lv_rows, columns=["box", "win", "di", "grp", "react", "reclaimed"])
    return ev, lv, len(dates)


def take(ev, bi, w, xn, maxord):
    t = ev[(ev.box == bi) & (ev.win == w) & (ev.ord < maxord)].sort_values(["di", "bar"])
    keep, cur, busy = [], -1, -1
    for i, (di, bar, xb) in enumerate(zip(t.di.values, t.bar.values, t[f"x_{xn}"].values)):
        if di != cur:
            cur, busy = di, -1
        if bar > busy:
            keep.append(i)
            busy = xb
    t = t.iloc[keep]
    return t, t[f"o_{xn}"].values


def stat(t, r, nd):
    if len(r) == 0:
        return {"Tr/Wo": 0.0, "Win %": np.nan, "Ø R": np.nan, "t": np.nan}
    d = np.zeros(nd)
    np.add.at(d, t.di.values, r)
    return {"Tr/Wo": round(len(r) / nd * 5, 2), "Win %": round((r > 0).mean() * 100, 1), "Ø R": round(r.mean(), 3),
            "t": round(d.mean() / d.std(ddof=1) * np.sqrt(nd), 2) if d.std() > 0 else 0.0}


def report(d):
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 280)
    E = {(ds, sf): pd.read_pickle(d / f"bw_{ds}{sf}.pkl") for ds in ("CFD", "NQ") for sf in ("", "_fake+0.07", "_fake-0.07")}
    LV = {(ds, sf): pd.read_pickle(d / f"bwlv_{ds}{sf}.pkl") for ds in ("CFD", "NQ") for sf in ("", "_fake+0.07", "_fake-0.07")}
    ND = {ds: int(pd.read_pickle(d / f"bwnd_{ds}.pkl").iloc[0]) for ds in ("CFD", "NQ")}
    names = list(BOXES)

    rows = []
    for bi, bname in enumerate(names):
        r = {"Box": bname}
        for ds in ("CFD", "NQ"):
            bx = E[(ds, "")]
            bx = bx[(bx.box == bi) & (bx.win == "_box")]
            r[f"{ds} Boxen"] = len(bx)
            r[f"{ds} Boxhöhe Median (ATR)"] = round(bx.rel.median(), 3)
            r[f"{ds} Box > 0,15 ATR %"] = round((bx.rel > 0.15).mean() * 100, 1)
        rows.append(r)
    R0 = pd.DataFrame(rows)
    R0.to_csv(OUT / "box_sizes.csv", index=False)
    print("=== Boxgrößen ==="); print(R0.to_string(index=False))

    rows = []
    for w in WINDOWS:
        for bi, bname in enumerate(names):
            r = {"Fenster": w, "Box": bname}
            for ds in ("CFD", "NQ"):
                nbox = ((E[(ds, "")].box == bi) & (E[(ds, "")].win == "_box")).sum()
                lv = LV[(ds, "")]
                lv = lv[(lv.box == bi) & (lv.win == w)]
                fk = pd.concat([LV[(ds, sf)] for sf in ("_fake+0.07", "_fake-0.07")])
                fk = fk[(fk.box == bi) & (fk.win == w)]
                r[f"{ds} 3.5 erreicht %"] = round(lv[lv.grp == "l35"].di.nunique() / max(nbox, 1) * 100, 1)
                dec, decf = lv[lv.react >= 0], fk[fk.react >= 0]
                r[f"{ds} Rejection %"] = round(dec.react.mean() * 100, 1) if len(dec) else np.nan
                r[f"{ds} Rejection % Fake"] = round(decf.react.mean() * 100, 1) if len(decf) else np.nan
                for lab, xn, mo in (("K2", "mid", 3), ("V2", "opp2", 4)):
                    t, rr = take(E[(ds, "")][E[(ds, "")].win != "_box"], bi, w, xn, mo)
                    st = stat(t, rr, ND[ds])
                    fr = np.concatenate([take(E[(ds, sf)][E[(ds, sf)].win != "_box"], bi, w, xn, mo)[1] for sf in ("_fake+0.07", "_fake-0.07")])
                    r[f"{ds} {lab} Tr/Wo"], r[f"{ds} {lab} Win %"], r[f"{ds} {lab} Ø R"], r[f"{ds} {lab} t"] = st["Tr/Wo"], st["Win %"], st["Ø R"], st["t"]
                    r[f"{ds} {lab} Fake Ø R"] = round(fr.mean(), 3) if len(fr) else np.nan
            rows.append(r)
    R1 = pd.DataFrame(rows)
    R1.to_csv(OUT / "box_windows_results.csv", index=False)
    for w in WINDOWS:
        g = R1[R1.Fenster == w]
        print(f"\n=== Handelsfenster: {w} — Level erreicht / Reaktion ===")
        print(g[["Box"] + [c for c in g.columns if "erreicht" in c or "Rejection" in c]].to_string(index=False))
        for lab in ("K2", "V2"):
            print(f"--- {lab} ---")
            print(g[["Box"] + [c for c in g.columns if f" {lab} " in c]].to_string(index=False))


if __name__ == "__main__":
    cmd, d = sys.argv[1], Path(sys.argv[2])
    d.mkdir(parents=True, exist_ok=True)
    if cmd == "build":
        sets = {"CFD": ("CFD", "2016-11-01", "2023-01-01", "2016-12-05"), "NQ": ("NQ", "2022-12-01", "2026-01-01", "2023-01-17")}
        for shift in (0.0, 0.07, -0.07):
            sf = "" if shift == 0 else f"_fake{shift:+.2f}"
            for name, a in sets.items():
                ev, lv, nd = build(*a, shift=shift)
                ev.to_pickle(d / f"bw_{name}{sf}.pkl")
                lv.to_pickle(d / f"bwlv_{name}{sf}.pkl")
                pd.Series([nd]).to_pickle(d / f"bwnd_{name}.pkl")
                print(name, sf, len(ev), "Zeilen,", nd, "Handelstage", flush=True)
    else:
        report(d)
