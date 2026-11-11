"""K1 (limit at stdv level inside an ICT zone, 11:00-13:30 ET, stop 0.06 ATR, target box mid):
details, relaxations and 50k-eval Monte Carlo (also K1 + K2+ combined)."""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import eval_sim as es                                # noqa: E402
import k2_relax as kr                                # noqa: E402
import search as se                                  # noqa: E402
from search_events import EXITS, STOPS_T             # noqa: E402

OUT = Path(__file__).parent / "results" / "k1"
STDV = ("c2", "l35", "c4")


def trades(ev, grp=STDV, t0=150, t1=300, ict=True, maxord=3, stop="0.06atr", exit_="mid", rel=0.0, dedupe=True):
    """t0/t1 = session bar index (0 = 08:30): 150 = 11:00, 300 = 13:30."""
    si, xi = STOPS_T.index(stop), EXITS.index(exit_)
    s = ev[ev.kind == "T"].sort_values(["di", "bar"]).reset_index(drop=True)
    m = s.grp.isin(grp).values & (s.bar.values >= t0) & (s.bar.values < t1) & (s.ord.values < maxord) & (s.rel.values >= rel)
    if ict:
        m &= s.ict.values
    r = s[f"o{si}_{xi}"].values
    m &= ~np.isnan(r)
    t = s[m][["di", "day", "bar", "side", "level"]].copy()
    t["R"] = r[m]
    t["xbar"] = s[f"x{si}_{xi}"].values[m]
    t["risk_atr"] = s[f"risk{si}"].values[m]
    t["atr"] = s["atr"].values[m]
    t["rel"] = s["rel"].values[m]
    return se.one_at_a_time(t) if dedupe else t


VARIANTS = {
    "K1 Basis (11:00–13:30, ICT, 3 Touches)": {},
    "bis 6 Touches": dict(maxord=6),
    "Zeit 10:30–14:00": dict(t0=120, t1=330),
    "Zeit 10:00–14:30": dict(t0=90, t1=360),
    "Zeit 09:30–16:00": dict(t0=60, t1=450),
    "ganzer Tag ab 08:30": dict(t0=0, t1=450),
    "ohne ICT-Zone": dict(ict=False),
    "ohne ICT, Zeit 10:30–14:00": dict(ict=False, t0=120, t1=330),
    "nur Level 3.5–4.5": dict(grp=("l35", "c4")),
    "nur Cluster 2–2.5": dict(grp=("c2",)),
    "Stop 0,03 ATR": dict(stop="0.03atr"),
    "Box ≥ 0,1 ATR": dict(rel=0.1),
    "K1+ : 10:30–14:00, 6 Touches": dict(t0=120, t1=330, maxord=6),
    "K1-breit: 10:00–14:30, 6 Touches": dict(t0=90, t1=360, maxord=6),
}


def describe(t, nd, label):
    w, l = t[t.R > 0], t[t.R <= 0]
    eq = t.R.cumsum()
    d = se.daily_series(t, nd)
    pts = t.risk_atr * t.atr
    streak = max((len(list(g)) for k, g in itertools.groupby(t.R <= 0) if k), default=0)
    return {"Daten": label, "Tage": nd, "Trades": len(t), "Trades/Woche": round(len(t) / nd * 5, 2),
            "Long/Short": f"{(t.side == 1).sum()}/{(t.side == -1).sum()}", "Winrate %": round(len(w) / len(t) * 100, 1),
            "Ø Gewinner R": round(w.R.mean(), 2), "Ø Verlierer R": round(l.R.mean(), 2),
            "Ø R": round(t.R.mean(), 3), "Σ R": round(t.R.sum(), 1), "PF": round(w.R.sum() / -l.R.sum(), 2),
            "t (Tage)": round(d.mean() / d.std(ddof=1) * np.sqrt(nd), 2),
            "Max DD R": round((eq - eq.cummax()).min(), 1), "längste Verlustserie": streak,
            "Stop Median Pkt": round(pts.median(), 1), "RR geplant Median": round((np.abs(t.level_k) * t.rel / 2 / t.risk_atr).median(), 2),
            "Long Ø R": round(t[t.side == 1].R.mean(), 3), "Short Ø R": round(t[t.side == -1].R.mean(), 3)}


