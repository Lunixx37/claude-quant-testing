import pickle, numpy as np, pandas as pd
from multiprocessing import Pool
import prop3
from v6_eval import pool_from
from prop import block_bootstrap
C = pickle.load(open('cache/v9_trades_cfd.pkl', 'rb')); N = pickle.load(open('cache/v9_trades_nq.pkl', 'rb'))
CANDS = {'BASE (no target, trail 1R/1.25)': (('none', 0.0), ('base s1 lag1.25', 1.0, 1.25)),
         'POC target >=1.5R + base trail': (('poc', 1.5), ('base s1 lag1.25', 1.0, 1.25)),
         'POC target >=1.0R, no trail': (('poc', 1.0), ('no trail', 0.0, 0.0)),
         'no target, no trail (EOD)': (('none', 0.0), ('no trail', 0.0, 0.0)),
         'high win rate: trail 0.75R/lag 0.5': (('none', 0.0), ('s0.75 lag0.5', 0.75, 0.5))}
GRID = [(e, f) for e in (350, 500) for f in (200, 250, 300)]
G = {}
def initp(pool): G['pool'] = pool; G['paths'] = block_bootstrap(len(pool), 504, 1500, seed=31)
def jobp(g): return g, prop3.evaluate(G['paths'], G['pool'], *g)
if __name__ == '__main__':
    for lab_, key in CANDS.items():
        c = C[key].assign(sdate=lambda x: pd.to_datetime(x.sdate)); n = N[key].assign(sdate=lambda x: pd.to_datetime(x.sdate))
        dev = c[c.sdate < '2023-01-01']
        res = {}
        for which, ds_name, t in (('dev', 'cfd', dev), ('nq', 'nq', n)):
            with Pool(4, initializer=initp, initargs=(pool_from(ds_name, t),)) as p:
                res[which] = dict(p.map(jobp, GRID))
        g = max(GRID, key=lambda x: res['dev'][x]['pay_24m_mean']); b = res['nq'][g]
        print(f"{lab_:36s} NQ win {(n.Rf>0).mean():.1%} avgwin {n[n.Rf>0].Rf.mean():.2f}R E {n.Rf.mean():+.3f} | sizing {g} | payouts 12m ${b['pay_12m_mean']:5.0f} (median ${b['pay_12m_median']:5.0f}) "
              f"24m ${b['pay_24m_mean']:6.0f} | evals/24m {b['evals_24m']:.1f} | 1st payout <=2M {b['p_first_2m']:.0%} <=3M {b['p_first_3m']:.0%} median {b['med_first']:.0f}d")
