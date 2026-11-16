"""
Ereignis-Wahrscheinlichkeiten statt Kurvenprognose: Reversals unter bestimmten Bedingungen.

Frage je Ereignis: Laeuft der Kurs danach zuerst b GEGEN die bisherige Bewegung (Reversal)
oder zuerst b MIT ihr weiter?  b = 0.25 bzw. 0.5 x erwartete Tagesschwankung (sigma).
Bei einem Zufallslauf waeren das 50 %.  Alles nur mit Daten bis zum jeweiligen Zeitpunkt.

Daten:  CFD 2016-2022 (Suche)  und  NQ-Future 2023-2025 (Gegenprobe), 1-Min-Bars, 09:30-16:00 NY,
        Stichprobe alle 5 Minuten zwischen 09:35 und 15:30.

Teil 1  Vorab festgelegte Reversal-Ereignisse (beide Richtungen gespiegelt zusammengefasst)
Teil 2  Modell mit allen Bedingungen: trainiert auf einem Datensatz, getestet auf dem anderen
Teil 3  Tagesbasis: Reversal nach Ueberdehnung (naechste 1 / 5 Handelstage)

Aufruf:  python funktions_studien/reversal_events.py
"""
import numpy as np
import pandas as pd
from numba import njit
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from k2_level_scan import load

M = 390
COLS = np.arange(5, 361, 5)             # 09:35 .. 15:30
BARRIERS = (0.25, 0.5)
pd.set_option("display.width", 230)


# ------------------------------------------------------------------ Daten
def build(kind):
    b = load(kind)
    if kind == "NQ":
        b = b[b.index >= "2022-12-01"]
    lp = np.log(b["close"].values)
    ret = np.diff(lp, prepend=lp[0])
    b = b.assign(vol=pd.Series(ret).ewm(span=390, min_periods=100).std().values, lp=lp)
    a = 2 / 101
    b["ema"] = pd.Series(ret).ewm(alpha=a, adjust=False).mean().values / (b["vol"].values * np.sqrt(a / (2 - a)))
    for k in (5, 15, 30, 60):
        b[f"z{k}"] = (lp - np.r_[np.full(k, np.nan), lp[:-k]]) / (b["vol"].values * np.sqrt(k))
    hm = b.index.strftime("%H:%M")
    rth = b[(hm >= "09:30") & (hm < "16:00")]
    grid = pd.timedelta_range("09:30:00", "15:59:00", freq="1min")
    cols = ["open", "high", "low", "close", "vol", "ema", "z5", "z15", "z30", "z60"]
    days, mats = [], {c: [] for c in cols}
    for d, g in rth.groupby(rth.index.normalize()):
        if len(g) < 380 or d.dayofweek > 4:
            continue
        g = g.set_index(g.index - d).reindex(grid)
        g[cols[3:]] = g[cols[3:]].ffill().bfill()
        for c in cols[:3]:
            g[c] = g[c].fillna(g["close"])
        days.append(d)
        for c in cols:
            mats[c].append(g[c].values)
    X = {c: np.array(v) for c, v in mats.items()}
    days = pd.DatetimeIndex(days)
    C, H, L = X["close"], X["high"], X["low"]
    X["sig"] = X["vol"][:, :1] * np.sqrt(M) * X["open"][:, :1]
    X["runlo"], X["runhi"] = np.minimum.accumulate(L, 1), np.maximum.accumulate(H, 1)
    idx = np.arange(M)
    X["since_lo"] = idx - np.maximum.accumulate(np.where(L <= X["runlo"], idx, 0), 1)
    X["since_hi"] = idx - np.maximum.accumulate(np.where(H >= X["runhi"], idx, 0), 1)
    # Vortag und Tageskontext (alles vor 09:30 bekannt)
    dc, dh, dl = C[:, -1], H.max(1), L.min(1)
    prev = lambda a: np.r_[np.nan, a[:-1]]
    X["pdh"], X["pdl"], X["pdc"] = prev(dh)[:, None], prev(dl)[:, None], prev(dc)[:, None]
    dret = np.log(dc / prev(dc))
    dsd = pd.Series(dret).rolling(60, min_periods=20).std().shift(1).values
    X["r1"] = (prev(dret) / dsd)[:, None]
    X["r5"] = (pd.Series(dret).rolling(5).sum().shift(1).values / (dsd * np.sqrt(5)))[:, None]
    ldc = np.log(dc)
    dev = ldc - pd.Series(ldc).rolling(20).mean().values
    X["over"] = (pd.Series(dev).rolling(20).sum().shift(1).values / (dsd * 20))[:, None]
    X["daily"] = pd.DataFrame({"ret": dret, "sd": dsd, "lc": ldc}, index=days)
    keep = ~np.isnan(X["pdc"][:, 0]) & ~np.isnan(X["sig"][:, 0])
    if kind == "NQ":
        keep &= days >= "2023-01-01"
    for k, v in X.items():
        if k != "daily":
            X[k] = v[keep]
    return days[keep], X


