"""
VWAP-Filter: nicht 'unten' shorten (und nicht 'oben' kaufen).

VWAP mit Anker 18:00 New York (Beginn der Futures-Sitzung am Vortag), Baender = VWAP +/- k x volumengewichtete
Standardabweichung (sigma) seit 18:00. Beim CFD beruht die VWAP auf Tick-Volumen.

Merkmale beim Signal (positiv = der Kurs liegt in Trade-Richtung jenseits der VWAP; ein Short weit unter der VWAP
hat also einen grossen positiven Wert):
  z     = Seite x (Einstieg - VWAP) / sigma
  platz = Abstand vom Einstieg bis zum naechsten Band (1, 2 oder 3 sigma) in Trade-Richtung, in ATR

Regeln:
  ueber k       Trade auslassen, wenn z > k (Short unter dem -k-Band, Long ueber dem +k-Band)
  platz x       Trade auslassen, wenn das naechste Band in Trade-Richtung naeher als x ATR liegt (Reaktion moeglich)
  mit VWAP      Gegenprobe: Trade auslassen, wenn er gegen die VWAP-Seite geht (Short ueber, Long unter der VWAP)

Segmente: A = CFD 2016-2020, B = CFD 2021-2022 (Auswahl), N = NQ 2023-2025 (Gegenprobe).

Aufruf:  python open_drive/vwap_study.py <cache-ordner>
"""
import sys

import numpy as np
import pandas as pd
from scipy import stats as st

from opt_lib import BASE, add_features, load_cache, run_exit, signals

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 200)
EXITS = {"Trend": dict(stop=0.08, rr=None), "R1": BASE}
SEGS = {"A": "CFD 2016-20", "B": "CFD 2021-22", "N": "NQ 2023-25"}


def stats(S, t, R, seg):
    m = (t.seg.values == seg) & ~np.isnan(R)
    r = R[m]
    nd = S["ndays"][seg]
    eq = np.cumsum(r)
    return dict(wk=len(r) / nd * 5, win=(r > 0).mean(), E=r.mean(), Ryr=r.sum() / nd * 252,
                dd=(eq - np.maximum.accumulate(eq)).min())


def cell(s, s0):
    return f"{s['wk']:.1f}/W {s['win']:.0%} {s['E']:+.3f} {s['Ryr']:+.0f}R/J DD{s['dd']:.0f} ({s['Ryr'] - s0['Ryr']:+.0f})"


def main(cache):
    S = load_cache(cache)
    b = add_features(S, signals(S))
    b = b[b.rng <= 0.5].reset_index(drop=True)
    di, k, s, e, a = b.di.values, b.known.values, b.side.values, b.entry.values, b.atr.values
    vw, sd = S["vwe"][di, k], S["vwe_sd"][di, k]
    b["z"] = s * (e - vw) / np.where(sd > 0, sd, np.nan)
    ahead = np.full(len(b), np.inf)
    for kk in (1, 2, 3):                                    # Baender in Trade-Richtung vor dem Einstieg
        for sg in (1, -1):
            band = vw + sg * kk * sd
            d = s * (band - e) / a
            ahead = np.where((d > 0) & (d < ahead), d, ahead)
    b["platz"] = ahead
    seg = b.seg.values
    R0 = {x: run_exit(S, b, **kw)[0] for x, kw in EXITS.items()}
    print(f"{len(b)} Trades. Sigma der VWAP beim Signal im Median {np.nanmedian(sd / a):.2f} ATR "
          f"(NQ 2023-25: {np.nanmedian(sd[seg == 'N']):.0f} Punkte)\n")

    print("== 1. Ergebnis je Lage zur VWAP beim Signal (Trades, Trefferquote, E je Trade: Trend | R1) ==")
    bins = [-np.inf, -1, 0, 1, 2, 3, np.inf]
    lab = ["< -1 sigma (gegen die VWAP-Seite)", "-1 bis 0", "0 bis 1", "1 bis 2", "2 bis 3",
           "> 3 sigma (Short weit unten / Long weit oben)"]
    q = pd.cut(b.z, bins, labels=lab)
    rows = []
    for L in lab:
        r = {"Lage (Trade-Richtung)": L}
        for sg in "ABN":
            m = (q == L).values & (seg == sg)
            r[SEGS[sg]] = (f"{m.sum():3d}  {(R0['Trend'][m] > 0).mean():.0%} {R0['Trend'][m].mean():+.2f} | "
                           f"{(R0['R1'][m] > 0).mean():.0%} {R0['R1'][m].mean():+.2f}") if m.sum() >= 5 else f"{m.sum():3d}  -"
        rows.append(r)
    print(pd.DataFrame(rows).to_string(index=False))
    for x in ("Trend", "R1"):
        print(f"Rangkorrelation z mit R ({x}): " + " | ".join(
            f"{SEGS[sg]} {st.spearmanr(b.z[(seg == sg) & b.z.notna()], R0[x][(seg == sg) & b.z.notna().values])[0]:+.3f}" for sg in "ABN"))
    print("(positiv = Trades weiter jenseits der VWAP in Trade-Richtung sind besser)\n")

    print("== 2. Naechstes Band in Trade-Richtung (Trades, E je Trade: Trend | R1) ==")
    rows = []
    for lo, hi, L in ((0, 0.03, "< 0,03 ATR"), (0.03, 0.06, "0,03 bis 0,06"), (0.06, 0.1, "0,06 bis 0,1"),
                      (0.1, 0.2, "0,1 bis 0,2"), (0.2, np.inf, "> 0,2 bzw. kein Band mehr")):
        m = ((b.platz >= lo) & (b.platz < hi)).values
        rows.append({"Platz bis zum Band": L, **{SEGS[sg]: f"{(m & (seg == sg)).sum():3d}  {R0['Trend'][m & (seg == sg)].mean():+.2f} | {R0['R1'][m & (seg == sg)].mean():+.2f}" for sg in "ABN"}})
    print(pd.DataFrame(rows).to_string(index=False), "\n")

    for x, kw in EXITS.items():
        base = {sg: stats(S, b, R0[x], sg) for sg in "ABN"}
        rows = [{"Regel": "ohne VWAP-Filter", **{SEGS[sg]: cell(base[sg], base[sg]) for sg in "ABN"}}]
        rules = [(f"auslassen ueber {kk} sigma", b.z.values > kk) for kk in (0.5, 1, 1.5, 2, 2.5, 3)]
        rules += [(f"auslassen, Band naeher als {xx} ATR", b.platz.values < xx) for xx in (0.02, 0.03, 0.05, 0.1)]
        rules += [("Gegenprobe: nur mit der VWAP-Seite", b.z.values < 0),
                  ("Gegenprobe: nur mit der VWAP-Seite, mind. 1 sigma", b.z.values < 1)]
        for name, skip in rules:
            skip = np.nan_to_num(skip, nan=0).astype(bool)
            rows.append({"Regel": name, **{SEGS[sg]: cell(stats(S, b[~skip], R0[x][~skip], sg), base[sg]) for sg in "ABN"}})
        print(f"== 3. Regeln, Ausstieg {x} ==")
        print("Zellen: Trades/Woche, Trefferquote, E je Trade, R pro Jahr, groesster Drawdown, (R pro Jahr gegen ohne Filter)")
        print(pd.DataFrame(rows).to_string(index=False), "\n")


if __name__ == "__main__":
    main(sys.argv[1])
