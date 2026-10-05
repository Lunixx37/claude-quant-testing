"""Money management for the best-test FVG candidate (intraday, 40-pt stop, TP 3R) with the user's cycle:
withdraw 0.5x base after 'month 1' if equity >= 1.5x base; +$100 after 'month 2' (new base)."""
import numpy as np, pandas as pd
from multiprocessing import Pool
import fvg_lab as L

T = {sp: L.run(sp, (), ('fixed', 40.0), 3.0, False, 1) for sp in ('train', 'valid', 'test22', 'test_nq')}


def kelly(R):
    fs = np.linspace(0.001, 0.30, 300)
    g = [np.mean(np.log1p(f * R)) if (1 + f * R).min() > 0 else -np.inf for f in fs]
    return fs[int(np.argmax(g))]


def months_of(t, start, end):
    t = t.assign(m=pd.to_datetime(t.sdate).dt.to_period('M'))
    return [t[t.m == m][['Rc', 'R_pts']].to_numpy() for m in pd.period_range(start, end, freq='M')]


POOLS = {'all years 2017-2025': months_of(pd.concat(T.values()), '2017-01', '2025-11'),
         'recent 2023-2025 (NQ)': months_of(T['test_nq'], '2023-01', '2025-11')}


def sim(args):
    pn, risk, n_paths, months = args
    pool = POOLS[pn]
    rng = np.random.default_rng(7)
    res = []
    for _ in range(n_paths):
        E, base, wd, dep = 100.0, 100.0, 0.0, 100.0
        for m, j in enumerate(rng.integers(0, len(pool), size=months)):
            for Rc, Rp in pool[j]:
                lots = np.floor(E * risk / Rp / 0.01) * 0.01
                if lots < 0.01:
                    if E > 0.01 * Rp:
                        lots = 0.01
                    else:
                        continue
                E = max(E + lots * Rp * Rc, 0.0)
            if m % 2 == 0:
                if E >= 1.5 * base:
                    E -= 0.5 * base
                    wd += 0.5 * base
            else:
                E += 100.0
                dep += 100.0
                base = E
        res.append((wd, dep, E))
    a = np.array(res)
    net = a[:, 0] + a[:, 2] - a[:, 1]
    return pn, risk, dict(med=np.median(net) / months, p10=np.percentile(net, 10) / months, p90=np.percentile(net, 90) / months,
                          wd=np.median(a[:, 0]) / months, ploss=(net < 0).mean(), fin=np.median(a[:, 2]))


if __name__ == '__main__':
    print('FVG candidate (intraday, stop 40, TP 3R):')
    for sp, t in T.items():
        s = L.stats(t, sp)
        print(f"  {sp:8s} n={s['n']} ({s['per_week']:.1f}/wk) win={s['win']:.1%} E_cfd={s['E']:+.3f}R maxDD={s['dd']:.1f}R")
    k_dev = kelly(pd.concat([T['train'], T['valid']]).Rc.to_numpy())
    k_all = kelly(pd.concat(T.values()).Rc.to_numpy())
    k_rec = kelly(T['test_nq'].Rc.to_numpy())
    print(f"Kelly: dev 2017-21 {k_dev:.1%} | all years {k_all:.1%} | recent 2023-25 {k_rec:.1%}")
    risks = [('Kelly/2', k_all / 2), ('Kelly', k_all), ('5 %', 0.05), ('10 %', 0.10)]
    with Pool(4) as p:
        out = p.map(sim, [(pn, r, 2000, 36) for pn in POOLS for _, r in risks])
    lab = {r: n for n, r in risks}
    print('\n$100 start, user cycle, 36 months, 2000 paths (month-block bootstrap):')
    for pn, r, d in out:
        print(f"  [{pn:22s}] {lab[r]:8s} ({r:.1%}): net/month median ${d['med']:6.1f} (10%..90%: ${d['p10']:6.1f}..${d['p90']:6.1f}) | "
              f"withdrawals/month ${d['wd']:5.1f} | P(net loss 3y) {d['ploss']:.0%} | final equity ${d['fin']:.0f}")
