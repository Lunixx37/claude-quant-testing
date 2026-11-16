"""
Systematic strategy search on the Stdv-Box event table (search_events.py).

Three strictly separated stages to keep the result distinguishable from data-mining luck:

  A  SEARCH    CFD 2016-11 .. 2020-12   all ~1.5 M combinations are evaluated
  B  CONFIRM   CFD 2021 .. 2022         only looked at for combinations that passed A
  C  FINAL     NQ futures 2023 .. 2025  one shot for the 5 selected strategies (search.py final)

Strategy = entry kind (T limit at level / R reclaim close) x box-size filter x level group x min. stop size
           x up to 2 extra filters x stop model x exit model.

Statistics are computed on DAILY R sums (days without trade = 0), so several trades on one day do not
inflate the t-statistic.

Usage:  python search.py search <evdir>      # stages A+B, writes results/search/selected.json
        python search.py final  <evdir>      # stage C for the selected strategies
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from search_events import EXITS, STOPS_R, STOPS_T   # noqa: E402

OUT = Path(__file__).parent / "results" / "search"
MIN_TPD = 0.5            # raw trades per day required in the search (>= 2 per week after de-overlap)
RELS = [0.0, 0.1, 0.2]
GROUPS = {"alle": None, "kanten": ["edge00", "edge830"], "kante00": ["edge00"], "c2": ["c2"], "3.5": ["l35"],
          "c4": ["c4"], "stdv": ["c2", "l35", "c4"], "aussen": ["l35", "c4"]}
MINRISK = [0.0, 0.01, 0.02, 0.03]
NS, NX = 4, len(EXITS)


def filter_options(s, kind):
    f = {"natural": ("nat", s.natural.values), "flip": ("nat", ~s.natural.values),
         "mit_box": ("dir", s.with_dir.values), "gegen_box": ("dir", ~s.with_dir.values),
         "t<09:30": ("time", s.bar.values < 60), "t09:30-11": ("time", (s.bar.values >= 60) & (s.bar.values < 150)),
         "t11-13:30": ("time", (s.bar.values >= 150) & (s.bar.values < 300)), "t>=13:30": ("time", s.bar.values >= 300),
         "t>=09:30": ("time", s.bar.values >= 60),
         "ict": ("ict", s.ict.values),
         "vwap_gedehnt": ("z", s.z.values <= -1), "vwap_mit": ("z", s.z.values >= 0),
         "vorher_reaktion": ("prior", s.prior_same.values), "vorher_reaktion_q": ("prior", s.prior_same_q.values),
         "keine_vorher": ("prior", ~s.prior_same.values), "vorher_gegen": ("prior", s.prior_opp.values),
         "erster_touch": ("ord", s.ord.values == 0), "wiederholt": ("ord", s.ord.values > 0),
         "psych50": ("psych", s.psych.values)}
    if kind == "R":
        f["momentum"] = ("mom", s.mom.values)
    return f


def combos(fo):
    names = list(fo)
    out = [()]
    out += [(a,) for a in names]
    out += [(a, b) for a, b in itertools.combinations(names, 2) if fo[a][0] != fo[b][0]]
    return out


def strat_mask(s, kind, rel, grp, f):
    m = (s.rel.values >= rel)
    if GROUPS[grp] is not None:
        m &= s.grp.isin(GROUPS[grp]).values
    fo = filter_options(s, kind)
    for name in f:
        m &= fo[name][1]
    return m


def outcome_arrays(s):
    O = np.stack([s[f"o{si}_{xi}"].values for si in range(NS) for xi in range(NX)], axis=1)
    risk = np.stack([s[f"risk{si}"].values for si in range(NS)], axis=1)
    return O, risk


def daily_sums(di, M, nd):
    """di sorted; M [n, k] -> [nd, k] sums per day."""
    out = np.zeros((nd, M.shape[1]))
    if len(di) == 0:
        return out
    starts = np.concatenate(([0], np.flatnonzero(np.diff(di)) + 1))
    out[di[starts]] = np.add.reduceat(M, starts, axis=0)
    return out


def tstat(d):
    sd = d.std(axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(sd > 0, d.mean(axis=0) / sd * np.sqrt(len(d)), 0.0)


def search(evdir):
    OUT.mkdir(parents=True, exist_ok=True)
    ev = pd.read_pickle(evdir / "events_CFD.pkl")
    days = pd.read_pickle(evdir / "days_CFD.pkl")
    nd = len(days)
    yr = days.day.dt.year.values
    A, B = yr <= 2020, yr >= 2021
    years_a = [2017, 2018, 2019, 2020]
    res = []
    for kind in ("T", "R"):
        s = ev[ev.kind == kind].sort_values(["di", "bar"]).reset_index(drop=True)
        O, risk = outcome_arrays(s)
        di = s.di.values
        fo = filter_options(s, kind)
        cmb = combos(fo)
        stops = STOPS_T if kind == "T" else STOPS_R
        for mr in MINRISK:
            V = ~np.isnan(O)
            if mr > 0:
                V &= np.repeat(risk >= mr, NX, axis=1)
            O0 = np.where(V, O, 0.0)
            W = (O0 > 0)
            for rel in RELS:
                for grp in GROUPS:
                    base = strat_mask(s, kind, rel, grp, ())
                    for f in cmb:
                        mk = base.copy()
                        for name in f:
                            mk &= fo[name][1]
                        idx = np.flatnonzero(mk)
                        if len(idx) < MIN_TPD * A.sum() * 0.5:
                            continue
                        d = daily_sums(di[idx], O0[idx], nd)
                        c = daily_sums(di[idx], V[idx].astype(float), nd)
                        w = W[idx].sum(axis=0)
                        dA, dB = d[A], d[B]
                        nA, nB = c[A].sum(0), c[B].sum(0)
                        tA, tB, tAB = tstat(dA), tstat(dB), tstat(d)
                        ypos = sum((d[yr == y].sum(0) > 0).astype(int) for y in years_a)
                        ok = (nA >= MIN_TPD * A.sum())
                        for k in np.flatnonzero(ok):
                            si, xi = divmod(k, NX)
                            res.append((kind, rel, grp, mr, "+".join(f), stops[si], EXITS[xi],
                                        nA[k], dA[:, k].sum() / nA[k], tA[k], ypos[k],
                                        nB[k], (dB[:, k].sum() / nB[k]) if nB[k] else np.nan, tB[k], tAB[k],
                                        w[k] / (nA[k] + nB[k])))
            print(kind, "minrisk", mr, "fertig, Zeilen:", len(res), flush=True)
    R = pd.DataFrame(res, columns=["kind", "rel", "grp", "minrisk", "filter", "stop", "exit",
                                   "nA", "R_A", "tA", "years_pos_A", "nB", "R_B", "tB", "tAB", "win"])
    R.to_pickle(OUT / "all_results.pkl")
    report(R, A.sum(), B.sum())
    return R


def report(R, NA, NB):
    print(f"\nGetestete Kombinationen (>= {MIN_TPD} Trades/Tag in A): {len(R):,}")
    passA = R[(R.tA >= 2.5) & (R.years_pos_A >= 3) & (R.R_A > 0)]
    print(f"Stufe A bestanden (t>=2.5, >=3 von 4 Jahren positiv): {len(passA):,}")
    okB = passA[(passA.nB >= MIN_TPD * NB)]
    passB = okB[(okB.tB >= 1.5)]
    print(f"davon Stufe B bestanden (t>=1.5): {len(passB):,} von {len(okB):,} = {len(passB) / max(len(okB), 1) * 100:.1f} % "
          f"(bei reinem Zufall erwartet: 6.7 %)")
    print("Anteil A-Bestandener mit positivem B:", round((okB.R_B > 0).mean() * 100, 1), "% (Zufall: 50 %)")
    print("Korrelation tA vs tB über alle Kombinationen:", round(np.corrcoef(R.tA, R.tB)[0, 1], 3))
    for col in ("kind", "stop", "exit", "grp", "rel", "minrisk"):
        g = R.groupby(col).agg(n=("tA", "size"), tA=("tA", "mean"), tB=("tB", "mean"),
                               passA=("tA", lambda x: (x >= 2.5).mean() * 100)).round(2)
        print(g.to_string())
        g.to_csv(OUT / f"marginal_{col}.csv")
    passB.sort_values("tAB", ascending=False).to_csv(OUT / "passed_A_and_B.csv", index=False)
    print(passB.sort_values("tAB", ascending=False).head(40).to_string(index=False))


# ----------------------------------------------------------------------------- selection + final
def events_of(ev, st):
    s = ev[ev.kind == st["kind"]].sort_values(["di", "bar"]).reset_index(drop=True)
    f = tuple(x for x in st["filter"].split("+") if x)
    mk = strat_mask(s, st["kind"], st["rel"], st["grp"], f)
    stops = STOPS_T if st["kind"] == "T" else STOPS_R
    si, xi = stops.index(st["stop"]), EXITS.index(st["exit"])
    r = s[f"o{si}_{xi}"].values
    mk &= ~np.isnan(r) & (s[f"risk{si}"].values >= st["minrisk"])
    t = s[mk][["di", "day", "bar", "side", "level"]].copy()
    t["R"] = r[mk]
    t["xbar"] = s[f"x{si}_{xi}"].values[mk]
    return t


def one_at_a_time(t):
    keep, cur_day, busy = [], -1, -1
    for i, (di, bar, xb) in enumerate(zip(t.di.values, t.bar.values, t.xbar.values)):
        if di != cur_day:
            cur_day, busy = di, -1
        if bar > busy:
            keep.append(i)
            busy = xb
    return t.iloc[keep]


def stats(t, nd, label=""):
    d = np.zeros(nd)
    np.add.at(d, t.di.values, t.R.values)
    ts = d.mean() / d.std(ddof=1) * np.sqrt(nd) if d.std() > 0 else 0.0
    rng = np.random.default_rng(0)
    boot = rng.choice(d, (5000, nd)).mean(1)
    eq = np.cumsum(t.R.values)
    return {"Daten": label, "Trades": len(t), "Trades/Woche": round(len(t) / nd * 5, 2),
            "Winrate %": round((t.R > 0).mean() * 100, 1), "Ø R/Trade": round(t.R.mean(), 3),
            "Σ R": round(t.R.sum(), 1), "t (Tagesbasis)": round(ts, 2),
            "p einseitig (Bootstrap)": round(float((boot <= 0).mean()), 4),
            "Max DD (R)": round(float((eq - np.maximum.accumulate(eq)).min()), 1)}


def daily_series(t, nd):
    d = np.zeros(nd)
    np.add.at(d, t.di.values, t.R.values)
    return d


def select(evdir, n_pick=5, max_corr=0.6, pool=400):
    """Pick n diverse strategies from those that passed A and B (ranked by combined t). NQ is NOT touched."""
    ev = pd.read_pickle(evdir / "events_CFD.pkl")
    nd = len(pd.read_pickle(evdir / "days_CFD.pkl"))
    P = pd.read_csv(OUT / "passed_A_and_B.csv", keep_default_na=False).head(pool)
    P["confirmed"] = True
    # fallback pool if fewer than n strategies survived A+B: best remaining by combined t (NOT confirmed)
    allr = pd.read_pickle(OUT / "all_results.pkl")
    rest = allr[(allr.R_A > 0) & (allr.R_B > 0) & (allr.tA >= 2.0)].sort_values("tAB", ascending=False).head(pool)
    rest["confirmed"] = False
    P = pd.concat([P, rest], ignore_index=True)
    picked, series = [], []
    for _, row in P.iterrows():
        st = {k: (row[k].item() if hasattr(row[k], "item") else row[k]) for k in
              ("kind", "rel", "grp", "minrisk", "filter", "stop", "exit")}
        t = one_at_a_time(events_of(ev, st))
        if len(t) / nd * 5 < 2.0:
            continue
        d = daily_series(t, nd)
        if any(abs(np.corrcoef(d, x)[0, 1]) > max_corr for x in series):
            continue
        st["confirmed_A_B"] = bool(row["confirmed"])
        st["tA"], st["tB"] = round(float(row["tA"]), 2), round(float(row["tB"]), 2)
        picked.append(st)
        series.append(d)
        if len(picked) == n_pick:
            break
    json.dump(picked, open(OUT / "selected.json", "w"), indent=1, ensure_ascii=False)
    print(json.dumps(picked, indent=1, ensure_ascii=False))
    return picked


def final(evdir):
    picked = json.load(open(OUT / "selected.json"))
    rows = []
    sets = [("CFD", "", "CFD 2016–2022 (Suche+Bestätigung)"), ("NQ", "", "NQ 2023–2025 (Endtest)"),
            ("CFD", "_fake+0.07", "CFD Fake-Level +0.07 ATR"), ("CFD", "_fake-0.07", "CFD Fake-Level −0.07 ATR"),
            ("NQ", "_fake+0.07", "NQ Fake-Level +0.07 ATR"), ("NQ", "_fake-0.07", "NQ Fake-Level −0.07 ATR")]
    for name, suffix, label in sets:
        ev = pd.read_pickle(evdir / f"events_{name}{suffix}.pkl")
        nd = len(pd.read_pickle(evdir / f"days_{name}.pkl"))
        for i, st in enumerate(picked, 1):
            t = one_at_a_time(events_of(ev, st))
            if suffix == "":
                t.to_csv(OUT / f"trades_S{i}_{name}.csv", index=False)
            r = {"Strategie": f"S{i}", **stats(t, nd, label)}
            if name == "NQ" and suffix == "":
                yr = t.day.dt.year
                for y in sorted(yr.unique()):
                    r[f"Σ R {y}"] = round(t.R[yr == y].sum(), 1)
            rows.append(r)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "final_top5.csv", index=False)
    pd.set_option("display.width", 250)
    print(res.to_string(index=False))



# ----------------------------------------------------------------------------- full-sample scan + fake-level null
def scan_one(ev, days):
    """All combinations on one dataset: n, sum R, sum of squared daily R, positive years."""
    nd = len(days)
    yr = days.day.dt.year.values
    years = [y for y in np.unique(yr) if (yr == y).sum() > 100]
    rows = []
    for kind in ("T", "R"):
        s = ev[ev.kind == kind].sort_values(["di", "bar"]).reset_index(drop=True)
        O, risk = outcome_arrays(s)
        di = s.di.values
        fo = filter_options(s, kind)
        cmb = combos(fo)
        stops = STOPS_T if kind == "T" else STOPS_R
        for mr in MINRISK:
            V = ~np.isnan(O)
            if mr > 0:
                V &= np.repeat(risk >= mr, NX, axis=1)
            O0 = np.where(V, O, 0.0)
            for rel in RELS:
                for grp in GROUPS:
                    base = strat_mask(s, kind, rel, grp, ())
                    for f in cmb:
                        mk = base.copy()
                        for name in f:
                            mk &= fo[name][1]
                        idx = np.flatnonzero(mk)
                        if len(idx) < MIN_TPD * nd * 0.5:
                            continue
                        d = daily_sums(di[idx], O0[idx], nd)
                        n = V[idx].sum(axis=0)
                        ypos = sum((d[yr == y].sum(0) > 0).astype(int) for y in years)
                        tt = tstat(d)
                        S, SS = d.sum(0), (d ** 2).sum(0)
                        for k in np.flatnonzero(n >= MIN_TPD * nd):
                            si, xi = divmod(k, NX)
                            rows.append((kind, rel, grp, mr, "+".join(f), stops[si], EXITS[xi],
                                         n[k], S[k], SS[k], tt[k], ypos[k]))
    return pd.DataFrame(rows, columns=["kind", "rel", "grp", "minrisk", "filter", "stop", "exit",
                                       "n", "S", "SS", "t", "ypos"]), nd, len(years)


def scan(evdir, suffix=""):
    """Full-sample scan (CFD 2016-2022 + NQ 2023-2025) for real levels (suffix '') or a fake-level table."""
    key = ["kind", "rel", "grp", "minrisk", "filter", "stop", "exit"]
    parts, nds, nys = [], [], []
    for name in ("CFD", "NQ"):
        r, nd, ny = scan_one(pd.read_pickle(evdir / f"events_{name}{suffix}.pkl"), pd.read_pickle(evdir / f"days_{name}.pkl"))
        parts.append(r.set_index(key).add_suffix(f"_{name}"))
        nds.append(nd)
        nys.append(ny)
    M = parts[0].join(parts[1], how="inner").reset_index()
    N = sum(nds)
    S, SS = M.S_CFD + M.S_NQ, M.SS_CFD + M.SS_NQ
    var = (SS - S ** 2 / N) / (N - 1)
    M["t_all"] = (S / N) / np.sqrt(var) * np.sqrt(N)
    M["R_CFD"], M["R_NQ"] = M.S_CFD / M.n_CFD, M.S_NQ / M.n_NQ
    M["ypos"] = M.ypos_CFD + M.ypos_NQ
    M["n_years"] = sum(nys)
    M.to_pickle(OUT / f"scan{suffix or '_real'}.pkl")
    good = M[(M.R_CFD > 0) & (M.R_NQ > 0) & (M.t_CFD >= 1.5) & (M.t_NQ >= 1.5) & (M.ypos >= M.n_years - 2)]
    print(f"[{suffix or 'ECHTE LEVEL'}] Kombinationen: {len(M):,} | max t_all: {M.t_all.max():.2f} | "
          f"t_all>=3: {(M.t_all >= 3).sum():,} | t_all>=3.5: {(M.t_all >= 3.5).sum():,} | "
          f"robust (beide Datensätze t>=1.5, >= {int(M.n_years.iloc[0]) - 2} von {int(M.n_years.iloc[0])} Jahren positiv): {len(good):,} "
          f"| bestes robustes t_all: {good.t_all.max() if len(good) else float('nan'):.2f}", flush=True)
    return M, good


def select_all(evdir, n_pick=5, max_corr=0.6):
    """Top-5 forward-test candidates on ALL data (in-sample!), diverse, >= 2 trades/week in both datasets."""
    M = pd.read_pickle(OUT / "scan_real.pkl")
    good = M[(M.R_CFD > 0) & (M.R_NQ > 0) & (M.t_CFD >= 1.5) & (M.t_NQ >= 1.5) & (M.ypos >= M.n_years - 2)]
    good = good.sort_values("t_all", ascending=False)
    good.head(300).to_csv(OUT / "robust_candidates_all_data.csv", index=False)
    evs = {n: pd.read_pickle(evdir / f"events_{n}.pkl") for n in ("CFD", "NQ")}
    nds = {n: len(pd.read_pickle(evdir / f"days_{n}.pkl")) for n in ("CFD", "NQ")}
    picked, series = [], []
    for _, row in good.iterrows():
        st = {k: (row[k].item() if hasattr(row[k], "item") else row[k]) for k in
              ("kind", "rel", "grp", "minrisk", "filter", "stop", "exit")}
        ts = {n: one_at_a_time(events_of(evs[n], st)) for n in evs}
        if min(len(ts[n]) / nds[n] * 5 for n in evs) < 2.0:
            continue
        d = np.concatenate([daily_series(ts[n], nds[n]) for n in ("CFD", "NQ")])
        if any(abs(np.corrcoef(d, x)[0, 1]) > max_corr for x in series):
            continue
        st["t_all"] = round(float(row.t_all), 2)
        picked.append(st)
        series.append(d)
        if len(picked) == n_pick:
            break
    json.dump(picked, open(OUT / "top5_all_data.json", "w"), indent=1, ensure_ascii=False)
    rows = []
    for i, st in enumerate(picked, 1):
        for n, lab in (("CFD", "CFD 2016–2022"), ("NQ", "NQ 2023–2025")):
            t = one_at_a_time(events_of(evs[n], st))
            t.to_csv(OUT / f"trades_K{i}_{n}.csv", index=False)
            r = {"Kandidat": f"K{i}", **stats(t, nds[n], lab)}
            rows.append(r)
            for suffix in ("_fake+0.07", "_fake-0.07"):
                tf = one_at_a_time(events_of(pd.read_pickle(evdir / f"events_{n}{suffix}.pkl"), st))
                r[f"Ø R Fake{suffix[5:]}"] = round(tf.R.mean(), 3)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "top5_all_data.csv", index=False)
    pd.set_option("display.width", 250)
    print(json.dumps(picked, ensure_ascii=False))
    print(res.to_string(index=False))


if __name__ == "__main__":
    cmd, evdir = sys.argv[1], Path(sys.argv[2])
    if cmd == "search":
        search(evdir)
    elif cmd == "report":
        d = pd.read_pickle(evdir / "days_CFD.pkl")
        y = d.day.dt.year.values
        report(pd.read_pickle(OUT / "all_results.pkl"), (y <= 2020).sum(), (y >= 2021).sum())
    elif cmd == "select":
        select(evdir)
    elif cmd == "final":
        final(evdir)
    elif cmd == "scan":
        for suffix in ("", "_fake+0.07", "_fake-0.07"):
            scan(evdir, suffix)
    elif cmd == "select_all":
        select_all(evdir)
