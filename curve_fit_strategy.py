"""
Kurvendiskussion als Handelssignal (NQ, Tagesbasis).

Idee: Die letzten N Tage (10 / 50 / 100) des log-Kurses werden durch ein Polynom
f(x) angenaehert. Aus f'(x) und f''(x) folgen
  - Extremstellen  (f' = 0)  -> Trendwechsel
  - Wendestellen   (f'' = 0) -> Trend verliert / gewinnt an Dynamik
Gehandelt wird nur mit Information, die am Tag t bekannt ist (Fit ueber
[t-N+1, t], Ableitungen am rechten Rand ausgewertet, Position gilt fuer t -> t+1).

Zum Vergleich wird dieselbe Regel mit einem zentrierten Fenster gerechnet
(nutzt Zukunftsdaten, NICHT handelbar) - das zeigt, wie stark der Rueckblick taeuscht.

Aufruf:  python curve_fit_strategy.py [--plot]
"""
import sys
import numpy as np
import pandas as pd

CSV = "Dataset_NQ_1min_2022_2025.csv"
WINDOWS = (10, 50, 100)
DEGREES = (2, 3)
COST = 0.0001          # 1 bp pro Positionswechsel-Einheit (Spread + Gebuehren, grob)
SPLIT = 0.6            # erste 60 % = In-Sample, Rest = Out-of-Sample


def load_daily(path=CSV):
    df = pd.read_csv(path, usecols=["timestamp ET", "close"])
    ts = pd.to_datetime(df["timestamp ET"], format="%m/%d/%Y %H:%M")
    df = df.set_index(ts).sort_index()
    rth = df.between_time("09:30", "16:00")           # regulaere Handelszeit
    daily = rth["close"].groupby(rth.index.date).agg(["last", "count"])
    daily = daily[daily["count"] > 300]["last"]       # halbe / lueckenhafte Tage raus
    daily.index = pd.to_datetime(daily.index)
    return daily


