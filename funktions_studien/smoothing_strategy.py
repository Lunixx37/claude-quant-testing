"""
Glaettung statt Polynom, mit Unsicherheitsband (NQ, Tagesbasis).

Vier kausale Glaetter schaetzen am Tag t die Trend-Steigung des log-Kurses:
  Gauss-Kern     : einseitiger Gauss-Kern ueber die letzten N Tage
  Gauss lok.-lin.: Gauss-gewichtete Regressionsgerade (korrigiert den Randfehler)
  EMA            : exponentielle Glaettung, Span N
  Kalman         : lokales lineares Trendmodell (Level + Steigung)

Unsicherheit: Jede Steigung wird durch ihre Standardabweichung unter der
Nullhypothese "Random Walk ohne Trend" geteilt -> t-Wert. Gehandelt wird
  z=0/1/2 : nur wenn |t| > z (sonst flat)
  prob    : Positionsgroesse = Wahrscheinlichkeit, dass der Trend positiv ist

Aufruf:  python funktions_studien/smoothing_strategy.py
"""
from math import erf, sqrt

import numpy as np
import pandas as pd

from curve_fit_strategy import SPLIT, WINDOWS, load_daily, stats

Phi = np.vectorize(lambda v: 0.5 * (1 + erf(v / sqrt(2))))


def filter_t(ret, d, vol):
    """Steigung = sum_k d[k]*ret[t-k]; t-Wert unter Random-Walk-Null."""
    slope = np.convolve(ret, d)[:len(ret)]
    slope[:len(d) - 1] = np.nan
    return slope / (vol * np.sqrt((d ** 2).sum()))


def gauss_kernel(n):
    k = np.arange(n)
    w = np.exp(-0.5 * (k / (n / 3)) ** 2)
    return w / w.sum()                                 # d[k] fuer ret[t-k]


def gauss_loclin(n):
    x = np.arange(n) - (n - 1.0)                       # 0 = heute
    w = np.exp(-0.5 * (x / (n / 3)) ** 2)
    X = np.c_[np.ones(n), x]
    c = (np.linalg.inv(X.T * w @ X) @ (X.T * w))[1]    # Steigung = c @ y (alt..neu)
    d = np.cumsum(c[::-1])[::-1][1:]                   # Gewichte auf Renditen (alt..neu)
    return d[::-1]


def ema_t(ret, vol, n):
    a = 2 / (n + 1)
    slope = pd.Series(ret).ewm(alpha=a, adjust=False).mean().to_numpy(copy=True)
    slope[:n] = np.nan
    return slope / (vol * np.sqrt(a / (2 - a)))


def kalman_t(logp, vol, n):
    """Glatter Trend (integrierter Random Walk); Grenzperiode des Filters ~ n Tage."""
    F = np.array([[1.0, 1.0], [0.0, 1.0]])
    H = np.array([1.0, 0.0])
    x = np.array([logp[0], 0.0])
    P = np.eye(2) * 1e-2
    out = np.full(len(logp), np.nan)
    for t in range(1, len(logp)):
        r = vol[t] ** 2 if np.isfinite(vol[t]) else 1e-4
        Q = np.diag([0.0, r / (n / (2 * np.pi)) ** 4])  # nur die Steigung driftet
        x, P = F @ x, F @ P @ F.T + Q
        S = H @ P @ H + r
        K = P @ H / S
        x = x + K * (logp[t] - H @ x)
        P = P - np.outer(K, H @ P)
        if t >= n:
            out[t] = x[1] / np.sqrt(P[1, 1])
    return out


def rules(t):
    t = np.nan_to_num(t)
    out = {}
    for z in (0, 1, 2):
        out[f"L/S z={z}"] = np.where(t > z, 1.0, np.where(t < -z, -1.0, 0.0))
        out[f"L/F z={z}"] = (t > z).astype(float)
    out["L/S prob"] = 2 * Phi(t) - 1
    out["L/F prob"] = Phi(t)
    return out


def main():
    px = load_daily()
    logp = np.log(px).values
    ret = np.diff(logp, prepend=logp[0])
    vol = pd.Series(ret).ewm(span=60, min_periods=20).std().values   # kausal
    k = int(len(px) * SPLIT)

    rows = []
    for n in WINDOWS:
        ts = {"Gauss-Kern": filter_t(ret, gauss_kernel(n), vol),
              "Gauss lok.-lin.": filter_t(ret, gauss_loclin(n), vol),
              "EMA": ema_t(ret, vol, n),
              "Kalman": kalman_t(logp, vol, n)}
        # Rueckblick: zentrierter Gauss-Kern (kennt n/2 Tage Zukunft) - nicht handelbar
        c = filter_t(ret, gauss_kernel(n), vol)
        ts["RUECKBLICK Gauss"] = np.r_[c[n // 2:], np.full(n // 2, np.nan)]
        for m, t in ts.items():
            for rule, pos in rules(t).items():
                a, o = stats(pos, ret), stats(pos[k:], ret[k:])
                rows.append(dict(Methode=m, N=n, Regel=rule, ann=a["ann"], sharpe=a["sharpe"],
                                 oos=o["sharpe"], mdd=a["mdd"], trades=a["trades"],
                                 expo=np.abs(pos).mean()))
    res = pd.DataFrame(rows)
    bh, bho = stats(np.ones(len(ret)), ret), stats(np.ones(len(ret) - k), ret[k:])
    print(f"{len(px)} Handelstage, OOS ab {px.index[k].date()}")
    print(f"Buy & Hold: {bh['ann']:+.1%} p.a., Sharpe {bh['sharpe']:.2f} "
          f"(OOS {bho['sharpe']:.2f}), Max DD {bh['mdd']:.1%}\n")

    pd.set_option("display.width", 220)
    for col, title, f in (("sharpe", "Sharpe gesamt", "{:+.2f}"), ("oos", "Sharpe OOS", "{:+.2f}"),
                          ("ann", "Rendite p.a.", "{:+.1%}"), ("mdd", "Max Drawdown", "{:.0%}"),
                          ("expo", "Anteil der Zeit investiert", "{:.0%}"),
                          ("trades", "Positionswechsel", "{:.0f}")):
        t = res.pivot_table(index=["Methode", "N"], columns="Regel", values=col, sort=False)
        print(f"== {title} ==")
        print(t.map(f.format).to_string(), "\n")


if __name__ == "__main__":
    main()
