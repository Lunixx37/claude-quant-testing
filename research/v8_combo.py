import pickle, numpy as np, pandas as pd
from multiprocessing import Pool
import lab, prop3
from v6_eval import pool_from
from prop import block_bootstrap
T = pickle.load(open('cache/v8_exit_trades.pkl', 'rb'))
LO, HI = -0.405, 0.079          # dev quintile edges: excluded = small gap (Q2+Q3), directional gap/ATR14
G = {}
def initp(pool): G['pool'] = pool; G['paths'] = block_bootstrap(len(pool), 504, 1500, seed=31)
def jobp(g): return g, prop3.evaluate(G['paths'], G['pool'], *g)
GRID = [(e, f) for e in (350, 500) for f in (200, 250, 300)]
def gapfilter(t, name, period):
    d = lab.DS(name, *period).d
    t = t.assign(sdate=pd.to_datetime(t.sdate))
    g = ((d.o - d.pc) / d.atr14).reindex(t.sdate).to_numpy() * t.dir.to_numpy()
    return t[~((g > LO) & (g <= HI))]
if __name__ == '__main__':
    for ex in ('lag1.25 (base)', 'lag0.75'):
        c = gapfilter(T['cfd'][ex], 'cfd', ('2017-01-01', '2025-09-30')); n = gapfilter(T['nq'][ex], 'nq', ('2023-01-01', '2025-12-11'))
        dev = c[c.sdate < '2023-01-01']; te = c[c.sdate >= '2023-01-01']
        print(f"gap filter + {ex}: dev n={len(dev)} win={(dev.Rc>0).mean():.1%} E={dev.Rc.mean():+.3f} | testCFD n={len(te)} win={(te.Rc>0).mean():.1%} E={te.Rc.mean():+.3f} | "
              f"NQ n={len(n)} ({len(n)/35.4:.1f}/mo) win={(n.Rf>0).mean():.1%} E={n.Rf.mean():+.3f} avgwin={n[n.Rf>0].Rf.mean():.2f}R avgloss={n[n.Rf<=0].Rf.mean():.2f}R")
        res = {}
        for which, ds_name, tt in (('dev', 'cfd', dev), ('nq', 'nq', n)):
            with Pool(4, initializer=initp, initargs=(pool_from(ds_name, tt),)) as p:
                res[which] = dict(p.map(jobp, GRID))
        g = max(GRID, key=lambda x: res['dev'][x]['pay_24m_mean']); b = res['nq'][g]
        print(f"   prop sizing {g}: NQ payouts 12m ${b['pay_12m_mean']:.0f} (median ${b['pay_12m_median']:.0f}), 24m ${b['pay_24m_mean']:.0f}, payouts/24m {b['n_pay_24m']:.1f}, "
              f"evals/24m {b['evals_24m']:.1f}, 1st payout <=1M {b['p_first_1m']:.0%} <=2M {b['p_first_2m']:.0%} <=3M {b['p_first_3m']:.0%} <=12M {b['p_first_12m']:.0%}, median {b['med_first']:.0f}d")
