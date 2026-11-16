"""
Fruehe Verlustbegrenzung im Trend-Modus (Stop 0,08 ATR, kein Ziel, bis 15:59).

Frage: Gibt es eine Regel, die Verlierer frueher beendet und damit den Drawdown senkt, ohne mehr Ertrag zu
kosten, als sie an Drawdown spart?  Massstab: R pro Jahr geteilt durch den groessten Drawdown.

Regeln (alles in Vielfachen des Stops, Ausstieg jeweils zum Schlusskurs der Minute):
  close x      Ausstieg, sobald eine Minute weiter als x im Verlust schliesst (harter Stop bleibt bei 1)
  fort n/x     Ausstieg nach n Minuten, wenn der Trade dann nicht mindestens x im Gewinn schliesst
  gegen k      Ausstieg nach k Kerzen in Folge gegen den Trade, solange er im Verlust liegt
  eng n/x      nach n Minuten wandert der Stop auf x hinter den Einstieg (0 = Einstand)
  einstand x   Stop auf Einstand, sobald der Trade x im Gewinn lag
  stop s       anderer Anfangs-Stop (s x ATR); R bezieht sich dann auf diesen Stop

Aufruf:  python open_drive/losscut_study.py <cache-ordner>
"""
import sys

import numpy as np
import pandas as pd

from opt_lib import add_features, load_cache, run_exit, signals

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 400)
TREND = dict(stop=0.08, rr=None)


def variants():
    for x in (0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 0.9):
        yield f"close {x}", dict(close_stop=x)
    for n in (2, 3, 5, 10, 15, 20, 30, 45, 60, 90):
        for x in (-0.5, -0.25, 0.0, 0.25, 0.5, 1.0):
            yield f"fort {n}/{x:+.2f}", dict(progress=(n, x))
    for k in (2, 3, 4, 5, 6):
        yield f"gegen {k}", dict(adverse=k)
    for n in (3, 5, 10, 15, 30, 60):
        for x in (0.75, 0.5, 0.25, 0.0):
            yield f"eng {n}/{x}", dict(tighten=(n, x))
    for x in (0.5, 1.0, 1.5, 2.0, 3.0):
        yield f"einstand {x}", dict(be=x)
    for s in (0.05, 0.06, 0.07, 0.10, 0.12):
        yield f"stop {s}", dict(stop=s)


def dd(r):
    eq = np.cumsum(r)
    return (eq - np.maximum.accumulate(eq)).min()


def streak(r):
    m = c = 0
    for x in r:
        c = c + 1 if x <= 0 else 0
        m = max(m, c)
    return m


def row(name, R, R0, seg, nd):
    cfd, nq = seg != "N", seg == "N"
    ndc, ndn = nd["A"] + nd["B"], nd["N"]
    d = R - R0
    r = {"Regel": name, "Treffer": (R > 0).mean(), "Ø Verlust": R[R <= 0].mean(), "E": R.mean(),
         "R/Jahr": R.sum() / (ndc + ndn) * 252, "DD": dd(R), "Serie": streak(R), "R/J je DD": R.sum() / (ndc + ndn) * 252 / -dd(R),
         "E CFD": R[cfd].mean(), "E NQ": R[nq].mean(), "DD CFD": dd(R[cfd]), "DD NQ": dd(R[nq]),
         "Verh. CFD": R[cfd].sum() / ndc * 252 / -dd(R[cfd]), "Verh. NQ": R[nq].sum() / ndn * 252 / -dd(R[nq]),
         "t Diff": d.mean() / d.std(ddof=1) * np.sqrt(len(d)) if d.std() > 0 else 0.0}
    return r


