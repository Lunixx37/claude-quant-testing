"""
Ereignistabelle fuer die Abschluss-Suche.

Je Handelstag (08:30-16:00 New York, 1-Min-Bars) werden alle moeglichen Einstiege erfasst:

  Reclaim an einem Level (Kurs handelt durch, 1-Min-Schluss binnen 10 Kerzen zurueck), beide Seiten:
      Stdv-Box (Kanten, Mitte, 2 / 2.25 / 2.5 / 3.5 / 4 / 4.25 / 4.5), Psych 100 / 50,
      Vortageshoch/-tief/-schluss, Overnight-Hoch/-Tief, RTH-Eroeffnung, Opening Range (30 Min),
      RTH-VWAP, und die Kanten von FVG / iFVG / Order Block / Rejection Block (5-Min)
  Ausbruch (1-Min-Schluss jenseits):
      Abstand zur Eroeffnung 0.2 / 0.3 / 0.4 / 0.5 ATR, Opening Range 15 / 30 Min, neues Tagesextrem
      nach >= 30 Min Pause, Vortageshoch/-tief, Overnight-Hoch/-Tief, Indecision-Box
      (5-Min-Kerze mit Koerper <= 20 % der Spanne, Spanne >= 0.03 ATR; Ausbruch binnen 30 Min)

Zu jedem Ereignis: Kontext-Merkmale (Uhrzeit, Trend, Abstand zur Eroeffnung, VWAP-Lage, Box, ...),
Konfluenz-Flags am Einstiegskurs und das Ergebnis in R fuer 4 feste Stops x 5 Ziele plus Struktur-Stop.
Einstieg zum Schluss der Signalkerze, Stop zuerst wenn Stop und Ziel in derselben Kerze, 15:59 flat.
Kosten: NQ 1 Punkt je Trade, CFD derselbe Anteil der ATR (0.0032 ATR).

Aufruf:  python open_drive/build_events.py <ausgabe-ordner>
"""
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parent.parent
ORIG = [2.0, 2.25, 2.5, 3.5, 4.0, 4.25, 4.5]
STOPS = [0.06, 0.10, 0.15, 0.22]            # x ATR
RRS = [0.5, 0.75, 1.0, 1.5, 2.0]
NB = 450                                    # 08:30 .. 15:59
RTH0 = 60                                   # Index von 09:30
TICK, REARM, NREC, MAXEV = 0.25, 0.02, 10, 3
MAX_AGE = 24 * 60


# ------------------------------------------------------------------ Daten
def load(kind):
    if kind == "NQ":
        df = pd.read_csv(ROOT / "Dataset_NQ_1min_2022_2025.csv",
                         usecols=["timestamp ET", "open", "high", "low", "close", "volume"])
        df.index = pd.to_datetime(df.pop("timestamp ET"), format="%m/%d/%Y %H:%M") - pd.Timedelta("1min")
        return df[~df.index.duplicated()].sort_index()
    parts = []
    for i in (1, 2):
        with zipfile.ZipFile(ROOT / f"1m_data_part{i}.zip") as z:
            parts.append(pd.read_csv(z.open(f"1m_data_part{i}.csv"), sep="\t"))
    df = pd.concat(parts)
    broker = pd.DatetimeIndex(pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S"))
    et = broker.tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="NaT") \
        .tz_convert("America/New_York").tz_localize(None)
    out = pd.DataFrame({"open": df.Open.values, "high": df.High.values, "low": df.Low.values,
                        "close": df.Close.values, "volume": df.TickVolume.values.astype(float)}, index=et)
    out = out[~out.index.isna()]
    out = out[~out.index.duplicated()].sort_index()
    return out[out.index < "2023-01-01"]


