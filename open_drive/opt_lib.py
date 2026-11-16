"""
Werkzeuge fuer die Optimierung von R1: Signale, Merkmale, Ausstiegs-Simulation, Kennzahlen.

Beide Datensaetze liegen gestapelt in einer Struktur; Segmente:
  A = CFD 2016-2020, B = CFD 2021-2022 (Auswahl),  N = NQ 2023-2025 (Gegenprobe)
"""
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

NB = 390
TICK = 0.25


# ------------------------------------------------------------------ Laden
def load_cache(path):
    parts = []
    for kind in ("CFD", "NQ"):
        with open(Path(path) / f"opt_{kind}.pkl", "rb") as f:
            parts.append(pickle.load(f))
    S = {"D": pd.concat([p["D"] for p in parts], ignore_index=True)}
    for k in parts[0]:
        if k != "D":
            S[k] = np.vstack([p[k] for p in parts])
    D = S["D"]
    D["seg"] = np.where(D.kind == "NQ", "N", np.where(D.day < "2021-01-01", "A", "B"))
    D["year"] = D.day.dt.year
    D["dow"] = D.day.dt.dayofweek
    S["runhi"] = np.fmax.accumulate(S["H"], axis=1)
    S["runlo"] = np.fmin.accumulate(S["L"], axis=1)
    tp = np.nan_to_num((S["H"] + S["L"] + S["C"]) / 3)
    cv = np.cumsum(S["V"], axis=1)
    S["vwr"] = np.where(cv > 0, np.cumsum(tp * S["V"], axis=1) / np.maximum(cv, 1e-9), np.nan)
    S["cumv"] = cv
    for k in ("ema", "z30", "vwe", "vwr"):
        S[k] = pd.DataFrame(S[k]).ffill(axis=1).values
    S["Cf"] = pd.DataFrame(S["C"]).ffill(axis=1).values
    S["ndays"] = D[D.tradable].groupby("seg").size().to_dict()
    mv = np.abs(S["Cf"] - D.do.values[:, None]) / D.do.values[:, None]
    sg = np.full_like(mv, np.nan)
    for kind in D.kind.unique():                      # je Datensatz getrennt rollen
        m = (D.kind == kind).values
        sg[m] = pd.DataFrame(mv[m]).rolling(14).mean().shift(1).values
    S["sig_t"] = sg
    return S


# ------------------------------------------------------------------ Signale
def signals(S, trig=0.3, mode="close", i_min=1, i_max=359, ref="do"):
    """Erstes Signal des Tages. mode: close (Schlusskurs jenseits), close2 (zwei Schlusskurse in Folge),
    stop (Stop-Order am Level, Einstieg zum Levelpreis)."""
    D = S["D"]
    C, H, L, O = S["C"], S["H"], S["L"], S["O"]
    atr, o = D.atr.values, D[ref].values
    up, dn = (o + trig * atr)[:, None], (o - trig * atr)[:, None]
    rows = np.arange(len(D))
    with np.errstate(invalid="ignore"):
        if mode in ("close", "close2"):
            hu, hd = C >= up, C <= dn
            if mode == "close2":
                hu = hu & np.c_[np.zeros(len(D), bool), hu[:, :-1]]
                hd = hd & np.c_[np.zeros(len(D), bool), hd[:, :-1]]
        else:
            hu, hd = H >= up, L <= dn
    hit = hu | hd
    hit[:, :i_min] = False
    ok = hit.any(1)
    i = hit.argmax(1)
    both = hu[rows, i] & hd[rows, i]
    side = np.where(hu[rows, i], 1, -1)
    if mode == "stop":
        entry = np.where(side == 1, np.fmax(up[:, 0], O[rows, i]), np.fmin(dn[:, 0], O[rows, i]))
        known = i - 1
    else:
        entry, known = C[rows, i], i
    ok &= (i <= i_max) & D.tradable.values & ~np.isnan(atr) & ~np.isnan(o) & ~both
    sig = pd.DataFrame({"di": rows[ok], "i": i[ok], "known": known[ok], "side": side[ok], "entry": entry[ok],
                        "level": np.where(side == 1, up[:, 0], dn[:, 0])[ok]})
    sig["same_bar"] = mode == "stop"
    for c in ("day", "kind", "seg", "year", "dow", "atr"):
        sig[c] = D[c].values[sig.di.values]
    return sig


