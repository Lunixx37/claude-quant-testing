"""
R1 "Open-Drive-Fortsetzung" - eigenstaendige Nachrechnung, Kerze fuer Kerze wie im Pine-Skript.

Regeln (New Yorker Zeit, 1-Min-Kerzen):
  ATR    = Mittel der letzten 14 abgeschlossenen Tagesspannen (Sitzung 18:00-18:00)
  O      = Open der 09:30-Kerze
  Signal = erste Kerze ab 09:31 mit Schluss >= O + 0.3 ATR (Long) bzw. <= O - 0.3 ATR (Short)
  Filter = Tagesspanne seit 09:30 (Hoch - Tief, inkl. Signalkerze) <= 0.5 ATR, Signal bis 15:29
  Entry  = Schluss der Signalkerze, hoechstens 1 Trade pro Tag
  Stop   = 0.15 ATR, Ziel = 0.5 x Stop, spaetestens Schluss der 15:59-Kerze
  Kosten = 1 NQ-Punkt je Trade (CFD: 0.0032 ATR)

Aufruf:  python final/r1_strategy.py            -> Kennzahlen + results/r1_trades_NQ.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

from build_events import load

TRIG, RNG_MAX, STOP, RR = 0.3, 0.5, 0.15, 0.5


def run(kind, trig=TRIG, rng_max=RNG_MAX, stop=STOP, rr=RR, cost_pts=1.0):
    b = load(kind)
    g = b.groupby((b.index + pd.Timedelta("6h")).normalize())
    atr = (g.high.max() - g.low.min()).rolling(14).mean().shift(1)
    first = pd.Timestamp("2016-11-16" if kind == "CFD" else "2023-01-01")
    clock = b.index.hour * 60 + b.index.minute
    rth = b[(clock >= 570) & (clock < 960)]
    rows, ndays = [], 0
    for day, s in rth.groupby(rth.index.normalize()):
        if day < first or day.dayofweek > 4 or len(s) < 350 or day not in atr.index or np.isnan(atr.loc[day]):
            continue
        if s.index[0].minute != 30 or s.index[0].hour != 9:
            continue
        ndays += 1
        a = float(atr.loc[day])
        O, H, L, C = s.open.values, s.high.values, s.low.values, s.close.values
        mins = (s.index.hour * 60 + s.index.minute).values
        o = O[0]
        hit = np.flatnonzero((np.abs(C - o) >= trig * a) & (mins >= 571))
        if not len(hit):
            continue
        r = hit[0]
        if mins[r] > 15 * 60 + 29 or H[:r + 1].max() - L[:r + 1].min() > rng_max * a:
            continue
        side = 1 if C[r] > o else -1
        entry, d = C[r], stop * a
        sl, tp = entry - side * d, entry + side * d * rr
        px, why, x = C[-1], "Zeit", len(C) - 1
        for i in range(r + 1, len(C)):
            if (L[i] <= sl) if side == 1 else (H[i] >= sl):
                px, why, x = sl, "Stop", i
                break
            if (H[i] >= tp) if side == 1 else (L[i] <= tp):
                px, why, x = tp, "Ziel", i
                break
        c = cost_pts if kind == "NQ" else cost_pts * 0.0032 * a
        rows.append(dict(tag=day.date(), einstieg=s.index[r] + pd.Timedelta("1min"), seite="Long" if side == 1 else "Short",
                         entry=entry, stop=sl, ziel=tp, ausstieg=s.index[x] + pd.Timedelta("1min"), exit=px, grund=why,
                         atr=a, punkte=side * (px - entry) - c, R=(side * (px - entry) - c) / d))
    return pd.DataFrame(rows), ndays


def stats(t, nd):
    R = t.R.values
    eq = np.cumsum(R)
    w, l = R[R > 0], R[R <= 0]
    daily = np.zeros(nd); daily[:len(R)] = R                     # hoechstens 1 Trade pro Tag
    streak = mx = 0
    for x in R:
        streak = streak + 1 if x <= 0 else 0
        mx = max(mx, streak)
    return {"Trades": len(R), "pro Woche": len(R) / nd * 5, "Trefferquote": (R > 0).mean(), "Ø Gewinn R": w.mean(),
            "Ø Verlust R": l.mean(), "E (R)": R.mean(), "t": daily.mean() / daily.std(ddof=1) * np.sqrt(nd),
            "Profitfaktor": w.sum() / -l.sum(), "R pro Jahr": R.sum() / nd * 252,
            "Max DD (R)": (eq - np.maximum.accumulate(eq)).min(), "laengste Verlustserie": mx}


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    out = Path(__file__).parent / "results"
    out.mkdir(exist_ok=True)
    res, yearly = {}, []
    for kind in ("CFD", "NQ"):
        t, nd = run(kind)
        res[f"{kind} ({t.tag.min()} .. {t.tag.max()})"] = stats(t, nd)
        yearly.append(t.assign(Jahr=pd.to_datetime(t.tag).dt.year))
        if kind == "NQ":
            t.to_csv(out / "r1_trades_NQ.csv", index=False)
            print("Ausstiege NQ:", t.grund.value_counts().to_dict(), "| Ø Stop", round((t.atr * STOP).mean(), 1),
                  "Punkte, Ø Ziel", round((t.atr * STOP * RR).mean(), 1), "Punkte\n")
            for c2 in (2.0, 3.0):
                t2, _ = run(kind, cost_pts=c2)
                res[f"NQ, Kosten {c2:.0f} Punkte"] = stats(t2, nd)
    print(pd.DataFrame(res).T.to_string(float_format="{:.3f}".format), "\n")
    y = pd.concat(yearly).groupby("Jahr").R.agg(Trades="count", Trefferquote=lambda x: (x > 0).mean(), E="mean", Summe_R="sum")
    print(y.T.to_string(float_format="{:.2f}".format), "\n")
    print("Nachbarschaft (NQ / CFD: Trefferquote, E in R):")
    rows = []
    for name, kw in (("Basis 0.3 / 0.5 / 0.15 / 0.5", {}), ("Trigger 0.25", dict(trig=0.25)), ("Trigger 0.35", dict(trig=0.35)),
                     ("Spanne <= 0.4", dict(rng_max=0.4)), ("Spanne <= 0.6", dict(rng_max=0.6)), ("ohne Spannen-Filter", dict(rng_max=99)),
                     ("Stop 0.12", dict(stop=0.12)), ("Stop 0.18", dict(stop=0.18)), ("Ziel 0.4 R", dict(rr=0.4)),
                     ("Ziel 0.6 R", dict(rr=0.6)), ("Ziel 0.75 R", dict(rr=0.75)), ("Ziel 1 R", dict(rr=1.0)),
                     ("Stop 0.1, Ziel 1 R", dict(stop=0.1, rr=1.0)), ("Stop 0.15, Ziel 2 R", dict(rr=2.0))):
        r = {"Variante": name}
        for kind in ("NQ", "CFD"):
            t, nd = run(kind, **kw)
            s = stats(t, nd)
            r[kind] = f"{s['Trefferquote']:.1%}  {s['E (R)']:+.3f}  (t {s['t']:+.1f}, {s['pro Woche']:.1f}/Wo)"
        rows.append(r)
    print(pd.DataFrame(rows).to_string(index=False))