def detect_zones(bars):
    """5-Min-Zonen: (verfuegbar ab, ungueltig ab, unten, oben, Polaritaet, Typ 0 FVG 1 OB 2 RB 3 iFVG), Zeiten in Minuten."""
    b5 = bars.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    o, h, l, c = (b5[x].values for x in ("open", "high", "low", "close"))
    t = b5.index.values.astype("datetime64[m]").astype(np.int64)
    n = len(c)
    z = []
    for i in range(2, n):
        if t[i] - t[i - 2] > 15:
            continue
        if l[i] > h[i - 2]:
            z.append((t[i] + 5, h[i - 2], l[i], 1, 0, i))
        if h[i] < l[i - 2]:
            z.append((t[i] + 5, h[i], l[i - 2], -1, 0, i))
        k = i - 2
        if c[k] < o[k] and c[k + 1] > o[k + 1] and c[k + 1] > h[k] and l[i] > h[k]:
            z.append((t[i] + 5, l[k], h[k], 1, 1, i))
        if c[k] > o[k] and c[k + 1] < o[k + 1] and c[k + 1] < l[k] and h[i] < l[k]:
            z.append((t[i] + 5, l[k], h[k], -1, 1, i))
    for i in range(2, n - 2):
        if t[i + 2] - t[i - 2] > 25:
            continue
        rng = h[i] - l[i]
        if rng <= 0:
            continue
        if h[i] > max(h[i - 1], h[i - 2], h[i + 1], h[i + 2]) and (h[i] - max(o[i], c[i])) >= 0.5 * rng:
            z.append((t[i + 2] + 5, max(o[i], c[i]), h[i], -1, 2, i + 2))
        if l[i] < min(l[i - 1], l[i - 2], l[i + 1], l[i + 2]) and (min(o[i], c[i]) - l[i]) >= 0.5 * rng:
            z.append((t[i + 2] + 5, l[i], min(o[i], c[i]), 1, 2, i + 2))

    def invalid(idx, lo, hi, pol, av):
        seg = c[idx + 1: idx + 1 + 300]
        hit = np.flatnonzero(seg > hi) if pol == -1 else np.flatnonzero(seg < lo)
        if len(hit) and t[idx + 1 + hit[0]] + 5 <= av + MAX_AGE:
            return t[idx + 1 + hit[0]] + 5, idx + 1 + hit[0], True
        return av + MAX_AGE, -1, False

    rows = []
    for av, lo, hi, pol, typ, idx in z:
        inv, ii, broken = invalid(idx, lo, hi, pol, av)
        rows.append((av, inv, lo, hi, pol, typ))
        if typ == 0 and broken:                         # durchbrochene FVG wird zur inversen FVG
            inv2, _, _ = invalid(ii, lo, hi, -pol, inv)
            rows.append((inv, inv2, lo, hi, -pol, 3))
    zd = np.array(rows, dtype=float)
    return zd[np.argsort(zd[:, 0])]