@njit(cache=True)
def first_passage(H, L, C, cols, b):
    """+1: zuerst +b erreicht, -1: zuerst -b, 0: keins bis 16:00 oder beide in einer Kerze. pnl = long bis Barriere/Schluss."""
    nd, m = C.shape
    out = np.zeros((nd, len(cols)), np.int8)
    pnl = np.zeros((nd, len(cols)))
    for d in range(nd):
        for j in range(len(cols)):
            c = cols[j]
            up, dn = C[d, c] + b[d], C[d, c] - b[d]
            pnl[d, j] = C[d, m - 1] - C[d, c]
            for i in range(c + 1, m):
                u, v = H[d, i] >= up, L[d, i] <= dn
                if u and v:
                    pnl[d, j] = 0.0
                    break
                if u:
                    out[d, j] = 1
                    pnl[d, j] = b[d]
                    break
                if v:
                    out[d, j] = -1
                    pnl[d, j] = -b[d]
                    break
    return out, pnl


def features(X):
    C, sig = X["close"][:, COLS], X["sig"]
    f = {"minute": np.broadcast_to(COLS, C.shape),
         "z5": X["z5"][:, COLS], "z15": X["z15"][:, COLS], "z30": X["z30"][:, COLS], "z60": X["z60"][:, COLS],
         "dist_lo": (C - X["runlo"][:, COLS]) / sig, "dist_hi": (X["runhi"][:, COLS] - C) / sig,
         "since_lo": X["since_lo"][:, COLS], "since_hi": X["since_hi"][:, COLS],
         "range": (X["runhi"][:, COLS] - X["runlo"][:, COLS]) / sig,
         "from_open": (C - X["open"][:, :1]) / sig, "gap": np.broadcast_to((X["open"][:, :1] - X["pdc"]) / sig, C.shape),
         "vs_pdh": (C - X["pdh"]) / sig, "vs_pdl": (C - X["pdl"]) / sig, "ema": X["ema"][:, COLS],
         "r1": np.broadcast_to(X["r1"], C.shape), "r5": np.broadcast_to(X["r5"], C.shape),
         "over": np.broadcast_to(X["over"], C.shape)}
    return {k: np.asarray(v, float) for k, v in f.items()}


def events(X, f):
    """Je Ereignis: Richtung des erwarteten Reversals (+1 = nach oben, -1 = nach unten, 0 = kein Ereignis)."""
    C = X["close"][:, COLS]
    lo5 = lambda a, k: np.stack([a[:, max(c - k + 1, 0):c + 1].min(1) for c in COLS], 1)
    hi5 = lambda a, k: np.stack([a[:, max(c - k + 1, 0):c + 1].max(1) for c in COLS], 1)
    newlo, newhi = f["since_lo"] <= 5, f["since_hi"] <= 5
    two = lambda up, dn: np.where(up, 1, np.where(dn, -1, 0))
    mn = f["minute"]
    E = {
        "A  Schneller Abverkauf/Anstieg: 30-Min-Bewegung > 2 Sigma": two(f["z30"] <= -2, f["z30"] >= 2),
        "B  wie A und gerade neues Tagesextrem": two((f["z30"] <= -2) & newlo, (f["z30"] >= 2) & newhi),
        "C  Neues Tagesextrem (letzte 5 Min), ohne weitere Bedingung": two(newlo & ~newhi, newhi & ~newlo),
        "D  Neues Tagesextrem und Tagesspanne schon > 1.5 Sigma": two(newlo & (f["range"] >= 1.5), newhi & (f["range"] >= 1.5)),
        "E  Vortagestief/-hoch unterschritten und zurueckerobert (15 Min)":
            two((lo5(X["low"], 15) < X["pdl"]) & (C > X["pdl"]) & (f["vs_pdl"] < 0.15),
                (hi5(X["high"], 15) > X["pdh"]) & (C < X["pdh"]) & (f["vs_pdh"] > -0.15)),
        "F  Weit vom Eroeffnungskurs (> 1.5 Sigma)": two(f["from_open"] <= -1.5, f["from_open"] >= 1.5),
        "G  wie A, aber gegen den Trend der letzten 5 Tage (Ruecksetzer)":
            two((f["z30"] <= -2) & (f["r5"] > 0.5), (f["z30"] >= 2) & (f["r5"] < -0.5)),
        "H  wie A, mit dem Trend der letzten 5 Tage (Ueberdehnung)":
            two((f["z30"] <= -2) & (f["r5"] < -0.5), (f["z30"] >= 2) & (f["r5"] > 0.5)),
        "I  wie A, 09:35-10:30": two((f["z30"] <= -2) & (mn <= 60), (f["z30"] >= 2) & (mn <= 60)),
        "J  wie A, 10:30-14:00": two((f["z30"] <= -2) & (mn > 60) & (mn <= 270), (f["z30"] >= 2) & (mn > 60) & (mn <= 270)),
        "K  wie A, 14:00-15:30": two((f["z30"] <= -2) & (mn > 270), (f["z30"] >= 2) & (mn > 270)),
        "L  Grosse Eroeffnungsluecke (> 1 Sigma), 09:35-10:30, Gegenrichtung":
            two((f["gap"] <= -1) & (mn <= 60), (f["gap"] >= 1) & (mn <= 60)),
    }
    return E