def signals_noise(S, k=1.0, i_min=1, i_max=359, gap=True):
    """Erster Schlusskurs ausserhalb der Rausch-Zone: Eroeffnung x (1 +- k x mittlere Bewegung der letzten
    14 Tage zur selben Uhrzeit); mit gap=True wird die Zone um die Luecke zum Vortagesschluss erweitert."""
    D = S["D"]
    C, o, pc = S["C"], D.do.values, D.pdc.values
    hi0 = np.fmax(o, pc) if gap else o
    lo0 = np.fmin(o, pc) if gap else o
    up = hi0[:, None] * (1 + k * S["sig_t"])
    dn = lo0[:, None] * (1 - k * S["sig_t"])
    S["band_up"], S["band_dn"] = up, dn
    rows = np.arange(len(D))
    with np.errstate(invalid="ignore"):
        hu, hd = C > up, C < dn
    hit = hu | hd
    hit[:, :i_min] = False
    ok = hit.any(1)
    i = hit.argmax(1)
    side = np.where(hu[rows, i], 1, -1)
    ok &= (i <= i_max) & D.tradable.values & ~np.isnan(D.atr.values) & ~np.isnan(S["sig_t"][:, -1])
    sig = pd.DataFrame({"di": rows[ok], "i": i[ok], "known": i[ok], "side": side[ok], "entry": C[rows, i][ok],
                        "level": np.where(side == 1, up[rows, i], dn[rows, i])[ok]})
    sig["same_bar"] = False
    for c in ("day", "kind", "seg", "year", "dow", "atr"):
        sig[c] = D[c].values[sig.di.values]
    return sig


def add_features(S, sig):
    """Alles, was zum Entscheidungszeitpunkt (Kerze `known`) bekannt ist. Positiv = in Trade-Richtung."""
    D = S["D"].iloc[sig.di.values].reset_index(drop=True)
    di, k, s, e, a = sig.di.values, sig.known.values, sig.side.values, sig.entry.values, sig.atr.values
    o = D.do.values
    hi = np.fmax(S["runhi"][di, k], e)
    lo = np.fmin(S["runlo"][di, k], e)
    f = pd.DataFrame(index=sig.index)
    f["tmin"] = sig.i.values
    f["rng"] = (hi - lo) / a
    f["adv"] = np.where(s == 1, o - lo, hi - o) / a                 # Gegenbewegung vor dem Signal
    f["ext"] = np.where(s == 1, hi - o, o - lo) / a                 # wie weit schon gelaufen
    f["over"] = s * (e - sig.level.values) / a                      # Einstieg jenseits des Levels
    hb, lb, cb = S["H"][di, sig.i.values], S["L"][di, sig.i.values], S["C"][di, sig.i.values]
    f["sbr"] = (hb - lb) / a
    f["sbc"] = np.where(s == 1, cb - lb, hb - cb) / np.maximum(hb - lb, 1e-9)
    f["z30"] = s * S["z30"][di, k]
    f["ema"] = s * S["ema"][di, k]
    f["vwr"] = s * (e - S["vwr"][di, k]) / a
    f["vwe"] = s * (e - S["vwe"][di, k]) / a
    f["gap"] = s * (o - D.pdc.values) / a
    f["ond"] = s * (o - D.o18.values) / a
    f["onr"] = (D.onh.values - D.onl.values) / a
    f["onpos"] = np.where(s == 1, o - D.onl.values, D.onh.values - o) / np.maximum(D.onh.values - D.onl.values, 1e-9)
    f["brk_on"] = np.where(s == 1, e - D.onh.values, D.onl.values - e) / a
    f["pmd"] = s * (o - D.o830.values) / a
    f["pmr"] = (D.pmh.values - D.pml.values) / a
    f["boxd"] = s * np.sign(D.o830.values - D.o0.values)
    f["boxm"] = s * (D.o830.values - D.o0.values) / a
    f["boxr"] = np.abs(D.o830.values - D.o0.values) / a
    mid, h = (D.o0.values + D.o830.values) / 2, np.maximum(np.abs(D.o0.values - D.o830.values) / 2, 1e-9)
    f["boxk"] = np.clip(s * (e - mid) / h, -30, 30)
    f["brk_pd"] = np.where(s == 1, e - D.pdh.values, D.pdl.values - e) / a
    f["pdr"] = D.pdr.values
    f["pdret"] = s * (D.pdc.values - D.pdo.values) / a
    f["pdpos"] = np.where(s == 1, D.pdc.values - D.pdl.values, D.pdh.values - D.pdc.values) / np.maximum(
        D.pdh.values - D.pdl.values, 1e-9)
    f["r1"] = s * D.r1.values
    f["r5"] = s * D.r5.values
    f["r20"] = s * D.r20.values
    f["atr_ratio"] = a / D.atr60.values
    f["nr4"] = D.nr4.values.astype(float)
    f["nr7"] = D.nr7.values.astype(float)
    f["wr7"] = D.wr7.values.astype(float)
    f["inside"] = D.inside.values.astype(float)
    f["rvol"] = S["cumv"][di, k] / np.maximum(S["cumv_avg"][di, k], 1e-9)
    f["rvol"] = f["rvol"].where(~np.isnan(S["cumv_avg"][di, k]))
    f["spike"] = D.spike.values / a
    k5 = np.minimum(k, 4)
    f["first5"] = s * (S["Cf"][di, k5] - o) / a
    f["long"] = (s == 1).astype(float)
    return pd.concat([sig, f], axis=1)


