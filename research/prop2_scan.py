import sys, numpy as np
from multiprocessing import Pool
from engine import Params
from candidates import FINAL
from prop2 import Policy, Env, run_paths
from prop2_run import build_pool, show
from prop import block_bootstrap
H = int(sys.argv[1]) if len(sys.argv) > 1 else 252
VARIANTS = {'FINAL (kein Scale-out)': {}, 'Scale-out 1R x50%': dict(partial_r=1.0, partial_frac=0.5),
            'Scale-out 1R x33%': dict(partial_r=1.0, partial_frac=0.33), 'Scale-out 0.75R x50%': dict(partial_r=0.75, partial_frac=0.5)}
POLS = [Policy(ev_frac=ef, ev_max=em, ev_min=1, fu_frac=ff, fu_min=fmn, fu_max=fmx, stop_after_win=saw)
        for ef in (0.15, 0.25, 0.33) for em in (10, 16)
        for ff, fmn, fmx in ((0.0, 6, 6), (0.0, 8, 8), (0.0, 10, 10), (0.0, 12, 12), (0.15, 4, 12), (0.25, 4, 16))
        for saw in (False, True)]
G = {}
def init(pool, paths): G.update(pool=pool, paths=paths)
def job(p): return p, run_paths(G['paths'], G['pool'], Env(), p, H)
if __name__ == '__main__':
    for name, kw in VARIANTS.items():
        _, pool, tr = build_pool(Params(**{**FINAL, **kw}), 'is')
        paths = block_bootstrap(len(pool), H, 1500, seed=11)
        with Pool(4, initializer=init, initargs=(pool, paths)) as p:
            res = p.map(job, POLS, chunksize=2)
        print(f'\n=== {name} | IS bootstrap | horizon {H} days ==='); show(res, top=3)
