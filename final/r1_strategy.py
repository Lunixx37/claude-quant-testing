"""
Open-Drive-Fortsetzung R1 / V2a - eigenstaendige Nachrechnung, Kerze fuer Kerze wie im Pine-Skript.

Regeln (New Yorker Zeit, 1-Min-Kerzen):
  ATR    = Mittel der letzten 14 abgeschlossenen Tagesspannen (Sitzung 18:00-18:00)
  O      = Open der 09:30-Kerze
  Signal = erste Kerze ab 09:31 mit Schluss >= O + 0.3 ATR (Long) bzw. <= O - 0.3 ATR (Short)
  Filter = Tagesspanne seit 09:30 (Hoch - Tief, inkl. Signalkerze) <= 0.5 ATR, Signal bis 15:29
  Entry  = Schluss der Signalkerze, hoechstens 1 Trade pro Tag
  Stop   = 0.15 ATR
  R1     : ganze Position bei 0.5 x Stop glattstellen
  V2a    : halbe Position bei 0.5 x Stop glattstellen, danach Stop auf Einstand, Rest bis 15:59 halten
  Kosten = 1 NQ-Punkt je Kontrakt und Trade (CFD: 0.0032 ATR)

Liegen Stop und Ziel in derselben Kerze, zaehlt der Stop. Der Einstand-Stop gilt ab der Kerze nach dem
Teilverkauf.

Aufruf:  python final/r1_strategy.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

from build_events import load

TRIG, RNG_MAX, STOP, RR = 0.3, 0.5, 0.15, 0.5
_DATA = {}


def _days(kind):
    if kind not in _DATA:
        b = load(kind)
        g = b.groupby((b.index + pd.Timedelta("6h")).normalize())
        atr = (g.high.max() - g.low.min()).rolling(14).mean().shift(1)
        first = pd.Timestamp("2016-11-16" if kind == "CFD" else "2023-01-01")
        clock = b.index.hour * 60 + b.index.minute
        rth = b[(clock >= 570) & (clock < 960)]
        out = []
        for day, s in rth.groupby(rth.index.normalize()):
            if day < first or day.dayofweek > 4 or len(s) < 350 or day not in atr.index or np.isnan(atr.loc[day]):
                continue
            if s.index[0].minute != 30 or s.index[0].hour != 9:
                continue
            out.append((day, float(atr.loc[day]), s.index, s.open.values, s.high.values, s.low.values, s.close.values,
                        (s.index.hour * 60 + s.index.minute).values))
        _DATA[kind] = out
    return _DATA[kind]


def run(kind, trig=TRIG, rng_max=RNG_MAX, stop=STOP, rr=RR, cost_pts=1.0, part=0.0, runner_rr=None):
    """part = 0: R1 (alles bei rr x Stop).  part > 0: Anteil `part` bei rr x Stop, Rest bis runner_rr x Stop
    (None = Tagesende), Stop nach dem Teilverkauf auf Einstand."""
    rows = []
    days = _days(kind)
    for day, a, idx, O, H, L, C, mins in days:
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
        tp2 = entry + side * d * runner_rr if (part > 0 and runner_rr) else None
        cur, rem, real, tp1 = sl, 1.0, 0.0, False
        px, why, x = C[-1], "Zeit", len(C) - 1
        for i in range(r + 1, len(C)):
            if (L[i] <= cur) if side == 1 else (H[i] >= cur):
                fill = O[i] if (O[i] - cur) * side < 0 else cur            # Luecke ueber den Stop
                real += rem * (fill - entry) * side
                rem, px, why, x = 0.0, fill, ("Einstand" if tp1 else "Stop"), i
                break
            reach = (H[i] >= tp) if side == 1 else (L[i] <= tp)
            if part == 0:
                if reach:
                    real += rem * (tp - entry) * side
                    rem, px, why, x = 0.0, tp, "Ziel", i
                    break
            else:
                if not tp1 and reach:
                    real += part * (tp - entry) * side
                    rem -= part
                    tp1, cur = True, entry                                 # gilt ab der naechsten Kerze
                if tp2 is not None and ((H[i] >= tp2) if side == 1 else (L[i] <= tp2)):
                    real += rem * (tp2 - entry) * side
                    rem, px, why, x = 0.0, tp2, "Ziel 2", i
                    break
        if rem > 0:
            real += rem * (C[-1] - entry) * side
        c = cost_pts if kind == "NQ" else cost_pts * 0.0032 * a
        rows.append(dict(tag=day.date(), einstieg=idx[r] + pd.Timedelta("1min"), seite="Long" if side == 1 else "Short",
                         entry=entry, stop=sl, ziel1=tp, teilziel_erreicht=tp1 or why == "Ziel",
                         ausstieg=idx[x] + pd.Timedelta("1min"), exit=px, grund=why, atr=a,
                         punkte=real - c, R=(real - c) / d))
    return pd.DataFrame(rows), len(days)


def stats(t, nd):
    R = t.R.values
    eq = np.cumsum(R)
    w, l = R[R > 0], R[R <= 0]
    daily = np.zeros(nd)
    daily[:len(R)] = R                                                     # hoechstens 1 Trade pro Tag
    streak = mx = 0
    for x in R:
        streak = streak + 1 if x <= 0 else 0
        mx = max(mx, streak)
    return {"Trades": len(R), "pro Woche": len(R) / nd * 5, "Trefferquote": (R > 0).mean(), "Ø Gewinn R": w.mean(),
            "Ø Verlust R": l.mean(), "E (R)": R.mean(), "t": daily.mean() / daily.std(ddof=1) * np.sqrt(nd),
            "Profitfaktor": w.sum() / -l.sum(), "R pro Jahr": R.sum() / nd * 252,
            "Max DD (R)": (eq - np.maximum.accumulate(eq)).min(), "laengste Verlustserie": mx}


MODES = {"R1: alles bei 0,5 R": dict(),
         "V2a: 50 % bei 0,5 R, Rest bis Tagesende": dict(part=0.5),
         "V2a-75: 50 % bei 0,75 R, Rest bis Tagesende": dict(part=0.5, rr=0.75),
         "Trend: kein Ziel, Stop 0,08 ATR": dict(part=1e-9, rr=99.0, stop=0.08)}

if __name__ == "__main__":
    pd.set_option("display.width", 230)
    out = Path(__file__).parent / "results"
    out.mkdir(exist_ok=True)
    yearly = {}
    for kind in ("CFD", "NQ"):
        res = {}
        for name, kw in MODES.items():
            t, nd = run(kind, **kw)
            res[name] = stats(t, nd)
            yearly.setdefault(name, []).append(t.assign(Jahr=pd.to_datetime(t.tag).dt.year))
            if kind == "NQ" and name.startswith(("R1", "V2a:")):
                t.to_csv(out / ("r1_trades_NQ.csv" if name.startswith("R1") else "v2a_trades_NQ.csv"), index=False)
                if name.startswith("V2a:"):
                    print("V2a auf NQ - Ausgang des Rests:", t.grund.value_counts().to_dict(), "| Ø Stop",
                          round((t.atr * STOP).mean(), 1), "Punkte, Ø Teilziel", round((t.atr * STOP * RR).mean(), 1), "Punkte\n")
        print(f"== {kind} ==")
        print(pd.DataFrame(res).T.to_string(float_format="{:.3f}".format), "\n")
    for c2 in (2.0, 3.0):
        t2, nd = run("NQ", cost_pts=c2, part=0.5)
        print(f"V2a auf NQ mit {c2:.0f} Punkten Kosten: E {t2.R.mean():+.3f} R, {t2.R.sum() / nd * 252:+.1f} R pro Jahr")
    print("\nJahr fuer Jahr (E je Trade in R):")
    y = pd.DataFrame({k.split(":")[0]: pd.concat(v).groupby("Jahr").R.mean() for k, v in yearly.items()})
    y["Trades"] = pd.concat(yearly["R1: alles bei 0,5 R"]).groupby("Jahr").R.count()
    print(y.T.to_string(float_format="{:+.2f}".format))
