import sys, numpy as np
from multiprocessing import Pool
from engine import Params, stats
from run import backtest
from prop2 import Policy, Env, run_paths
from prop2_run import build_pool
from prop import block_bootstrap
from v2_candidates import V2C
H = 252
POL = Policy(risk_usd=250, stop_after_win=False, no_starve=True)
POL_SAW = Policy(risk_usd=250, stop_after_win=True, no_starve=True)
G = {}
def init(pool, paths): G.update(pool=pool, paths=paths)
def job(p): return run_paths(G['paths'], G['pool'], Env(), p, H)
if __name__ == '__main__':
    split = sys.argv[1] if len(sys.argv) > 1 else 'is'
    for name, kw in V2C.items():
        prm = Params(**kw)
        rows = []
        for sp in ('train', 'valid'):
            s = stats(backtest(prm, sp)); rows.append(f"{sp} n={s['n']} PF={s['pf']:.2f} E={s['expR']:+.3f} DD={s['maxdd_R']}")
        _, pool, tr = build_pool(prm, split)
        paths = block_bootstrap(len(pool), H, 2000, seed=21)
        with Pool(2, initializer=init, initargs=(pool, paths)) as p:
            r1, r2 = p.map(job, [POL, POL_SAW])
        print(f"\n{name}\n  {rows[0]} | {rows[1]}")
        for lab, r in (('$250/trade', r1), ('$250 + stop after win', r2)):
            print(f"  prop {lab:22s}: payout<=21d {r['p_pay21']:.1%} <=42d {r['p_pay42']:.1%} <=63d {r['p_pay63']:.1%} <=252d {r['p_payout']:.1%} | pass {r['p_pass']:.1%} evBlow {r['p_ev_blow']:.1%} medEvalDays {r['med_ev_days']:.0f}")