def main(cache):
    S = load_cache(cache)
    b = add_features(S, signals(S))
    b = b[b.rng <= 0.5].reset_index(drop=True)
    seg, nd = b.seg.values, S["ndays"]
    R0, i0 = run_exit(S, b, **TREND)

    # Wie verlaufen Verlierer und Gewinner in den ersten Minuten?
    print("== Verlauf nach dem Einstieg: spaetere Gewinner gegen spaetere Verlierer (ohne Zusatzregel) ==")
    win = R0 > 0
    C, di, i, s, e, sd = S["Cf"], b.di.values, b.i.values, b.side.values, b.entry.values, i0["stop_pts"]
    rows = []
    for n in (1, 2, 3, 5, 10, 15, 30, 60):
        j = np.minimum(i + n, 389)
        alive = (i0["X"] >= j)                                   # Trade nach n Minuten noch offen
        p = (C[di, j] - e) * s / sd
        rows.append({"Minuten nach Einstieg": n, "noch offen": alive.mean(),
                     "davon spaeter Gewinner": win[alive].mean(),
                     "Ø Stand Gewinner": p[alive & win].mean(), "Ø Stand Verlierer": p[alive & ~win].mean(),
                     "Gewinner im Minus": (p[alive & win] < 0).mean(), "Verlierer im Minus": (p[alive & ~win] < 0).mean()})
    print(pd.DataFrame(rows).to_string(index=False, formatters={
        "noch offen": "{:.0%}".format, "davon spaeter Gewinner": "{:.0%}".format, "Ø Stand Gewinner": "{:+.2f} R".format,
        "Ø Stand Verlierer": "{:+.2f} R".format, "Gewinner im Minus": "{:.0%}".format, "Verlierer im Minus": "{:.0%}".format}), "\n")

    rows = [row("ohne Zusatzregel", R0, R0, seg, nd)]
    for name, kw in variants():
        R, _ = run_exit(S, b, **dict(TREND, **kw))
        rows.append(row(name, R, R0, seg, nd))
    t = pd.DataFrame(rows)
    base = t.iloc[0]
    t["besser"] = (t["DD"] > base["DD"]) & (t["R/J je DD"] > base["R/J je DD"]) & (t["Verh. CFD"] > base["Verh. CFD"]) & \
                  (t["Verh. NQ"] > base["Verh. NQ"]) & (t["DD CFD"] > base["DD CFD"]) & (t["DD NQ"] > base["DD NQ"])
    f = {"Treffer": "{:.0%}".format, "Serie": "{:.0f}".format, "DD": "{:.1f}".format, "DD CFD": "{:.1f}".format,
         "DD NQ": "{:.1f}".format, "R/Jahr": "{:+.1f}".format, "R/J je DD": "{:.2f}".format, "Verh. CFD": "{:.2f}".format,
         "Verh. NQ": "{:.2f}".format, "t Diff": "{:+.2f}".format, "Ø Verlust": "{:+.2f}".format}
    fm = {c: f.get(c, "{:+.3f}".format) for c in t.columns if c not in ("Regel", "besser")}
    v = t.iloc[1:]
    print(f"== {len(v)} Regeln gegen 'ohne Zusatzregel' ==")
    print(f"kleinerer Drawdown: {int((v.DD > base.DD).sum())}   besseres Verhaeltnis Ertrag/Drawdown (gesamt): "
          f"{int((v['R/J je DD'] > base['R/J je DD']).sum())}   in CFD UND NQ besser bei Drawdown und Verhaeltnis: {int(v.besser.sum())}\n")
    print(t.iloc[[0]].to_string(index=False, formatters=fm), "\n")
    print("Beste 25 nach Ertrag je Drawdown (gesamt):")
    print(v.sort_values("R/J je DD", ascending=False).head(25).to_string(index=False, formatters=fm), "\n")
    print("Je Regel-Familie die Variante mit dem kleinsten Drawdown:")
    fam = v.assign(fam=v.Regel.str.split().str[0])
    print(fam.loc[fam.groupby("fam").DD.idxmax()].drop(columns="fam").to_string(index=False, formatters=fm), "\n")
    print("In beiden Datensaetzen besser:")
    print(v[v.besser].sort_values("R/J je DD", ascending=False).to_string(index=False, formatters=fm) if v.besser.any() else "keine")
    return t


if __name__ == "__main__":
    main(sys.argv[1])
