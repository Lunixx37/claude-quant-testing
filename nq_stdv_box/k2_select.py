"""Greedy filter selection for aggressive K2 variants on CFD 2016-2022 only, then one check on NQ 2023-2025
and on fake levels (levels shifted by +/-0.07 ATR)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import k2_optimize as ko     # noqa: E402

FILTERS = {
    "Box > 0,073 ATR": lambda e: e.rel.values > 0.0728,
    "Box > 0,156 ATR": lambda e: e.rel.values > 0.156,
    "nach 09:57": lambda e: e.bar.values > 87,
    "nach 11:28": lambda e: e.bar.values > 178,
    "nur 1.–2. Touch": lambda e: e.ord.values <= 1,
    "nur 1.–4. Touch": lambda e: e.ord.values <= 3,
    "Reclaim nach > 2 Kerzen": lambda e: e.reclaim_bars.values > 2,
    "VWAP gedehnt (z ≤ −1)": lambda e: e.z.values <= -1.02,
    "Sweep ≤ 0,065 ATR tief": lambda e: e.depth.values <= 0.0647,
    "in Box-Richtung": lambda e: e.with_dir.values,
    "keine ICT-Zone": lambda e: ~e.ict.values,
    "Volumen ≤ 1,14 × Schnitt": lambda e: e.vol_ratio.fillna(1).values <= 1.14,
}
COMBOS = [("struct_min", "mid"), ("struct_min", "opp2"), ("struct_min", "opp35"), ("half_struct", "opp2"),
          ("half_struct", "opp35"), ("fix0.030", "opp2"), ("fix0.030", "opp35"), ("fix0.020", "opp2")]


def evaluate(ev, nd, sn, xn, names):
    m = np.ones(len(ev), bool)
    for n in names:
        m &= FILTERS[n](ev)
    t, r = ko.take(ev, ko.STOPS.index(sn), xn, mask=m)
    return ko.stat(t, r, nd), t, r


def greedy(ev, nd, sn, xn, min_tpw):
    chosen = []
    best, _, _ = evaluate(ev, nd, sn, xn, chosen)
    while True:
        cand = None
        for f in FILTERS:
            if f in chosen:
                continue
            st, _, _ = evaluate(ev, nd, sn, xn, chosen + [f])
            if st.get("n", 0) == 0 or st["Tr/Wo"] < min_tpw:
                continue
            if st["t"] > best["t"] + 0.15 and (cand is None or st["t"] > cand[1]["t"]):
                cand = (f, st)
        if cand is None:
            return chosen, best
        chosen.append(cand[0])
        best = cand[1]


if __name__ == "__main__":
    d = Path(sys.argv[1])
    out = Path(__file__).parent / "results" / "k2_opt"
    E = {k: pd.read_pickle(d / f"k2ev_{k}.pkl") for k in ("CFD", "NQ", "CFD_fake+0.07", "CFD_fake-0.07", "NQ_fake+0.07", "NQ_fake-0.07")}
    nd = {"CFD": E["CFD"].attrs["nd"], "NQ": E["NQ"].attrs["nd"]}
    rows = []
    for min_tpw in (2.0, 1.0):
        for sn, xn in COMBOS:
            chosen, c = greedy(E["CFD"], nd["CFD"], sn, xn, min_tpw)
            q, tq, rq = evaluate(E["NQ"], nd["NQ"], sn, xn, chosen)
            fk = {}
            for ds in ("CFD", "NQ"):
                vals = [evaluate(E[f"{ds}_fake{s}"], nd[ds], sn, xn, chosen)[0].get("Ø R", np.nan) for s in ("+0.07", "-0.07")]
                fk[ds] = round(float(np.nanmean(vals)), 3)
            w = rq[rq > 0]
            rows.append({"min Trades/Wo (CFD)": min_tpw, "Stop": sn, "Ziel": xn, "Filter (auf CFD gewählt)": " + ".join(chosen) or "–",
                         "CFD Tr/Wo": c["Tr/Wo"], "CFD Win %": c["Win %"], "CFD Ø R": c["Ø R"], "CFD R/Wo": c["R/Wo"], "CFD t": c["t"],
                         "NQ Tr/Wo": q.get("Tr/Wo"), "NQ Win %": q.get("Win %"), "NQ Ø R": q.get("Ø R"), "NQ R/Wo": q.get("R/Wo"), "NQ t": q.get("t"),
                         "NQ Ø Gewinner R": round(w.mean(), 2) if len(w) else np.nan,
                         "NQ Stop Pkt": round((tq[f"risk_{ko.STOPS.index(sn)}"] * tq.atr).median(), 1) if len(tq) else np.nan,
                         "Fake Ø R CFD": fk["CFD"], "Fake Ø R NQ": fk["NQ"]})
    R = pd.DataFrame(rows)
    R.to_csv(out / "selected_variants.csv", index=False)
    pd.set_option("display.width", 320)
    pd.set_option("display.max_colwidth", 90)
    print(R.to_string(index=False))
