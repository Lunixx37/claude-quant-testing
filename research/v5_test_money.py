"""V5: one-time test of V5_FINAL + money management with the user's 2-month cycle."""
import numpy as np, pandas as pd
from multiprocessing import Pool
import fvg_lab as L
from candidates import V5_FINAL as P
def run(sp):
    return L.run(sp, P['filters'], P['stop'], P['tp_r'], P['trail'], P['hold'])
T = {sp: run(sp) for sp in ('train', 'valid', 'test22', 'test_nq', 'test_cfd')}
print('V5_FINAL = FVG swing, stop 60 pts, TP 2R, hold <= 2 sessions, no filters')
for sp, t in T.items():
    s = L.stats(t, sp); sf = L.stats(t, sp, 'Rf')
    tag = '(dev)' if sp in ('train', 'valid') else '(ONE-TIME TEST)'
    yrs = pd.to_datetime(t.sdate).dt.year.value_counts().sort_index().to_dict()
    print(f"  {sp:9s}{tag:16s} n={s['n']:4d} ({s['per_week']:.1f}/wk) win={s['win']:.1%} E_cfd={s['E']:+.3f}R E_futures={sf['E']:+.3f}R PF={s['pf']:.2f} maxDD={s['dd']:.1f}R avg overnight={t.nights.mean():.2f}")
by_year = pd.concat([T['train'], T['valid'], T['test22'], T['test_nq']]).assign(y=lambda x: pd.to_datetime(x.sdate).dt.year).groupby('y').Rc.agg(['count', 'mean']).round(3)
print('per year (CFD costs; 2023-25 = NQ prices):'); print(by_year.T.to_string())
# ---------- Kelly ----------
def kelly(R):
    fs = np.linspace(0.001, 0.30, 300)
    g = [np.mean(np.log1p(f * R)) if (1 + f * R).min() > 0 else -np.inf for f in fs]
    return fs[int(np.argmax(g))], max(g)
dev = pd.concat([T['train'], T['valid']]).Rc.to_numpy(); rec = T['test_nq'].Rc.to_numpy()
k_dev, _ = kelly(dev); k_rec, _ = kelly(rec)
print(f"\nKelly fraction (risk per trade at stop): dev 2017-21 = {k_dev:.1%}, recent 2023-25 = {k_rec:.1%}")
# ---------- money management sim ----------
def months_of(t, start, end):
    t = t.assign(m=pd.to_datetime(t.sdate).dt.to_period('M'))
    allm = pd.period_range(start, end, freq='M')
    return [t[t.m == m][['Rc', 'R_pts']].to_numpy() for m in allm]
POOLS = {'all years 2017-2025': months_of(pd.concat([T['train'], T['valid'], T['test22'], T['test_nq']]), '2017-01', '2025-11'),
         'recent 2023-2025 (NQ)': months_of(T['test_nq'], '2023-01', '2025-11')}
def sim(args):
    pool_name, risk, n_paths, months = args
    pool = POOLS[pool_name]; rng = np.random.default_rng(7)
    res = []
    for _ in range(n_paths):
        E, base, wd, dep, wipes = 100.0, 100.0, 0.0, 100.0, 0
        idx = rng.integers(0, len(pool), size=months)
        for m in range(months):
            for Rc, Rp in pool[idx[m]]:
                lots = np.floor(E * risk / Rp / 0.01) * 0.01
                if lots < 0.01:
                    if E > 0.01 * Rp: lots = 0.01
                    else: continue
                E += lots * Rp * Rc
                if E <= 1.0:
                    E = 0.0; wipes += 1; break
            if m % 2 == 0:                       # end of "Monat 1": withdraw 0.5x base if equity >= 1.5x base
                if E >= 1.5 * base:
                    E -= 0.5 * base; wd += 0.5 * base
            else:                                # end of "Monat 2": deposit $100, new Monat 0
                E += 100.0; dep += 100.0; base = E
        res.append((wd, dep, E, wipes))
    a = np.array(res)
    net = a[:, 0] + a[:, 2] - a[:, 1]
    return pool_name, risk, dict(wd_month=np.median(a[:, 0]) / months, net_month_med=np.median(net) / months,
                                 net_month_p10=np.percentile(net, 10) / months, net_month_p90=np.percentile(net, 90) / months,
                                 p_net_loss=(net < 0).mean(), p_wipe=(a[:, 3] > 0).mean(), mean_wipes=a[:, 3].mean(),
                                 deposits=np.median(a[:, 1]), final_eq=np.median(a[:, 2]))
risks = [('Kelly/2 (dev)', k_dev / 2), ('Kelly (dev)', k_dev), ('5 %', 0.05), ('10 %', 0.10)]
jobs = [(pn, r, 3000, 36) for pn in POOLS for _, r in risks]
with Pool(4) as p: out = p.map(sim, jobs)
lab = {r: n for n, r in risks}
print('\nMoney management: $100 start, user cycle (withdraw 0.5x base at >=1.5x after month 1; +$100 after month 2), 36 months, 3000 paths')
for pn, r, d in out:
    print(f"  [{pn:22s}] risk {lab[r]:14s} ({r:.1%}): net profit/month median ${d['net_month_med']:7.1f} (10%..90%: ${d['net_month_p10']:6.1f} .. ${d['net_month_p90']:7.1f}) | "
          f"withdrawals/month ${d['wd_month']:6.1f} | deposits total ${d['deposits']:.0f} | P(net loss after 3y) {d['p_net_loss']:.0%} | P(>=1 wipe-out) {d['p_wipe']:.0%} (avg {d['mean_wipes']:.1f}) | final equity ${d['final_eq']:.0f}")
