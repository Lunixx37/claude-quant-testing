"""
Grober Richtungs-Sinn: Wie weit ist der Tag beim Signal schon in Trade-Richtung gelaufen?

Idee: Ist der Tag schon weit ins Minus gelaufen, keinen Short mehr nehmen, eher Longs - und umgekehrt.

Tagesbewegung beim Signal, in Trade-Richtung und in ATR (positiv = der Trade geht mit der bisherigen Tagesrichtung):
  ab Vortagesschluss (16:00)     dm_vs = Seite x (Einstieg - Vortagesschluss) / ATR
  ab Sitzungsbeginn (18:00)      dm_18 = Seite x (Einstieg - Open 18:00) / ATR
  ab Mitternacht (00:00)         dm_00 = Seite x (Einstieg - Open 00:00) / ATR
Ein Short an einem Tag, der schon 1 ATR gefallen ist, hat also dm = +1; ein Long an demselben Tag dm = -1 + ...

Regeln:
  gegen X        Trade auslassen, wenn dm > X (keine Shorts an stark gefallenen Tagen, keine Longs an stark
                 gestiegenen)
  gegen X + 2.   wie 'gegen X', danach das erste Signal in die Gegenrichtung desselben Tages nehmen (ohne
                 Spannen-Filter, weil der Kurs dafuer einmal ueber die ganze Spanne laufen muss)
  drehen X       statt des Signals im selben Moment in die Gegenrichtung handeln
  mit X          Gegenprobe: Trade auslassen, wenn dm < -X (nur mit der Tagesrichtung handeln)

Segmente: A = CFD 2016-2020, B = CFD 2021-2022 (Auswahl), N = NQ 2023-2025 (Gegenprobe).

Aufruf:  python open_drive/direction_study.py <cache-ordner>
"""
import sys

import numpy as np
import pandas as pd

from opt_lib import BASE, add_features, load_cache, run_exit

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 300)
EXITS = {"Trend": dict(stop=0.08, rr=None), "R1": BASE}
SEGS = {"A": "CFD 2016-20", "B": "CFD 2021-22", "N": "NQ 2023-25"}


def both_signals(S, trig=0.3):
    """Je Tag der erste Schlusskurs jenseits Eroeffnung +/- trig x ATR, getrennt fuer oben und unten."""
    D = S["D"]
    C, atr, o = S["C"], D.atr.values, D.do.values
    with np.errstate(invalid="ignore"):
        hu = C >= (o + trig * atr)[:, None]
        hd = C <= (o - trig * atr)[:, None]
    for h in (hu, hd):
        h[:, 0] = False
        h[:, 360:] = False
    iu = np.where(hu.any(1), hu.argmax(1), 10 ** 6)
    idn = np.where(hd.any(1), hd.argmax(1), 10 ** 6)
    ok = D.tradable.values & ~np.isnan(atr) & ~np.isnan(o)
    return iu, idn, ok


def make_sig(S, di, i, side, trig=0.3):
    D = S["D"]
    sig = pd.DataFrame({"di": di, "i": i, "known": i, "side": side, "entry": S["C"][di, i]})
    sig["level"] = D.do.values[di] + side * trig * D.atr.values[di]
    sig["same_bar"] = False
    for c in ("day", "kind", "seg", "year", "dow", "atr"):
        sig[c] = D[c].values[di]
    f = add_features(S, sig)
    f["dm_vs"] = f.side * (f.entry - D.pdc.values[di]) / f.atr
    f["dm_18"] = f.side * (f.entry - D.o18.values[di]) / f.atr
    f["dm_00"] = f.side * (f.entry - D.o0.values[di]) / f.atr
    return f


def base_and_second(S):
    iu, idn, ok = both_signals(S)
    first = np.minimum(iu, idn)
    m = ok & (first < 10 ** 6) & (iu != idn)
    di = np.flatnonzero(m)
    side = np.where(iu[di] < idn[di], 1, -1)
    b = make_sig(S, di, first[di], side)
    keep = (b.rng <= 0.5).values
    b = b[keep].reset_index(drop=True)
    # zweites Signal in Gegenrichtung (fuer die Variante mit zweiter Chance)
    sec_i = np.where(b.side.values == 1, idn[b.di.values], iu[b.di.values])
    has = sec_i < 10 ** 6
    s2 = make_sig(S, b.di.values[has], sec_i[has], -b.side.values[has])
    s2["parent"] = np.flatnonzero(has)
    return b, s2


def stats(S, t, R, seg):
    m = (t.seg.values == seg) & ~np.isnan(R)
    r = R[m]
    nd = S["ndays"][seg]
    if len(r) < 10:
        return dict(n=len(r), wk=np.nan, win=np.nan, E=np.nan, Ryr=np.nan, dd=np.nan)
    eq = np.cumsum(r)
    return dict(n=len(r), wk=len(r) / nd * 5, win=(r > 0).mean(), E=r.mean(), Ryr=r.sum() / nd * 252,
                dd=(eq - np.maximum.accumulate(eq)).min())


def cell(s, s0):
    if not s["n"] or np.isnan(s["E"]):
        return "-"
    return (f"{s['wk']:.1f}/W {s['win']:.0%} {s['E']:+.3f} {s['Ryr']:+.0f}R/J DD{s['dd']:.0f}"
            f" ({s['Ryr'] - s0['Ryr']:+.0f})")


