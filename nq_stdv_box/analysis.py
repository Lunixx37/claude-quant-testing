"""Deeper analysis: box-size dependence, level 'reaction' vs. fake levels, filtered fade grid."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import stdv_box as m  # noqa: E402

OUT = Path(__file__).parent / "results"
FINE = np.round(np.arange(1.0, 6.01, 0.05), 2)


def reaction_curve(st, step=0.5):
    """P(price runs another `step` Stdv beyond k | k was reached) for a fine grid of k."""
    ext = pd.concat([st.ext_up, st.ext_dn]).values
    rows = []
    for k in FINE:
        n = (ext >= k).sum()
        rows.append({"k": k, "n": n, "pass %": (ext >= k + step).sum() / n * 100 if n else np.nan})
    return pd.DataFrame(rows).set_index("k")


def level_vs_fake(curve, levels=m.STDV_LEVELS):
    """Compare pass-through rate at real levels with the local neighbourhood (±0.15..0.35)."""
    rows = []
    for k in levels:
        if k not in curve.index:
            continue
        neigh = [round(k + d, 2) for d in (-0.35, -0.3, -0.25, -0.2, -0.15, 0.15, 0.2, 0.25, 0.3, 0.35)]
        neigh = [x for x in neigh if x in curve.index and min(abs(x - l) for l in levels) >= 0.1]
        rows.append({"Level": k, "Durchbruch % am Level": round(curve.loc[k, "pass %"], 1),
                     "Durchbruch % Nachbar-(Fake-)Level": round(curve.loc[neigh, "pass %"].mean(), 1)})
    return pd.DataFrame(rows).set_index("Level")


def main():
    data = {"NQ_2023_2025": m.load_nq().loc["2023-01-01":],
            "CFD_2016_2022": m.load_cfd().loc["2016-11-16":"2022-12-31"]}
    for name, bars in data.items():
        box = m.build_boxes(bars)
        st = m.level_stats(bars, box)
        n = len(st)
        print(f"\n######## {name} ({n} Tage)")

        # 1) box size buckets
        st["bucket"] = pd.qcut(st.box_pct, 3, labels=["klein", "mittel", "groß"])
        print("Boxgröße (Range in % vom Preis) Terzil-Grenzen:",
              st.box_pct.quantile([0, 1 / 3, 2 / 3, 1]).round(3).tolist())
        tb = {}
        for bkt, g in st.groupby("bucket", observed=True):
            ht = m.hit_table(g)
            tb[bkt] = ht["irgendeine Seite %"]
            tb[f"{bkt} gegen Richtung"] = ht["gegen Box-Richtung %"]
        tb = pd.DataFrame(tb)
        print(tb.round(1).to_string())
        tb.round(1).to_csv(OUT / f"{name}_hits_by_boxsize.csv")

        # 2) do real levels hold better than fake levels?
        cur = reaction_curve(st)
        cmp_ = level_vs_fake(cur)
        big = st[st.bucket == "groß"]
        cmp_big = level_vs_fake(reaction_curve(big)).add_suffix(" (große Boxen)")
        res = pd.concat([cmp_, cmp_big], axis=1)
        print(res.to_string())
        res.to_csv(OUT / f"{name}_level_vs_fake.csv")
        cur.to_csv(OUT / f"{name}_reaction_curve.csv")

        # 3) fade grid on large boxes only (box range >= upper tercile threshold of NQ)
        thr = st.box_pct.quantile(2 / 3)
        rows = []
        import itertools
        for e, s in itertools.combinations(m.STDV_LEVELS, 2):
            for t in (1.0, 0.0):
                tr = m.fade_backtest(bars, box, e, s, t, min_box_pct=thr)
                rows.append({"entry k": e, "stop k": s, "target": "Box-Kante" if t == 1 else "Mitte",
                             **m.summarize(tr, n)})
        g = pd.DataFrame(rows).sort_values("sum R", ascending=False)
        print(f"Fade-Grid nur große Boxen (Range >= {thr:.3f}%):")
        print(g.head(8).to_string(index=False))
        g.to_csv(OUT / f"{name}_grid_bigbox.csv", index=False)


if __name__ == "__main__":
    main()