# ------------------------------------------------------------------ Ausstiege
@njit(cache=True)
def _sim(O, H, L, C, di, i0, side, entry, stop_d, tgt_d, be_trig, be_off, tr_act, tr_d, tmax, part_f, part_d,
         part_be, same_bar, cost, ref_l, ref_s, ref_mode, ct_mode, ct_T, ct_k, ct_act, ct_open, nb_lo, nb_hi,
         ct_off, xbar, rt_f, rt_act, cl_stop, ps_n, ps_thr, adv_k, tt_n, tt_stop):
    n = len(di)
    nb = C.shape[1]
    R = np.full(n, np.nan)
    X = np.full(n, -1, np.int64)
    why = np.zeros(n, np.int8)          # 1 Stop, 2 Ziel, 3 Zeit-Stop, 4 Tagesende
    mae = np.zeros(n)
    mfe = np.zeros(n)
    for k in range(n):
        d, s, e, sd = di[k], side[k], entry[k], stop_d[k]
        if not (sd > 0):
            continue
        stop = e - s * sd
        has_tp = not np.isnan(tgt_d[k])
        tp = e + s * tgt_d[k] if has_tp else 0.0
        has_p = part_f > 0 and not np.isnan(part_d[k])
        tp1 = e + s * part_d[k] if has_p else 0.0
        rem, real, best, worst, done, last = 1.0, 0.0, e, e, False, -1
        act, streak, advc = False, 0, 0
        start = i0[k] if same_bar[k] else i0[k] + 1
        for i in range(start, nb):
            c = C[d, i]
            if np.isnan(c):
                continue
            last = i
            adv = L[d, i] if s == 1 else H[d, i]
            fav = H[d, i] if s == 1 else L[d, i]
            if (adv - worst) * s < 0:
                worst = adv
            if i == i0[k]:                       # Einstiegskerze einer Stop-Order: nur die Gegenseite pruefen
                if (adv - stop) * s <= 0:
                    real += rem * (stop - e) * s
                    rem, done = 0.0, True
                    X[k], why[k] = i, 1
                    break
                fav = c
            else:
                if (adv - stop) * s <= 0:
                    fill = stop
                    if (O[d, i] - stop) * s < 0:
                        fill = O[d, i]
                    real += rem * (fill - e) * s
                    rem, done = 0.0, True
                    X[k], why[k] = i, 1
                    break
                if has_p and rem == 1.0 and (fav - tp1) * s >= 0:
                    real += part_f * (tp1 - e) * s
                    rem = 1.0 - part_f
                    if part_be:
                        ns = e + s * be_off[k]
                        if (ns - stop) * s > 0:
                            stop = ns
                if has_tp and (fav - tp) * s >= 0:
                    real += rem * (tp - e) * s
                    rem, done = 0.0, True
                    X[k], why[k] = i, 2
                    break
            if (fav - best) * s > 0:             # Stop-Nachzug gilt ab der naechsten Kerze
                best = fav
            run = (best - e) * s
            if not np.isnan(be_trig[k]) and run >= be_trig[k]:
                ns = e + s * be_off[k]
                if (ns - stop) * s > 0:
                    stop = ns
            if not np.isnan(tr_act[k]) and run >= tr_act[k]:
                ns = best - s * tr_d[k]
                if (ns - stop) * s > 0:
                    stop = ns
            if ct_mode > 0:                      # Kerzen-Nachzug, gilt ab der naechsten Kerze
                if not act and (c - e) * s >= ct_act[k]:
                    act = True
                co = ct_open[d, i]
                if not np.isnan(co):             # hier schliesst eine Kerze des Nachzug-Zeitrahmens
                    if (c - co) * s > 0:
                        streak += 1
                    else:
                        streak = 0
                    if act:
                        ns = np.nan
                        if ct_mode == 1 and streak >= ct_k:
                            ns = ct_open[d, i - (ct_k - 1) * ct_T]
                        elif ct_mode == 2:
                            ns = nb_lo[d, i] - ct_off if s == 1 else nb_hi[d, i] + ct_off
                        if not np.isnan(ns) and (ns - stop) * s > 0 and (c - ns) * s > 0:
                            stop = ns
            if rt_f > 0 and run >= rt_act[k]:    # Anteil des offenen Gewinns absichern
                ns = e + s * rt_f * run
                if (ns - stop) * s > 0:
                    stop = ns
            cut = False                          # fruehe Verlustbegrenzung, Ausstieg zum Schlusskurs
            if not np.isnan(cl_stop[k]) and (e - c) * s >= cl_stop[k]:
                cut = True                       # Schlusskurs weiter als cl_stop im Verlust
            if ps_n >= 0 and i - i0[k] == ps_n and (c - e) * s < ps_thr[k]:
                cut = True                       # nach ps_n Minuten nicht mindestens ps_thr im Gewinn
            if adv_k > 0:
                advc = advc + 1 if (c - O[d, i]) * s < 0 else 0
                if advc >= adv_k and (c - e) * s < 0:
                    cut = True                   # adv_k Kerzen in Folge gegen den Trade, Trade im Verlust
            if cut:
                real += rem * (c - e) * s
                rem, done = 0.0, True
                X[k], why[k] = i, 6
                break
            if tt_n >= 0 and i - i0[k] >= tt_n:  # nach tt_n Minuten Stop auf tt_stop hinter den Einstieg
                ns = e - s * tt_stop[k]
                if (ns - stop) * s > 0:
                    stop = ns
            if (tmax >= 0 and i - i0[k] >= tmax) or i >= xbar:
                real += rem * (c - e) * s
                rem, done = 0.0, True
                X[k], why[k] = i, 3
                break
            if ref_mode > 0 and i > i0[k] and (ref_mode == 1 or rem < 1.0):
                rf = ref_l[d, i] if s == 1 else ref_s[d, i]       # Schlusskurs jenseits der Referenzlinie
                if not np.isnan(rf) and (c - rf) * s < 0:
                    real += rem * (c - e) * s
                    rem, done = 0.0, True
                    X[k], why[k] = i, 5
                    break
        if not done:
            if last < 0:
                continue
            real += rem * (C[d, last] - e) * s
            X[k], why[k] = last, 4
        R[k] = (real - cost[k]) / sd
        mae[k] = (e - worst) * s
        mfe[k] = (best - e) * s
    return R, X, why, mae, mfe


