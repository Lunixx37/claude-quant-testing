"""
Trendtage frueher erwischen: fruehere Einstiege im Trend-Modus (Stop 0,08 ATR, kein Ziel, bis 15:59).

Bisher: erster Schlusskurs 0,3 ATR jenseits der 09:30-Eroeffnung, Tagesspanne <= 0,5 ATR.
Die besten Trades sind die, bei denen der Tag schon in Trade-Richtung gelaufen ist (Luecke, Overnight).

Getestete Einstiege (immer hoechstens 1 Trade pro Tag, Einstieg zum Schlusskurs, Tagesspanne <= 0,5 ATR):
  tief t           Schwelle t statt 0,3 ATR fuer beide Richtungen
  luecke g/t       Schwelle t in Richtung einer Luecke >= g ATR, sonst 0,3 ATR
  vortag X/Y       Kurs >= X ATR jenseits des Vortagesschlusses UND >= Y ATR jenseits der Eroeffnung
  start n/x        nach n Minuten (09:30+n) Einstieg, wenn der Kurs dann >= x ATR von der Eroeffnung entfernt ist;
                   sonst das bisherige Signal
  gapgo g          Einstieg 09:31 in Richtung einer Luecke >= g ATR, wenn die erste Minute in Lueckenrichtung
                   schliesst; sonst das bisherige Signal
  frueh+nachkauf   frueher Teil-Einstieg nach 'luecke g/t' plus zweiter Einstieg beim bisherigen Signal in
                   dieselbe Richtung (zwei Positionen mit je 1 R Risiko)

Segmente: A = CFD 2016-2020, B = CFD 2021-2022 (Auswahl), N = NQ 2023-2025 (Gegenprobe).

Aufruf:  python open_drive/early_entry_study.py <cache-ordner>
"""
import sys

import numpy as np
import pandas as pd

from direction_study import make_sig
from opt_lib import load_cache, run_exit

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 300)
TREND = dict(stop=0.08, rr=None)
SEGS = {"A": "CFD 2016-20", "B": "CFD 2021-22", "N": "NQ 2023-25"}


def cross(S, up_thr, dn_thr, i_min=1, i_max=359):
    """Erster Schlusskurs ueber up_thr bzw. unter dn_thr (je Tag ein Preis, nan = Seite gesperrt)."""
    C = S["C"]
    with np.errstate(invalid="ignore"):
        hu = C >= up_thr[:, None]
        hd = C <= dn_thr[:, None]
    for h in (hu, hd):
        h[:, :i_min] = False
        h[:, i_max + 1:] = False
    iu = np.where(hu.any(1), hu.argmax(1), 10 ** 6)
    idn = np.where(hd.any(1), hd.argmax(1), 10 ** 6)
    return iu, idn


def pick(S, iu, idn, rng_max=0.5):
    D = S["D"]
    ok = D.tradable.values & ~np.isnan(D.atr.values) & (np.minimum(iu, idn) < 10 ** 6) & (iu != idn)
    di = np.flatnonzero(ok)
    side = np.where(iu[di] < idn[di], 1, -1)
    i = np.minimum(iu, idn)[di]
    sig = make_sig(S, di, i, side)
    return sig[sig.rng <= rng_max].reset_index(drop=True)


def base_thr(S, t=0.3):
    D = S["D"]
    return D.do.values + t * D.atr.values, D.do.values - t * D.atr.values


def rule_low(S, t):
    return pick(S, *cross(S, *base_thr(S, t)))


def rule_gap(S, g, t):
    D = S["D"]
    o, a = D.do.values, D.atr.values
    gap = (o - D.pdc.values) / a
    up = np.where(gap >= g, o + t * a, o + 0.3 * a)
    dn = np.where(gap <= -g, o - t * a, o - 0.3 * a)
    return pick(S, *cross(S, up, dn))


def rule_prev(S, X, Y):
    D = S["D"]
    o, a, pc = D.do.values, D.atr.values, D.pdc.values
    return pick(S, *cross(S, np.fmax(pc + X * a, o + Y * a), np.fmin(pc - X * a, o - Y * a)))


def with_fallback(S, early):
    """Fruehes Signal, wo vorhanden; an den uebrigen Tagen das bisherige Signal."""
    base = rule_low(S, 0.3)
    rest = base[~base.di.isin(early.di)]
    return pd.concat([early, rest], ignore_index=True).sort_values(["di"]).reset_index(drop=True)


def rule_start(S, n, x):
    D = S["D"]
    k = n - 1
    mv = (S["C"][:, k] - D.do.values) / D.atr.values
    side = np.sign(mv)
    m = (np.abs(mv) >= x) & D.tradable.values & ~np.isnan(mv)
    di = np.flatnonzero(m)
    sig = make_sig(S, di, np.full(len(di), k), side[di].astype(int))
    sig = sig[sig.rng <= 0.5].reset_index(drop=True)
    return with_fallback(S, sig)


def rule_gapgo(S, g):
    D = S["D"]
    gap = (D.do.values - D.pdc.values) / D.atr.values
    side = np.sign(gap)
    first = np.sign(S["C"][:, 1] - D.do.values)
    m = (np.abs(gap) >= g) & (first == side) & D.tradable.values & ~np.isnan(gap)
    di = np.flatnonzero(m)
    sig = make_sig(S, di, np.full(len(di), 1), side[di].astype(int))
    return with_fallback(S, sig)