def main(cache):
    S = load_cache(cache)
    b, s2 = base_and_second(S)
    seg = b.seg.values
    R0 = {k: run_exit(S, b, **kw)[0] for k, kw in EXITS.items()}
    atr_nq = np.median(b.atr[b.seg == "N"])
    print(f"Basis: {len(b)} Trades. Median-ATR auf NQ 2023-25: {atr_nq:.0f} Punkte "
          f"(1 ATR = {atr_nq:.0f} Punkte, 0,5 ATR = {atr_nq / 2:.0f} Punkte)\n")

    # ---------- 1. Zusammenhang Tagesbewegung - Ergebnis
    print("== 1. Ergebnis je Tagesbewegung beim Signal (ab Vortagesschluss, in Trade-Richtung) ==")
    print("Zellen: Trades, Trefferquote, E je Trade (Trend | R1)")
    bins = [-9, -0.5, 0, 0.25, 0.5, 0.75, 1.0, 1.5, 9]
    lab = ["< -0,5 (klar gegen den Tag)", "-0,5 bis 0", "0 bis 0,25", "0,25 bis 0,5", "0,5 bis 0,75",
           "0,75 bis 1,0", "1,0 bis 1,5", "> 1,5 (Tag schon weit gelaufen)"]
    q = pd.cut(b.dm_vs, bins, labels=lab)
    rows = []
    for k in lab:
        r = {"Tagesbewegung (ATR)": k}
        for sg in "ABN":
            m = (q == k).values & (seg == sg)
            r[SEGS[sg]] = (f"{m.sum():3d}  {(R0['Trend'][m] > 0).mean():.0%} {R0['Trend'][m].mean():+.2f} | "
                           f"{(R0['R1'][m] > 0).mean():.0%} {R0['R1'][m].mean():+.2f}") if m.sum() >= 5 else "-"
        rows.append(r)
    print(pd.DataFrame(rows).to_string(index=False), "\n")
    from scipy import stats as st
    for col in ("dm_vs", "dm_18", "dm_00"):
        out = []
        for sg in "ABN":
            m = (seg == sg) & b[col].notna().values
            out.append(f"{SEGS[sg]}: Trend {st.spearmanr(b[col][m], R0['Trend'][m])[0]:+.3f}, "
                       f"R1 {st.spearmanr(b[col][m], R0['R1'][m])[0]:+.3f}")
        print(f"Rangkorrelation {col} mit R:  " + " | ".join(out))
    print("(positiv = Trades mit der Tagesrichtung sind besser)\n")

    # ---------- 2. Regeln
    for ex, kw in EXITS.items():
        base = {sg: stats(S, b, R0[ex], sg) for sg in "ABN"}
        rows = [{"Regel": "ohne Richtungs-Filter", **{SEGS[sg]: cell(base[sg], base[sg]) for sg in "ABN"}}]
        R2 = run_exit(S, s2, **kw)[0]
        for col, nm in (("dm_vs", "ab Vortagesschluss"), ("dm_18", "ab 18:00"), ("dm_00", "ab 00:00")):
            for X in (0.5, 0.75, 1.0, 1.25, 1.5):
                dm = b[col].values
                skip = dm > X
                # gegen X
                t, R = b[~skip], R0[ex][~skip]
                rows.append({"Regel": f"gegen {X} ({nm})",
                             **{SEGS[sg]: cell(stats(S, t, R, sg), base[sg]) for sg in "ABN"}})
                if col == "dm_vs":
                    # gegen X + zweite Chance
                    take2 = skip[s2.parent.values]
                    tt = pd.concat([b[~skip], s2[take2]], ignore_index=True)
                    RR = np.r_[R0[ex][~skip], R2[take2]]
                    rows.append({"Regel": f"gegen {X} + 2. Signal",
                                 **{SEGS[sg]: cell(stats(S, tt, RR, sg), base[sg]) for sg in "ABN"}})
                    # drehen X
                    fl = b.copy()
                    fl.loc[skip, "side"] = -fl.loc[skip, "side"]
                    Rf = run_exit(S, fl, **kw)[0]
                    rows.append({"Regel": f"drehen {X}",
                                 **{SEGS[sg]: cell(stats(S, fl, Rf, sg), base[sg]) for sg in "ABN"}})
                    # Gegenprobe: mit X
                    sk2 = dm < -X
                    rows.append({"Regel": f"mit {X} (Gegenprobe)",
                                 **{SEGS[sg]: cell(stats(S, b[~sk2], R0[ex][~sk2], sg), base[sg]) for sg in "ABN"}})
        print(f"== 2. Regeln, Ausstieg {ex} ==")
        print("Zellen: Trades/Woche, Trefferquote, E je Trade, R pro Jahr, groesster Drawdown, (R pro Jahr gegen ohne Filter)")
        print(pd.DataFrame(rows).to_string(index=False), "\n")

    # ---------- 3. Mehrtages-Richtung als Gegenprobe
    print("== 3. Mehrtages-Richtung: Trades mit / gegen den Trend der letzten 5 bzw. 20 Tage (Trend-Ausstieg, E je Trade) ==")
    rows = []
    for col, nm in (("r5", "5 Tage"), ("r20", "20 Tage")):
        for lo, hi, lb in ((-9, -0.5, "gegen den Trend"), (-0.5, 0.5, "neutral"), (0.5, 9, "mit dem Trend")):
            m = ((b[col] > lo) & (b[col] <= hi)).values
            rows.append({"Richtung": f"{nm}: {lb}",
                         **{SEGS[sg]: f"{(m & (seg == sg)).sum():3d}  {R0['Trend'][m & (seg == sg)].mean():+.3f}" for sg in "ABN"}})
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
