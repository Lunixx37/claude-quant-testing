"""
K2 mit veraenderten Box-Leveln und Uhrzeit-Filter.

K2 (aus Branch claude/hopeful-hamilton-gxoy9x, hier eigenstaendig nachgebaut):
  Box   = Open 00:00 ET / Open 08:30 ET, Mitte, h = halbe Boxhoehe
  Level = Mitte +- k*h (Original: k = 3.5)
  Entry = Reclaim: Kurs handelt durch das Level, eine 1-Min-Kerze schliesst binnen 10 Kerzen
          zurueck, bricht das Extrem der Vorkerze und hat die passende Farbe; vorher gab es am
          selben Tag schon einen Reclaim in Gegenrichtung (an irgendeinem Original-Level)
  Stop  = Sweep-Extrem + 1 Tick, mindestens 0.02 ATR; Ziel = Box-Mitte; 15:59 flat
  max. 3 Touches je Level und Seite, immer nur eine Position, Kosten 1 Punkt (CFD: 0.0032 ATR)

Scans:
  1  Zeitumrechnung: alte feste -7h gegen korrekte Sommerzeit-Umrechnung (Level 3.5)
  2  k von 1.0 bis 7.0 in 0.25-Schritten (Box-Einheiten)
  3  Level in ATR-Einheiten statt Box-Einheiten: Mitte +- c*ATR
  4  Uhrzeit-Filter: Einstiege 09:30-10:00 auslassen
  6  Feines Raster um k = 3.5

Aufruf:  python funktions_studien/k2_level_scan.py [--plot]
"""
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parent.parent          # Daten liegen im Wurzelverzeichnis des Repositories
HERE = Path(__file__).resolve().parent
ORIG = [2.0, 2.25, 2.5, 3.5, 4.0, 4.25, 4.5]
TICK, REARM, NREC, MAXEV = 0.25, 0.02, 10, 3
pd.set_option("display.width", 220)


