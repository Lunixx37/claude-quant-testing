"""Prop sizing per phase for the refined VBO bot candidates: choose on CFD 2017-2022, report on NQ 2023-2025."""
import numpy as np, pandas as pd
from multiprocessing import Pool
from v6_wf import load_trades
from v6_eval import pool_from
from prop import block_bootstrap
from prop2 import Policy, Env, run_paths
G = {}
def init(pool): G['pool'] = pool; G['paths'] = block_bootstrap(len(pool), 252, 2000, seed=21)
def job(p): return p, run_paths(G['paths'], G['pool'], Env(), Policy(risk_ev=p[0], risk_fu=p[1], no_starve=True), 252)
GRID = [(e, f) for e in (250, 350, 500) for f in (100, 150, 200, 250)]
if __name__ == '__main__':
    TC, TN = load_trades('cfd'), load_trades('nq')
    for side in ('both', 'long'):
        key = ('F7b VBO refined', (('filt', 'none'), ('k', 0.3), ('side', side), ('sm', 1.0), ('tgt', 'trail')))
        tc = TC[key]; dev = tc[tc.sdate < '2023-01-01']; tn = TN[key]
        res = {}
        for lab_, name, t in (('dev CFD 2017-22', 'cfd', dev), ('NQ 2023-25', 'nq', tn)):
            with Pool(4, initializer=init, initargs=(pool_from(name, t),)) as p:
                res[lab_] = dict(p.map(job, GRID))
        best = max(GRID, key=lambda g: res['dev CFD 2017-22'][g]['p_pay63'] + res['dev CFD 2017-22'][g]['p_payout'])
        print(f'\n=== VBO k0.3 trail, side={side}: prop rules of the user (eval $ risk / funded $ risk)')
        for g in GRID:
            a, b = res['dev CFD 2017-22'][g], res['NQ 2023-25'][g]
            mark = '  <== chosen on dev' if g == best else ''
            print(f"  eval ${g[0]} / funded ${g[1]}: DEV payout<=2M {a['p_pay42']:.1%} <=3M {a['p_pay63']:.1%} <=12M {a['p_payout']:.1%} | "
                  f"NQ 23-25 payout<=1M {b['p_pay21']:.1%} <=2M {b['p_pay42']:.1%} <=3M {b['p_pay63']:.1%} <=12M {b['p_payout']:.1%} "
                  f"median days {b['med_first_pay']:.0f}, pass {b['p_pass']:.0%} (median {b['med_ev_days']:.0f}d){mark}")