def stats(S, t, R, seg):
    m = (t.seg.values == seg) & ~np.isnan(R)
    r = R[m]
    nd = S["ndays"][seg]
    eq = np.cumsum(r)
    return dict(n=len(r), wk=len(r) / nd * 5, win=(r > 0).mean(), E=r.mean(), Ryr=r.sum() / nd * 252,
                dd=(eq - np.maximum.accumulate(eq)).min(), ext=t.ext.values[m].mean())


def cell(s, s0):
    return (f"{s['wk']:.1f}/W {s['win']:.0%} {s['E']:+.3f} {s['Ryr']:+.0f}R/J DD{s['dd']:.0f} "
            f"Abst.{s['ext']:.2f} ({s['Ryr'] - s0['Ryr']:+.0f})")


def main(cache):
    S = load_cache(cache)
    base = rule_low(S, 0.3)
    Rb = run_exit(S, base, **TREND)[0]
    b0 = {sg: stats(S, base, Rb, sg) for sg in "ABN"}

    # Wie viel vom Trendtag nimmt das bisherige Signal mit?
    D = S["D"]
    di = base.di.values
    move = base.side.values * (D.dc.values[di] - D.do.values[di]) / base.atr.values
    big = Rb >= 3
    print("== Wie viel vom Trendtag nimmt das bisherige Signal mit? (Trades mit mindestens +3 R) ==")
    for sg in "ABN":
        m = big & (base.seg.values == sg)
        print(f"{SEGS[sg]}: {m.sum()} Trades; Tagesbewegung Eroeffnung bis Schluss Ø {move[m].mean():.2f} ATR, "
              f"Einstieg Ø {base.ext.values[m].mean():.2f} ATR nach der Eroeffnung, "
              f"Einstieg Ø {base.tmin.values[m].mean():.0f} Minuten nach 09:30")
    print()

    rules = [("bisher (0,3 ATR)", lambda: base)]
    rules += [(f"tief {t}", lambda t=t: rule_low(S, t)) for t in (0.15, 0.2, 0.25)]
    rules += [(f"luecke {g}/{t}", lambda g=g, t=t: rule_gap(S, g, t)) for g in (0.1, 0.2, 0.3) for t in (0.1, 0.15, 0.2, 0.25)]
    rules += [(f"vortag {X}/{Y}", lambda X=X, Y=Y: rule_prev(S, X, Y)) for X in (0.4, 0.5, 0.6, 0.8) for Y in (0.1, 0.15, 0.2)]
    rules += [(f"start {n}/{x}", lambda n=n, x=x: rule_start(S, n, x)) for n in (5, 15, 30) for x in (0.1, 0.15, 0.2, 0.25)]
    rules += [(f"gapgo {g}", lambda g=g: rule_gapgo(S, g)) for g in (0.2, 0.3, 0.5)]
    rows, keep = [], {}
    for name, fn in rules:
        t = fn()
        R = run_exit(S, t, **TREND)[0]
        st = {sg: stats(S, t, R, sg) for sg in "ABN"}
        keep[name] = (t, R)
        rows.append({"Einstieg": name, **{SEGS[sg]: cell(st[sg], b0[sg]) for sg in "ABN"},
                     "besser A+B": (st["A"]["Ryr"] > b0["A"]["Ryr"]) and (st["B"]["Ryr"] > b0["B"]["Ryr"])})
    print("== Einstiege im Trend-Modus ==")
    print("Zellen: Trades/Woche, Trefferquote, E je Trade, R pro Jahr, groesster Drawdown, Ø Abstand Einstieg zur "
          "Eroeffnung in ATR, (R pro Jahr gegen bisher)")
    df = pd.DataFrame(rows)
    print(df.to_string(index=False), "\n")
    print(f"In beiden CFD-Stufen besser als bisher: {int(df['besser A+B'].sum())} von {len(df) - 1}\n")

    # Frueher Teil-Einstieg plus Nachkauf beim bisherigen Signal
    print("== Frueher Teil-Einstieg plus Nachkauf beim bisherigen Signal (zwei Positionen, je 1 R) ==")
    rows = [{"Variante": "bisher (eine Position)", **{SEGS[sg]: cell(b0[sg], b0[sg]) for sg in "ABN"}}]
    for g, t in ((0.1, 0.15), (0.2, 0.15), (0.2, 0.2), (0.3, 0.15)):
        e, Re = keep[f"luecke {g}/{t}"]
        early = (e.ext.values < 0.29)                                   # wirklich vor der 0,3-Schwelle
        ed = e[early]
        add = base.merge(ed[["di", "side"]], on=["di", "side"], how="inner").di
        both = pd.concat([ed, base[base.di.isin(add)], base[~base.di.isin(ed.di)]], ignore_index=True)
        RR = np.r_[Re[early], Rb[base.di.isin(add).values], Rb[~base.di.isin(ed.di).values]]
        st = {}
        for sg in "ABN":
            m = both.seg.values == sg
            r = RR[m]
            nd = S["ndays"][sg]
            daily = pd.Series(r).groupby(both.di.values[m]).sum().values
            eq = np.cumsum(daily)
            st[sg] = f"{len(r) / nd * 5:.1f}/W {r.sum() / nd * 252:+.0f}R/J DD{(eq - np.maximum.accumulate(eq)).min():.0f} ({r.sum() / nd * 252 - b0[sg]['Ryr']:+.0f})"
        rows.append({"Variante": f"frueh nach 'luecke {g}/{t}' + Nachkauf bei 0,3", **{SEGS[k]: v for k, v in st.items()}})
    print(pd.DataFrame(rows).to_string(index=False))
    print("(Drawdown hier auf Tagesbasis, weil an einem Tag zwei Positionen offen sein koennen)")


if __name__ == "__main__":
    main(sys.argv[1])
