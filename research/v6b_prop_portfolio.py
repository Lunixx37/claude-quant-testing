"""Prop with the honest walk-forward top-5 portfolio stream (CFD, OOS 2019-2025). Trades of different
strategies on the same day are processed in time order (intraday overlap approximated as sequential)."""
import numpy as np, pandas as pd
from multiprocessing import Pool
from v6_eval import pool_from
from prop import block_bootstrap
from prop2 import Policy, Env, run_paths
G = {}
def init(pool): G['pool'] = pool; G['paths'] = block_bootstrap(len(pool), 252, 2000, seed=21)
def job(p): return p, run_paths(G['paths'], G['pool'], Env(), Policy(risk_ev=p[0], risk_fu=p[1], no_starve=True), 252)
GRID = [(e, f) for e in (150, 250, 350) for f in (75, 100, 150, 200)]
if __name__ == '__main__':
    o = pd.read_pickle('cache/v6_oos_HF_top5.pkl')
    s = o[o.sdate < '2023-01-01']; t = o[o.sdate >= '2023-01-01']
    res = {}
    for lab_, d in (('OOS 2019-22', s), ('OOS 2023-25', t)):
        with Pool(4, initializer=init, initargs=(pool_from('cfd', d),)) as p:
            res[lab_] = dict(p.map(job, GRID))
    best = max(GRID, key=lambda g: res['OOS 2019-22'][g]['p_pay63'] + res['OOS 2019-22'][g]['p_payout'])
    print('Walk-forward top-5 portfolio (~66 trades/month), user prop rules, $ risk per trade eval/funded:')
    for g in GRID:
        a, b = res['OOS 2019-22'][g], res['OOS 2023-25'][g]
        print(f"  eval ${g[0]} / funded ${g[1]}: 2019-22 payout<=2M {a['p_pay42']:.1%} <=3M {a['p_pay63']:.1%} <=12M {a['p_payout']:.1%} | "
              f"2023-25 payout<=1M {b['p_pay21']:.1%} <=2M {b['p_pay42']:.1%} <=3M {b['p_pay63']:.1%} <=12M {b['p_payout']:.1%} median days {b['med_first_pay']:.0f} pass {b['p_pass']:.0%}{'  <== chosen on 2019-22' if g == best else ''}")
