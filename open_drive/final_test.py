"""
Endtest der eingefrorenen Kandidaten (selection.json) auf CFD Stufe A / B und NQ 2023-2025.

Exakte Abfolge: immer nur eine Position, hoechstens max_pro_tag Trades pro Tag, Einstiege 09:30-15:30.

Aufruf:  python open_drive/final_test.py <ereignis-ordner>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from build_events import RRS, STOPS
from search import FLAGS, RECLAIM, prep

pd.set_option("display.width", 250)


def trades(ev, spec, stop=None, rr=None):
    stop, rr = stop or spec["stop"], rr or spec["rr"]
    a, b = STOPS.index(stop), RRS.index(rr)
    grp = RECLAIM if spec["grp"] == "RECLAIM" else spec["grp"]
    m = ev.grp.isin(grp).values.copy()
    if spec["fo_min"] is not None:
        m &= (ev.fo >= spec["fo_min"]).values
    if spec.get("bar_max"):
        m &= (ev.bar <= spec["bar_max"]).values
    for f in spec["flags"]:
        m &= np.asarray(FLAGS[f](ev), bool)
    s = ev[m]
    R, X = s[f"R{a}_{b}"].values, s[f"X{a}_{b}"].values
    keep, cur, busy, cnt = [], -1, -1, 0
    for i, (di, bar) in enumerate(zip(s.di.values, s.bar.values)):
        if di != cur:
            cur, busy, cnt = di, -1, 0
        if bar > busy and cnt < spec["max_pro_tag"] and not np.isnan(R[i]):
            keep.append(i)
            busy, cnt = X[i], cnt + 1
    t = s.iloc[keep][["di", "day", "bar", "side", "grp", "atr", "entry"]].copy()
    t["R"] = R[keep]
    t["xbar"] = X[keep]
    t["stop_pts"] = stop * t.atr
    return t


def summary(t, nd, extra_cost_pts=0.0, kind="NQ"):
    R = t.R.values - extra_cost_pts * (1.0 if kind == "NQ" else 0.0032 * t.atr.values) / t.stop_pts.values
    if len(R) < 5:
        return {}
    d = np.zeros(nd)
    np.add.at(d, t.di.values, R)
    eq = np.cumsum(R)
    w, l = R[R > 0], R[R <= 0]
    return {"Trades": len(R), "pro Woche": len(R) / nd * 5, "Trefferquote": (R > 0).mean(),
            "Ø Gewinn R": w.mean(), "Ø Verlust R": l.mean(), "E (R)": R.mean(),
            "t": d.mean() / d.std(ddof=1) * np.sqrt(nd), "Profitfaktor": w.sum() / -l.sum(),
            "R pro Woche": R.sum() / nd * 5, "Max DD (R)": (eq - np.maximum.accumulate(eq)).min()}


def fmt(df):
    f = {"Trefferquote": "{:.1%}".format, "pro Woche": "{:.2f}".format, "Trades": "{:.0f}".format}
    return df.to_string(formatters={c: f.get(c, "{:+.3f}".format) for c in df.columns
                                    if df[c].dtype != object})


def main(evdir):
    sel = json.loads((Path(__file__).parent / "selection.json").read_text())["kandidaten"]
    sets = {}
    cfd, dlc = prep(pd.read_pickle(evdir / "events_CFD.pkl")), pd.read_pickle(evdir / "days_CFD.pkl")
    nq, dln = prep(pd.read_pickle(evdir / "events_NQ.pkl")), pd.read_pickle(evdir / "days_NQ.pkl")
    cutA = (dlc.day < "2021-01-01").sum()
    out = Path(__file__).parent / "results"
    out.mkdir(exist_ok=True)
    only = sys.argv[2] if len(sys.argv) > 2 else ""
    for spec in sel:
        if not spec["name"].startswith(only):
            continue
        print("=" * 110, "\n" + spec["name"], f"  (Stop {spec['stop']} ATR, Ziel {spec['rr']} R)\n")
        tc, tn = trades(cfd, spec), trades(nq, spec)
        A, B = tc[tc.di < cutA], tc[tc.di >= cutA].assign(di=lambda x: x.di - cutA)
        rows = {"CFD A 2016-20": summary(A, cutA, kind="CFD"), "CFD B 2021-22": summary(B, len(dlc) - cutA, kind="CFD"),
                "NQ 2023-25 (Endtest)": summary(tn, len(dln)),
                "NQ, Kosten 2 Pkt": summary(tn, len(dln), 1.0), "NQ nur Long": summary(tn[tn.side == 1], len(dln)),
                "NQ nur Short": summary(tn[tn.side == -1], len(dln))}
        print(fmt(pd.DataFrame(rows).T), "\n")
        yr = pd.concat([tc, tn]).assign(Jahr=lambda x: x.day.dt.year).groupby("Jahr").R.agg(
            Trades="count", Trefferquote=lambda x: (x > 0).mean(), E="mean", Summe_R="sum")
        print(yr.T.to_string(float_format="{:.2f}".format), "\n")
        g = []
        for st in STOPS[1:]:
            r = {"Stop": f"{st} ATR"}
            for rr in RRS:
                s = summary(trades(nq, spec, st, rr), len(dln))
                r[f"Ziel {rr}R"] = f"{s['Trefferquote']:.0%} {s['E (R)']:+.3f} ({s['t']:+.1f})"
            g.append(r)
        print("NQ, andere Ausstiege (Trefferquote, E in R, t):")
        print(pd.DataFrame(g).to_string(index=False), "\n")
        tn.assign(zeit=lambda x: x.day + pd.to_timedelta(510 + x.bar, unit="m")).drop(columns=["di"]).to_csv(
            out / f"trades_NQ_{spec['name'][:2]}.csv", index=False)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
