import sys, numpy as np
from multiprocessing import Pool
from engine import Params
from candidates import FINAL
from prop2 import Policy, Env, run_paths
from prop2_run import build_pool, show
from prop import block_bootstrap
H = 252
POLS = [Policy(ev_frac=ef, ev_max=em, fu_frac=ff, fu_min=fmn, fu_max=fmx, stop_after_win=saw)
        for ef in (0.25, 0.33, 0.5, 0.75, 1.0) for em in (10, 20, 30)
        for ff, fmn, fmx in ((0, 3, 3), (0, 4, 4), (0, 5, 5), (0, 6, 6), (0, 8, 8), (0.1, 3, 10), (0.2, 3, 12), (0.33, 3, 20))
        for saw in (False, True)]
G = {}
def init(pool, paths): G.update(pool=pool, paths=paths)
def job(p): return p, run_paths(G['paths'], G['pool'], Env(), p, H)
def shift_pool(pool, add_pts):
    """Hypothetical: add a constant edge (points) to every trade's final result (diagnostic only)."""
    return [[(f, a, pts + add_pts, rt) for (f, a, pts, rt) in day] for day in pool]
if __name__ == '__main__':
    kw = dict(partial_r=1.0, partial_frac=0.5) if 'scale' in sys.argv else {}
    _, pool, tr = build_pool(Params(**{**FINAL, **kw}), 'is')
    paths = block_bootstrap(len(pool), H, 1500, seed=11)
    with Pool(4, initializer=init, initargs=(pool, paths)) as p:
        res = p.map(job, POLS, chunksize=4)
    print(f'=== real IS trades {"(scale-out)" if kw else "(FINAL)"}: {len(POLS)} policies, best:'); show(res, top=4)
    best = sorted(res, key=lambda x: -x[1]['p_payout'])[:6]
    for addR in (0.1, 0.2, 0.3, 0.5):
        sp = shift_pool(pool, addR * 25)
        with Pool(4, initializer=init, initargs=(sp, paths)) as p:
            r2 = p.map(job, POLS, chunksize=4)
        top = sorted(r2, key=lambda x: -x[1]['p_payout'])[0]
        print(f'HYPOTHETICAL edge +{addR}R/trade (E={tr.R.mean()+addR:.2f}R): best P(payout 12m) = {top[1]["p_payout"]:.1%}  pass {top[1]["p_pass"]:.1%}')
