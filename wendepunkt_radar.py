"""
Rollierender Ruecktest des "Wendepunkt-Radars" (Ansatz aus dem ChatGPT-Verlauf) auf NQ-Tagesdaten.

Verfahren wie dort beschrieben:
  * Savitzky-Golay = lokales Polynom 3. Grades ueber 7 / 11 / 15 Handelstage
  * 1. und 2. Ableitung am rechten Rand (nur Daten bis zum jeweiligen Tag)
  * Ampel:  ROT   f' < 0 und f'' < 0   (faellt, beschleunigt)
            GELB  f' < 0 und f'' > 0   (faellt, bremst ab)
            GRUEN f' > 0               (steigt; getrennt nach f'' > 0 / < 0)
  * Auswertung: Rendite der folgenden 5 und 10 Handelstage

Daten: Schlusskurs 16:00 New York, CFD 2016-2022 und NQ-Future 2023-2025 (Renditen verkettet).

Teile:
  1  Ampel je Fenster und bei Einigkeit aller drei Fenster
  2  Signal-Ereignisse (Wechsel ROT->GELB, Dreh nach oben / unten)
  3  Live gemeldete Wendepunkte gegen Wendepunkte im Rueckblick (zentrierte Glaettung)
  4  Integral der Abweichung vom Trend als Ueberdehnungs-Indikator
  5  Einfache Handelsregeln aus der Ampel

Aufruf:  python wendepunkt_radar.py [--plot]         (eigene Kurse: --csv datei.csv, Spalten date,close)
"""
import sys

import numpy as np
import pandas as pd

from k2_level_scan import load

WINDOWS = (7, 11, 15)
HORIZONS = (5, 10)
pd.set_option("display.width", 200)


def daily_closes():
    if "--csv" in sys.argv:
        df = pd.read_csv(sys.argv[sys.argv.index("--csv") + 1])
        df.columns = [c.lower() for c in df.columns]
        s = pd.Series(df["close"].values, index=pd.to_datetime(df["date"])).sort_index().dropna()
        return np.log(s)
    rets = []
    for kind in ("CFD", "NQ"):
        b = load(kind)
        if kind == "NQ":
            b = b[b.index >= "2023-01-01"]
        hm = b.index.strftime("%H:%M")
        r = b[(hm >= "09:30") & (hm < "16:00")]
        d = r["close"].groupby(r.index.normalize()).agg(["last", "count"])
        d = d[(d["count"] > 300) & (d.index.dayofweek < 5)]["last"]
        rets.append(np.log(d).diff().dropna())
    r = pd.concat(rets)
    return r.cumsum() + np.log(10000)                    # verketteter log-Kurs (Startniveau beliebig)