def day_t(val, day, nd):
    """t-Wert ueber Tagessummen (Tage ohne Trade = 0), mehrere Trades am selben Tag zaehlen nicht mehrfach."""
    d = np.zeros(nd)
    np.add.at(d, day, val)
    return d.mean() / d.std(ddof=1) * np.sqrt(nd) if d.std() > 0 else np.nan


def part1(sets):
    """Nur das ERSTE Ereignis je Tag: unabhaengige Faelle, so auch handelbar."""
    rows = []
    for name in next(iter(sets.values()))["E"]:
        r = {"Ereignis": name}
        for kind, S in sets.items():
            e = S["E"][name]
            has = (e != 0).any(1)
            j = (e != 0).argmax(1)
            d = np.where(has)[0]
            side = e[d, j[d]]
            for b in BARRIERS:
                o, pnl = S["fp"][b]
                oo = o[d, j[d]]
                dec = oo != 0
                rev = (oo[dec] == side[dec]).astype(float)
                R = (side * pnl[d, j[d]] - S["cost"][d]) / S["bpts"][b][d]
                tag = f"{kind} b={b}"
                se = np.sqrt(0.25 / max(len(rev), 1))
                W = (-side * pnl[d, j[d]] - S["cost"][d]) / S["bpts"][b][d]      # Trade MIT der Bewegung
                r.update({f"{tag} Tage": len(d), f"{tag} Rev": rev.mean(), f"{tag} t": (rev.mean() - 0.5) / se,
                          f"{tag} R": R.mean(), f"{tag} tR": R.mean() / R.std(ddof=1) * np.sqrt(len(R)),
                          f"{tag} Mit R": W.mean(), f"{tag} tMit": W.mean() / W.std(ddof=1) * np.sqrt(len(W))})
        rows.append(r)
    df = pd.DataFrame(rows).set_index("Ereignis")
    for b in BARRIERS:
        cols = [c for c in df.columns if f"b={b}" in c]
        d = df[cols].copy()
        d.columns = [c.replace(f" b={b}", "") for c in cols]
        fm = {c: ("{:.1%}".format if c.endswith("Rev") else "{:+.3f}".format if c.endswith(" R") else "{:+.2f}".format)
              for c in d.columns if not c.endswith("Tage")}
        print(f"== Teil 1: Reversal-Quote beim ersten Ereignis des Tages (Zufall = 50 %), Barriere b = {b} Sigma; "
              f"R = Trade GEGEN die Bewegung netto, Mit R = Trade MIT der Bewegung netto, Stop = Ziel = b ==")
        print(d.to_string(formatters=fm), "\n")


def part2(sets):
    print("== Teil 2: Modell mit allen Bedingungen -> P(zuerst +b), b = 0.25 Sigma ==")
    names = list(next(iter(sets.values()))["f"])
    for tr, te in (("CFD", "NQ"), ("NQ", "CFD")):
        A, B = sets[tr], sets[te]
        Xa = np.stack([A["f"][n].ravel() for n in names], 1)
        Xb = np.stack([B["f"][n].ravel() for n in names], 1)
        oa, ob = A["fp"][0.25][0].ravel(), B["fp"][0.25][0].ravel()
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.03, min_samples_leaf=500,
                                             l2_regularization=1.0, random_state=0).fit(Xa[oa != 0], oa[oa != 0] == 1)
        p = clf.predict_proba(Xb)[:, 1]
        ok = ob != 0
        di = np.broadcast_to(np.arange(B["E"][next(iter(B["E"]))].shape[0])[:, None], B["fp"][0.25][0].shape).ravel()
        pnl, bp, cost = B["fp"][0.25][1].ravel(), B["bpts"][0.25][di], B["cost"][di]
        print(f"Training {tr} -> Test {te}:  AUC {roc_auc_score(ob[ok] == 1, p[ok]):.3f}   "
              f"(0.5 = Zufall;  Grundquote 'zuerst oben' {np.mean(ob[ok] == 1):.1%})")
        rows = []
        for lo, hi in ((0, .40), (.40, .45), (.45, .48), (.48, .52), (.52, .55), (.55, .60), (.60, 1.01)):
            m = (p >= lo) & (p < hi)
            if m.sum() < 30:
                continue
            side = 1 if lo >= .5 else (-1 if hi <= .5 else 0)
            R = (side * pnl[m] - cost[m]) / bp[m] if side else np.full(m.sum(), np.nan)
            rows.append({"Modell sagt P(oben)": f"{lo:.0%}-{min(hi, 1):.0%}", "Faelle": int(m.sum()),
                         "Tage": len(np.unique(di[m])), "tatsaechlich oben": np.mean(ob[m & ok] == 1),
                         "Trade": {1: "long", -1: "short", 0: "-"}[side], "R netto": np.nanmean(R) if side else np.nan,
                         "t (Tage)": day_t(R, di[m], di.max() + 1) if side else np.nan})
        print(pd.DataFrame(rows).to_string(index=False, formatters={
            "tatsaechlich oben": "{:.1%}".format, "R netto": "{:+.3f}".format, "t (Tage)": "{:+.2f}".format}), "\n")