def prepare(kind):
    bars = load(kind)
    t = bars.index
    lp = np.log(bars["close"].values)
    ret = np.diff(lp, prepend=lp[0])
    vol = pd.Series(ret).ewm(span=390, min_periods=100).std().values
    a = 2 / 101
    ema = pd.Series(ret).ewm(alpha=a, adjust=False).mean().values / (vol * np.sqrt(a / (2 - a)))
    z30 = (lp - np.r_[np.full(30, np.nan), lp[:-30]]) / (vol * np.sqrt(30))
    eth = (t + pd.Timedelta("6h")).normalize()
    g = bars.groupby(eth)
    atr = (g.high.max() - g.low.min()).rolling(14).mean().shift(1)
    zones = detect_zones(bars)
    tmin = t.values.astype("datetime64[m]").astype(np.int64)
    clock = (t.hour * 60 + t.minute).values
    dnum = t.normalize().values
    O, H, L, C, V = (bars[c].values for c in ("open", "high", "low", "close", "volume"))
    udays = np.unique(dnum)
    first = pd.Timestamp("2016-11-16" if kind == "CFD" else "2023-01-01")
    days, prev = [], None
    for d in udays:
        day = pd.Timestamp(d)
        i0, i1 = np.searchsorted(dnum, d), np.searchsorted(dnum, d, side="right")
        ck = clock[i0:i1]
        s = (ck >= 510) & (ck < 960)
        if day.dayofweek > 4 or s.sum() < 400 or day not in atr.index or np.isnan(atr.loc[day]):
            continue
        pos = np.arange(i0, i1)[s]
        idx = ck[s] - 510
        full = {}
        cl = np.full(NB, np.nan); cl[idx] = C[pos]
        cl = pd.Series(cl).ffill().bfill().values
        for nm, arr in (("O", O), ("H", H), ("L", L)):
            x = np.full(NB, np.nan); x[idx] = arr[pos]
            full[nm] = np.where(np.isnan(x), cl, x)
        full["C"] = cl
        v = np.zeros(NB); v[idx] = V[pos]
        for nm, arr in (("ema", ema), ("z30", z30)):
            x = np.full(NB, np.nan); x[idx] = arr[pos]
            full[nm] = pd.Series(x).ffill().bfill().values
        # Open 00:00 und 08:30, Overnight (18:00 Vortag - 09:30)
        m0 = np.flatnonzero(ck == 0)
        m830 = np.flatnonzero(ck == 510)
        if not len(m0) or not len(m830):
            prev_ok = False
            continue
        o0, o830 = O[i0 + m0[0]], O[i0 + m830[0]]
        j0 = np.searchsorted(tmin, tmin[i0] - 360)                      # 18:00 Vortag
        j1 = i0 + np.searchsorted(ck, 570)
        if j1 - j0 < 200:
            continue
        rth = slice(RTH0, NB)
        tp = (full["H"] + full["L"] + full["C"]) / 3
        vv = np.where(np.arange(NB) >= RTH0, v, 0.0)
        cv = np.cumsum(vv)
        vw = np.where(cv > 0, np.cumsum(tp * vv) / np.maximum(cv, 1e-9), np.nan)
        rec = dict(day=day, atr=float(atr.loc[day]), o0=o0, o830=o830, onh=H[j0:j1].max(), onl=L[j0:j1].min(),
                   vwap=vw, t0=tmin[i0 + m830[0]], **full,
                   dh=full["H"][rth].max(), dl=full["L"][rth].min(), dc=full["C"][-1])
        rec["prev"] = prev
        prev = rec
        if day >= first and rec["prev"] is not None and (day - rec["prev"]["day"]).days <= 5:
            days.append(rec)
    # Tageskontext: 5-Tage-Rendite
    dc = pd.Series({d["day"]: d["dc"] for d in days})
    r = np.log(dc).diff()
    sd = r.rolling(60, min_periods=20).std().shift(1)
    r5 = (r.rolling(5).sum().shift(1) / (sd * np.sqrt(5))).fillna(0)
    for d in days:
        d["r5"] = float(r5.loc[d["day"]])
    return days, zones


# ------------------------------------------------------------------ Engine
@njit(cache=True)
def find_events(O, H, L, C, lvl, side, rearm, thr, i0, i1):
    """Reclaim-Ereignisse an einem (ggf. beweglichen) Level zwischen Bar i0 und i1."""
    S = np.full(MAXEV, -1, np.int64)
    R = np.full(MAXEV, -1, np.int64)
    E = np.full(MAXEV, np.nan)
    k = 0
    if i0 >= i1 or np.isnan(lvl[i0]):
        return S, R, E
    armed = (O[i0] - lvl[i0]) * side >= rearm
    i = i0
    while i < i1 and k < MAXEV:
        lv = lvl[i]
        if armed:
            touched = (L[i] <= lv - thr) if side == 1 else (H[i] >= lv + thr)
            if touched:
                S[k] = i
                ext = L[i] if side == 1 else H[i]
                r = -1
                through = False
                for q in range(i, min(i + NREC + 1, i1)):
                    if side == 1:
                        ext = min(ext, L[q])
                        through = through or (L[q] < lvl[q])
                        if through and C[q] > lvl[q]:
                            r = q
                            break
                    else:
                        ext = max(ext, H[q])
                        through = through or (H[q] > lvl[q])
                        if through and C[q] < lvl[q]:
                            r = q
                            break
                R[k] = r
                E[k] = ext
                k += 1
                armed = False
        if not armed and (C[i] - lv) * side >= rearm:
            armed = True
        i += 1
    return S, R, E


