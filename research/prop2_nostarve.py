from multiprocessing import Pool
from engine import Params
from candidates import FINAL
from prop2 import Policy, Env, run_paths
from prop2_run import build_pool, show
from prop import block_bootstrap
from prop2_final import rolling_hist
H = 252
POLS = [Policy(ev_frac=ef, ev_max=em, fu_frac=ff, fu_min=fmn, fu_max=fmx, stop_after_win=saw, no_starve=True, ev_min=evmin)
        for ef in (0.33, 0.5, 0.75) for em in (10, 20) for evmin in (1, 3)
        for ff, fmn, fmx in ((0, 3, 3), (0, 4, 4), (0, 5, 5), (0, 6, 6), (0.2, 3, 12))
        for saw in (False, True)]
G = {}
def init(pool, paths): G.update(pool=pool, paths=paths)
def job(p): return p, run_paths(G['paths'], G['pool'], Env(), p, H)
def ev(pool, pols, n=1500):
    paths = block_bootstrap(len(pool), H, n, seed=11)
    with Pool(4, initializer=init, initargs=(pool, paths)) as p:
        return p.map(job, pols, chunksize=3)
if __name__ == '__main__':
    for name, kw in {'FINAL': {}, 'cl0.7': dict(cl_min=0.7)}.items():
        prm = Params(**{**FINAL, **kw})
        _, pis, _ = build_pool(prm, 'is'); _, pfw, _ = build_pool(prm, 'forward', allow_forward=True)
        res = ev(pis, POLS)
        bp, b = sorted(res, key=lambda x: -x[1]['p_payout'])[0]
        fw = dict(ev(pfw, [bp]))[bp]
        print(f"\n=== {name} + no-starve | best on IS: {bp}")
        print(f"  IS bootstrap  : payout {b['p_payout']:.1%} pass {b['p_pass']:.1%} evBlow {b['p_ev_blow']:.1%} fuBlow {b['p_fu_blow_before_pay']:.1%}")
        print(f"  2025 bootstrap: payout {fw['p_payout']:.1%} pass {fw['p_pass']:.1%} evBlow {fw['p_ev_blow']:.1%} fuBlow {fw['p_fu_blow_before_pay']:.1%}")
        print(f"  rolling hist IS: payout/pass {rolling_hist(pis, bp)[:2]}  2025: {rolling_hist(pfw, bp)[:2]}")
