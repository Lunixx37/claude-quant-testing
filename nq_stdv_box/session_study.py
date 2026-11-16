"""
Do the box / stdv levels matter outside the New-York day session?

The box of day D exists from 08:30 ET. Its levels are followed until the next box is complete:

  RTH     08:30 - 16:00 ET  (day D)          reference, same as all previous tests
  POST    16:00 - 17:00 ET  (day D)
  ASIA    18:00 - 02:00 ET  (evening before the next trading day)
  LONDON  02:00 - 08:30 ET  (next trading day, before its own box is complete)

Per session every level x side gets up to 3 touches (fresh arming at the session start). For every touch:
  T = limit entry at the level (1 tick trade-through), stop 0.06 ATR, exits: mid / 3R / 5R
  R = reclaim close within 10 bars, stop = sweep extreme (>= 0.02 ATR), exits: mid / 5R
  reaction: after the touch, does price move 0.03 ATR back before it moves 0.03 ATR beyond?  (first passage)
Positions are closed at 15:59 (RTH), 16:59 (POST) or 08:29 of the next trading day (ASIA / LONDON).

Usage: python session_study.py build <outdir>     # real levels + fake levels (+/-0.07 ATR)
       python session_study.py report <outdir>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, str(Path(__file__).parent))
import confluence as cf        # noqa: E402
import followup as fu          # noqa: E402
import ict                     # noqa: E402
import search as se            # noqa: E402
import search_events as sev    # noqa: E402
import stdv_box as m           # noqa: E402

TICK = 0.25
SESSIONS = ["RTH", "POST", "ASIA", "LONDON"]
SESS_LABEL = {"RTH": "RTH 08:30–16:00", "POST": "Nachbörse 16:00–17:00", "ASIA": "Asien 18:00–02:00", "LONDON": "London 02:00–08:30"}
REACT_X = 0.03          # x ATR
OUT = Path(__file__).parent / "results" / "sessions"


@njit(cache=True)
def first_passage(H, L, s, lvl, side, x):
    """1 = rejection (x back first), 0 = break (x beyond first), -1 = undecided / same bar."""
    for i in range(s, len(H)):
        if side == 1:
            rej, brk = H[i] >= lvl + x, L[i] <= lvl - x
        else:
            rej, brk = L[i] <= lvl - x, H[i] >= lvl + x
        if i == s:
            rej = False      # the touch bar's opposite extreme may stem from before the touch
        if rej and brk:
            return -1
        if rej:
            return 1
        if brk:
            return 0
    return -1


def session_bounds(day, nxt):
    d0, d1 = day, nxt
    return {"RTH": (d0 + pd.Timedelta("8h30min"), d0 + pd.Timedelta("16h"), d0 + pd.Timedelta("16h")),
            "POST": (d0 + pd.Timedelta("16h"), d0 + pd.Timedelta("17h"), d0 + pd.Timedelta("17h")),
            "ASIA": (d1 - pd.Timedelta("6h"), d1 + pd.Timedelta("2h"), d1 + pd.Timedelta("8h30min")),
            "LONDON": (d1 + pd.Timedelta("2h"), d1 + pd.Timedelta("8h30min"), d1 + pd.Timedelta("8h30min"))}


def build(kind, start, end, first_day, shift=0.0):
    bars = cf.load(kind)[["open", "high", "low", "close"]]
    bars = bars[(bars.index >= start) & (bars.index < end)]
    box = m.build_boxes(bars)
    box["atr"] = fu.daily_atr(bars).reindex(box.index)
    box["rel"] = 2 * box.h / box.atr
    box = box.dropna(subset=["atr"])
    box = box[(box.h > 0) & (box.index >= pd.Timestamp(first_day))]
    zones = ict.detect_zones(bars)
    z_av_all = zones.avail.values
    tvals = bars.index.values
    O_, H_, L_, C_ = (bars[c].values for c in ("open", "high", "low", "close"))
    T_ = tvals.astype("datetime64[m]").astype(np.int64)
    days = list(box.index)
    rows, drift = [], []
    for di in range(len(days) - 1):
        day, nxt = days[di], days[di + 1]
        if (nxt - day).days > 4:
            continue
        b = box.loc[day]
        atr, h, mid = b.atr, b.h, b.mid
        cost_l, cost_m = (0.5, 1.0) if kind == "NQ" else (0.0016 * atr, 0.0032 * atr)
        thr = TICK if kind == "NQ" else 0.0008 * atr
        bounds = session_bounds(day, nxt)
        for sess in SESSIONS:
            t0, t1, t2 = bounds[sess]
            a, e_touch, e_hold = np.searchsorted(tvals, np.datetime64(t0)), np.searchsorted(tvals, np.datetime64(t1)), np.searchsorted(tvals, np.datetime64(t2))
            nseg = e_touch - a
            if nseg < (300 if sess == "RTH" else 30):
                continue
            O, H, L, C, T = O_[a:e_hold], H_[a:e_hold], L_[a:e_hold], C_[a:e_hold], T_[a:e_hold]
            # zones valid at any time in this window
            lo_i, hi_i = np.searchsorted(z_av_all, T[0] - ict.MAX_AGE), np.searchsorted(z_av_all, T[-1], side="right")
            zd = zones.iloc[lo_i:hi_i]
            zd = zd[zd.inv > T[0]]
            z_av, z_inv, z_lo, z_hi, z_pol = (zd[c].values for c in ("avail", "inv", "lo", "hi", "pol"))
            ev = []
            for name, lvl, grp in sev.levels_of(b, shift):
                for side in (1, -1):
                    S, R, E = sev.find_events(O, H, L, C, lvl, side, sev.REARM * atr, 10, 3, thr)
                    for k in range(3):
                        if S[k] < 0 or S[k] >= nseg:
                            break
                        ev.append((name, lvl, grp, side, k, int(S[k]), int(R[k]), E[k]))
            recl = [(e[6], e[3]) for e in ev if e[6] >= 0]
            for name, lvl, grp, side, k, s, r, ext in ev:
                t = T[s]
                zm = (z_pol == side) & (z_av <= t) & (z_inv > t) & (z_lo - ict.ZONE_TOL <= lvl) & (z_hi + ict.ZONE_TOL >= lvl)
                natural = ((lvl < mid) == (side == 1)) if grp not in ("edge00", "edge830") else ((lvl <= mid) == (side == 1))
                base = {"di": di, "day": day, "sess": sess, "level": name, "grp": grp, "side": side, "ord": k, "rel": b.rel,
                        "atr": atr, "natural": natural, "ict": bool(zm.any()),
                        "prior_opp": any(rr < s and sd == -side for rr, sd in recl),
                        "react": first_passage(H, L, s, lvl, side, REACT_X * atr), "reclaimed": r >= 0}
                # T: limit, stop 0.06 ATR
                dist = 0.06 * atr
                rec = dict(base, kind="T", bar=s, mom=False)
                for xn, (mode, rm) in (("mid", (1, 0.0)), ("3R", (0, 3.0)), ("5R", (0, 5.0))):
                    px, xb = sev.sim(H, L, C, s, side, lvl, lvl - side * dist, mode, rm, mid, True)
                    rec[f"o_{xn}"] = (side * (px - lvl) - cost_l) / dist if not np.isnan(px) else np.nan
                    rec[f"x_{xn}"] = xb
                rows.append(rec)
                # R: reclaim close, structural stop >= 0.02 ATR
                if 1 <= r < len(C) - 1 and r < nseg:
                    entry = C[r]
                    ss = ext - side * TICK
                    stop = min(ss, entry - 0.02 * atr) if side == 1 else max(ss, entry + 0.02 * atr)
                    dist = abs(entry - stop)
                    rec = dict(base, kind="R", bar=r,
                               mom=bool((C[r] > H[r - 1] and C[r] > O[r]) if side == 1 else (C[r] < L[r - 1] and C[r] < O[r])))
                    for xn, (mode, rm) in (("mid", (1, 0.0)), ("5R", (0, 5.0))):
                        px, xb = sev.sim(H, L, C, r, side, entry, stop, mode, rm, mid, False)
                        rec[f"o_{xn}"] = (side * (px - entry) - cost_m) / dist if not np.isnan(px) else np.nan
                        rec[f"x_{xn}"] = xb
                    rows.append(rec)
        # overnight drift relative to the box (16:00 close -> next 08:29)
        i16 = np.searchsorted(tvals, np.datetime64(day + pd.Timedelta("16h"))) - 1
        i83 = np.searchsorted(tvals, np.datetime64(nxt + pd.Timedelta("8h30min"))) - 1
        if i16 > 0 and i83 > i16:
            drift.append({"day": day, "k16": (C_[i16] - mid) / h, "dist16": (C_[i16] - mid) / atr,
                          "move": (C_[i83] - C_[i16]) / atr, "rel": b.rel})
    return pd.DataFrame(rows), pd.DataFrame(drift), len(days) - 1


# ----------------------------------------------------------------------------- report
STRATS = {
    "K1  Limit an Stdv-Level in ICT-Zone, Stop 0,06 ATR, Ziel Mitte": dict(kind="T", grp=("c2", "l35", "c4"), ict=True, exit="mid"),
    "K2  Reclaim 3.5 + Momentum + vorher Gegenreaktion, Ziel Mitte": dict(kind="R", grp=("l35",), prior=True, mom=True, exit="mid"),
    "K3  Limit an 3.5–4.5, erster Touch, Stop 0,06 ATR, Ziel 3R": dict(kind="T", grp=("l35", "c4"), first=True, exit="3R"),
    "K4  Reclaim 3.5–4.5 in ICT-Zone, Box ≥ 0,2 ATR, Ziel 5R": dict(kind="R", grp=("l35", "c4"), ict=True, rel=0.2, exit="5R"),
    "K5  wie K1, Ziel 5R": dict(kind="T", grp=("c2", "l35", "c4"), ict=True, exit="5R"),
}
GROUPS = {"Box-Kante 00:00": ("edge00",), "Box-Kante 08:30": ("edge830",), "Cluster 2–2.5": ("c2",), "3.5": ("l35",), "Cluster 4–4.5": ("c4",)}


def strat_trades(ev, sess, kind, grp, exit, ict=False, prior=False, mom=False, first=False, rel=0.0):
    s = ev[(ev.kind == kind) & (ev.sess == sess)].sort_values(["di", "bar"])
    mk = s.grp.isin(grp).values & (s.rel.values >= rel) & ~np.isnan(s[f"o_{exit}"].values)
    if ict:
        mk &= s.ict.values
    if prior:
        mk &= s.prior_opp.values
    if mom:
        mk &= s.mom.values
    if first:
        mk &= s.ord.values == 0
    t = s[mk][["di", "day", "bar", "side"]].copy()
    t["R"] = s[f"o_{exit}"].values[mk]
    t["xbar"] = s[f"x_{exit}"].values[mk]
    return se.one_at_a_time(t)


def sstat(t, nd):
    if len(t) == 0:
        return {"Trades/Wo": 0.0, "Win %": np.nan, "Ø R": np.nan, "t": np.nan}
    d = np.zeros(nd)
    np.add.at(d, t.di.values, t.R.values)
    return {"Trades/Wo": round(len(t) / nd * 5, 2), "Win %": round((t.R > 0).mean() * 100, 1), "Ø R": round(t.R.mean(), 3),
            "t": round(d.mean() / d.std(ddof=1) * np.sqrt(nd), 2) if d.std() > 0 else 0.0}


def report(d):
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 260)
    pd.set_option("display.max_colwidth", 70)
    E = {(ds, sf): pd.read_pickle(d / f"sess_{ds}{sf}.pkl") for ds in ("CFD", "NQ") for sf in ("", "_fake+0.07", "_fake-0.07")}
    ND = {ds: int(pd.read_pickle(d / f"nd_{ds}.pkl").iloc[0]) for ds in ("CFD", "NQ")}

    # 1) how often are levels reached, and how do they react (real vs fake)
    rows = []
    for sess in SESSIONS:
        for gname, grp in GROUPS.items():
            r = {"Sitzung": SESS_LABEL[sess], "Level": gname}
            for ds in ("CFD", "NQ"):
                ev = E[(ds, "")]
                t = ev[(ev.kind == "T") & (ev.sess == sess) & ev.grp.isin(grp) & (ev.ord == 0)]
                dec = t[t.react >= 0]
                fk = pd.concat([E[(ds, sf)] for sf in ("_fake+0.07", "_fake-0.07")])
                tf = fk[(fk.kind == "T") & (fk.sess == sess) & fk.grp.isin(grp) & (fk.ord == 0)]
                decf = tf[tf.react >= 0]
                r[f"{ds} Tage mit Touch %"] = round(t.di.nunique() / ND[ds] * 100, 1)
                r[f"{ds} Rejection %"] = round(dec.react.mean() * 100, 1) if len(dec) else np.nan
                r[f"{ds} Rejection % Fake"] = round(decf.react.mean() * 100, 1) if len(decf) else np.nan
                r[f"{ds} Reclaim %"] = round(t.reclaimed.mean() * 100, 1) if len(t) else np.nan
                r[f"{ds} Reclaim % Fake"] = round(tf.reclaimed.mean() * 100, 1) if len(tf) else np.nan
                r[f"{ds} n"] = len(t)
            rows.append(r)
    R1 = pd.DataFrame(rows)
    R1.to_csv(OUT / "reactions_by_session.csv", index=False)
    print("\n=== 1) Erster Touch je Level und Sitzung: Häufigkeit und Reaktion (echt vs. Fake-Level) ===")
    print(R1.to_string(index=False))

    # 2) generic fades per session / level group, natural side only
    rows = []
    for sess in SESSIONS:
        for gname, grp in GROUPS.items():
            r = {"Sitzung": SESS_LABEL[sess], "Level": gname}
            for ds in ("CFD", "NQ"):
                for lab, kw in (("Limit→Mitte", dict(kind="T", exit="mid")), ("Reclaim→Mitte", dict(kind="R", exit="mid"))):
                    t = strat_trades(E[(ds, "")], sess, grp=grp, **kw)
                    tf = pd.concat([strat_trades(E[(ds, sf)], sess, grp=grp, **kw) for sf in ("_fake+0.07", "_fake-0.07")])
                    st = sstat(t, ND[ds])
                    r[f"{ds} {lab} Ø R"] = st["Ø R"]
                    r[f"{ds} {lab} Fake"] = round(tf.R.mean(), 3) if len(tf) else np.nan
                    r[f"{ds} {lab} n"] = len(t)
            rows.append(r)
    R2 = pd.DataFrame(rows)
    R2.to_csv(OUT / "generic_fades_by_session.csv", index=False)
    print("\n=== 2) Einfache Fades je Level und Sitzung (Ø R, echt vs. Fake) ===")
    print(R2.to_string(index=False))

    # 3) K1-K5 per session (no time-of-day filter)
    rows = []
    for name, kw in STRATS.items():
        for sess in SESSIONS:
            r = {"Strategie": name, "Sitzung": SESS_LABEL[sess]}
            for ds in ("CFD", "NQ"):
                t = strat_trades(E[(ds, "")], sess, **kw)
                tf = pd.concat([strat_trades(E[(ds, sf)], sess, **kw) for sf in ("_fake+0.07", "_fake-0.07")])
                st = sstat(t, ND[ds])
                for k, v in st.items():
                    r[f"{ds} {k}"] = v
                r[f"{ds} Fake Ø R"] = round(tf.R.mean(), 3) if len(tf) else np.nan
            rows.append(r)
    R3 = pd.DataFrame(rows)
    R3.to_csv(OUT / "k1_k5_by_session.csv", index=False)
    print("\n=== 3) K1–K5 je Sitzung (ohne Tageszeit-Filter) ===")
    print(R3.to_string(index=False))

    # 4) overnight drift relative to the box
    print("\n=== 4) Über Nacht: zieht der Preis zurück zur Box? (16:00 -> 08:29 nächster Tag) ===")
    rows = []
    for ds in ("CFD", "NQ"):
        dr = pd.read_pickle(d / f"drift_{ds}.pkl")
        dr["toward"] = -np.sign(dr.dist16) * dr.move          # > 0: overnight move back toward the box mid
        for lab, mk in (("alle Tage", np.ones(len(dr), bool)), ("Schluss innerhalb ±2 Stdv", dr.k16.abs() <= 2),
                        ("Schluss 2–4.5 Stdv entfernt", (dr.k16.abs() > 2) & (dr.k16.abs() <= 4.5)),
                        ("Schluss > 4.5 Stdv entfernt", dr.k16.abs() > 4.5)):
            x = dr.toward[mk]
            rows.append({"Daten": ds, "Fall": lab, "Tage": len(x), "Ø Bewegung Richtung Mitte (ATR)": round(x.mean(), 4),
                         "t": round(x.mean() / x.std(ddof=1) * np.sqrt(len(x)), 2), "Anteil Richtung Mitte %": round((x > 0).mean() * 100, 1)})
    R4 = pd.DataFrame(rows)
    R4.to_csv(OUT / "overnight_drift.csv", index=False)
    print(R4.to_string(index=False))


if __name__ == "__main__":
    cmd, d = sys.argv[1], Path(sys.argv[2])
    d.mkdir(parents=True, exist_ok=True)
    if cmd == "build":
        sets = {"CFD": ("CFD", "2016-11-01", "2023-01-01", "2016-11-16"), "NQ": ("NQ", "2022-12-01", "2026-01-01", "2023-01-01")}
        for shift in (0.0, 0.07, -0.07):
            sf = "" if shift == 0 else f"_fake{shift:+.2f}"
            for name, a in sets.items():
                ev, dr, nd = build(*a, shift=shift)
                ev.to_pickle(d / f"sess_{name}{sf}.pkl")
                if shift == 0:
                    dr.to_pickle(d / f"drift_{name}.pkl")
                    pd.Series([nd]).to_pickle(d / f"nd_{name}.pkl")
                print(name, sf, len(ev), "Events", ev.groupby("sess").size().to_dict(), flush=True)
    else:
        report(d)