@njit(cache=True)
def outcomes(H, L, C, j, side, dists, rrs, cost):
    """R netto je (Stop, Ziel). dists in Punkten (nan = ungueltig)."""
    n = len(C)
    out = np.full((len(dists), len(rrs)), np.nan)
    xb = np.full((len(dists), len(rrs)), -1, np.int64)
    entry = C[j]
    for a in range(len(dists)):
        d = dists[a]
        if np.isnan(d) or d <= 0:
            continue
        for b in range(len(rrs)):
            stop = entry - side * d
            tp = entry + side * d * rrs[b]
            px, e = C[n - 1], n - 1
            for i in range(j + 1, n):
                if side == 1:
                    if L[i] <= stop:
                        px, e = stop, i
                        break
                    if H[i] >= tp:
                        px, e = tp, i
                        break
                else:
                    if H[i] >= stop:
                        px, e = stop, i
                        break
                    if L[i] <= tp:
                        px, e = tp, i
                        break
            out[a, b] = (side * (px - entry) - cost) / d
            xb[a, b] = e
    return out, xb


@njit(cache=True)
def zone_flags(zz, t, price, side, tol):
    """Flags je Zonentyp: Kurs liegt in gueltiger Zone gleicher Polaritaet (0-3) / gegenlaeufiger FVG (4)."""
    f = np.zeros(5, np.bool_)
    for i in range(len(zz)):
        if zz[i, 0] <= t and zz[i, 1] > t and zz[i, 2] - tol <= price and zz[i, 3] + tol >= price:
            if zz[i, 4] == side:
                f[int(zz[i, 5])] = True
            elif zz[i, 5] == 0:
                f[4] = True
    return f


