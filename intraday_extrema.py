"""
Tageshoch / Tagestief intraday erkennen (NQ, 1-Minuten-Bars, RTH 09:30-16:00 ET).

Teil 1  Wann am Tag fallen Hoch und Tief? (reine Zeitabhaengigkeit)
Teil 2  Prognose "das bisherige Tagestief/-hoch ist das endgueltige":
        M0 nur Uhrzeit | M1 + Abstand zum Extrem, Zeit seit Extrem, Range
        M2 = M1 + Glaetter-Steigungen | Ms = Uhrzeit + nur Glaetter
Teil 3  Glaetter als Extremstellen-Detektor: Steigung dreht ins Plus (Minus)
        -> lag das Tagestief (-hoch) in den N Minuten davor?
Teil 4  Handel: Position = Vorzeichen der Glaetter-Steigung, nur RTH, flat zum Schluss.

Aufruf:  python intraday_extrema.py [--plot]
"""
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score

from smoothing_strategy import filter_t, gauss_kernel, gauss_loclin

CSV = "Dataset_NQ_1min_2022_2025.csv"
WINDOWS = (10, 50, 100)        # Minuten
SPLIT = 0.6
COST_PTS = 0.5                 # Punkte je Positionswechsel-Einheit (1 Tick Slippage + Gebuehr)
M = 390                        # RTH-Minuten


def load():
    df = pd.read_csv(CSV, usecols=["timestamp ET", "high", "low", "close"])
    df.index = pd.to_datetime(df.pop("timestamp ET"), format="%m/%d/%Y %H:%M")
    df = df[~df.index.duplicated()].sort_index()
    logp = np.log(df["close"].values)
    ret = np.diff(logp, prepend=logp[0])
    vol = pd.Series(ret).ewm(span=390, min_periods=100).std().values       # kausal
    T = {}
    for n in WINDOWS:
        T[f"GaussKern{n}"] = filter_t(ret, gauss_kernel(n), vol)
        T[f"GaussLin{n}"] = filter_t(ret, gauss_loclin(n), vol)
        a = 2 / (n + 1)
        T[f"EMA{n}"] = pd.Series(ret).ewm(alpha=a, adjust=False).mean().values / (
            vol * np.sqrt(a / (2 - a)))
    feat = pd.DataFrame(T, index=df.index)
    feat["vol"] = vol
    full = pd.concat([df, feat], axis=1).between_time("09:31", "16:00")

    grid = pd.timedelta_range("09:31:00", "16:00:00", freq="1min")
    days, mats = [], {c: [] for c in full.columns}
    for d, g in full.groupby(full.index.normalize()):
        if len(g) < 380:
            continue
        g = g.set_index(g.index - d).reindex(grid)
        g[["close"] + list(T) + ["vol"]] = g[["close"] + list(T) + ["vol"]].ffill().bfill()
        g["high"] = g["high"].fillna(g["close"])
        g["low"] = g["low"].fillna(g["close"])
        days.append(d)
        for c in full.columns:
            mats[c].append(g[c].values)
    return pd.DatetimeIndex(days), {c: np.array(v) for c, v in mats.items()}, list(T)


def clock(m):
    return f"{9 + (m + 31) // 60:02d}:{(m + 31) % 60:02d}"


# ---------------------------------------------------------------- Teil 1
def part1(X):
    lo_t, hi_t = X["low"].argmin(1), X["high"].argmax(1)
    print("== Teil 1: Zeitpunkt von Tagestief / Tageshoch (Anteil der Tage je 30 Min) ==")
    edges = np.arange(0, M + 1, 30)
    hl = np.histogram(lo_t, edges)[0] / len(lo_t)
    hh = np.histogram(hi_t, edges)[0] / len(hi_t)
    tab = pd.DataFrame({"Tief": hl, "Hoch": hh, "Tief schon drin (kum.)": hl.cumsum(),
                        "Hoch schon drin (kum.)": hh.cumsum()},
                       index=[f"{clock(e - 1) if e else '09:30'}-{clock(e + 29)}" for e in edges[:-1]])
    print(tab.map("{:.1%}".format).to_string(), "\n")
    return lo_t, hi_t, tab