def stop_dist(S, sig, stop):
    """stop: Zahl = x ATR; ('bar', min, max) = hinter die Signalkerze; ('swing', n, min, max) = hinter das
    Tief/Hoch der letzten n Kerzen; ('level', x) = x ATR hinter das Ausbruchs-Level."""
    a, e, s = sig.atr.values, sig.entry.values, sig.side.values
    if isinstance(stop, (int, float)):
        return stop * a
    di, k = sig.di.values, sig.known.values
    if stop[0] == "level":
        return np.maximum(s * (e - sig.level.values) + stop[1] * a, 0.02 * a)
    n = 1 if stop[0] == "bar" else stop[1]
    lo_, hi_ = stop[-2], stop[-1]
    ext = np.empty(len(sig))
    for j in range(len(sig)):
        seg = slice(max(k[j] - n + 1, 0), k[j] + 1)
        ext[j] = np.nanmin(S["L"][di[j], seg]) if s[j] == 1 else np.nanmax(S["H"][di[j], seg])
    d = s * (e - ext) + TICK
    return np.clip(d, lo_ * a, hi_ * a)


def _ctrail(S, ct, sd):
    """Kerzen-Nachzug. ct = dict(mode='open'|'ext', T=Kerzenlaenge in Min, k=Kerzen in Folge, act=Ausloeser in R,
    win=Fenster in Min fuer 'ext', off=Abstand in Punkten).
      open: nach k Kerzen in Folge in Trade-Richtung Stop auf das Open der ersten dieser Kerzen
      ext : Stop hinter das Tief/Hoch der letzten `win` Minuten, bei jedem Kerzenschluss"""
    z = np.zeros((1, 1))
    if ct is None:
        return 0, 1, 1, np.zeros(len(sd)), z, z, z, 0.0
    T = ct.get("T", 1)
    key = ("ct_open", T)
    if key not in S:
        Of = np.where(np.isnan(S["O"]), np.c_[S["Cf"][:, :1], S["Cf"][:, :-1]], S["O"])
        co = np.full_like(Of, np.nan)
        idx = np.arange(T - 1, NB, T)
        co[:, idx] = Of[:, idx - T + 1]
        S[key] = co
    if ct["mode"] == "ext":
        w = ct["win"]
        if ("nb_lo", w) not in S:
            S[("nb_lo", w)] = pd.DataFrame(S["L"]).T.rolling(w, min_periods=1).min().T.values
            S[("nb_hi", w)] = pd.DataFrame(S["H"]).T.rolling(w, min_periods=1).max().T.values
        lo, hi = S[("nb_lo", w)], S[("nb_hi", w)]
    else:
        lo = hi = z
    return (1 if ct["mode"] == "open" else 2, T, ct.get("k", 1), ct.get("act", 1.0) * sd, S[key], lo, hi,
            float(ct.get("off", 0.0)))


