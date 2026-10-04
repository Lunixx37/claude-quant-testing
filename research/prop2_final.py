import sys, pickle, numpy as np
from multiprocessing import Pool
from engine import Params
from candidates import FINAL
from prop2 import Policy, Env, run_paths
from prop2_run import build_pool, show
from prop import block_bootstrap
H = 252
POLS = [Policy(ev_frac=ef, ev_max=em, fu_frac=ff, fu_min=fmn, fu_max=fmx, stop_after_win=saw)
        for ef in (0.33, 0.5, 0.75) for em in (10, 20)
        for ff, fmn, fmx in ((0, 3, 3), (0, 4, 4), (0, 5, 5), (0, 6, 6), (0.2, 3, 12), (0.33, 3, 20))
        for saw in (False, True)]
VARIANTS = {'FINAL': {}, 'FINAL+scale1R': dict(partial_r=1.0, partial_frac=0.5),
            'cl0.7': dict(cl_min=0.7), 'cl0.7+scale1R': dict(cl_min=0.7, partial_r=1.0, partial_frac=0.5)}
G = {}
def init(pool, paths): G.update(pool=pool, paths=paths)
def job(p): return p, run_paths(G['paths'], G['pool'], Env(), p, H)
def evalpool(pool, pols, seed=11, n=1500):
    paths = block_bootstrap(len(pool), H, n, seed=seed)
    with Pool(4, initializer=init, initargs=(pool, paths)) as p:
        return p.map(job, pols, chunksize=3)
def rolling_hist(pool, pol, step=5):
    """Historical (non-bootstrapped) accounts started every `step` days; horizon truncated at data end."""
    from prop2 import simulate
    out = []
    for s in range(0, len(pool) - 60, step):
        seq = list(range(s, len(pool)))
        ok, evd, fp, pays, dead = simulate(seq, pool, Env(), pol, H)
        out.append((fp > 0, ok, len(seq)))
    a = np.array(out, dtype=float)
    return a[:, 0].mean(), a[:, 1].mean(), len(a), np.median(a[:, 2])
if __name__ == '__main__':
    summary = {}
    for name, kw in VARIANTS.items():
        prm = Params(**{**FINAL, **kw})
        _, pis, tis = build_pool(prm, 'is')
        _, pfw, tfw = build_pool(prm, 'forward', allow_forward=True)
        res = evalpool(pis, POLS)
        best_pol, best = sorted(res, key=lambda x: -x[1]['p_payout'])[0]
        fw = dict(evalpool(pfw, [best_pol]))[best_pol]
        rh = rolling_hist(pfw, best_pol)
        rhi = rolling_hist(pis, best_pol)
        summary[name] = (best_pol, best, fw, rh, rhi, tis.R.mean(), tfw.R.mean())
        print(f"\n=== {name}: E/trade IS {tis.R.mean():+.3f} (n={len(tis)}) | 2025 {tfw.R.mean():+.3f} (n={len(tfw)})")
        print(f"  best policy (chosen on IS): {best_pol}")
        print(f"  IS bootstrap  : P(payout 12m) {best['p_payout']:.1%}  pass {best['p_pass']:.1%}  median eval days {best['med_ev_days']:.0f}  1st payout day {best['med_first_pay']:.0f}")
        print(f"  2025 bootstrap: P(payout 12m) {fw['p_payout']:.1%}  pass {fw['p_pass']:.1%}  median eval days {fw['med_ev_days']:.0f}  1st payout day {fw['med_first_pay']:.0f}")
        print(f"  historical rolling starts IS : payout {rhi[0]:.1%} pass {rhi[1]:.1%} ({rhi[2]} starts, median remaining days {rhi[3]:.0f})")
        print(f"  historical rolling starts 2025: payout {rh[0]:.1%} pass {rh[1]:.1%} ({rh[2]} starts, median remaining days {rh[3]:.0f}, truncated at 2025-12-11)")
    pickle.dump(summary, open('cache/prop2_summary.pkl', 'wb'))