# ------------------------------------------------------------------ Daten
def load(kind, fixed7h=False):
    if kind == "NQ":
        df = pd.read_csv(ROOT / "Dataset_NQ_1min_2022_2025.csv", usecols=["timestamp ET", "open", "high", "low", "close"])
        df.index = pd.to_datetime(df.pop("timestamp ET"), format="%m/%d/%Y %H:%M") - pd.Timedelta("1min")
        return df[~df.index.duplicated()].sort_index()
    parts = []
    for i in (1, 2):
        with zipfile.ZipFile(ROOT / f"1m_data_part{i}.zip") as z:
            parts.append(pd.read_csv(z.open(f"1m_data_part{i}.csv"), sep="\t"))
    df = pd.concat(parts)
    broker = pd.DatetimeIndex(pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S"))
    et = broker - pd.Timedelta("7h") if fixed7h else broker.tz_localize(
        "Europe/Athens", ambiguous="NaT", nonexistent="NaT").tz_convert("America/New_York").tz_localize(None)
    out = pd.DataFrame({"open": df.Open.values, "high": df.High.values, "low": df.Low.values,
                        "close": df.Close.values}, index=et)
    out = out[~out.index.isna()]
    out = out[~out.index.duplicated()].sort_index()
    return out[out.index < "2023-01-01"]


def prepare(kind, fixed7h=False):
    bars = load(kind, fixed7h)
    hm = bars.index.strftime("%H:%M")
    o0, o830 = bars.loc[hm == "00:00", "open"], bars.loc[hm == "08:30", "open"]
    o0.index, o830.index = o0.index.normalize(), o830.index.normalize()
    box = pd.concat({"o0": o0, "o830": o830}, axis=1, sort=True).dropna()
    box = box[box.index.dayofweek < 5]
    box["mid"], box["h"] = (box.o0 + box.o830) / 2, (box.o0 - box.o830).abs() / 2
    g = bars.groupby((bars.index + pd.Timedelta("6h")).normalize())
    box["atr"] = (g.high.max() - g.low.min()).rolling(14).mean().shift(1).reindex(box.index)
    box = box.dropna(subset=["atr"])
    first = pd.Timestamp("2016-11-16" if kind == "CFD" else "2023-01-01")
    sel = (hm >= "08:30") & (hm < "16:00")
    sess = dict(tuple(bars[sel].groupby(bars.index[sel].normalize())))
    days = []
    for day, b in box.iterrows():
        s = sess.get(day)
        if b.h <= 0 or s is None or len(s) < 300 or day < first:
            continue
        days.append(dict(day=day, mid=b.mid, h=b.h, atr=b.atr, o0=b.o0, o830=b.o830,
                         O=s.open.values, H=s.high.values, L=s.low.values, C=s.close.values,
                         clock=(s.index.hour * 60 + s.index.minute).values))
    return days


# ------------------------------------------------------------------ Engine
@njit(cache=True)
def find_events(O, H, L, C, lvl, side, rearm, nrec, maxev, thr):
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
def sim_mid(H, L, C, j, side, entry, stop, tp):
    if abs(entry - stop) <= 0 or (tp - entry) * side <= 0:
        return np.nan, -1
    n = len(C)
    for i in range(j + 1, n):
        if side == 1:
            if L[i] <= stop:
                return stop, i
            if H[i] >= tp:
                return tp, i
        else:
            if H[i] >= stop:
                return stop, i
            if L[i] <= tp:
                return tp, i
    return C[n - 1], n - 1


def day_context(d, kind):
    """Erster Reclaim je Richtung an den Original-Leveln (fuer 'vorher Gegenreaktion')."""
    thr = TICK if kind == "NQ" else 0.0008 * d["atr"]
    first = {1: 10 ** 9, -1: 10 ** 9}
    lv = [d["o0"], d["o830"]] + [d["mid"] + s * k * d["h"] for k in ORIG for s in (1, -1)]
    for lvl in lv:
        for side in (1, -1):
            _, R, _ = find_events(d["O"], d["H"], d["L"], d["C"], lvl, side, REARM * d["atr"], NREC, MAXEV, thr)
            r = R[R >= 0]
            if len(r):
                first[side] = min(first[side], r.min())
    return first, thr


def k2_trades(days, kind, level_fn, skip=None, ctx=None):
    """level_fn(d) -> Liste von Levelpreisen. skip = (von, bis) Minuten seit Mitternacht fuer Einstiege."""
    rows = []
    for di, d in enumerate(days):
        first, thr = ctx[di]
        O, H, L, C, atr = d["O"], d["H"], d["L"], d["C"], d["atr"]
        cost = 1.0 if kind == "NQ" else 0.0032 * atr
        ev = []
        for lvl in level_fn(d):
            for side in (1, -1):
                S, R, E = find_events(O, H, L, C, lvl, side, REARM * atr, NREC, MAXEV, thr)
                for k in range(MAXEV):
                    if S[k] < 0:
                        break
                    ev.append((side, S[k], R[k], E[k]))
        own = {sd: min([e[2] for e in ev if e[0] == sd and e[2] >= 0], default=10 ** 9) for sd in (1, -1)}
        for side, s, r, ext in ev:
            if r < 1 or r >= len(C) - 1:
                continue
            if min(first[-side], own[-side]) >= s:                      # keine Gegenreaktion vorher
                continue
            mom = (C[r] > H[r - 1] and C[r] > O[r]) if side == 1 else (C[r] < L[r - 1] and C[r] < O[r])
            if not mom or (skip and skip[0] <= d["clock"][r] < skip[1]):
                continue
            entry = C[r]
            st = ext - side * TICK
            stop = min(st, entry - 0.02 * atr) if side == 1 else max(st, entry + 0.02 * atr)
            px, xb = sim_mid(H, L, C, r, side, entry, stop, d["mid"])
            if np.isnan(px):
                continue
            rows.append((di, r, xb, (side * (px - entry) - cost) / abs(entry - stop)))
    rows.sort()
    out, cur, busy = [], -1, -1
    for di, r, xb, R in rows:                                           # nur eine Position gleichzeitig
        if di != cur:
            cur, busy = di, -1
        if r > busy:
            out.append((di, R))
            busy = xb
    return np.array(out).reshape(-1, 2)


def stat(t, nd):
    if len(t) == 0:
        return dict(n=0, wk=0.0, win=np.nan, R=np.nan, t=0.0, Rwk=0.0)
    daily = np.zeros(nd)
    np.add.at(daily, t[:, 0].astype(int), t[:, 1])
    return dict(n=len(t), wk=len(t) / nd * 5, win=(t[:, 1] > 0).mean(), R=t[:, 1].mean(),
                t=daily.mean() / daily.std(ddof=1) * np.sqrt(nd), Rwk=t[:, 1].sum() / nd * 5)


def row(label, sets, ctxs, level_fn, skip=None):
    r = {"Level": label}
    for kind in ("CFD", "NQ"):
        s = stat(k2_trades(sets[kind], kind, level_fn, skip, ctxs[kind]), len(sets[kind]))
        r.update({f"{kind} Trades": s["n"], f"{kind} Win": s["win"], f"{kind} Ø R": s["R"], f"{kind} t": s["t"],
                  f"{kind} R/Wo": s["Rwk"]})
    return r


def show(title, rows):
    df = pd.DataFrame(rows)
    f = {c: ("{:.0%}".format if "Win" in c else "{:+.3f}".format if ("Ø R" in c or "R/Wo" in c) else "{:+.2f}".format)
         for c in df.columns if c != "Level" and "Trades" not in c}
    print(f"== {title} ==")
    print(df.to_string(index=False, formatters=f), "\n")
    return df


def main():
    kfn = lambda k: (lambda d: [d["mid"] + k * d["h"], d["mid"] - k * d["h"]])
    afn = lambda c: (lambda d: [d["mid"] + c * d["atr"], d["mid"] - c * d["atr"]])

    old = {"CFD": prepare("CFD", fixed7h=True)}
    sets = {"CFD": prepare("CFD"), "NQ": prepare("NQ")}
    ctxs = {k: [day_context(d, k) for d in v] for k, v in sets.items()}
    octx = [day_context(d, "CFD") for d in old["CFD"]]
    print({k: len(v) for k, v in sets.items()}, "Tage\n")

    so = stat(k2_trades(old["CFD"], "CFD", kfn(3.5), None, octx), len(old["CFD"]))
    print(f"== 1: Zeitumrechnung (K2, Level 3.5, CFD) ==\n"
          f"alte feste -7h : {so['n']} Trades, Ø R {so['R']:+.3f}, t {so['t']:+.2f}  (Branch-Ergebnis: 699 Trades, +0.144)")
    sn = stat(k2_trades(sets["CFD"], "CFD", kfn(3.5), None, ctxs["CFD"]), len(sets["CFD"]))
    print(f"Sommerzeit korrekt: {sn['n']} Trades, Ø R {sn['R']:+.3f}, t {sn['t']:+.2f}\n")

    ks = np.arange(1.0, 7.01, 0.25)
    dk = show("2: K2 an Mitte +- k*h  (k = 3.5 ist das Original)", [row(f"k={k:.2f}", sets, ctxs, kfn(k)) for k in ks])
    cs = np.round(np.arange(0.05, 0.61, 0.05), 2)
    da = show("3: K2 an Mitte +- c*ATR  (Level unabhaengig von der Boxhoehe)",
              [row(f"c={c:.2f}", sets, ctxs, afn(c)) for c in cs])
    skip = (9 * 60 + 30, 10 * 60)
    show("4: Uhrzeit-Filter - Einstiege 09:30-10:00 auslassen",
         [row("k=3.5 alle Zeiten", sets, ctxs, kfn(3.5)), row("k=3.5 ohne 09:30-10:00", sets, ctxs, kfn(3.5), skip)]
         + [x for k in (2.0, 2.5, 4.5, 5.5) for x in (row(f"k={k} alle Zeiten", sets, ctxs, kfn(k)),
                                                     row(f"k={k} ohne 09:30-10:00", sets, ctxs, kfn(k), skip))])
    dks = show("5: k-Scan mit Uhrzeit-Filter (ohne 09:30-10:00)",
               [row(f"k={k:.2f}", sets, ctxs, kfn(k), skip) for k in ks])
    fine = np.round(np.arange(3.30, 3.71, 0.05), 2)
    show("6: Feines Raster um 3.5 (alle Zeiten)", [row(f"k={k:.2f}", sets, ctxs, kfn(k)) for k in fine])
    show("6b: Feines Raster um 3.5 (ohne 09:30-10:00)", [row(f"k={k:.2f}", sets, ctxs, kfn(k), skip) for k in fine])
    if "--plot" in sys.argv:
        plot(ks, dk, dks)


def plot(ks, dk, dks):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ink, mute, surf, blue, orange = "#0b0b0b", "#52514e", "#fcfcfb", "#2a78d6", "#eb6834"
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": "#d9d8d2", "axes.labelcolor": mute,
                         "xtick.color": mute, "ytick.color": mute, "text.color": ink})
    fig, ax = plt.subplots(2, 1, figsize=(9, 7.5), facecolor=surf, sharex=True)
    for a, df, title in ((ax[0], dk, "K2 je Level: Ø R pro Trade, alle Einstiegszeiten"),
                         (ax[1], dks, "K2 je Level: Ø R pro Trade, ohne Einstiege 09:30–10:00")):
        a.set_facecolor(surf)
        a.spines[["top", "right"]].set_visible(False)
        a.grid(axis="y", color="#ebeae5", lw=.8)
        a.axhline(0, color="#8a8983", lw=1)
        for k in ORIG:
            a.axvline(k, color="#d9d8d2", lw=1, ls=(0, (3, 3)), zorder=0)
        a.plot(ks, df["CFD Ø R"], color=blue, lw=2, marker="o", ms=4, label="CFD 2016–2022")
        a.plot(ks, df["NQ Ø R"], color=orange, lw=2, marker="o", ms=4, label="NQ 2023–2025")
        a.set_title(title, loc="left", fontsize=11)
        a.legend(frameon=False, loc="upper right", ncols=2)
    ax[1].set_xlabel("Level k (Vielfaches der halben Boxhöhe; gestrichelt = bisherige Level)")
    fig.tight_layout()
    fig.savefig(HERE / "k2_level_scan.png", dpi=200, facecolor=surf)
    print("Grafik gespeichert: k2_level_scan.png")


if __name__ == "__main__":
    main()
