"""
Monte-Carlo simulation of a 50k prop-firm evaluation with the K2 trade distribution.

Days (including days without a trade) are resampled with replacement from the backtest (CFD 2016-2022 +
NQ 2023-2025), trades keep their order inside a day. P&L per trade = R x risk$ (risk$ = risk % x 50,000).

Rule sets (ASSUMPTIONS - adjust to your firm):
  A  target +3,000 | max loss 2,000 trailing on END-OF-DAY balance, stops trailing at the start balance |
     consistency: best day <= 50 % of total profit when passing            (Topstep-like 50K)
  B  target +3,000 | 2,500 trailing on the equity peak (here: after each closed trade, real rule uses
     unrealised peaks -> slightly optimistic), stops at start + 100 | no consistency rule   (Apex-like 50K)

Edge scenarios: backtest as is | half the backtest edge | no edge (mean R shifted to 0).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import k2_relax as kr      # noqa: E402

START, TARGET = 50_000.0, 3_000.0
HORIZON, NSIM = 120, 20_000
RISKS = [0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 1.0, 1.25, 1.5, 2.0]


def day_matrix(t, nd):
    """[nd, maxk] matrix of trade R per day (nan padded)."""
    g = t.groupby("di").R.apply(list)
    k = max(len(x) for x in g)
    M = np.full((nd, k), np.nan)
    for di, lst in g.items():
        M[di, :len(lst)] = lst
    return M


def simulate(M, risk_usd, rule, rng):
    nd, k = M.shape
    idx = rng.integers(0, nd, (NSIM, HORIZON))
    bal = np.full(NSIM, START)
    alive = np.ones(NSIM, bool)
    passed = np.zeros(NSIM, bool)
    day_pass = np.full(NSIM, -1)
    best_day = np.zeros(NSIM)
    if rule == "A":
        floor = np.full(NSIM, START - 2000.0)
    else:
        peak = np.full(NSIM, START)
        floor = np.full(NSIM, START - 2500.0)
    for d in range(HORIZON):
        day_start = bal.copy()
        for j in range(k):
            r = M[idx[:, d], j]
            act = alive & ~np.isnan(r)
            bal = np.where(act, bal + np.nan_to_num(r) * risk_usd, bal)
            if rule == "B":
                peak = np.maximum(peak, bal)
                floor = np.minimum(START + 100.0, np.maximum(floor, peak - 2500.0))
            bust = alive & (bal <= floor)
            alive &= ~bust
            if rule == "B":
                ok = alive & (bal - START >= TARGET)
                passed |= ok
                day_pass = np.where(ok & (day_pass < 0), d + 1, day_pass)
                alive &= ~ok
        best_day = np.maximum(best_day, bal - day_start)
        if rule == "A":
            prof = bal - START
            ok = alive & (prof >= TARGET) & (best_day <= 0.5 * prof)
            passed |= ok
            day_pass = np.where(ok & (day_pass < 0), d + 1, day_pass)
            alive &= ~ok
            floor = np.where(alive, np.minimum(START, np.maximum(floor, bal - 2000.0)), floor)
    busted = ~passed & ~alive
    dp = day_pass[passed]
    return {"Pass %": round(passed.mean() * 100, 1), "Bust %": round(busted.mean() * 100, 1),
            "offen nach 120 T %": round((alive & ~passed).mean() * 100, 1),
            "Pass ≤30 T %": round((passed & (day_pass <= 30)).mean() * 100, 1),
            "Pass ≤60 T %": round((passed & (day_pass <= 60)).mean() * 100, 1),
            "Median Tage bis Pass": int(np.median(dp)) if len(dp) else np.nan}


if __name__ == "__main__":
    evd = Path(sys.argv[1])
    out = Path(__file__).parent / "results" / "k2"
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    variants = {"K2 Basis": {}, "K2+ (6 Touches)": dict(maxord=6),
                "K2-breit": dict(prior=False, nrec=30, maxord=6)}
    rows = []
    for vname, kw in variants.items():
        mats, info = [], []
        for n in ("CFD", "NQ"):
            ev = pd.read_pickle(evd / f"events_{n}.pkl")
            nd = len(pd.read_pickle(evd / f"days_{n}.pkl"))
            t = kr.trades(ev, **kw)
            mats.append(day_matrix(t, nd))
            if n == "NQ":
                t.to_csv(out / f"trades_{vname.split()[0]}_NQ.csv", index=False)
                pts = t.risk_atr * t.atr
                info = [len(t) / nd * 5, t.R.mean(), pts.median(), pts.mean()]
        k = max(m.shape[1] for m in mats)
        M = np.vstack([np.pad(m, ((0, 0), (0, k - m.shape[1])), constant_values=np.nan) for m in mats])
        mean_r = np.nanmean(M)
        print(f"{vname}: Ø R gepoolt {mean_r:.3f}, Trades/Tag {np.isfinite(M).sum() / len(M):.2f}, "
              f"NQ: {info[0]:.2f} Trades/Woche, Stop Median {info[2]:.1f} Pkt", flush=True)
        for edge, shift in (("wie Backtest", 0.0), ("halbe Kante", mean_r / 2), ("keine Kante", mean_r)):
            for rule in ("A", "B"):
                for rp in RISKS:
                    res = simulate(M - shift, rp / 100 * START, rule, rng)
                    rows.append({"Variante": vname, "Kante": edge, "Regel": rule, "Risiko %": rp,
                                 "Risiko $": int(rp / 100 * START), **res})
    R = pd.DataFrame(rows)
    R.to_csv(out / "eval_simulation.csv", index=False)
    pd.set_option("display.width", 250)
    for (v, e, r), g in R.groupby(["Variante", "Kante", "Regel"], sort=False):
        print(f"\n### {v} | {e} | Regel {r}")
        print(g.drop(columns=["Variante", "Kante", "Regel"]).to_string(index=False))
