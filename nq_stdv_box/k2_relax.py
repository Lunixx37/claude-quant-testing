"""K2 relaxations: which loosened criteria raise trade frequency without destroying the expectancy?"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import search as se                                  # noqa: E402
from search_events import EXITS, STOPS_R             # noqa: E402

SI, XI = STOPS_R.index("struct_min"), EXITS.index("mid")


def trades(ev, grp=("l35",), prior=True, mom="mom", nrec=10, maxord=3, minrisk=0.02, rel=0.0, xi=XI, si=SI):
    s = ev[ev.kind == "R"].sort_values(["di", "bar"]).reset_index(drop=True)
    m = s.grp.isin(grp).values & (s.reclaim_bars.values <= nrec) & (s.ord.values < maxord) & (s.rel.values >= rel)
    if prior:
        m &= s.prior_opp.values
    if mom:
        m &= s[mom].fillna(False).astype(bool).values
    r = s[f"o{si}_{xi}"].values
    m &= ~np.isnan(r) & (s[f"risk{si}"].values >= minrisk)
    t = s[m][["di", "day", "bar", "side", "level"]].copy()
    t["R"] = r[m]
    t["xbar"] = s[f"x{si}_{xi}"].values[m]
    t["risk_atr"] = s[f"risk{si}"].values[m]
    t["atr"] = s["atr"].values[m]
    return se.one_at_a_time(t)


VARIANTS = {
    "K2 Basis": {},
    "ohne 'vorher Gegenreaktion'": dict(prior=False),
    "Reclaim ≤ 20 Kerzen": dict(nrec=20),
    "Reclaim ≤ 30 Kerzen": dict(nrec=30),
    "bis 6 Touches je Level": dict(maxord=6),
    "Momentum: nur Bruch Vorkerze": dict(mom="mom_ext"),
    "Momentum: nur Kerzenfarbe": dict(mom="mom_body"),
    "Mindest-Stop 0,01 ATR": dict(minrisk=0.01),
    "K2-breit: ohne Vorreaktion, Reclaim ≤ 30, 6 Touches": dict(prior=False, nrec=30, maxord=6),
    "K2-breit + Momentum nur Bruch Vorkerze": dict(prior=False, nrec=30, maxord=6, mom="mom_ext"),
    "wie K2-breit, Level 3.5–4.5": dict(prior=False, nrec=30, maxord=6, grp=("l35", "c4")),
}

if __name__ == "__main__":
    evd = Path(sys.argv[1])
    evs = {n: pd.read_pickle(evd / f"events_{n}.pkl") for n in ("CFD", "NQ")}
    nds = {n: len(pd.read_pickle(evd / f"days_{n}.pkl")) for n in ("CFD", "NQ")}
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
    res = pd.DataFrame(rows)
    out = Path(__file__).parent / "results" / "k2"
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "k2_relaxations.csv", index=False)
    pd.set_option("display.width", 250)
    print(res.to_string(index=False))