# ---------------------------------------------------------------- Teil 2
def part2(X, smooth, k):
    C, H, L = X["close"], X["high"], X["low"]
    runlo, runhi = np.minimum.accumulate(L, 1), np.maximum.accumulate(H, 1)
    sig = (X["vol"][:, :1] * np.sqrt(M)) * C[:, :1]            # erwartete Tagesschwankung (Punkte)
    idx = np.arange(M)
    since_lo = idx - np.maximum.accumulate(np.where(L <= runlo, idx, 0), 1)
    since_hi = idx - np.maximum.accumulate(np.where(H >= runhi, idx, 0), 1)
    lo_in = runlo <= L.min(1, keepdims=True)
    hi_in = runhi >= H.max(1, keepdims=True)
    cols = np.arange(4, M - 1, 5)                               # alle 5 Minuten

    def flat(a):
        return a[:, cols].ravel()

    minute = flat(np.broadcast_to(idx, C.shape))
    rng = (runhi - runlo) / sig
    S = np.c_[tuple(flat(X[s]) for s in smooth)]
    train = flat(np.broadcast_to((np.arange(len(C)) < k)[:, None], C.shape))
    print("== Teil 2: Ist das bisherige Extrem schon das endgueltige? (Test auf letzten 40 % der Tage) ==")
    out = []
    for name, y, dist, since in (("Tief", lo_in, (C - runlo) / sig, since_lo),
                                 ("Hoch", hi_in, (runhi - C) / sig, since_hi)):
        yv = flat(y)
        base = np.c_[minute, flat(dist), flat(since), flat(rng)]
        models = {"M0 nur Uhrzeit": base[:, :1], "Ms Uhrzeit + Glaetter": np.c_[minute, S],
                  "M1 Uhrzeit + Abstand/Zeit seit Extrem": base, "M2 = M1 + Glaetter": np.c_[base, S]}
        for mname, F in models.items():
            clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05,
                                                 min_samples_leaf=200, random_state=0)
            clf.fit(F[train], yv[train])
            p = clf.predict_proba(F[~train])[:, 1]
            out.append(dict(Ziel=name, Modell=mname, AUC=roc_auc_score(yv[~train], p),
                            Brier=brier_score_loss(yv[~train], p)))
    r = pd.DataFrame(out)
    r["Brier-Gewinn ggü. M0"] = 1 - r.Brier / r.groupby("Ziel").Brier.transform("first")
    print(r.to_string(index=False, formatters={"AUC": "{:.3f}".format, "Brier": "{:.4f}".format,
                                               "Brier-Gewinn ggü. M0": "{:+.1%}".format}), "\n")

    print(f"== Teil 2b: Nachschlagetabelle - P(Extrem haelt bis 16:00), alle Tage ==\n"
          f"Abstand = Kurs minus bisheriges Extrem, in Einheiten der erwarteten Tagesschwankung "
          f"(Median {np.median(sig):.0f} Punkte)")
    tcols = [29, 89, 149, 209, 269, 329, 359]
    bins = [0, .1, .25, .5, 1, np.inf]
    lab = ["<0.1", "0.1-0.25", "0.25-0.5", "0.5-1", ">1"]
    for name, y, dist in (("Tief", lo_in, (C - runlo) / sig), ("Hoch", hi_in, (runhi - C) / sig)):
        t = pd.DataFrame({clock(c): pd.Series(y[:, c].astype(float)).groupby(
            pd.cut(dist[:, c], bins, labels=lab, right=False), observed=False).agg(
            lambda v: f"{v.mean():.0%} ({len(v)})" if len(v) >= 15 else "-") for c in tcols})
        t.index.name = f"Abstand zum {name}"
        print(t.to_string(), "\n")


# ---------------------------------------------------------------- Teil 3
def part3(X, lo_t, hi_t):
    print("== Teil 3: Glaetter dreht -> lag das Tagesextrem in den N Minuten davor? ==")
    rows = []
    idx = np.arange(M)
    for n in WINDOWS:
        for meth in ("GaussKern", "GaussLin", "EMA"):
            t = X[f"{meth}{n}"]
            for z in (0, 1):
                for name, ext, s in (("Tief", lo_t, 1), ("Hoch", hi_t, -1)):
                    v = s * t
                    ev = np.zeros_like(v, bool)
                    ev[:, 1:] = (v[:, 1:] > z) & (v[:, :-1] <= z)          # Dreh-Signal
                    lag = idx[None, :] - ext[:, None]                      # Minuten seit Extrem
                    win = (lag >= 0) & (lag <= n)
                    base = win.mean(0)                                     # Trefferquote je Uhrzeit ohne Signal
                    w = ev.sum(0)
                    rows.append(dict(N=n, Glaetter=meth, z=z, Ziel=name,
                                     Signale_pro_Tag=ev.sum() / len(t),
                                     Treffer=(ev & win).sum() / ev.sum(),
                                     Zufall=(base * w).sum() / w.sum(),
                                     Tage_erkannt=(ev & win).any(1).mean()))
    r = pd.DataFrame(rows)
    r["Lift"] = r.Treffer / r.Zufall
    print(r.to_string(index=False, formatters={
        "Signale_pro_Tag": "{:.1f}".format, "Treffer": "{:.1%}".format, "Zufall": "{:.1%}".format,
        "Tage_erkannt": "{:.0%}".format, "Lift": "{:.2f}x".format}), "\n")
    return r


