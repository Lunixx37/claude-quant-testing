"""Which entry criteria make the aggressive (tight-stop) K2 variants valid?
Buckets are defined on CFD 2016-2022 (discovery) and then applied unchanged to NQ 2023-2025 (check)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import k2_optimize as ko     # noqa: E402

FEATS = ["depth", "reclaim_bars", "body", "close_dist", "vol_ratio", "rel", "z", "bar", "ord", "n_same", "n_opp", "rr_mid_struct"]
BOOLS = ["with_dir", "ict"]
COMBOS = [("struct_min", "mid"), ("struct_min", "opp2"), ("half_struct", "opp2"), ("fix0.030", "opp2"), ("fix0.020", "opp2"), ("fix0.015", "opp2")]

if __name__ == "__main__":
    d = Path(sys.argv[1])
    out = Path(__file__).parent / "results" / "k2_opt"
    cfd, nq = pd.read_pickle(d / "k2ev_CFD.pkl"), pd.read_pickle(d / "k2ev_NQ.pkl")
    rows = []
    for f in FEATS + BOOLS:
        if f in BOOLS:
            edges, labels = None, ["nein", "ja"]
            bc, bn = cfd[f].astype(int).values, nq[f].astype(int).values
        else:
            q = cfd[f].quantile([1 / 3, 2 / 3]).values
            if q[0] == q[1]:
                q = np.array([q[0], q[0] + 1e-9])
            edges = q
            labels = [f"≤{q[0]:.3g}", f"{q[0]:.3g}–{q[1]:.3g}", f">{q[1]:.3g}"]
            bc, bn = np.searchsorted(q, cfd[f].values, side="left"), np.searchsorted(q, nq[f].values, side="left")
        for sn, xn in COMBOS:
            col = f"o_{ko.STOPS.index(sn)}_{xn}"
            for b, lab in enumerate(labels):
                rc, rn = cfd[col].values[bc == b], nq[col].values[bn == b]
                rc, rn = rc[~np.isnan(rc)], rn[~np.isnan(rn)]
                rows.append({"Merkmal": f, "Bucket": lab, "Stop": sn, "Exit": xn,
                             "CFD n": len(rc), "CFD Ø R": round(rc.mean(), 3) if len(rc) else np.nan,
                             "CFD Win %": round((rc > 0).mean() * 100, 1) if len(rc) else np.nan,
                             "NQ n": len(rn), "NQ Ø R": round(rn.mean(), 3) if len(rn) else np.nan,
                             "NQ Win %": round((rn > 0).mean() * 100, 1) if len(rn) else np.nan})
    R = pd.DataFrame(rows)
    R.to_csv(out / "filter_buckets.csv", index=False)
    pd.set_option("display.width", 250)
    for (sn, xn) in COMBOS:
        g = R[(R.Stop == sn) & (R.Exit == xn)].drop(columns=["Stop", "Exit"])
        print(f"\n### Stop {sn} | Exit {xn}")
        print(g.to_string(index=False))
