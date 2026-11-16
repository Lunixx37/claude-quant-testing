"""
Gegenprobe der eingefrorenen Optimierungs-Kandidaten (opt_selection.json).

Segmente: A = CFD 2016-2020, B = CFD 2021-2022 (dort gewaehlt), N = NQ 2023-2025 (Gegenprobe).

Aufruf:  python open_drive/opt_final.py <cache-ordner>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

from opt_lib import BASE, HYB, add_features, load_cache, run_exit, signals

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 200)
SEGS = {"A": "CFD 2016-20", "B": "CFD 2021-22", "N": "NQ 2023-25"}


def streak(r):
    m = c = 0
    for x in r:
        c = c + 1 if x <= 0 else 0
        m = max(m, c)
    return m


def kpi(S, t, R, seg, w=None):
    m = (t.seg.values == seg) & ~np.isnan(R)
    r = R[m] * (w[m] if w is not None else 1.0)
    nd = S["ndays"][seg]
    d = np.zeros(nd)
    d[:len(r)] = r
    eq = np.cumsum(r)
    win, loss = r[r > 0], r[r <= 0]
    return {"Trades": len(r), "pro Woche": len(r) / nd * 5, "Trefferquote": (r > 0).mean(), "Ø Gewinn": win.mean(),
            "Ø Verlust": loss.mean(), "E (R)": r.mean(), "t": d.mean() / d.std(ddof=1) * np.sqrt(nd),
            "Profitfaktor": win.sum() / -loss.sum(), "R pro Jahr": r.sum() / nd * 252,
            "Max DD": (eq - np.maximum.accumulate(eq)).min(), "Verlustserie": streak(r)}


def show(rows, title):
    df = pd.DataFrame(rows).T
    f = {"Trefferquote": "{:.1%}".format, "pro Woche": "{:.2f}".format, "Trades": "{:.0f}".format,
         "Verlustserie": "{:.0f}".format, "t": "{:+.2f}".format, "Profitfaktor": "{:.2f}".format,
         "R pro Jahr": "{:+.1f}".format, "Max DD": "{:.1f}".format}
    print(f"== {title} ==")
    print(df.to_string(formatters={c: f.get(c, "{:+.3f}".format) for c in df.columns}), "\n")


def main(cache):
    S = load_cache(cache)
    sig = add_features(S, signals(S))
    base = sig[sig.rng <= 0.5].reset_index(drop=True)
    base["Rb"], _ = run_exit(S, base, **BASE)
    base["Rh"], info = run_exit(S, base, **HYB)
    w = np.where(base.onpos.values >= 0.5, 1.5, 0.5)
    systems = {"R1 (Ziel 0,5 R)": (base, "Rb", None),
               "V2a Teilverkauf + Runner": (base, "Rh", None),
               "V2b V2a + onpos >= 0,3": (base[base.onpos >= 0.3], "Rh", None),
               "V2c V2a + onpos >= 0,5": (base[base.onpos >= 0.5], "Rh", None),
               "V2d V2a, Risiko 1,5x / 0,5x": (base, "Rh", w)}
    for seg, lab in SEGS.items():
        show({k: kpi(S, t, t[c].values, seg, ww[t.index] if ww is not None else None)
              for k, (t, c, ww) in systems.items()}, lab)

    n = base[base.seg == "N"]
    print("== H1: Hybrid gegen Basis auf NQ (dieselben Trades) ==")
    d = n.Rh - n.Rb
    print(f"Unterschied je Trade {d.mean():+.3f} R, t = {d.mean() / d.std(ddof=1) * np.sqrt(len(d)):+.2f}, "
          f"Trefferquote Hybrid {(n.Rh > 0).mean():.1%}\n")

    print("== H2: Lage zur Overnight-Spanne auf NQ (Hybrid-Ausstieg) ==")
    ok = n.onpos.notna()
    rho, p = st.spearmanr(n.onpos[ok], n.Rh[ok])
    rb, pb = st.spearmanr(n.onpos[ok], n.Rb[ok])
    print(f"Rangkorrelation onpos / R: Hybrid {rho:+.3f} (p = {p:.3f}), Basis {rb:+.3f} (p = {pb:.3f})")
    rows = []
    for lab, m in (("onpos < 0,3", n.onpos < 0.3), ("0,3 bis 0,5", (n.onpos >= 0.3) & (n.onpos < 0.5)),
                   ("0,5 bis 0,7", (n.onpos >= 0.5) & (n.onpos < 0.7)), ("onpos >= 0,7", n.onpos >= 0.7),
                   ("onpos < 0,5", n.onpos < 0.5), ("onpos >= 0,5", n.onpos >= 0.5)):
        x = n[m]
        rows.append({"Gruppe": lab, "Trades": len(x), "Treffer": f"{(x.Rh > 0).mean():.0%}",
                     "E Basis": x.Rb.mean(), "E Hybrid": x.Rh.mean(),
                     "t Hybrid": x.Rh.mean() / x.Rh.std(ddof=1) * np.sqrt(len(x))})
    print(pd.DataFrame(rows).to_string(index=False, float_format="{:+.3f}".format))
    a, b = n.Rh[n.onpos >= 0.5], n.Rh[n.onpos < 0.5]
    tt = st.ttest_ind(a, b, equal_var=False)
    print(f"Unterschied >= 0,5 gegen < 0,5: {a.mean() - b.mean():+.3f} R, t = {tt.statistic:+.2f}, p = {tt.pvalue:.3f}\n")

    print("== H3: Wochentage (Hybrid-Ausstieg): alle Basis-Trades | nur onpos >= 0,3 ==")
    rows = []
    for dnum, nm in enumerate(["Mo", "Di", "Mi", "Do", "Fr"]):
        r = {"Tag": nm}
        for seg in "ABN":
            x = base[(base.seg == seg) & (base.dow == dnum)]
            y = x[x.onpos >= 0.3]
            r[SEGS[seg]] = f"{x.Rh.mean():+.2f} ({len(x)}) | {y.Rh.mean():+.2f} ({len(y)})"
        rows.append(r)
    print(pd.DataFrame(rows).to_string(index=False))
    for seg in "ABN":
        x = base[base.seg == seg]
        print(f"{SEGS[seg]}: ANOVA p = {st.f_oneway(*[x.Rh[x.dow == k] for k in range(5)]).pvalue:.2f}", end="   ")
    print("\n")

    print("== H1 gepoolt ueber alle drei Segmente: Hybrid minus Basis je Trade ==")
    for seg, lab in list(SEGS.items()) + [("ABN", "alle")]:
        x = base[base.seg.isin(list(seg))]
        d = x.Rh - x.Rb
        print(f"{lab:12s} {d.mean():+.3f} R  (t = {d.mean() / d.std(ddof=1) * np.sqrt(len(d)):+.2f}, {len(d)} Trades)")
    print()

    v2b = base[base.onpos >= 0.3]
    print("== Jahr fuer Jahr: E je Trade ==")
    yr = pd.DataFrame({"Trades": base.groupby("year").Rh.count(), "R1": base.groupby("year").Rb.mean(),
                       "V2a": base.groupby("year").Rh.mean(), "V2a Summe R": base.groupby("year").Rh.sum(),
                       "V2a Trefferquote": base.groupby("year").Rh.agg(lambda v: (v > 0).mean()),
                       "V2b (verworfen)": v2b.groupby("year").Rh.mean()})
    print(yr.T.to_string(float_format="{:+.2f}".format), "\n")

    print("== V2a: Kosten, Richtung, Nachbarschaft (Trefferquote, E, t, Trades/Woche) ==")

    def line(label, t, **kw):
        r = {"Variante": label}
        for seg in ("N", "A", "B"):
            R, _ = run_exit(S, t, **kw)
            k = kpi(S, t, R, seg)
            r[SEGS[seg]] = f"{k['Trefferquote']:.0%} {k['E (R)']:+.3f} (t {k['t']:+.1f}) {k['R pro Jahr']:+.0f}R/J"
        return r

    def sel(trig=0.3, rng=0.5):
        s = add_features(S, signals(S, trig=trig))
        return s[s.rng <= rng].reset_index(drop=True)

    t0 = sel()
    rows = [line("V2a: 50 % bei 0,5 R, Rest bis Tagesende, Stop auf Einstand", t0, **HYB),
            line("R1: alles bei 0,5 R", t0, **BASE),
            line("Kosten 2 Punkte", t0, cost_mult=2.0, **HYB), line("Kosten 3 Punkte", t0, cost_mult=3.0, **HYB),
            line("nur Long", t0[t0.side == 1].reset_index(drop=True), **HYB),
            line("nur Short", t0[t0.side == -1].reset_index(drop=True), **HYB)]
    for trig in (0.25, 0.35):
        rows.append(line(f"Signal {trig} ATR", sel(trig=trig, rng=trig + 0.2), **HYB))
    for rng in (0.4, 0.6, 99):
        rows.append(line(f"Spanne <= {rng}" if rng < 9 else "ohne Spannen-Filter", sel(rng=rng), **HYB))
    for stp in (0.10, 0.12, 0.18, 0.22):
        rows.append(line(f"Stop {stp} ATR", t0, **dict(HYB, stop=stp)))
    for pf in (0.33, 0.67):
        rows.append(line(f"Teilverkauf {pf:.0%}", t0, **dict(HYB, part=pf)))
    for pr in (0.4, 0.6, 0.75, 1.0):
        rows.append(line(f"Teilverkauf bei {pr} R", t0, **dict(HYB, part_rr=pr)))
    rows += [line("Rest mit Ziel 2 R", t0, **dict(HYB, rr=2.0)), line("Rest mit Ziel 3 R", t0, **dict(HYB, rr=3.0)),
             line("Rest: Stop auf Einstand + 0,1 R", t0, **dict(HYB, be_off=0.1)),
             line("Rest ohne Einstand-Stop", t0, **dict(HYB, part_be=False)),
             line("Rest mit VWAP-Nachzug", t0, **dict(HYB, ref="vwap", ref_mode=2)),
             line("ganz ohne Ziel (Runner), Stop 0,15", t0, stop=0.15, rr=None),
             line("ganz ohne Ziel (Runner), Stop 0,08", t0, stop=0.08, rr=None)]
    print(pd.DataFrame(rows).to_string(index=False), "\n")


if __name__ == "__main__":
    main(sys.argv[1])
