import pickle, numpy as np, pandas as pd
from multiprocessing import Pool
import prop3
from v6_eval import pool_from
from prop import block_bootstrap
C = pickle.load(open('cache/v10_trades_cfd.pkl', 'rb')); N = pickle.load(open('cache/v10_trades_nq.pkl', 'rb'))
def split(t):
    t = t.assign(sdate=pd.to_datetime(t.sdate)); return t[t.sdate < '2023-01-01'], t[t.sdate >= '2023-01-01']
rows = []
for k in C:
    d_, t_ = split(C[k]); n_ = N[k]
    def m(t, col, months):
        w = t[t[col] > 0]
        return (t[col] > 0).mean(), w[col].mean(), t[t[col] <= 0][col].mean(), t[col].mean(), len(t) / months * t[col].mean(), len(t) / months
    a, b, c = m(d_, 'Rc', 72), m(t_, 'Rc', 33), m(n_, 'Rf', 35.4)
    rows.append(dict(variant=k, trades_mo=c[5], dev_win=a[0], dev_avgwin=a[1], dev_E=a[3], dev_Rmo=a[4], cfd23_Rmo=b[4],
                     nq_win=c[0], nq_avgwin=c[1], nq_avgloss=c[2], nq_E=c[3], nq_Rmo=c[4]))
df = pd.DataFrame(rows); base = df.iloc[0]
df['beats_base_all3'] = (df.dev_Rmo > base.dev_Rmo) & (df.cfd23_Rmo > base.cfd23_Rmo) & (df.nq_Rmo > base.nq_Rmo)
pd.set_option('display.width', 250)
print(df.round(3).to_string(index=False)); df.to_csv('v10_variants.csv', index=False)
GRID = [(e, f) for e in (350, 500) for f in (200, 250, 300)]
G = {}
def initp(pool): G['pool'] = pool; G['paths'] = block_bootstrap(len(pool), 504, 1500, seed=31)
def jobp(g): return g, prop3.evaluate(G['paths'], G['pool'], *g)
if __name__ == '__main__':
    print('\nProp lifecycle (sizing chosen on dev, reported on NQ 2023-25):')
    for k in ('base', 'cut 0.9R', 'cut 0.75R', 'time-cut 60min <0.0R', 'stop sm0.6 (re-sized)', 'fixed TP 4R (no trail)', 'fixed TP 2R (no trail)'):
        dev, _ = split(C[k]); nq = N[k].assign(sdate=lambda x: pd.to_datetime(x.sdate))
        res = {}
        for which, ds_name, t in (('dev', 'cfd', dev), ('nq', 'nq', nq)):
            with Pool(4, initializer=initp, initargs=(pool_from(ds_name, t),)) as p:
                res[which] = dict(p.map(jobp, GRID))
        g = max(GRID, key=lambda x: res['dev'][x]['pay_24m_mean']); b = res['nq'][g]; a = res['dev'][g]
        print(f"  {k:24s} sizing {g} | DEV payouts/24m ${a['pay_24m_mean']:6.0f} | NQ payouts 12m ${b['pay_12m_mean']:5.0f} (median ${b['pay_12m_median']:5.0f}) 24m ${b['pay_24m_mean']:6.0f} "
              f"| evals/24m {b['evals_24m']:.1f} | 1st payout <=2M {b['p_first_2m']:.0%} <=3M {b['p_first_3m']:.0%} median {b['med_first']:.0f}d")