def run_exit(S, sig, stop=0.15, rr=0.5, tgt_atr=None, be=None, be_off=0.0, trail=None, tmax=-1,
             part=0.0, part_rr=None, part_be=True, cost_mult=1.0, ref=None, ref_mode=1, ctrail=None,
             xbar=NB, ratchet=None, close_stop=None, progress=None, adverse=0, tighten=None):
    """Liefert R je Trade. be = Ausloeser in R; trail = (Ausloeser in R, Abstand in R); part = Anteil,
    der bei part_rr x Stop glattgestellt wird; xbar = spaetester Ausstieg (Minuten-Index ab 09:30);
    ratchet = (Anteil, Ausloeser in R): Stop sichert diesen Anteil des hoechsten offenen Gewinns.
    Fruehe Verlustbegrenzung (alles in Vielfachen des Stops):
      close_stop = x      : Ausstieg, sobald eine Minute weiter als x im Verlust schliesst
      progress = (n, x)   : Ausstieg nach n Minuten, wenn der Trade dann nicht mindestens x im Gewinn schliesst
      adverse = k         : Ausstieg nach k Kerzen in Folge gegen den Trade, solange er im Verlust liegt
      tighten = (n, x)    : nach n Minuten wandert der Stop auf x hinter den Einstieg (0 = Einstand)"""
    a = sig.atr.values
    sd = stop_dist(S, sig, stop)
    tgt = np.full(len(sig), np.nan) if (rr is None and tgt_atr is None) else (
        tgt_atr * a if tgt_atr is not None else rr * sd)
    nanv = np.full(len(sig), np.nan)
    bt = be * sd if be is not None else nanv
    bo = be_off * sd
    ta, td = (trail[0] * sd, trail[1] * sd) if trail is not None else (nanv, nanv)
    pd_ = part_rr * sd if part > 0 else nanv
    cost = np.where(sig.kind.values == "NQ", 1.0, 0.0032 * a) * cost_mult
    if ref == "vwap":                       # Rest/Position schliessen, wenn ein Schlusskurs hinter der VWAP liegt
        rl = rs = S["vwr"]
    elif ref == "band":                     # ... hinter max(Zonenrand, VWAP) bzw. min(...)
        rl, rs = np.fmax(S["band_up"], S["vwr"]), np.fmin(S["band_dn"], S["vwr"])
    else:
        rl = rs = S["vwr"]
    R, X, why, mae, mfe = _sim(S["O"], S["H"], S["L"], S["C"], sig.di.values, sig.i.values, sig.side.values,
                               sig.entry.values, sd, tgt, bt, bo, ta, td, tmax, part, pd_, part_be,
                               sig.same_bar.values, cost, rl, rs, ref_mode if ref else 0, *_ctrail(S, ctrail, sd),
                               xbar, ratchet[0] if ratchet else 0.0, ratchet[1] * sd if ratchet else nanv,
                               close_stop * sd if close_stop is not None else nanv,
                               progress[0] if progress else -1, progress[1] * sd if progress else nanv, adverse,
                               tighten[0] if tighten else -1, tighten[1] * sd if tighten else nanv)
    return R, dict(X=X, why=why, mae=mae / a, mfe=mfe / a, stop_pts=sd)


