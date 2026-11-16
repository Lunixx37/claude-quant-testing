"""
Tagesdaten und Kontext fuer die Optimierung von R1 (wird einmal gebaut und zwischengespeichert).

Je gueltigem Handelstag (09:30-Kerze vorhanden, >= 350 RTH-Minuten):
  Raster 09:30..15:59 (390 Minuten) mit Open/High/Low/Close/Volumen und Intraday-Indikatoren,
  dazu alles, was VOR dem Signal bekannt ist: ATR, Overnight-Spanne, 00:00- und 08:30-Open,
  Vortageswerte, Mehrtages-Trend, Volumenprofil der letzten 20 Tage.

Aufruf:  python final/opt_data.py <cache-ordner>
"""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from build_events import load

NB = 390


def build(kind):
    b = load(kind)
    t = b.index
    tmin = t.values.astype("datetime64[m]").astype(np.int64)
    clock = (t.hour * 60 + t.minute).values
    O, H, L, C, V = (b[c].values.astype(float) for c in ("open", "high", "low", "close", "volume"))
    sess = (t + pd.Timedelta("6h")).normalize()
    g = b.groupby(sess)
    rng_d = g.high.max() - g.low.min()
    atr14 = rng_d.rolling(14).mean().shift(1)
    atr60 = rng_d.rolling(60, min_periods=30).mean().shift(1)

    lp = np.log(C)
    ret = np.diff(lp, prepend=lp[0])
    vol = pd.Series(ret).ewm(span=390, min_periods=100).std().values
    a = 2 / 101
    ema = pd.Series(ret).ewm(alpha=a, adjust=False).mean().values / (vol * np.sqrt(a / (2 - a)))
    z30 = (lp - np.r_[np.full(30, np.nan), lp[:-30]]) / (vol * np.sqrt(30))
    tp = (H + L + C) / 3
    sk = sess.values
    cv = pd.Series(V).groupby(sk).cumsum().values
    cpv = pd.Series(tp * V).groupby(sk).cumsum().values
    vwe = np.where(cv > 0, cpv / np.maximum(cv, 1e-9), np.nan)

    dnum = t.normalize().values
    first = pd.Timestamp("2016-11-16" if kind == "CFD" else "2023-01-01")
    recs, grids, hist = [], {k: [] for k in ("O", "H", "L", "C", "V", "ema", "z30", "vwe", "cumv_avg")}, []
    prev = prev2 = None
    for d in np.unique(dnum):
        day = pd.Timestamp(d)
        i0, i1 = np.searchsorted(dnum, d), np.searchsorted(dnum, d, side="right")
        ck = clock[i0:i1]
        m = (ck >= 570) & (ck < 960)
        if day.dayofweek > 4 or m.sum() < 350 or ck[m][0] != 570:
            continue
        pos = np.arange(i0, i1)[m]
        idx = ck[m] - 570
        gr = {}
        for nm, arr in (("O", O), ("H", H), ("L", L), ("C", C), ("ema", ema), ("z30", z30), ("vwe", vwe)):
            x = np.full(NB, np.nan)
            x[idx] = arr[pos]
            gr[nm] = x
        v = np.zeros(NB)
        v[idx] = V[pos]
        gr["V"] = v
        cumv = np.cumsum(v)
        gr["cumv_avg"] = np.mean(hist[-20:], axis=0) if len(hist) >= 5 else np.full(NB, np.nan)
        dm = np.int64(day.value // 60_000_000_000)

        def at(minute, arr):
            j = np.searchsorted(tmin, dm + minute)
            return arr[j] if j < len(tmin) and tmin[j] == dm + minute else np.nan

        js, je = np.searchsorted(tmin, dm - 360), np.searchsorted(tmin, dm + 570)
        on_ok = je - js >= 200
        jp0, jp1, jsp = (np.searchsorted(tmin, dm + x) for x in (510, 570, 515))
        a14 = float(atr14.get(day, np.nan))
        rec = dict(day=day, kind=kind, atr=a14, atr60=float(atr60.get(day, np.nan)),
                   o0=at(0, O), o830=at(510, O),
                   onh=H[js:je].max() if on_ok else np.nan, onl=L[js:je].min() if on_ok else np.nan,
                   o18=O[js] if on_ok else np.nan,
                   pmh=H[jp0:jp1].max() if jp1 - jp0 >= 30 else np.nan,
                   pml=L[jp0:jp1].min() if jp1 - jp0 >= 30 else np.nan,
                   spike=(H[jp0:jsp].max() - L[jp0:jsp].min()) if jsp > jp0 else np.nan,
                   do=gr["O"][0], dh=np.nanmax(gr["H"]), dl=np.nanmin(gr["L"]), dc=C[pos[-1]],
                   tradable=bool(day >= first and not np.isnan(a14)))
        ok = prev is not None and (day - prev["day"]).days <= 5
        for k in ("dh", "dl", "dc", "do"):
            rec["p" + k] = prev[k] if ok else np.nan
        ok2 = ok and prev2 is not None and (prev["day"] - prev2["day"]).days <= 5
        rec["inside"] = bool(ok2 and prev["dh"] <= prev2["dh"] and prev["dl"] >= prev2["dl"])
        recs.append(rec)
        for k in grids:
            grids[k].append(gr[k])
        hist.append(cumv)
        prev2, prev = prev, rec

    D = pd.DataFrame(recs)
    dret = np.log(D.dc).diff()
    sd = dret.rolling(60, min_periods=20).std().shift(1)
    D["r1"] = dret.shift(1) / sd
    D["r5"] = dret.rolling(5).sum().shift(1) / (sd * np.sqrt(5))
    D["r20"] = dret.rolling(20).sum().shift(1) / (sd * np.sqrt(20))
    rr = (D.dh - D.dl)
    D["pdr"] = rr.shift(1) / D.atr
    D["nr4"] = rr.shift(1) <= rr.shift(1).rolling(4).min()
    D["nr7"] = rr.shift(1) <= rr.shift(1).rolling(7).min()
    D["wr7"] = rr.shift(1) >= rr.shift(1).rolling(7).max()
    return dict(D=D, **{k: np.array(v) for k, v in grids.items()})


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for kind in ("CFD", "NQ"):
        S = build(kind)
        with open(out / f"opt_{kind}.pkl", "wb") as f:
            pickle.dump(S, f)
        print(kind, len(S["D"]), "Tage,", int(S["D"].tradable.sum()), "handelbar", flush=True)
