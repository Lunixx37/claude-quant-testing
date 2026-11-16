"""
Abschluss-Suche in drei Stufen.

  A  Suche       CFD 2016-11 .. 2020-12
  B  Bestaetigung CFD 2021-01 .. 2022-12
  C  Endtest     NQ-Future 2023-2025   (wird hier NICHT angefasst, siehe final_test.py)

Kombination = Einstiegsgruppe x Trendbedingung x Zeitfenster x bis zu 2 Zusatzbedingungen x Stop x Ziel.
Je Kombination zaehlt nur das erste passende Ereignis des Tages (hoechstens 1 Trade pro Tag, beide Richtungen).

Kriterien A: >= 2 Trades/Woche, Trefferquote >= 60 %, Erwartungswert > 0 mit t >= 2.5
Kriterien B: >= 2 Trades/Woche, Trefferquote >= 58 %, Erwartungswert > 0 mit t >= 1.0

Aufruf:  python final/search.py <ereignis-ordner>
"""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from build_events import RRS, STOPS

NSTOP, NRR = len(STOPS) + 1, len(RRS)
STOPN = [f"{s}atr" for s in STOPS] + ["struct"]

RECLAIM = ["edge", "mid", "c2", "l35", "c4", "ps100", "ps50", "pd", "pdc", "on", "open", "or", "vwap",
           "fvg", "ob", "rb", "ifvg"]
GROUPS = {g: [g] for g in RECLAIM + ["fo0.2", "fo0.3", "fo0.4", "fo0.5", "orb15", "orb30", "bo_pd", "bo_on",
                                     "newext", "ib"]}
GROUPS.update({"stdv_alle": ["c2", "l35", "c4"], "psych": ["ps100", "ps50"], "ict": ["fvg", "ob", "rb", "ifvg"],
               "tageslevel": ["pd", "pdc", "on", "open", "or"], "alle_reclaims": RECLAIM,
               "box_alle": ["edge", "mid", "c2", "l35", "c4"]})

TREND = {"-": lambda e: np.ones(len(e), bool), "fo>=0": lambda e: e.fo >= 0, "fo>=0.15": lambda e: e.fo >= 0.15,
         "fo>=0.3": lambda e: e.fo >= 0.3, "fo<=-0.15": lambda e: e.fo <= -0.15, "ema>=0": lambda e: e.ema >= 0,
         "ema>=1": lambda e: e.ema >= 1, "ema<=-1": lambda e: e.ema <= -1,
         "fo>=0.15&ema>=0": lambda e: (e.fo >= 0.15) & (e.ema >= 0)}
WINDOWS = {"09:30-15:30": (60, 420), "09:30-10:30": (60, 120), "10:00-12:00": (90, 210),
           "10:00-15:30": (90, 420), "12:00-15:30": (210, 420)}
FLAGS = {"mom": lambda e: e.mom, "vorher_gegen": lambda e: e.prior_opp, "erster_touch": lambda e: e.ord == 0,
         "psych100": lambda e: e.c_ps100, "psych50": lambda e: e.c_ps50, "stdv": lambda e: e.c_stdv,
         "vwap_nah": lambda e: e.c_vwap, "tageslevel_nah": lambda e: e.c_pd | e.c_on,
         "fvg": lambda e: e.c_fvg, "ob": lambda e: e.c_ob, "rb": lambda e: e.c_rb, "ifvg": lambda e: e.c_ifvg,
         "ict_zone": lambda e: e.c_fvg | e.c_ob | e.c_rb | e.c_ifvg, "keine_gegen_fvg": lambda e: ~e.c_fvg_opp,
         "mit_vwap": lambda e: e.vw >= 0, "gegen_vwap": lambda e: e.vw <= 0, "box>=0.1": lambda e: e.boxrel >= 0.1,
         "mit_box": lambda e: e.boxdir > 0, "im_vortag": lambda e: e.in_pd, "5T_mit": lambda e: e.r5 >= 0.5,
         "5T_gegen": lambda e: e.r5 <= -0.5, "platz>=0.1": lambda e: e.room >= 0.1, "am_extrem": lambda e: e.room <= 0.02,
         "spanne<=0.5": lambda e: e.rng <= 0.5, "spanne>=0.8": lambda e: e.rng >= 0.8, "gap_mit": lambda e: e.gap >= 0.1}
RCOLS = [f"R{a}_{b}" for a in range(NSTOP) for b in range(NRR)]


def prep(ev):
    ev = ev[(ev.bar >= 60) & (ev.bar < 420)].sort_values(["di", "bar"]).reset_index(drop=True)
    return ev


def first_per_day(idx, di):
    d = di[idx]
    return idx[np.r_[True, d[1:] != d[:-1]]] if len(idx) else idx


