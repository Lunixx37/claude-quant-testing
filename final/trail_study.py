"""
Kerzen-Nachzug fuer offen gelassene Positionen (gleicher Einstieg wie R1).

Getestete Regeln, jeweils erst aktiv, sobald der Schlusskurs einer Minute den Trade um `act` x Stop im Gewinn zeigt:
  open k/T : nach k Kerzen in Folge in Trade-Richtung (Kerzenlaenge T Minuten) Stop auf das Open der ersten
             dieser Kerzen (k = 1: Open der gerade geschlossenen Kerze)
  ext W    : Stop einen Tick hinter das Tief/Hoch der letzten W Minuten, jede Minute nachgezogen
Der Stop wird nie zurueckgenommen und gilt ab der naechsten Kerze.

Grundmodi:
  V2a    Stop 0,15 ATR, halbe Position bei 0,5 x Stop, Rest mit Stop auf Einstand bis 15:59
  Trend  Stop 0,08 ATR, kein Ziel, bis 15:59
  Run15  Stop 0,15 ATR, kein Ziel, bis 15:59

Aufruf:  python final/trail_study.py <cache-ordner>
"""
import sys

import numpy as np
import pandas as pd

from opt_lib import HYB, add_features, load_cache, run_exit, signals

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 400)
MODES = {"V2a": HYB, "Trend": dict(stop=0.08, rr=None), "Run15": dict(stop=0.15, rr=None)}
TS, KS, WINS = (1, 2, 3, 5, 10, 15, 30), (1, 2, 3), (3, 5, 10, 15, 30, 60, 120)
ACTS = {"V2a": (1.0, 1.5, 2.0, 3.0), "Trend": (1.0, 2.0, 3.0, 5.0), "Run15": (1.0, 1.5, 2.0, 3.0)}


def variants(mode):
    for act in ACTS[mode]:
        for T in TS:
            for k in KS:
                yield f"open k={k} T={T} ab {act}R", dict(mode="open", T=T, k=k, act=act)
        for w in WINS:
            yield f"ext W={w} ab {act}R", dict(mode="ext", T=1, win=w, act=act, off=0.25)


def pt(d):
    return d.mean() / d.std(ddof=1) * np.sqrt(len(d)) if d.std() > 0 else 0.0


def kpi(R, seg, S, mask):
    r = R[mask]
    nd = sum(S["ndays"][x] for x in seg)
    eq = np.cumsum(r)
    m = c = 0
    for x in r:
        c = c + 1 if x <= 0 else 0
        m = max(m, c)
    return {"Trefferquote": (r > 0).mean(), "E (R)": r.mean(), "R pro Jahr": r.sum() / nd * 252,
            "Max DD": (eq - np.maximum.accumulate(eq)).min(), "Verlustserie": m,
            "Ø Gewinn": r[r > 0].mean(), "Ø Verlust": r[r <= 0].mean()}