def day_events(d, zones, kind):
    O, H, L, C, atr = d["O"], d["H"], d["L"], d["C"], d["atr"]
    p = d["prev"]
    thr = TICK if kind == "NQ" else 0.0008 * atr
    cost = 1.0 if kind == "NQ" else 0.0032 * atr
    mid, h = (d["o0"] + d["o830"]) / 2, abs(d["o0"] - d["o830"]) / 2
    open930 = O[RTH0]
    runhi = np.maximum.accumulate(np.where(np.arange(NB) >= RTH0, H, -np.inf))
    runlo = np.minimum.accumulate(np.where(np.arange(NB) >= RTH0, L, np.inf))
    const = lambda v: np.full(NB, v)
    ev = []        # (grp, name, side, s, r, ext, lvl_at_r, struct_stop, ord)

    def reclaim(grp, name, lvl, i0=0, sides=(1, -1), far=None):
        for side in sides:
            S, R, E = find_events(O, H, L, C, lvl, side, REARM * atr, thr, i0, NB)
            for k in range(MAXEV):
                if S[k] < 0:
                    break
                if R[k] >= 1:
                    st = E[k] - side * TICK
                    if far is not None:                                  # Zone: Stop hinter die ferne Kante
                        st = min(st, far - TICK) if side == 1 else max(st, far + TICK)
                    ev.append((grp, name, side, S[k], R[k], E[k], lvl[R[k]], st, k))

    # --- Level
    if h > 0:
        reclaim("edge", "edge00", const(d["o0"])); reclaim("edge", "edge830", const(d["o830"]))
        reclaim("mid", "mid", const(mid))
        for k in ORIG:
            g = "c2" if k <= 2.5 else ("l35" if k == 3.5 else "c4")
            reclaim(g, f"+{k}", const(mid + k * h)); reclaim(g, f"-{k}", const(mid - k * h))
    lo_p, hi_p = L.min() - 0.02 * atr, H.max() + 0.02 * atr
    for lv in np.arange(np.ceil(lo_p / 50) * 50, hi_p, 50):
        reclaim("ps100" if lv % 100 == 0 else "ps50", f"ps{lv:.0f}", const(lv))
    reclaim("pd", "pdh", const(p["dh"])); reclaim("pd", "pdl", const(p["dl"])); reclaim("pdc", "pdc", const(p["dc"]))
    reclaim("on", "onh", const(d["onh"]), RTH0); reclaim("on", "onl", const(d["onl"]), RTH0)
    reclaim("open", "open", const(open930), RTH0 + 5)
    orh, orl = H[RTH0:RTH0 + 30].max(), L[RTH0:RTH0 + 30].min()
    reclaim("or", "orh", const(orh), RTH0 + 30); reclaim("or", "orl", const(orl), RTH0 + 30)
    reclaim("vwap", "vwap", d["vwap"], RTH0 + 15)
    # --- Zonen
    t0 = d["t0"]
    a = zones[:, 0]
    zz = zones[np.searchsorted(a, t0 - MAX_AGE): np.searchsorted(a, t0 + NB)]
    zz = zz[zz[:, 1] > t0]
    zn = ("fvg", "ob", "rb", "ifvg")
    for av, inv, zlo, zhi, pol, typ in zz:
        if zhi < lo_p or zlo > hi_p:
            continue
        i0 = int(max(av - t0, 0)); i1 = int(min(inv - t0, NB))
        if i1 - i0 < 3:
            continue
        side = int(pol)
        lvl = const(zhi if side == 1 else zlo)
        S, R, E = find_events(O, H, L, C, lvl, side, REARM * atr, thr, i0, i1)
        for k in range(MAXEV):
            if S[k] < 0:
                break
            if R[k] >= 1:
                far = zlo if side == 1 else zhi
                st = min(E[k], far) - TICK if side == 1 else max(E[k], far) + TICK
                ev.append((zn[int(typ)], zn[int(typ)], side, S[k], R[k], E[k], lvl[0], st, k))
    # --- Ausbrueche
    bars = np.arange(NB)

    def first_close(mask, i0):
        ii = np.flatnonzero(mask & (bars >= i0))
        return int(ii[0]) if len(ii) else -1

    def brk(grp, name, side, r, struct=np.nan, lvl=np.nan):
        if r >= 1:
            ev.append((grp, name, side, r, r, np.nan, lvl, struct, 0))

    for x in (0.2, 0.3, 0.4, 0.5):
        brk(f"fo{x}", f"fo{x}", 1, first_close(C >= open930 + x * atr, RTH0 + 1), lvl=open930 + x * atr)
        brk(f"fo{x}", f"fo{x}", -1, first_close(C <= open930 - x * atr, RTH0 + 1), lvl=open930 - x * atr)
    for n in (15, 30):
        oh, ol = H[RTH0:RTH0 + n].max(), L[RTH0:RTH0 + n].min()
        brk(f"orb{n}", f"orb{n}", 1, first_close(C > oh, RTH0 + n), struct=(oh + ol) / 2, lvl=oh)
        brk(f"orb{n}", f"orb{n}", -1, first_close(C < ol, RTH0 + n), struct=(oh + ol) / 2, lvl=ol)
    brk("bo_pd", "bo_pdh", 1, first_close(C > p["dh"], RTH0), lvl=p["dh"])
    brk("bo_pd", "bo_pdl", -1, first_close(C < p["dl"], RTH0), lvl=p["dl"])
    brk("bo_on", "bo_onh", 1, first_close(C > d["onh"], RTH0), lvl=d["onh"])
    brk("bo_on", "bo_onl", -1, first_close(C < d["onl"], RTH0), lvl=d["onl"])
    # neues Tagesextrem nach >= 30 Min Pause
    for side in (1, -1):
        run = runhi if side == 1 else runlo
        cnt, last_new = 0, RTH0
        for i in range(RTH0 + 1, NB - 1):
            new = (H[i] > run[i - 1]) if side == 1 else (L[i] < run[i - 1])
            if new:
                if i - last_new >= 30 and cnt < 3 and ((C[i] > run[i - 1]) if side == 1 else (C[i] < run[i - 1])):
                    brk("newext", "newext", side, i, lvl=run[i - 1])
                    cnt += 1
                last_new = i
    # Indecision-Box (5-Min)
    cnt = 0
    for b0 in range(RTH0, NB - 10, 5):
        o5, c5, h5, l5 = O[b0], C[b0 + 4], H[b0:b0 + 5].max(), L[b0:b0 + 5].min()
        rg = h5 - l5
        if rg >= 0.03 * atr and abs(c5 - o5) <= 0.2 * rg and cnt < 6:
            seg = slice(b0 + 5, min(b0 + 35, NB - 1))
            up = np.flatnonzero(C[seg] > h5); dn = np.flatnonzero(C[seg] < l5)
            iu = up[0] if len(up) else 10 ** 6
            idn = dn[0] if len(dn) else 10 ** 6
            if min(iu, idn) < 10 ** 6:
                side = 1 if iu < idn else -1
                brk("ib", "ib", side, b0 + 5 + min(iu, idn), struct=(l5 if side == 1 else h5) - side * TICK,
                    lvl=h5 if side == 1 else l5)
                cnt += 1

    # --- Merkmale und Ergebnisse
    recl_first = {1: 10 ** 9, -1: 10 ** 9}
    for g, nme, side, s, r, ext, lv, st, k in ev:
        if g in ("edge", "c2", "l35", "c4") and s != r or g in ("edge", "c2", "l35", "c4"):
            recl_first[side] = min(recl_first[side], r)
    rows = []
    tol = 0.012 * atr
    lv_stdv = np.array([mid + s_ * k * h for k in ORIG for s_ in (1, -1)]) if h > 0 else np.array([np.nan])
    for g, nme, side, s, r, ext, lv, st, k in ev:
        if r < RTH0 or r > NB - 31:
            continue
        entry = C[r]
        sd = abs(entry - st) if not np.isnan(st) else np.nan
        if not np.isnan(sd):
            sd = max(sd, 0.02 * atr)
            if sd > 0.4 * atr or (entry - st) * side <= 0:
                sd = np.nan
        dists = np.array([x * atr for x in STOPS] + [sd])
        out, xb = outcomes(H, L, C, r, side, dists, np.array(RRS), cost)
        zf = zone_flags(zz, t0 + r, entry, side, 0.008 * atr)
        vw = d["vwap"][r]
        rec = dict(day=d["day"], bar=r, side=side, grp=g, name=nme, ord=k, rb=r - s, atr=atr, entry=entry,
                   risk_s=sd / atr if not np.isnan(sd) else np.nan,
                   fo=side * (entry - open930) / atr, ema=side * d["ema"][r], z30=side * d["z30"][r],
                   room=((runhi[r] - entry) if side == 1 else (entry - runlo[r])) / atr,
                   back=((entry - runlo[r]) if side == 1 else (runhi[r] - entry)) / atr,
                   rng=(runhi[r] - runlo[r]) / atr, gap=side * (open930 - p["dc"]) / atr, r5=side * d["r5"],
                   vw=side * (entry - vw) / atr if not np.isnan(vw) else 0.0,
                   boxrel=2 * h / atr, boxk=side * (entry - mid) / h if h > 0 else 0.0,
                   boxdir=side * np.sign(d["o830"] - d["o0"]),
                   mom=bool((C[r] > H[r - 1] and C[r] > O[r]) if side == 1 else (C[r] < L[r - 1] and C[r] < O[r])),
                   prior_opp=bool(recl_first[-side] < s), depth=abs(ext - lv) / atr if not np.isnan(ext) else 0.0,
                   c_ps100=abs(entry - round(entry / 100) * 100) <= tol,
                   c_ps50=abs(entry - round(entry / 50) * 50) <= tol,
                   c_stdv=bool(np.nanmin(np.abs(lv_stdv - entry)) <= tol) if h > 0 else False,
                   c_vwap=bool(not np.isnan(vw) and abs(entry - vw) <= 1.5 * tol),
                   c_pd=min(abs(entry - p["dh"]), abs(entry - p["dl"]), abs(entry - p["dc"])) <= tol,
                   c_on=min(abs(entry - d["onh"]), abs(entry - d["onl"])) <= tol,
                   c_fvg=zf[0], c_ob=zf[1], c_rb=zf[2], c_ifvg=zf[3], c_fvg_opp=zf[4],
                   in_pd=bool(p["dl"] <= entry <= p["dh"]), dow=d["day"].dayofweek)
        for a in range(len(dists)):
            for b in range(len(RRS)):
                rec[f"R{a}_{b}"] = out[a, b]
                rec[f"X{a}_{b}"] = xb[a, b]
        rows.append(rec)
    return rows


def build(kind):
    days, zones = prepare(kind)
    rows = []
    for di, d in enumerate(days):
        for r in day_events(d, zones, kind):
            r["di"] = di
            rows.append(r)
    ev = pd.DataFrame(rows).sort_values(["di", "bar"]).reset_index(drop=True)
    dl = pd.DataFrame({"di": range(len(days)), "day": [d["day"] for d in days]})
    return ev, dl


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for kind in ("CFD", "NQ"):
        ev, dl = build(kind)
        ev.to_pickle(out / f"events_{kind}.pkl")
        dl.to_pickle(out / f"days_{kind}.pkl")
        print(kind, len(dl), "Tage", len(ev), "Ereignisse;", ev.grp.value_counts().to_dict(), flush=True)
