import pickle, numpy as np, pandas as pd
from multiprocessing import Pool
import lab, vbo_sess as V, prop3
from v6_eval import pool_from
from prop import block_bootstrap
P = dict(k=0.35, sm=0.75, exitm='trail', side='both', maxtr=2)
EXITS = {'lag1.25 (base)': dict(lag=1.25), 'lag1.0 (BE at +1R)': dict(lag=1.0), 'lag0.75': dict(lag=0.75), 'lag0.5': dict(lag=0.5),
         'TP1R+trail': dict(lag=1.25, tp_r=1.0), 'TP1.5R+trail': dict(lag=1.25, tp_r=1.5)}
G = {}
def init(name, a, b): G['S'] = V.Sess(lab.DS(name, a, b))
def job(ex): return ex, V.run_model(G['S'], 'M0/M1 NY', **P, **EXITS[ex])
def initp(pool): G['pool'] = pool; G['paths'] = block_bootstrap(len(pool), 504, 1500, seed=31)
def jobp(g): return g, prop3.evaluate(G['paths'], G['pool'], *g)
GRID = [(e, f) for e in (350, 500) for f in (200, 250, 300)]
if __name__ == '__main__':
    T = {}
    for name, a, b in (('cfd', '2017-01-01', '2025-09-30'), ('nq', '2023-01-01', '2025-12-11')):
        with Pool(4, initializer=init, initargs=(name, a, b)) as p:
            T[name] = dict(p.map(job, list(EXITS)))
    print('Exit variants (same entries; win = R>0 after costs):')
    for ex in EXITS:
        c = T['cfd'][ex].assign(sdate=lambda x: pd.to_datetime(x.sdate)); n = T['nq'][ex]
        dev, te = c[c.sdate < '2023-01-01'], c[c.sdate >= '2023-01-01']
        print(f"  {ex:20s} dev n={len(dev)} win={(dev.Rc>0).mean():.1%} E={dev.Rc.mean():+.3f} | testCFD win={(te.Rc>0).mean():.1%} E={te.Rc.mean():+.3f} | "
              f"NQ n={len(n)} win={(n.Rf>0).mean():.1%} E={n.Rf.mean():+.3f} avgwin={n[n.Rf>0].Rf.mean():.2f}R avgloss={n[n.Rf<=0].Rf.mean():.2f}R")
    pickle.dump(T, open('cache/v8_exit_trades.pkl', 'wb'))
    # prop comparison: base, gap filter, all-3 filters (from V8 scan), and each exit variant
    sets = pickle.load(open('cache/v8_sets.pkl', 'rb')); top = pickle.load(open('cache/v8_top_filters.pkl', 'rb'))
    def filt(v, excl):
        m = np.ones(len(v), bool)
        for f, b in excl: m &= (v[f].astype(str) != b).to_numpy()
        return v[m]
    gap = [x for x in top if x[0].startswith('F_f')]
    cands = {'no filter (base)': (pd.concat([sets['dev']]), sets['testNQ']),
             'gap filter (no small gap)': (filt(sets['dev'], gap), filt(sets['testNQ'], gap)),
             'all 3 filters': (filt(sets['dev'], top), filt(sets['testNQ'], top))}
    for ex in EXITS:
        if ex == 'lag1.25 (base)': continue
        c = T['cfd'][ex].assign(sdate=lambda x: pd.to_datetime(x.sdate))
        cands['exit ' + ex] = (c[c.sdate < '2023-01-01'], T['nq'][ex].assign(sdate=lambda x: pd.to_datetime(x.sdate)))
    print('\nProp lifecycle (sizing chosen on dev CFD 2017-22, reported on NQ 2023-25):')
    for lab_, (dev, nq) in cands.items():
        res = {}
        for which, ds_name, t in (('dev', 'cfd', dev), ('nq', 'nq', nq)):
            with Pool(4, initializer=initp, initargs=(pool_from(ds_name, t),)) as p:
                res[which] = dict(p.map(jobp, GRID))
        g = max(GRID, key=lambda x: res['dev'][x]['pay_24m_mean']); b = res['nq'][g]
        print(f"  {lab_:28s} trades/mo NQ {len(nq)/35.4:4.1f} win {(nq.Rf>0).mean():.1%} | sizing {g} | NQ payouts 12m ${b['pay_12m_mean']:5.0f} (median ${b['pay_12m_median']:5.0f}) "
              f"24m ${b['pay_24m_mean']:6.0f} | evals/24m {b['evals_24m']:.1f} | 1st payout <=2M {b['p_first_2m']:.0%} <=3M {b['p_first_3m']:.0%} median {b['med_first']:.0f}d")