def main(cache):
    S = load_cache(cache)
    b = add_features(S, signals(S))
    b = b[b.rng <= 0.5].reset_index(drop=True)
    seg = b.seg.values
    late = (b.kind.values == "NQ") & (b.day.values >= np.datetime64("2024-07-01"))

    # ---------------- Wie viel geben offene Positionen wieder ab?
    print("== Rueckgabe offener Positionen (alle Datensaetze), in Vielfachen des Stops ==")
    rows = []
    for mode, kw in (("V2a-Rest (Stop 0,15 ATR, Einstand ab +0,5 R)", dict(stop=0.15, rr=None, be=0.5)),
                     ("Trend (Stop 0,08 ATR)", MODES["Trend"])):
        R, info = run_exit(S, b, **kw)
        mfe = info["mfe"] * b.atr.values / info["stop_pts"]
        for th in (1, 2, 3, 5):
            m = mfe >= th
            rows.append({"Position": mode, "erreicht mindestens": f"{th} R", "Anteil der Trades": m.mean(),
                         "Ø Hoechststand": mfe[m].mean(), "Ø Ergebnis ohne Nachzug": R[m].mean(),
                         "behalten": R[m].mean() / mfe[m].mean()})
    print(pd.DataFrame(rows).to_string(index=False, formatters={
        "Anteil der Trades": "{:.0%}".format, "Ø Hoechststand": "{:+.2f} R".format,
        "Ø Ergebnis ohne Nachzug": "{:+.2f} R".format, "behalten": "{:.0%}".format}), "\n")

    best = {}
    for mode, kw in MODES.items():
        R0, _ = run_exit(S, b, **kw)
        rows = []
        for name, ct in variants(mode):
            R, _ = run_exit(S, b, **dict(kw, ctrail=ct))
            d = R - R0
            r = {"Nachzug": name, "Treffer": (R > 0).mean(), "E": R.mean(), "Diff": d.mean(), "t": pt(d)}
            for sg in "ABN":
                r[f"Diff {sg}"] = d[seg == sg].mean()
            r["Diff NQ seit 07/2024"] = d[late].mean()
            rows.append(r)
        t = pd.DataFrame(rows)
        best[mode] = t
        allpos = (t[["Diff A", "Diff B", "Diff N"]] > 0).all(axis=1)
        print(f"== {mode}: ohne Nachzug E {R0.mean():+.3f} R (A {R0[seg == 'A'].mean():+.3f}, B {R0[seg == 'B'].mean():+.3f}, "
              f"N {R0[seg == 'N'].mean():+.3f}), Treffer {(R0 > 0).mean():.0%} ==")
        print(f"{len(t)} Nachzug-Varianten: {int((t.Diff > 0).sum())} im Mittel besser, {int(allpos.sum())} in allen drei "
              f"Datensaetzen besser, {int((t.t > 2).sum())} mit t > 2, {int((t.t < -2).sum())} mit t < -2")
        f = {"Treffer": "{:.0%}".format, "t": "{:+.2f}".format}
        fm = {c: f.get(c, "{:+.3f}".format) for c in t.columns if c != "Nachzug"}
        print("Beste 12 nach mittlerem Unterschied:")
        print(t.sort_values("Diff", ascending=False).head(12).to_string(index=False, formatters=fm))
        print("Schlechteste 4:")
        print(t.sort_values("Diff").head(4).to_string(index=False, formatters=fm))
        # Raster: mittlerer Unterschied je Kerzenlaenge und Ausloeser
        t["act"] = t.Nachzug.str.extract(r"ab ([\d.]+)R")[0].astype(float)
        o = t[t.Nachzug.str.startswith("open")].copy()
        o["k"] = o.Nachzug.str.extract(r"k=(\d)")[0].astype(int)
        o["T"] = o.Nachzug.str.extract(r"T=(\d+)")[0].astype(int)
        for k in KS:
            print(f"Unterschied zum Halten bis 15:59, 'open' k={k} (Zeilen: Kerzenlaenge in Min, Spalten: Ausloeser in R):")
            print(o[o.k == k].pivot(index="T", columns="act", values="Diff").to_string(float_format="{:+.3f}".format))
        e = t[t.Nachzug.str.startswith("ext")].copy()
        e["W"] = e.Nachzug.str.extract(r"W=(\d+)")[0].astype(int)
        print("Unterschied, 'ext' (Zeilen: Fenster in Min, Spalten: Ausloeser in R):")
        print(e.pivot(index="W", columns="act", values="Diff").to_string(float_format="{:+.3f}".format), "\n")

    # ---------------- Frueherer Ausstieg und Gewinn-Anteil absichern
    print("== Spaetester Ausstieg: Unterschied zum Halten bis 15:59 (R je Trade; A / B / N) ==")
    rows = []
    for lab, xb in (("11:00", 90), ("12:00", 150), ("13:00", 210), ("14:00", 270), ("15:00", 330), ("15:30", 360),
                    ("15:45", 375)):
        r = {"Ausstieg spaetestens": lab}
        for mode, kw in MODES.items():
            R0, _ = run_exit(S, b, **kw)
            d = run_exit(S, b, **dict(kw, xbar=xb))[0] - R0
            r[mode] = f"{d.mean():+.3f} (t {pt(d):+.1f})  " + " / ".join(f"{d[seg == g].mean():+.3f}" for g in "ABN")
        rows.append(r)
    print(pd.DataFrame(rows).to_string(index=False), "\n")
    print("== Anteil des hoechsten offenen Gewinns absichern: Unterschied zum Halten bis 15:59 ==")
    rows = []
    for act in (1.0, 2.0, 3.0, 5.0):
        for fr in (0.25, 0.33, 0.5, 0.67, 0.8):
            r = {"gesichert": f"{fr:.0%} ab {act:.0f} R"}
            for mode, kw in MODES.items():
                R0, _ = run_exit(S, b, **kw)
                R = run_exit(S, b, **dict(kw, ratchet=(fr, act)))[0]
                d = R - R0
                r[mode] = f"{d.mean():+.3f} (t {pt(d):+.1f})  " + " / ".join(f"{d[seg == g].mean():+.3f}" for g in "ABN") \
                    + f"  Treffer {(R > 0).mean():.0%}"
            rows.append(r)
    print(pd.DataFrame(rows).to_string(index=False), "\n")

    # ---------------- Kennzahlen ausgewaehlter Varianten
    print("== Kennzahlen: ohne Nachzug gegen ausgewaehlte Nachzug-Regeln ==")
    picks = {"V2a": [("ohne Nachzug", None), ("open k=1 T=1 ab 1R", dict(mode="open", T=1, k=1, act=1.0)),
                     ("open k=2 T=1 ab 1R", dict(mode="open", T=1, k=2, act=1.0)),
                     ("open k=1 T=5 ab 1R", dict(mode="open", T=5, k=1, act=1.0)),
                     ("open k=1 T=30 ab 2R", dict(mode="open", T=30, k=1, act=2.0)),
                     ("ext W=60 ab 2R", dict(mode="ext", T=1, win=60, act=2.0, off=0.25))],
             "Trend": [("ohne Nachzug", None), ("open k=1 T=1 ab 1R", dict(mode="open", T=1, k=1, act=1.0)),
                       ("open k=1 T=5 ab 2R", dict(mode="open", T=5, k=1, act=2.0)),
                       ("open k=1 T=30 ab 3R", dict(mode="open", T=30, k=1, act=3.0)),
                       ("ext W=60 ab 3R", dict(mode="ext", T=1, win=60, act=3.0, off=0.25)),
                       ("ext W=120 ab 5R", dict(mode="ext", T=1, win=120, act=5.0, off=0.25))]}
    for mode, lst in picks.items():
        for sg, lab in (("AB", "CFD 2016-22"), ("N", "NQ 2023-25")):
            out = {}
            for name, ct in lst:
                R, _ = run_exit(S, b, **dict(MODES[mode], ctrail=ct))
                out[name] = kpi(R, sg, S, np.isin(seg, list(sg)))
            df = pd.DataFrame(out).T
            print(f"{mode}, {lab}")
            print(df.to_string(formatters={"Trefferquote": "{:.1%}".format, "E (R)": "{:+.3f}".format,
                                           "R pro Jahr": "{:+.1f}".format, "Max DD": "{:.1f}".format,
                                           "Verlustserie": "{:.0f}".format, "Ø Gewinn": "{:+.2f}".format,
                                           "Ø Verlust": "{:+.2f}".format}), "\n")


if __name__ == "__main__":
    main(sys.argv[1])
