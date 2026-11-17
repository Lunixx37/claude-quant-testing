"""
NQ Open-Drive - eigenstaendige Nachrechnung, Kerze fuer Kerze wie im Pine-Skript.

Einstieg (New Yorker Zeit, 1-Min-Kerzen):
  ATR    = Mittel der letzten 14 abgeschlossenen Tagesspannen (Sitzung 18:00-18:00)
  O      = Open der 09:30-Kerze
  Signal = erste Kerze ab 09:31 mit Schluss >= O + 0.3 ATR (Long) bzw. <= O - 0.3 ATR (Short)
  Filter = Tagesspanne seit 09:30 (Hoch - Tief, inkl. Signalkerze) <= 0.5 ATR, Signal bis 15:29
  Entry  = Schluss der Signalkerze, hoechstens 1 Trade pro Tag

Ausstiegs-Modi:
  Trend  : Stop 0.08 ATR, kein Ziel, bis 15:59 halten                       (empfohlen)
  Trend+N: wie Trend, dazu Kerzen-Nachzug: sobald der Trade 1 x Stop im Gewinn schliesst, wandert der Stop
           nach jeder 1-Min-Kerze in Trade-Richtung auf deren Open
  V2a    : Stop 0.15 ATR, halbe Position bei 0.5 x Stop, danach Stop auf Einstand, Rest bis 15:59
  R1     : Stop 0.15 ATR, ganze Position bei 0.5 x Stop

Kosten = 1 NQ-Punkt je Kontrakt und Trade (CFD: 0.0032 ATR). Liegen Stop und Ziel in derselben Kerze, zaehlt der
Stop. Geaenderte Stops (Einstand, Nachzug) gelten ab der naechsten Kerze.

Aufruf:  python open_drive/r1_strategy.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

from build_events import load

TRIG, RNG_MAX = 0.3, 0.5
_DATA = {}


def _days(kind):
    if kind not in _DATA:
        b = load(kind)
        g = b.groupby((b.index + pd.Timedelta("6h")).normalize())
        atr = (g.high.max() - g.low.min()).rolling(14).mean().shift(1)
        first = pd.Timestamp("2016-11-16" if kind == "CFD" else "2023-01-01")
        clock = b.index.hour * 60 + b.index.minute
        rth = b[(clock >= 570) & (clock < 960)]
        out, prev_day, prev_close = [], None, np.nan
        for day, s in rth.groupby(rth.index.normalize()):
            if day.dayofweek > 4 or len(s) < 350 or s.index[0].minute != 30 or s.index[0].hour != 9:
                continue
            pc = prev_close if prev_day is not None and (day - prev_day).days <= 5 else np.nan
            prev_day, prev_close = day, s.close.values[-1]
            if day < first or day not in atr.index or np.isnan(atr.loc[day]):
                continue
            out.append((day, float(atr.loc[day]), s.index, s.open.values, s.high.values, s.low.values, s.close.values,
                        (s.index.hour * 60 + s.index.minute).values, pc))
        _DATA[kind] = out
    return _DATA[kind]


def run(kind, trig=TRIG, rng_max=RNG_MAX, stop=0.15, rr=0.5, cost_pts=1.0, part=0.0, runner_rr=None,
        no_target=False, trail_act=None, trail_k=1, trail_part=1.0, cut=None, gapgo=None):
    """part = 0 und no_target = False: alles bei rr x Stop (R1).
    part > 0: Anteil `part` bei rr x Stop, Rest bis runner_rr x Stop (None = Tagesende), Stop danach auf Einstand.
    no_target: kein Ziel, nur Stop und Tagesende (Trend).
    trail_act: Kerzen-Nachzug ab trail_act x Stop Gewinn (Schlusskurs); trail_k = Kerzen in Folge;
               trail_part < 1: nur dieser Anteil der Position folgt dem Nachzug, der Rest behaelt den Stop.
    gapgo = g: Gap-and-Go - liegt die Eroeffnung >= g x ATR jenseits des Vortagesschlusses und schliesst die
               09:31-Kerze in Lueckenrichtung jenseits der Eroeffnung, Einstieg zu diesem Schlusskurs in
               Lueckenrichtung (ohne Spannen-Filter); sonst das normale Signal.
    cut = (n, x): Zeit-Regel - Ausstieg zum Schlusskurs, wenn der Trade n Minuten nach dem Einstieg mehr als
               x x Stop im Minus schliesst."""
    if trail_act is not None and 0 < trail_part < 1:                       # zwei Teilpositionen, gleicher Einstieg
        kw = dict(trig=trig, rng_max=rng_max, stop=stop, rr=rr, cost_pts=cost_pts, part=part, runner_rr=runner_rr,
                  no_target=no_target, cut=cut, gapgo=gapgo)
        a, nd = run(kind, trail_act=trail_act, trail_k=trail_k, **kw)
        h, _ = run(kind, **kw)
        m = h.copy()
        m["R"] = trail_part * a.R + (1 - trail_part) * h.R
        m["punkte"] = trail_part * a.punkte + (1 - trail_part) * h.punkte
        m["grund"] = a.grund + " / " + h.grund
        return m, nd
    rows = []
    days = _days(kind)
    for day, a, idx, O, H, L, C, mins, pc in days:
        o = O[0]
        g = (o - pc) / a
        if gapgo is not None and abs(g) >= gapgo and mins[1] == 571 and (C[1] - o) * np.sign(g) > 0:
            r, side, src = 1, int(np.sign(g)), "Gap-and-Go"
        else:
            hit = np.flatnonzero((np.abs(C - o) >= trig * a) & (mins >= 571))
            if not len(hit):
                continue
            r = hit[0]
            if mins[r] > 15 * 60 + 29 or H[:r + 1].max() - L[:r + 1].min() > rng_max * a:
                continue
            side, src = (1 if C[r] > o else -1), "Signal 0,3"
        entry, d = C[r], stop * a
        sl = entry - side * d
        tp = None if no_target else entry + side * d * rr
        tp2 = entry + side * d * runner_rr if (part > 0 and runner_rr) else None
        cur, kind_stop, rem, real, tp1 = sl, "Stop", 1.0, 0.0, False
        active, streak = False, 0
        px, why, x = C[-1], "Tagesende", len(C) - 1
        for i in range(r + 1, len(C)):
            if (L[i] <= cur) if side == 1 else (H[i] >= cur):
                fill = O[i] if (O[i] - cur) * side < 0 else cur            # Luecke ueber den Stop
                real += rem * (fill - entry) * side
                rem, px, why, x = 0.0, fill, kind_stop, i
                break
            if tp is not None:
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
                        tp1 = True
                        if (entry - cur) * side > 0:
                            cur, kind_stop = entry, "Einstand"
                    if tp2 is not None and ((H[i] >= tp2) if side == 1 else (L[i] <= tp2)):
                        real += rem * (tp2 - entry) * side
                        rem, px, why, x = 0.0, tp2, "Ziel 2", i
                        break
            if trail_act is not None:                                      # Kerzen-Nachzug
                if not active and (C[i] - entry) * side >= trail_act * d:
                    active = True
                streak = streak + 1 if (C[i] - O[i]) * side > 0 else 0
                if active and streak >= trail_k:
                    ns = O[i - (trail_k - 1)]
                    if (ns - cur) * side > 0 and (C[i] - ns) * side > 0:
                        cur, kind_stop = ns, "Nachzug"
            if cut is not None and mins[i] - mins[r] == cut[0] and (entry - C[i]) * side > cut[1] * d:
                real += rem * (C[i] - entry) * side                         # Zeit-Regel
                rem, px, why, x = 0.0, C[i], "Zeit-Regel", i
                break
        if rem > 0:
            real += rem * (C[-1] - entry) * side
        c = cost_pts if kind == "NQ" else cost_pts * 0.0032 * a
        rows.append(dict(tag=day.date(), einstieg=idx[r] + pd.Timedelta("1min"), art=src,
                         seite="Long" if side == 1 else "Short",
                         entry=entry, stop=sl, ziel1=tp, teilziel_erreicht=tp1 or why == "Ziel",
                         ausstieg=idx[x] + pd.Timedelta("1min"), exit=px, grund=why, atr=a, stop_punkte=d,
                         minuten=int((idx[x] - idx[r]).total_seconds() // 60), punkte=real - c, R=(real - c) / d))
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


def sheet(t, nd):
    """Ausfuehrliches Kennzahlenblatt."""
    R = t.R.values
    eq = np.cumsum(R)
    peak = np.maximum.accumulate(eq)
    w, l = R[R > 0], R[R <= 0]
    streak = mx = 0
    for x in R:
        streak = streak + 1 if x <= 0 else 0
        mx = max(mx, streak)
    under = longest = 0                                                    # Trades unter dem letzten Hoch
    for e, p in zip(eq, peak):
        under = under + 1 if e < p else 0
        longest = max(longest, under)
    mon = t.assign(m=pd.to_datetime(t.tag).dt.to_period("M")).groupby("m").R.sum()
    yr = t.assign(j=pd.to_datetime(t.tag).dt.year).groupby("j").R.sum()
    s = stats(t, nd)
    return {"Zeitraum": f"{t.tag.min()} bis {t.tag.max()}", "Handelstage": nd, "Trades": len(R),
            "Trades pro Woche": round(len(R) / nd * 5, 2), "Anteil Tage mit Trade": f"{len(R) / nd:.0%}",
            "Long / Short": f"{(t.seite == 'Long').sum()} / {(t.seite == 'Short').sum()}",
            "Trefferquote": f"{(R > 0).mean():.1%}", "Ø Gewinn": f"{w.mean():+.2f} R", "Ø Verlust": f"{l.mean():+.2f} R",
            "Realisiertes Chance-Risiko-Verhältnis": f"{w.mean() / -l.mean():.2f} zu 1",
            "Median-Gewinn": f"{np.median(w):+.2f} R", "Größter Gewinn": f"{R.max():+.1f} R",
            "Ergebnis je Trade": f"{R.mean():+.3f} R", "R gesamt": f"{R.sum():+.1f} R",
            "R pro Jahr": f"{R.sum() / nd * 252:+.1f} R", "R pro Woche": f"{R.sum() / nd * 5:+.2f} R",
            "Profitfaktor": f"{w.sum() / -l.sum():.2f}", "t-Wert": f"{s['t']:.2f}",
            "Größter Drawdown": f"{(eq - peak).min():.1f} R", "Längste Verlustserie": mx,
            "Längste Durststrecke (Trades ohne neues Hoch)": longest,
            "Positive Monate": f"{(mon > 0).sum()} von {len(mon)}", "Positive Jahre": f"{(yr > 0).sum()} von {len(yr)}",
            "Ø Haltedauer Gewinner / Verlierer": f"{t.minuten[t.R > 0].mean():.0f} / {t.minuten[t.R <= 0].mean():.0f} Min",
            "Ø Stop": f"{t.stop_punkte.mean():.1f} Punkte",
            "Ausgang": ", ".join(f"{k} {v}" for k, v in t.grund.value_counts().items())}


MODES = {"Trend: Stop 0,08 ATR, kein Ziel": dict(stop=0.08, no_target=True),
         "Trend + Nachzug: 1-Min-Kerzen ab 1 R": dict(stop=0.08, no_target=True, trail_act=1.0),
         "Trend, halbe Position mit Nachzug": dict(stop=0.08, no_target=True, trail_act=1.0, trail_part=0.5),
         "Trend + Zeit-Regel 30 Min / 0,25 R": dict(stop=0.08, no_target=True, cut=(30, 0.25)),
         "Trend + Gap-and-Go 0,3": dict(stop=0.08, no_target=True, gapgo=0.3),
         "V2a: 50 % bei 0,5 R, Rest bis Tagesende": dict(part=0.5),
         "V2a-75: 50 % bei 0,75 R, Rest bis Tagesende": dict(part=0.5, rr=0.75),
         "R1: alles bei 0,5 R": dict()}
FILES = {"Trend:": "trend_trades_NQ.csv", "Trend + Nachzug": "trend_nachzug_trades_NQ.csv",
         "Trend, halbe": "trend_halb_nachzug_trades_NQ.csv", "Trend + Zeit": "trend_zeitregel_trades_NQ.csv",
         "Trend + Gap": "trend_gapgo_trades_NQ.csv", "V2a:": "v2a_trades_NQ.csv",
         "R1:": "r1_trades_NQ.csv"}

if __name__ == "__main__":
    pd.set_option("display.width", 230)
    pd.set_option("display.max_colwidth", 80)
    out = Path(__file__).parent / "results"
    out.mkdir(exist_ok=True)
    yearly, both = {}, {}
    for kind in ("CFD", "NQ"):
        res = {}
        for name, kw in MODES.items():
            t, nd = run(kind, **kw)
            res[name] = stats(t, nd)
            yearly.setdefault(name, []).append(t.assign(Jahr=pd.to_datetime(t.tag).dt.year))
            both.setdefault(name, []).append((t, nd))
            if kind == "NQ":
                for pre, fn in FILES.items():
                    if name.startswith(pre):
                        t.to_csv(out / fn, index=False)
        print(f"== {kind} ==")
        print(pd.DataFrame(res).T.to_string(float_format="{:.3f}".format), "\n")

    for name in list(MODES)[:3]:
        (tc, nc), (tn, nn) = both[name]
        ta = pd.concat([tc, tn], ignore_index=True)
        print(f"== Kennzahlenblatt: {name} ==")
        print(pd.DataFrame({"CFD 2016-2022": sheet(tc, nc), "NQ 2023-2025": sheet(tn, nn),
                            "beide zusammen": sheet(ta, nc + nn)}).to_string(), "\n")
        for c2 in (2.0, 3.0):
            t2, nd = run("NQ", cost_pts=c2, **MODES[name])
            print(f"   NQ mit {c2:.0f} Punkten Kosten: {t2.R.mean():+.3f} R je Trade, {t2.R.sum() / nd * 252:+.1f} R pro Jahr")
        print()

    print("Jahr fuer Jahr - Summe R (Trefferquote):")
    y = pd.DataFrame({k.split(":")[0]: pd.concat(v).groupby("Jahr").R.agg(lambda x: f"{x.sum():+.0f} ({(x > 0).mean():.0%})")
                      for k, v in yearly.items()})
    y["Trades"] = pd.concat(yearly["R1: alles bei 0,5 R"]).groupby("Jahr").R.count()
    print(y.T.to_string())