def stats(R):
    """R: (n, 25) mit nan. Liefert n, Trefferquote, Mittel, t je Ausstieg."""
    ok = ~np.isnan(R)
    n = ok.sum(0)
    Rz = np.where(ok, R, 0.0)
    mean = Rz.sum(0) / np.maximum(n, 1)
    var = (np.where(ok, (R - mean) ** 2, 0.0)).sum(0) / np.maximum(n - 1, 1)
    win = (np.where(ok, R > 0, False)).sum(0) / np.maximum(n, 1)
    t = mean / np.sqrt(np.maximum(var, 1e-12) / np.maximum(n, 1))
    return n, win, mean, t


def combos():
    fl = [()] + [(f,) for f in FLAGS] + list(itertools.combinations(FLAGS, 2))
    for g in GROUPS:
        for tr in TREND:
            for w in WINDOWS:
                for f in fl:
                    yield g, tr, w, f


def run(evdir):
    ev = prep(pd.read_pickle(evdir / "events_CFD.pkl"))
    dl = pd.read_pickle(evdir / "days_CFD.pkl")
    isA = (ev.day < "2021-01-01").values
    ndA, ndB = (dl.day < "2021-01-01").sum(), (dl.day >= "2021-01-01").sum()
    print(f"CFD: {len(ev)} Ereignisse, Stufe A {ndA} Tage, Stufe B {ndB} Tage", flush=True)
    R = ev[RCOLS].values
    di = ev.di.values
    grp = ev.grp.values
    tmask = {k: np.asarray(f(ev), bool) for k, f in TREND.items()}
    wmask = {k: ((ev.bar >= a) & (ev.bar < b)).values for k, (a, b) in WINDOWS.items()}
    fmask = {k: np.asarray(f(ev), bool) for k, f in FLAGS.items()}
    fl = [()] + [(f,) for f in FLAGS] + list(itertools.combinations(FLAGS, 2))
    rows, n_tested, base = [], 0, []
    for g, members in GROUPS.items():
        gi = np.flatnonzero(np.isin(grp, members))
        if len(gi) < 500:
            continue
        Rg, dig, Ag = R[gi], di[gi], isA[gi]
        for tr in TREND:
            m1 = tmask[tr][gi]
            for w in WINDOWS:
                m2 = m1 & wmask[w][gi]
                if m2.sum() < 300:
                    continue
                for f in fl:
                    m = m2
                    for x in f:
                        m = m & fmask[x][gi]
                    idx = first_per_day(np.flatnonzero(m), dig)
                    a = idx[Ag[idx]]
                    b = idx[~Ag[idx]]
                    if len(a) / ndA * 5 < 2 or len(b) / ndB * 5 < 2:
                        continue
                    nA, wA, mA, tA = stats(Rg[a])
                    nB, wB, mB, tB = stats(Rg[b])
                    n_tested += NSTOP * NRR
                    hi = (wA >= 0.60) & (nA / ndA * 5 >= 2)
                    for j in np.flatnonzero(hi):
                        base.append((mA[j] > 0 and tA[j] >= 2.5, mB[j] > 0))
                        if mA[j] > 0 and tA[j] >= 2.5:
                            rows.append(dict(grp=g, trend=tr, fenster=w, f1=f[0] if len(f) > 0 else "",
                                             f2=f[1] if len(f) > 1 else "", stop=STOPN[j // NRR], rr=RRS[j % NRR],
                                             ex=j, nA=nA[j], wkA=nA[j] / ndA * 5, winA=wA[j], RA=mA[j], tA=tA[j],
                                             nB=nB[j], wkB=nB[j] / ndB * 5, winB=wB[j], RB=mB[j], tB=tB[j]))
        print(g, "fertig;", n_tested, "getestet,", len(rows), "bestehen A", flush=True)
    res = pd.DataFrame(rows)
    res["passB"] = (res.winB >= 0.58) & (res.RB > 0) & (res.tB >= 1.0) & (res.wkB >= 2)
    res.to_pickle(evdir / "search_result.pkl")
    base = np.array(base)
    print(f"\nGetestete Konfigurationen (mit >= 2 Trades/Woche): {n_tested}")
    print(f"Trefferquote >= 60 % in A: {len(base)}")
    print(f"  davon in B positiv, wenn A die Kriterien NICHT erfuellt: {base[~base[:, 0], 1].mean():.1%}")
    print(f"  davon in B positiv, wenn A die Kriterien erfuellt:        {base[base[:, 0], 1].mean():.1%}")
    print(f"Bestehen A: {len(res)}   bestehen A und B: {res.passB.sum()}")
    return res


if __name__ == "__main__":
    run(Path(sys.argv[1]))