if __name__ == "__main__":
    evd = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    evs = {n: pd.read_pickle(evd / f"events_{n}.pkl") for n in ("CFD", "NQ")}
    nds = {n: len(pd.read_pickle(evd / f"days_{n}.pkl")) for n in ("CFD", "NQ")}
    pd.set_option("display.width", 260)

    # ---- details of the base strategy
    det, yearly = [], []
    for n, lab in (("NQ", "NQ 2023–2025"), ("CFD", "CFD 2016–2022")):
        t = trades(evs[n])
        t["level_k"] = t.level.astype(float)
        det.append(describe(t, nds[n], lab))
        t.to_csv(OUT / f"trades_K1_{n}.csv", index=False)
        y = t.groupby(t.day.dt.year).R.agg(Trades="size", SummeR="sum").round(1)
        y["Daten"] = n
        yearly.append(y)
        print(lab, "R-Verteilung:", pd.cut(t.R, [-9, -0.5, 0, 1, 2, 4, 99]).value_counts(sort=False).to_dict())
        print(lab, "nach Level:", t.groupby(t.level_k.abs()).R.agg(["size", "mean"]).round(3).T.to_dict())
    det = pd.DataFrame(det).set_index("Daten").T
    det.to_csv(OUT / "k1_details.csv")
    print(det.to_string())
    yearly = pd.concat(yearly)
    yearly.to_csv(OUT / "k1_yearly.csv")
    print(yearly.T.to_string())

    # ---- relaxations
    rows = []
    for name, kw in VARIANTS.items():
        r = {"Variante": name}
        for n in ("CFD", "NQ"):
            t = trades(evs[n], **kw)
            d = se.daily_series(t, nds[n])
            r[f"{n} Trades/Wo"] = round(len(t) / nds[n] * 5, 2)
            r[f"{n} Win %"] = round((t.R > 0).mean() * 100, 1)
            r[f"{n} Ø R"] = round(t.R.mean(), 3)
            r[f"{n} R/Woche"] = round(t.R.sum() / nds[n] * 5, 3)
            r[f"{n} t"] = round(d.mean() / d.std(ddof=1) * np.sqrt(nds[n]), 2)
        rows.append(r)
    rel = pd.DataFrame(rows)
    rel.to_csv(OUT / "k1_relaxations.csv", index=False)
    print(rel.to_string(index=False))

    # ---- eval Monte Carlo
    es.HORIZON, es.NSIM = 250, 10_000
    rng = np.random.default_rng(11)
    sets = {"K1 Basis": lambda ev: trades(ev),
            "K1+ (10:30–14:00, 6 Touches)": lambda ev: trades(ev, t0=120, t1=330, maxord=6),
            "K1 + K2+ kombiniert": lambda ev: pd.concat([trades(ev), kr.trades(ev, maxord=6)]).sort_values(["di", "bar"])}
    rows = []
    for vname, fn in sets.items():
        mats = [es.day_matrix(fn(evs[n]), nds[n]) for n in ("CFD", "NQ")]
        k = max(m.shape[1] for m in mats)
        M = np.vstack([np.pad(m, ((0, 0), (0, k - m.shape[1])), constant_values=np.nan) for m in mats])
        mr = np.nanmean(M)
        print(f"{vname}: Ø R gepoolt {mr:.3f}, Trades/Woche {np.isfinite(M).sum() / len(M) * 5:.2f}", flush=True)
        for edge, shift in (("wie Backtest", 0.0), ("halbe Kante", mr / 2), ("keine Kante", mr)):
            for rule in "AB":
                for rp in [0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 1.0]:
                    rows.append({"Variante": vname, "Kante": edge, "Regel": rule, "Risiko %": rp,
                                 **es.simulate(M - shift, rp / 100 * 50_000, rule, rng)})
    R = pd.DataFrame(rows)
    R.to_csv(OUT / "eval_simulation_250d.csv", index=False)
    for v in R.Variante.unique():
        for rule in "AB":
            g = R[(R.Variante == v) & (R.Regel == rule)]
            print(v, "Regel", rule)
            print(g.pivot(index="Risiko %", columns="Kante", values=["Pass %", "Median Tage bis Pass"]).to_string())
