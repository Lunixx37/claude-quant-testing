"""Final comparison of K2 variants (risk profile + 50k eval Monte Carlo)."""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import eval_sim as es        # noqa: E402
import k2_optimize as ko     # noqa: E402
import k2_select as ks       # noqa: E402

VARIANTS = {
    "V0  K2 Basis: Struktur-Stop, Ziel Mitte, 3 Touches": ("struct_min", "mid", [], 3),
    "V1  Struktur-Stop, Ziel Mitte, 4 Touches": ("struct_min", "mid", ["nur 1.–4. Touch"], 6),
    "V2  Struktur-Stop, Ziel gegenüberliegendes 2.0-Level, 4 Touches": ("struct_min", "opp2", ["nur 1.–4. Touch"], 6),
    "V3  Struktur-Stop, Ziel gegenüberliegendes 3.5-Level, 4 Touches": ("struct_min", "opp35", ["nur 1.–4. Touch"], 6),
    "V4  halber Struktur-Stop, Ziel 2.0 gegenüber, Box > 0,073 ATR": ("half_struct", "opp2", ["Box > 0,073 ATR"], 6),
    "V5  Stop fix 0,03 ATR, Ziel 2.0 gegenüber, nach 09:57": ("fix0.030", "opp2", ["nach 09:57"], 6),
    "V6  halber Struktur-Stop, Ziel 2.0 gegenüber, Box > 0,073 + Reclaim > 2 Kerzen": ("half_struct", "opp2", ["Box > 0,073 ATR", "Reclaim nach > 2 Kerzen"], 6),
}


def trades(ev, sn, xn, names, maxord):
    m = np.ones(len(ev), bool)
    for n in names:
        m &= ks.FILTERS[n](ev)
    t, r = ko.take(ev, ko.STOPS.index(sn), xn, mask=m, maxord=maxord)
    t = t[["di", "day", "bar", "side"]].copy()
    t["R"] = r
    return t


if __name__ == "__main__":
    d = Path(sys.argv[1])
    out = Path(__file__).parent / "results" / "k2_opt"
    E = {k: pd.read_pickle(d / f"k2ev_{k}.pkl") for k in ("CFD", "NQ")}
    nd = {k: E[k].attrs["nd"] for k in E}
    es.HORIZON, es.NSIM = 250, 10_000
    rng = np.random.default_rng(21)
    prof, sim = [], []
    for name, (sn, xn, fl, mo) in VARIANTS.items():
        mats = []
        for ds in ("CFD", "NQ"):
            t = trades(E[ds], sn, xn, fl, mo)
            mats.append(es.day_matrix(t, nd[ds]))
            eq = t.R.cumsum()
            streak = max((len(list(g)) for k, g in itertools.groupby(t.R <= 0) if k), default=0)
            dd = np.zeros(nd[ds]); np.add.at(dd, t.di.values, t.R.values)
            yr = t.groupby(t.day.dt.year).R.sum()
            prof.append({"Variante": name, "Daten": ds, "Trades/Wo": round(len(t) / nd[ds] * 5, 2),
                         "Win %": round((t.R > 0).mean() * 100, 1), "Ø Gewinner R": round(t.R[t.R > 0].mean(), 2),
                         "Ø R": round(t.R.mean(), 3), "R/Woche": round(t.R.sum() / nd[ds] * 5, 3),
                         "t": round(dd.mean() / dd.std(ddof=1) * np.sqrt(nd[ds]), 2),
                         "Max DD R": round((eq - eq.cummax()).min(), 1), "längste Verlustserie": streak,
                         "Jahre positiv": f"{(yr > 0).sum()}/{len(yr)}"})
        k = max(m.shape[1] for m in mats)
        M = np.vstack([np.pad(m, ((0, 0), (0, k - m.shape[1])), constant_values=np.nan) for m in mats])
        mr = np.nanmean(M)
        for edge, shift in (("wie Backtest", 0.0), ("halbe Kante", mr / 2), ("keine Kante", mr)):
            for rule in "AB":
                for rp in [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75]:
                    sim.append({"Variante": name, "Kante": edge, "Regel": rule, "Risiko %": rp,
                                **es.simulate(M - shift, rp / 100 * 50_000, rule, rng)})
    P = pd.DataFrame(prof)
    P.to_csv(out / "variant_profiles.csv", index=False)
    Sm = pd.DataFrame(sim)
    Sm.to_csv(out / "variant_eval_sim.csv", index=False)
    pd.set_option("display.width", 300); pd.set_option("display.max_colwidth", 80)
    print(P.to_string(index=False))
    best = Sm.loc[Sm.groupby(["Variante", "Kante", "Regel"])["Pass %"].idxmax()]
    piv = best.pivot(index="Variante", columns=["Regel", "Kante"], values="Pass %")
    print("\nBeste Bestehensquote je Variante (Risiko jeweils optimiert):"); print(piv.to_string())
    b = best[best.Kante == "wie Backtest"].pivot(index="Variante", columns="Regel", values=["Risiko %", "Median Tage bis Pass"])
    print(b.to_string())