def edge_derivs(y, w, deg=3, at="right"):
    """Lokales Polynom ueber w Punkte; f' und f'' am rechten Rand (kausal) oder in der Mitte (Rueckblick)."""
    x = np.arange(w) - (w - 1 if at == "right" else (w - 1) / 2)
    P = np.linalg.pinv(np.vander(x, deg + 1, increasing=True))
    win = np.lib.stride_tricks.sliding_window_view(y, w)
    c = win @ P.T
    n = len(y)
    f, d1, d2 = (np.full(n, np.nan) for _ in range(3))
    idx = np.arange(len(win)) + (w - 1 if at == "right" else w // 2)
    f[idx], d1[idx], d2[idx] = c[:, 0], c[:, 1], 2 * c[:, 2]
    return f, d1, d2


def fwd(y, h):
    out = np.full(len(y), np.nan)
    out[:-h] = y[h:] - y[:-h]
    return out


def summ(mask, y, base=None):
    """Mittlere Folgerendite, Trefferquote, t-Wert gegen den Durchschnitt aller Tage (ueberlappungsbereinigt)."""
    r = {"Tage": int(np.nansum(mask))}
    for h in HORIZONS:
        f = fwd(y, h)
        ok = mask & ~np.isnan(f)
        allf = f[~np.isnan(f)]
        if ok.sum() < 5:
            r.update({f"{h}T Ø": np.nan, f"{h}T >0": np.nan, f"{h}T t": np.nan}); continue
        x = f[ok]
        se = x.std(ddof=1) / np.sqrt(max(len(x) / h, 1))            # ~ unabhaengige Beobachtungen
        r.update({f"{h}T Ø": x.mean(), f"{h}T >0": (x > 0).mean(), f"{h}T t": (x.mean() - allf.mean()) / se})
    return r


def show(title, rows, idx):
    df = pd.DataFrame(rows).set_index(idx)
    f = {c: ("{:+.2%}".format if c.endswith("Ø") else "{:.0%}".format if c.endswith(">0") else "{:+.2f}".format)
         for c in df.columns if c != "Tage" and df[c].dtype != object}
    print(f"== {title} ==")
    print(df.to_string(formatters=f), "\n")
    return df


def state(d1, d2):
    s = np.full(len(d1), "", dtype=object)
    s[(d1 < 0) & (d2 < 0)] = "ROT"
    s[(d1 < 0) & (d2 >= 0)] = "GELB"
    s[(d1 >= 0) & (d2 >= 0)] = "GRUEN beschleunigt"
    s[(d1 >= 0) & (d2 < 0)] = "GRUEN bremst"
    return s


ORDER = ["ROT", "GELB", "GRUEN beschleunigt", "GRUEN bremst"]


def main():
    lp = daily_closes()
    y = lp.values
    n = len(y)
    print(f"{n} Handelstage {lp.index[0].date()} .. {lp.index[-1].date()}\n")
    D = {w: edge_derivs(y, w) for w in WINDOWS}
    S = {w: state(D[w][1], D[w][2]) for w in WINDOWS}
    valid = S[15] != ""

    # ---- 1
    rows = [dict(Fenster="-", Ampel="alle Tage", **summ(valid, y))]
    for w in WINDOWS:
        rows += [dict(Fenster=w, Ampel=a, **summ(S[w] == a, y)) for a in ORDER]
    agree = (S[7] == S[11]) & (S[11] == S[15]) & valid
    rows += [dict(Fenster="alle 3 einig", Ampel=a, **summ(agree & (S[11] == a), y)) for a in ORDER]
    show("1: Ampel -> Rendite der folgenden 5 / 10 Handelstage (t = Abstand zum Durchschnitt aller Tage)",
         rows, ["Fenster", "Ampel"])
    print(f"Alle drei Fenster einig an {agree.sum() / valid.sum():.0%} der Tage\n")

    # ---- 2
    rows = []
    for w in WINDOWS:
        d1, d2, s = D[w][1], D[w][2], S[w]
        prev = np.r_[[""], s[:-1]]
        ev = {"ROT -> GELB (Abwaertsbewegung bremst)": (prev == "ROT") & (s == "GELB"),
              "Dreh nach oben (f' wird positiv)": (np.r_[np.nan, d1[:-1]] < 0) & (d1 >= 0),
              "Dreh nach unten (f' wird negativ)": (np.r_[np.nan, d1[:-1]] >= 0) & (d1 < 0),
              "GRUEN: Anstieg beginnt zu bremsen": (prev == "GRUEN beschleunigt") & (s == "GRUEN bremst")}
        rows += [dict(Fenster=w, Ereignis=k, **summ(v, y)) for k, v in ev.items()]
        g = np.where((prev == "ROT") & (s == "GELB"))[0]
        nxt = [next((S[w][j] for j in range(i + 1, min(i + 11, n)) if S[w][j] != "GELB"), "GELB") for i in g]
        print(f"Fenster {w}: nach ROT->GELB folgt zuerst GRUEN in {np.mean([x.startswith('GRUEN') for x in nxt]):.0%}, "
              f"zurueck zu ROT in {np.mean([x == 'ROT' for x in nxt]):.0%} der {len(g)} Faelle")
    print()
    show("2: Signal-Ereignisse -> Folgerendite", rows, ["Fenster", "Ereignis"])

    # ---- 3
    print("== 3: Live gemeldete Wendepunkte gegen Wendepunkte im Rueckblick ==")
    rows = []
    for w in WINDOWS:
        fc, c1, _ = edge_derivs(y, w, at="center")                       # Rueckblick-Kurve
        d1 = D[w][1]
        for name, sgn in (("Tief", 1), ("Hoch", -1)):
            hind = np.where((sgn * np.r_[np.nan, c1[:-1]] < 0) & (sgn * c1 >= 0))[0]
            live = np.where((sgn * np.r_[np.nan, d1[:-1]] < 0) & (sgn * d1 >= 0))[0]
            live = live[live < n - w]                                    # Rueckblick muss dort schon feststehen
            lag = [l - hind[hind <= l][-1] for l in live if (hind <= l).any()]
            hit = np.array([x <= w // 2 for x in lag])
            found = np.mean([((live >= h) & (live <= h + w // 2)).any() for h in hind[hind < n - w]])
            # wie viel der Bewegung ist bei der Live-Meldung schon vorbei?
            gone, rest = [], []
            for l in live:
                hh = hind[hind <= l]
                if len(hh) and l - hh[-1] <= w // 2:
                    lo = y[max(hh[-1] - 2, 0):l + 1].min() if sgn == 1 else y[max(hh[-1] - 2, 0):l + 1].max()
                    gone.append(sgn * (y[l] - lo))
                    rest.append(sgn * (y[min(l + 10, n - 1)] - y[l]))
            rows.append(dict(Fenster=w, Typ=name, Rueckblick=len(hind), Live_Meldungen=len(live),
                             echt=hit.mean(), Rueckblick_erkannt=found, Verzug_Tage=np.median(np.array(lag)[hit]),
                             schon_gelaufen=np.mean(gone), danach_10T=np.mean(rest)))
    df = pd.DataFrame(rows).set_index(["Fenster", "Typ"])
    print(df.to_string(formatters={"echt": "{:.0%}".format, "Rueckblick_erkannt": "{:.0%}".format,
                                   "Verzug_Tage": "{:.0f}".format, "schon_gelaufen": "{:+.2%}".format,
                                   "danach_10T": "{:+.2%}".format}), "\n")

    # ---- 4
    sma = pd.Series(y).rolling(20).mean().values
    dev = y - sma
    sd = pd.Series(np.diff(y, prepend=y[0])).rolling(60).std().shift(1).values
    integ = pd.Series(dev).rolling(20).sum().values / (sd * 20)           # Flaeche der Abweichung, normiert
    q = pd.qcut(pd.Series(integ), 5, labels=["Q1 stark darunter", "Q2", "Q3", "Q4", "Q5 stark darueber"])
    show("4: Integral der Abweichung vom 20-Tage-Durchschnitt (20 Tage, in Tages-Sigma) -> Folgerendite",
         [dict(Quintil=k, **summ((q == k).values, y)) for k in q.cat.categories], "Quintil")

    # ---- 5
    r = np.diff(y, append=np.nan)                                         # Rendite von t nach t+1
    cost = 0.0001
    def perf(pos):
        pnl = pos[:-1] * r[:-1] - cost * np.abs(np.diff(pos, prepend=0))[:-1]
        pnl = pnl[np.where(valid)[0][0]:]
        eq = np.cumsum(pnl)
        return dict(Rendite_pa=pnl.mean() * 252, Sharpe=pnl.mean() / pnl.std() * np.sqrt(252),
                    MaxDD=(eq - np.maximum.accumulate(eq)).min(), investiert=np.abs(pos[valid]).mean())
    rows = [dict(Regel="Kaufen und Halten", **perf(valid.astype(float)))]
    for w in WINDOWS:
        s = S[w]
        g = np.char.startswith(s.astype(str), "GRUEN")
        rows += [dict(Regel=f"{w}T: long bei GRUEN", **perf(g.astype(float))),
                 dict(Regel=f"{w}T: long bei GRUEN oder GELB", **perf((g | (s == "GELB")).astype(float))),
                 dict(Regel=f"{w}T: long ausser bei ROT->short", **perf(np.where(s == "ROT", -1.0, 1.0) * valid)),
                 dict(Regel=f"{w}T: long bei GELB oder ROT (Gegenteil)", **perf(((s == "GELB") | (s == "ROT")).astype(float)))]
    a = agree
    rows += [dict(Regel="einig: long bei GRUEN, flat bei ROT, sonst halten",
                  **perf(pd.Series(np.where(a & np.char.startswith(S[11].astype(str), "GRUEN"), 1.0,
                                            np.where(a & (S[11] == "ROT"), 0.0, np.nan))).ffill().fillna(0).values))]
    df = pd.DataFrame(rows).set_index("Regel")
    print("== 5: Handelsregeln aus der Ampel (1 bp Kosten je Wechsel) ==")
    print(df.to_string(formatters={"Rendite_pa": "{:+.1%}".format, "Sharpe": "{:+.2f}".format,
                                   "MaxDD": "{:.0%}".format, "investiert": "{:.0%}".format}), "\n")

    if "--plot" in sys.argv:
        plot(lp, D)


def plot(lp, D, w=11, last=120):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ink, mute, surf, blue, orange = "#0b0b0b", "#52514e", "#fcfcfb", "#2a78d6", "#eb6834"
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": "#d9d8d2", "axes.labelcolor": mute,
                         "xtick.color": mute, "ytick.color": mute, "text.color": ink})
    y = lp.values
    n = len(y)
    fc, _, _ = edge_derivs(y, w, at="center")
    fr, _, _ = D[w]
    sl = slice(n - last, n)
    x = np.arange(last)
    base = y[sl][0]
    idx = lambda a: np.exp(a - base) * 100
    fig, ax = plt.subplots(figsize=(9, 4.8), facecolor=surf)
    ax.set_facecolor(surf)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#ebeae5", lw=.8)
    ax.plot(x, idx(y[sl]), color="#b5b4ad", lw=1, label="Schlusskurs")
    ax.plot(x, idx(fc[sl]), color=blue, lw=2, label="Glättung im Rückblick (kennt 5 Folgetage)")
    ax.plot(x, idx(fr[sl]), color=orange, lw=2, label="Glättung live (rechter Rand)")
    ax.set_title(f"NQ, letzte {last} Handelstage (Start = 100): dieselbe Glättung über {w} Tage, im Rückblick und live",
                 loc="left", fontsize=11)
    ax.set_xlabel("Handelstag")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig("wendepunkt_radar.png", dpi=200, facecolor=surf)
    print("Grafik gespeichert: wendepunkt_radar.png")


if __name__ == "__main__":
    main()
