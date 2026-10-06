"""V7 prop evaluation: M0 (1/day) vs M1 (re-entry), sizing chosen on CFD 2017-22, reported on NQ 2023-25."""
import pickle, numpy as np, pandas as pd
from multiprocessing import Pool
from v6_eval import pool_from
from prop import block_bootstrap
import prop3
C = pickle.load(open('cache/v7_trades_cfd.pkl', 'rb')); N = pickle.load(open('cache/v7_trades_nq.pkl', 'rb'))
KEYS = {'M0 NY 1/day k0.3 sm1.0': ('M0/M1 NY', (('exitm', 'trail'), ('k', 0.3), ('maxtr', 1), ('side', 'both'), ('sm', 1.0))),
        'M1 NY re-entry 2/day k0.35 sm0.75': ('M0/M1 NY', (('exitm', 'trail'), ('k', 0.35), ('maxtr', 2), ('side', 'both'), ('sm', 0.75)))}
GRID = [(e, f) for e in (250, 350, 500) for f in (150, 200, 250, 300, 400)]
G = {}
def init(pool): G['pool'] = pool; G['paths'] = block_bootstrap(len(pool), 504, 1500, seed=31)
def job(g): return g, prop3.evaluate(G['paths'], G['pool'], *g)
if __name__ == '__main__':
    for name, key in KEYS.items():
        tc = C[key].assign(sdate=lambda x: pd.to_datetime(x.sdate)); tn = N[key].assign(sdate=lambda x: pd.to_datetime(x.sdate))
        dev = tc[tc.sdate < '2023-01-01']
        res = {}
        for lab_, ds_name, t in (('dev', 'cfd', dev), ('nq', 'nq', tn)):
            with Pool(4, initializer=init, initargs=(pool_from(ds_name, t),)) as p:
                res[lab_] = dict(p.map(job, GRID))
        best = max(GRID, key=lambda g: res['dev'][g]['pay_24m_mean'])
        print(f'\n=== {name} | trades/month NQ: {len(tn)/35.4:.1f}, E {tn.Rf.mean():+.3f}R, win {(tn.Rf>0).mean():.1%}')
        for g in GRID:
            a, b = res['dev'][g], res['nq'][g]
            print(f"  eval ${g[0]} / funded ${g[1]}: DEV payouts/24m ${a['pay_24m_mean']:6.0f} | NQ: payouts 12m mean ${b['pay_12m_mean']:5.0f} "
                  f"(median ${b['pay_12m_median']:5.0f}), 24m ${b['pay_24m_mean']:6.0f}, #payouts/24m {b['n_pay_24m']:.1f}, evals/24m {b['evals_24m']:.1f}, "
                  f"first payout <=1M {b['p_first_1m']:.0%} <=2M {b['p_first_2m']:.0%} <=3M {b['p_first_3m']:.0%} <=12M {b['p_first_12m']:.0%}, "
                  f"median {b['med_first']:.0f}d{'  <== chosen on dev' if g == best else ''}")
