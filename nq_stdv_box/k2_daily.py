"""K2 variants with at most ONE trade per day, plus a filter on how far price already ran beyond the
4.x stdv levels before the entry (ext_k = furthest excursion on the trade's side since 08:30, in stdv units)."""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import eval_sim as es        # noqa: E402
import k2_optimize as ko     # noqa: E402
import k2_select as ks       # noqa: E402
import k2_variants as kv     # noqa: E402

OUT = Path(__file__).parent / "results" / "k2_daily"
THRESH = [4.0, 4.25, 4.5, 4.75, 5.0, 5.5, 6.0, 7.0, 9.0, np.inf]


def trades(ev, sn, xn, names, maxord, max_per_day=None, max_ext=np.inf):
    m = np.ones(len(ev), bool)
    for n in names:
        m &= ks.FILTERS[n](ev)
    m &= ev.ext_k.values <= max_ext
    t, r = ko.take(ev, ko.STOPS.index(sn), xn, mask=m, maxord=maxord, max_per_day=max_per_day)
    t = t[["di", "day", "bar", "side", "ext_k"]].copy()
    t["R"] = r
    return t


def prof(t, nd):
    if len(t) == 0:
        return {"Trades": 0}
    d = np.zeros(nd)
    np.add.at(d, t.di.values, t.R.values)
    eq = t.R.cumsum()
    streak = max((len(list(g)) for k, g in itertools.groupby(t.R <= 0) if k), default=0)
    return {"Trades": len(t), "Tr/Wo": round(len(t) / nd * 5, 2), "Win %": round((t.R > 0).mean() * 100, 1),
            "Ø Gewinner": round(t.R[t.R > 0].mean(), 2), "Ø R": round(t.R.mean(), 3), "R/Wo": round(t.R.sum() / nd * 5, 3),
            "t": round(d.mean() / d.std(ddof=1) * np.sqrt(nd), 2), "MaxDD": round((eq - eq.cummax()).min(), 1), "Serie": streak}


if __name__ == "__main__":
    d = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 260); pd.set_option("display.max_colwidth", 60)
    E = {k: pd.read_pickle(d / f"k2ev_{k}.pkl") for k in ("CFD", "NQ", "CFD_fake+0.07", "CFD_fake-0.07", "NQ_fake+0.07", "NQ_fake-0.07")}
    nd = {"CFD": E["CFD"].attrs["nd"], "NQ": E["NQ"].attrs["nd"]}

    # 1) unlimited vs max 1 trade per day
    rows = []
    for name, (sn, xn, fl, mo) in kv.VARIANTS.items():
        for lab, mpd in (("unbegrenzt", None), ("max. 1 pro Tag", 1)):
            r = {"Variante": name[:2], "Trades/Tag": lab}
            for ds in ("CFD", "NQ"):
                p = prof(trades(E[ds], sn, xn, fl, mo, mpd), nd[ds])
                for k, v in p.items():
                    r[f"{ds} {k}"] = v
            rows.append(r)
    R1 = pd.DataFrame(rows)
    R1.to_csv(OUT / "one_per_day.csv", index=False)
    print("=== 1) unbegrenzt vs. max. 1 Trade pro Tag ==="); print(R1.to_string(index=False))

    # 2) how far had price run? distribution + bucket results (max 1/day is applied AFTER the filter)
    print("\n=== 2) Ausdehnung vor dem Entry (ext_k) — Verteilung der K2-Einstiege ===")
    for ds in ("CFD", "NQ"):
        print(ds, E[ds].ext_k.quantile([.1, .25, .5, .75, .9]).round(2).to_dict())
    rows = []
    for vid in ("V0", "V2", "V3"):
        name = [n for n in kv.VARIANTS if n.startswith(vid)][0]
        sn, xn, fl, mo = kv.VARIANTS[name]
        for th in THRESH:
            r = {"Variante": vid, "max. Ausdehnung (Stdv)": "ohne Filter" if np.isinf(th) else th}
            for ds in ("CFD", "NQ"):
                p = prof(trades(E[ds], sn, xn, fl, mo, 1, th), nd[ds])
                fk = pd.concat([trades(E[f"{ds}_fake{s}"], sn, xn, fl, mo, 1, th) for s in ("+0.07", "-0.07")])
                for k in ("Tr/Wo", "Win %", "Ø R", "R/Wo", "t", "MaxDD", "Serie"):
                    r[f"{ds} {k}"] = p.get(k)
                r[f"{ds} Fake Ø R"] = round(fk.R.mean(), 3) if len(fk) else np.nan
            rows.append(r)
    R2 = pd.DataFrame(rows)
    R2.to_csv(OUT / "extension_filter.csv", index=False)
    print(R2.to_string(index=False))

    # 3) buckets of ext_k (all K2+ entries, V2 exit, no daily cap) to see where the edge sits
    rows = []
    edges = [3.5, 3.75, 4.0, 4.25, 4.5, 5.0, 6.0, np.inf]
    for ds in ("CFD", "NQ"):
        ev = E[ds]
        col = f"o_{ko.STOPS.index('struct_min')}_opp2"
        for a, b in zip(edges[:-1], edges[1:]):
            x = ev[(ev.ext_k > a) & (ev.ext_k <= b) & (ev.ord <= 3)][col].dropna()
            rows.append({"Daten": ds, "Ausdehnung (Stdv)": f"{a}–{b}", "n": len(x), "Win %": round((x > 0).mean() * 100, 1) if len(x) else np.nan,
                         "Ø R": round(x.mean(), 3) if len(x) else np.nan})
    R3 = pd.DataFrame(rows)
    R3.to_csv(OUT / "extension_buckets.csv", index=False)
    print("\n=== 3) Ergebnis nach Ausdehnung (Einstieg + Ziel wie V2, alle Einstiege) ===")
    print(R3.pivot(index="Ausdehnung (Stdv)", columns="Daten", values=["n", "Win %", "Ø R"]).reindex([f"{a}–{b}" for a, b in zip(edges[:-1], edges[1:])]).to_string())