# ------------------------------------------------------------------ Kennzahlen
def perf(S, sig, R, seg=None):
    m = ~np.isnan(R)
    if seg is not None:
        m &= np.isin(sig.seg.values, list(seg))
    r = R[m]
    nd = sum(S["ndays"][x] for x in (seg or "ABN"))
    if len(r) < 5:
        return dict(n=len(r), wk=0.0, win=np.nan, E=np.nan, t=np.nan, pf=np.nan, Ryr=0.0, dd=np.nan, aw=np.nan, al=np.nan)
    daily = np.zeros(nd)
    daily[:len(r)] = r
    eq = np.cumsum(r)
    w, l = r[r > 0], r[r <= 0]
    return dict(n=len(r), wk=len(r) / nd * 5, win=(r > 0).mean(), E=r.mean(),
                t=daily.mean() / daily.std(ddof=1) * np.sqrt(nd), pf=w.sum() / max(-l.sum(), 1e-9),
                Ryr=r.sum() / nd * 252, dd=(eq - np.maximum.accumulate(eq)).min(),
                aw=w.mean() if len(w) else np.nan, al=l.mean() if len(l) else np.nan)


def cell(S, sig, R, seg):
    p = perf(S, sig, R, seg)
    return f"{p['win']:.0%} {p['E']:+.3f} ({p['t']:+.1f}) {p['wk']:.1f}/W" if p["n"] >= 5 else "-"


def row(S, sig, R, label, segs=("A", "B")):
    r = {"Variante": label}
    for sg in segs:
        r[sg] = cell(S, sig, R, sg)
    return r


# ------------------------------------------------------------------ Einstiegs-Varianten nach dem Signal
def pullback(S, sig, off=0.0, window=30):
    """Limit-Order nach dem Schlusskurs-Signal: Level + off x ATR (off < 0 = tiefer). Fuellung nur, wenn der
    Kurs einen Tick durch das Limit handelt, binnen `window` Kerzen."""
    out = sig.copy()
    lim = sig.level.values + sig.side.values * off * sig.atr.values
    j_ = np.full(len(sig), -1)
    for n, (d, i, s) in enumerate(zip(sig.di.values, sig.i.values, sig.side.values)):
        hi = min(i + window, 359)
        seg = S["L"][d, i + 1:hi + 1] if s == 1 else S["H"][d, i + 1:hi + 1]
        with np.errstate(invalid="ignore"):
            hit = np.flatnonzero((seg <= lim[n] - TICK) if s == 1 else (seg >= lim[n] + TICK))
        if len(hit):
            j_[n] = i + 1 + hit[0]
    ok = j_ >= 0
    out = out[ok].copy()
    out["i"], out["known"], out["entry"], out["same_bar"] = j_[ok], j_[ok] - 1, lim[ok], True
    return out.reset_index(drop=True)


def confirm(S, sig, window=5):
    """Stop-Order einen Tick ueber dem Hoch (unter dem Tief) der Signalkerze, binnen `window` Kerzen."""
    out = sig.copy()
    d_, i_, s_ = sig.di.values, sig.i.values, sig.side.values
    trg = np.where(s_ == 1, S["H"][d_, i_] + TICK, S["L"][d_, i_] - TICK)
    j_, px = np.full(len(sig), -1), np.full(len(sig), np.nan)
    for n, (d, i, s) in enumerate(zip(d_, i_, s_)):
        hi = min(i + window, 359)
        seg = S["H"][d, i + 1:hi + 1] if s == 1 else S["L"][d, i + 1:hi + 1]
        with np.errstate(invalid="ignore"):
            hit = np.flatnonzero((seg >= trg[n]) if s == 1 else (seg <= trg[n]))
        if len(hit):
            j_[n] = i + 1 + hit[0]
            o = S["O"][d, j_[n]]
            px[n] = max(trg[n], o) if s == 1 else min(trg[n], o)
    ok = j_ >= 0
    out = out[ok].copy()
    out["i"], out["known"], out["entry"], out["same_bar"] = j_[ok], j_[ok] - 1, px[ok], True
    return out.reset_index(drop=True)


BASE = dict(stop=0.15, rr=0.5)
HYB = dict(stop=0.15, rr=None, part=0.5, part_rr=0.5)
RUN = dict(stop=0.15, rr=None)