def part3(sets):
    print("== Teil 3: Tagesbasis - Rendite nach Ueberdehnung (naechster Tag / naechste 5 Tage) ==")
    rows = []
    for kind, S in sets.items():
        d = S["X"]["daily"]
        z1, lc = d.ret / d.sd, d.lc
        r5 = d.ret.rolling(5).sum() / (d.sd * np.sqrt(5))
        streak = d.ret.lt(0).astype(int).groupby(d.ret.ge(0).cumsum()).cumsum()
        ustreak = d.ret.gt(0).astype(int).groupby(d.ret.le(0).cumsum()).cumsum()
        sma, sd20 = lc.rolling(20).mean(), lc.rolling(20).std()
        f1, f5 = lc.shift(-1) - lc, lc.shift(-5) - lc
        conds = {"alle Tage": z1.notna(), "Tagesverlust > 1.5 Sigma": z1 <= -1.5, "Tagesgewinn > 1.5 Sigma": z1 >= 1.5,
                 "3+ Verlusttage in Folge": streak >= 3, "3+ Gewinntage in Folge": ustreak >= 3,
                 "5-Tage-Verlust > 1.5 Sigma": r5 <= -1.5, "5-Tage-Gewinn > 1.5 Sigma": r5 >= 1.5,
                 "Neues 20-Tage-Tief": lc <= lc.rolling(20).min(), "Neues 20-Tage-Hoch": lc >= lc.rolling(20).max(),
                 "Unter unterem Bollinger-Band (2 Sigma)": lc < sma - 2 * sd20,
                 "Ueber oberem Bollinger-Band (2 Sigma)": lc > sma + 2 * sd20}
        for i, (k, m) in enumerate(conds.items()):
            if kind == "CFD":
                rows.append({"Bedingung": k})
            m = m.fillna(False).values
            for h, f in ((1, f1), (5, f5)):
                x, a = f[m].dropna(), f.dropna()
                se = x.std(ddof=1) / np.sqrt(max(len(x) / h, 1))
                rows[i].update({f"{kind} Tage": int(m.sum()), f"{kind} {h}T Ø": x.mean(), f"{kind} {h}T >0": (x > 0).mean(),
                                f"{kind} {h}T t": (x.mean() - a.mean()) / se})
    df = pd.DataFrame(rows).set_index("Bedingung")
    fm = {c: ("{:+.2%}".format if c.endswith("Ø") else "{:.0%}".format if c.endswith(">0") else "{:+.2f}".format)
          for c in df.columns if not c.endswith("Tage")}
    print(df.to_string(formatters=fm), "\n")


def main():
    sets = {}
    for kind in ("CFD", "NQ"):
        days, X = build(kind)
        f = features(X)
        S = {"X": X, "f": f, "E": events(X, f), "fp": {}, "bpts": {}}
        for b in BARRIERS:
            bp = b * X["sig"][:, 0]
            S["fp"][b] = first_passage(X["high"], X["low"], X["close"], COLS, bp)
            S["bpts"][b] = bp
        S["cost"] = np.full(len(days), 1.0) if kind == "NQ" else 0.55e-4 * X["open"][:, 0]   # ~1 NQ-Punkt je Trade
        sets[kind] = S
        print(f"{kind}: {len(days)} Tage {days[0].date()} .. {days[-1].date()}, Median Sigma {np.median(X['sig']):.0f} Punkte")
    print()
    part1(sets)
    part2(sets)
    part3(sets)


if __name__ == "__main__":
    main()