def band_study(d):
    """Lower + upper bound on the excursion, 1 trade per day, with eval Monte Carlo."""
    E = {k: pd.read_pickle(d / f"k2ev_{k}.pkl") for k in ("CFD", "NQ", "CFD_fake+0.07", "CFD_fake-0.07", "NQ_fake+0.07", "NQ_fake-0.07")}
    nd = {"CFD": E["CFD"].attrs["nd"], "NQ": E["NQ"].attrs["nd"]}
    es.HORIZON, es.NSIM = 250, 10_000
    rng = np.random.default_rng(31)
    cases = [("V2 unbegrenzt (bisher)", "V2", None, 0.0, np.inf), ("V2, 1 pro Tag", "V2", 1, 0.0, np.inf),
             ("V2, 1 pro Tag, Auslauf ≤ 5,0", "V2", 1, 0.0, 5.0), ("V2, 1 pro Tag, Auslauf ≥ 3,75", "V2", 1, 3.75, np.inf),
             ("V2, 1 pro Tag, Auslauf 3,75–5,0", "V2", 1, 3.75, 5.0), ("V2, 1 pro Tag, Auslauf 3,75–6,0", "V2", 1, 3.75, 6.0),
             ("V2 unbegrenzt, Auslauf 3,75–5,0", "V2", None, 3.75, 5.0),
             ("V3, 1 pro Tag", "V3", 1, 0.0, np.inf), ("V3, 1 pro Tag, Auslauf 3,75–5,0", "V3", 1, 3.75, 5.0),
             ("V0, 1 pro Tag", "V0", 1, 0.0, np.inf), ("V0, 1 pro Tag, Auslauf 3,75–5,0", "V0", 1, 3.75, 5.0)]
    rows = []
    for label, vid, mpd, lo, hi in cases:
        name = [n for n in kv.VARIANTS if n.startswith(vid)][0]
        sn, xn, fl, mo = kv.VARIANTS[name]
        r = {"Fall": label}
        mats = []
        for ds in ("CFD", "NQ"):
            def tr(ev):
                m = np.ones(len(ev), bool)
                for n in fl:
                    m &= ks.FILTERS[n](ev)
                m &= (ev.ext_k.values >= lo) & (ev.ext_k.values <= hi)
                t, rr = ko.take(ev, ko.STOPS.index(sn), xn, mask=m, maxord=mo, max_per_day=mpd)
                t = t[["di", "day", "bar", "side"]].copy(); t["R"] = rr
                return t
            t = tr(E[ds])
            fk = pd.concat([tr(E[f"{ds}_fake{s}"]) for s in ("+0.07", "-0.07")])
            p = prof(t, nd[ds])
            for k in ("Tr/Wo", "Win %", "Ø Gewinner", "Ø R", "R/Wo", "t", "MaxDD", "Serie"):
                r[f"{ds} {k}"] = p.get(k)
            r[f"{ds} Fake Ø R"] = round(fk.R.mean(), 3) if len(fk) else np.nan
            yr = t.groupby(t.day.dt.year).R.sum()
            r[f"{ds} Jahre +"] = f"{(yr > 0).sum()}/{len(yr)}"
            mats.append(es.day_matrix(t, nd[ds]))
            t.to_csv(OUT / f"trades_{label.replace(' ', '_').replace(',', '').replace('≤', 'le').replace('≥', 'ge')}_{ds}.csv", index=False)
        k = max(mm.shape[1] for mm in mats)
        M = np.vstack([np.pad(mm, ((0, 0), (0, k - mm.shape[1])), constant_values=np.nan) for mm in mats])
        mr = np.nanmean(M)
        for rule in "AB":
            best = max(({"rp": rp, **es.simulate(M, rp / 100 * 50_000, rule, rng)} for rp in (0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 1.0)), key=lambda x: x["Pass %"])
            none = max((es.simulate(M - mr, rp / 100 * 50_000, rule, rng)["Pass %"] for rp in (0.3, 0.5, 0.75)))
            r[f"Eval {rule} %"], r[f"Eval {rule} Risiko %"], r[f"Eval {rule} Tage"], r[f"Eval {rule} ohne Kante %"] = best["Pass %"], best["rp"], best["Median Tage bis Pass"], none
        rows.append(r)
    R = pd.DataFrame(rows)
    R.to_csv(OUT / "band_filter.csv", index=False)
    print("\n=== 4) Unter- und Obergrenze für den Auslauf ===")
    c1 = ["Fall"] + [c for c in R.columns if c.startswith("CFD")]
    c2 = ["Fall"] + [c for c in R.columns if c.startswith("NQ")]
    c3 = ["Fall"] + [c for c in R.columns if c.startswith("Eval")]
    print(R[c1].to_string(index=False)); print(R[c2].to_string(index=False)); print(R[c3].to_string(index=False))


if __name__ == "__main__":
    band_study(Path(sys.argv[1]))
