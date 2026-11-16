"""Stop x exit grid for the K2 entries (see k2_optimize.py)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import k2_optimize as ko     # noqa: E402

if __name__ == "__main__":
    d = Path(sys.argv[1])
    out = Path(__file__).parent / "results" / "k2_opt"
    out.mkdir(parents=True, exist_ok=True)
    evs = {n: pd.read_pickle(d / f"k2ev_{n}.pkl") for n in ("CFD", "NQ")}
    nds = {n: evs[n].attrs["nd"] for n in evs}
    for label, mo in (("K2 Basis (3 Touches)", 3), ("K2+ (6 Touches)", 6)):
        rows = []
        for si, sn in enumerate(ko.STOPS):
            for xn in ko.EXITS:
                r = {"Stop": sn, "Exit": xn}
                for n in ("CFD", "NQ"):
                    t, R = ko.take(evs[n], si, xn, maxord=mo)
                    st = ko.stat(t, R, nds[n])
                    for k in ("n", "Win %", "Ø R", "R/Wo", "t"):
                        r[f"{n} {k}"] = st.get(k)
                    r[f"{n} Stop Pkt"] = round((t[f"risk_{si}"] * t.atr).median(), 1)
                rows.append(r)
        g = pd.DataFrame(rows)
        g["min t"] = g[["CFD t", "NQ t"]].min(axis=1)
        g.to_csv(out / f"grid_{'base' if mo == 3 else 'plus'}.csv", index=False)
        pd.set_option("display.width", 250)
        print("\n#####", label)
        print("Ø R  (CFD / NQ) je Stop x Exit:")
        for ds in ("CFD", "NQ"):
            print(ds, "Ø R"); print(g.pivot(index="Stop", columns="Exit", values=f"{ds} Ø R").reindex(ko.STOPS)[ko.EXITS].to_string())
        print("Winrate NQ"); print(g.pivot(index="Stop", columns="Exit", values="NQ Win %").reindex(ko.STOPS)[ko.EXITS].to_string())
        print("R pro Woche NQ"); print(g.pivot(index="Stop", columns="Exit", values="NQ R/Wo").reindex(ko.STOPS)[ko.EXITS].to_string())
        print("R pro Woche CFD"); print(g.pivot(index="Stop", columns="Exit", values="CFD R/Wo").reindex(ko.STOPS)[ko.EXITS].to_string())
        print("Top 12 nach min(t CFD, t NQ):")
        print(g.sort_values("min t", ascending=False).head(12).to_string(index=False))