def derivatives(logp, n, deg, centered=False):
    """f' und f'' des Polynom-Fits, ausgewertet am Tag t.

    centered=False: Fenster [t-n+1, t], Auswertung am rechten Rand (kausal).
    centered=True : Fenster [t-n/2, t+n/2], Auswertung in der Mitte (Lookahead!).
    """
    x = np.arange(n, dtype=float)
    x0 = (n - 1) / 2 if centered else n - 1
    V = np.vander(x - x0, deg + 1, increasing=True)   # Spalten: 1, x, x^2, ...
    P = np.linalg.pinv(V)                             # Koeffizienten = P @ y
    win = np.lib.stride_tricks.sliding_window_view(logp.values, n)
    coef = win @ P.T                                  # (Anzahl Fenster, deg+1)
    d1 = np.full(len(logp), np.nan)
    d2 = np.full(len(logp), np.nan)
    idx = np.arange(len(win)) + (n // 2 if centered else n - 1)
    d1[idx] = coef[:, 1]                              # f'(x0)  = c1
    d2[idx] = 2 * coef[:, 2]                          # f''(x0) = 2*c2
    return d1, d2


def signals(d1, d2):
    s = {}
    # A: Extremstellen-Regel - long solange f' > 0, short solange f' < 0
    s["A f'>0 long/short"] = np.sign(d1)
    # B: nur long, sonst flat
    s["B f'>0 long/flat"] = (d1 > 0).astype(float)
    # C: Wendestellen-Regel - nur handeln, wenn Steigung UND Kruemmung gleich gerichtet
    s["C f',f'' gleich"] = np.where((d1 > 0) & (d2 > 0), 1.0,
                             np.where((d1 < 0) & (d2 < 0), -1.0, 0.0))
    # D: Kruemmung allein (antizipiert das Extremum)
    s["D f''>0 long/short"] = np.sign(d2)
    return {k: np.nan_to_num(v) for k, v in s.items()}


def stats(pos, ret):
    """pos[t] wird am Schluss von t eingegangen und verdient ret[t+1]."""
    pnl = pos[:-1] * ret[1:] - COST * np.abs(np.diff(pos, prepend=0.0))[:-1]
    if len(pnl) < 2 or pnl.std() == 0:
        return dict(ann=0.0, sharpe=0.0, mdd=0.0, trades=0)
    eq = np.cumsum(pnl)
    return dict(ann=pnl.mean() * 252,
                sharpe=pnl.mean() / pnl.std() * np.sqrt(252),
                mdd=(eq - np.maximum.accumulate(eq)).min(),
                trades=int((np.diff(pos) != 0).sum()))


def main():
    px = load_daily()
    logp = np.log(px)
    ret = logp.diff().fillna(0).values
    k = int(len(px) * SPLIT)
    print(f"{len(px)} Handelstage  {px.index[0].date()} .. {px.index[-1].date()}"
          f"   (Out-of-Sample ab {px.index[k].date()})\n")

    rows = []
    for name, sl in (("gesamt", slice(None)), ("IS", slice(0, k)), ("OOS", slice(k, None))):
        st = stats(np.ones(len(px))[sl], ret[sl])
        rows.append(dict(N="-", Grad="-", Regel="Buy & Hold", Fenster="-", Teil=name, **st))
    for n in WINDOWS:
        for deg in DEGREES:
            for centered in (False, True):
                d1, d2 = derivatives(logp, n, deg, centered)
                for rule, pos in signals(d1, d2).items():
                    for name, sl in (("gesamt", slice(None)), ("IS", slice(0, k)),
                                     ("OOS", slice(k, None))):
                        rows.append(dict(N=n, Grad=deg, Regel=rule,
                                         Fenster="RUECKBLICK" if centered else "kausal",
                                         Teil=name, **stats(pos[sl], ret[sl])))
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    fmt = {"ann": "{:+.1%}".format, "sharpe": "{:+.2f}".format, "mdd": "{:.1%}".format}

    def table(mask, title):
        t = res[mask].pivot_table(index=["N", "Grad", "Regel"], columns="Teil",
                                  values=["ann", "sharpe", "mdd", "trades"], sort=False)
        t = t[[("ann", "gesamt"), ("sharpe", "gesamt"), ("mdd", "gesamt"),
               ("trades", "gesamt"), ("sharpe", "IS"), ("sharpe", "OOS")]]
        t.columns = ["Rendite p.a.", "Sharpe", "Max DD", "Trades", "Sharpe IS", "Sharpe OOS"]
        print(title)
        print(t.to_string(formatters={"Rendite p.a.": fmt["ann"], "Sharpe": fmt["sharpe"],
                                      "Max DD": fmt["mdd"], "Trades": "{:.0f}".format,
                                      "Sharpe IS": fmt["sharpe"], "Sharpe OOS": fmt["sharpe"]}))
        print()

    table(res.Regel == "Buy & Hold", "== Benchmark ==")
    table(res.Fenster == "kausal", "== Handelbar (nur Vergangenheitsdaten) ==")
    table((res.Fenster == "RUECKBLICK") & (res.Regel.str.startswith("A")),
          "== NICHT handelbar: gleiche Regel A mit zentriertem Fenster (kennt die Zukunft) ==")

    if "--plot" in sys.argv:
        plot(px, logp)


def plot(px, logp, n=100, deg=3):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    seg = logp.iloc[-n:]
    x = np.arange(n, dtype=float)
    p = np.polynomial.Polynomial.fit(x, seg.values, deg)
    xs = np.linspace(0, n - 1, 400)
    real = lambda r: [v.real for v in r if abs(v.imag) < 1e-9 and 0 <= v.real <= n - 1]
    ext, infl = real(p.deriv(1).roots()), real(p.deriv(2).roots())

    fig, ax = plt.subplots(3, 1, figsize=(10, 9), sharex=True,
                           gridspec_kw={"height_ratios": [3, 1, 1]})
    ax[0].plot(x, np.exp(seg.values), color="#888", lw=1, label="NQ Schlusskurs")
    ax[0].plot(xs, np.exp(p(xs)), color="#1f6feb", lw=2, label=f"Polynom Grad {deg}")
    ax[0].scatter(ext, np.exp(p(np.array(ext))), color="#d1242f", zorder=5,
                  label="Extremstelle (f'=0)")
    ax[0].scatter(infl, np.exp(p(np.array(infl))), color="#bf8700", marker="D", zorder=5,
                  label="Wendestelle (f''=0)")
    ax[0].set_title(f"Letzte {n} Handelstage bis {px.index[-1].date()} - Fit im Rueckblick")
    ax[0].legend(loc="best")
    ax[1].plot(xs, p.deriv(1)(xs), color="#1f6feb"); ax[1].axhline(0, color="k", lw=.6)
    ax[1].set_ylabel("f'  (Steigung)")
    ax[2].plot(xs, p.deriv(2)(xs), color="#1f6feb"); ax[2].axhline(0, color="k", lw=.6)
    ax[2].set_ylabel("f''  (Kruemmung)"); ax[2].set_xlabel("Tag im Fenster")
    fig.tight_layout()
    fig.savefig("curve_fit_example.png", dpi=140)
    print("Grafik gespeichert: curve_fit_example.png")


if __name__ == "__main__":
    main()