# ---------------------------------------------------------------- Teil 4
def part4(X, k):
    print(f"== Teil 4: Handel nach Glaetter-Vorzeichen, nur RTH (Kosten {COST_PTS} Pkt je Wechsel) ==")
    C = X["close"]
    dC = np.diff(C, axis=1)
    rows = []
    for n in WINDOWS:
        for meth in ("GaussKern", "GaussLin", "EMA"):
            t = X[f"{meth}{n}"]
            for z in (0, 1):
                raw = np.where(t > z, 1.0, np.where(t < -z, -1.0, np.nan))
                pos = pd.DataFrame(raw).ffill(axis=1).fillna(0).values[:, :-1]
                turn = np.abs(np.diff(pos, axis=1, prepend=0)).sum(1) + np.abs(pos[:, -1])
                gross = (pos * dC).sum(1)
                net = gross - COST_PTS * turn
                sh = lambda x: x.mean() / x.std() * np.sqrt(252)
                rows.append(dict(N=n, Glaetter=meth, z=z, Wechsel_pro_Tag=turn.mean() / 2,
                                 Brutto_Pkt_Tag=gross.mean(), Netto_Pkt_Tag=net.mean(),
                                 Sharpe_brutto=sh(gross), Sharpe_netto=sh(net),
                                 Sharpe_netto_OOS=sh(net[k:])))
    r = pd.DataFrame(rows)
    bh = dC.sum(1)
    print(f"Vergleich long 09:31-16:00: {bh.mean():+.1f} Pkt/Tag, Sharpe {bh.mean() / bh.std() * 252 ** .5:.2f}")
    print(r.to_string(index=False, float_format="{:+.2f}".format,
                      formatters={"Wechsel_pro_Tag": "{:.1f}".format}), "\n")


def plot(tab, ndays):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ink, mute, surf = "#0b0b0b", "#52514e", "#fcfcfb"
    blue, orange = "#2a78d6", "#eb6834"
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": "#d9d8d2", "axes.labelcolor": mute,
                         "xtick.color": mute, "ytick.color": mute, "text.color": ink})
    fig, ax = plt.subplots(2, 1, figsize=(9, 7.5), facecolor=surf)
    x = np.arange(len(tab))
    for a in ax:
        a.set_facecolor(surf)
        a.spines[["top", "right"]].set_visible(False)
        a.grid(axis="y", color="#ebeae5", lw=.8)
        a.set_axisbelow(True)
        a.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax[0].bar(x - .2, tab["Tief"], .38, color=blue, label="Tagestief")
    ax[0].bar(x + .2, tab["Hoch"], .38, color=orange, label="Tageshoch")
    ax[0].set_xticks(x, [i.split("-")[0] for i in tab.index])
    ax[0].set_title(f"Wann fällt das Tagesextrem? Anteil der {ndays} Tage je 30-Minuten-Fenster (ET)",
                    loc="left", fontsize=11)
    ax[0].legend(frameon=False)
    xe = np.arange(len(tab) + 1)
    ax[1].plot(xe, np.r_[0, tab["Tief schon drin (kum.)"]], color=blue, lw=2, label="Tagestief")
    ax[1].plot(xe, np.r_[0, tab["Hoch schon drin (kum.)"]], color=orange, lw=2, label="Tageshoch")
    ax[1].set_xticks(xe, [i.split("-")[0] for i in tab.index] + ["16:00"])
    ax[1].set_ylim(0, 1)
    ax[1].set_title("Wahrscheinlichkeit, dass das Extrem zu dieser Uhrzeit schon erreicht ist",
                    loc="left", fontsize=11)
    ax[1].legend(frameon=False)
    fig.tight_layout()
    fig.savefig("intraday_extrema_timing.png", dpi=200, facecolor=surf)
    print("Grafik gespeichert: intraday_extrema_timing.png")


def main():
    days, X, smooth = load()
    k = int(len(days) * SPLIT)
    print(f"{len(days)} RTH-Tage {days[0].date()} .. {days[-1].date()}, Test ab {days[k].date()}\n")
    lo_t, hi_t, tab = part1(X)
    part2(X, smooth, k)
    part3(X, lo_t, hi_t)
    part4(X, k)
    if "--plot" in sys.argv:
        plot(tab, len(days))


if __name__ == "__main__":
    main()
