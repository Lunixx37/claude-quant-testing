"""Drivers: build day pools for a strategy variant, bootstrap, grid-search the prop policy."""
import sys, itertools, pickle, time
from dataclasses import replace
from multiprocessing import Pool
import numpy as np
from run import backtest, data
from engine import Params, SPLITS
from candidates import FINAL
from prop import block_bootstrap
from prop2 import Env, Policy, run_paths, simulate

def build_pool(params, split, allow_forward=False):
    f = data()
    tr = backtest(params, split, allow_forward=allow_forward)
    a, b = (SPLITS['train'][0], SPLITS['valid'][1]) if split == 'is' else SPLITS[split]
    sd = f['sdate']
    m = (f['mod'] == 570) & (sd >= np.datetime64(a)) & (sd <= np.datetime64(b))
    days = list(np.unique(sd[m]))
    by = {d: [] for d in days}
    h, l = f['h'], f['l']
    for r in tr.itertuples():
        e, d = r.entry, r.dir
        idx = np.arange(r.entry_i, r.exit_i + 1)
        adv = (l[idx] - e) if d > 0 else (e - h[idx])
        fav = (h[idx] - e) if d > 0 else (e - l[idx])
        runner = getattr(r, 'runner_pts', r.pts)
        if not isinstance(runner, float) or runner != runner:
            runner = r.pts
        if r.why == 'stop':
            adv[-1] = max(adv[-1], runner)
        pi = getattr(r, 'part_i', float('nan'))
        if pi == pi and params.partial_r > 0:      # scale-out done: reduce exposure after the fill bar
            k = int(pi) - r.entry_i
            fr = params.partial_frac
            adv = adv.copy()
            adv[k + 1:] = fr * r.part_pts + (1 - fr) * adv[k + 1:]
        by[r.sdate].append((fav, adv, r.pts, r.stop_ticks))
    return days, [by[d] for d in days], tr

_G = {}
def _init(pool, paths, env):
    _G.update(pool=pool, paths=paths, env=env)
def _job(pol):
    return pol, run_paths(_G['paths'], _G['pool'], _G['env'], pol, 252)

def grid(pool, pols, env=Env(), n_paths=2000, seed=11, length=252):
    paths = block_bootstrap(len(pool), length, n_paths, seed=seed)
    with Pool(4, initializer=_init, initargs=(pool, paths, env)) as p:
        return p.map(_job, pols, chunksize=2)

def show(res, top=15, key='p_payout'):
    for pol, r in sorted(res, key=lambda x: -x[1][key])[:top]:
        print(f"  ev {pol.ev_frac:.2f}/max{pol.ev_max:2d} fu {pol.fu_frac:.2f}/max{pol.fu_max:2d} saw={int(pol.stop_after_win)} "
              f"coast={int(pol.ev_coast)} paym={int(pol.fu_payout_mode)} | PAYOUT {r['p_payout']:.1%} pass {r['p_pass']:.1%} "
              f"evBlow {r['p_ev_blow']:.1%} fuBlow {r['p_fu_blow_before_pay']:.1%} evDays {r['med_ev_days']:.0f} "
              f"1stPay day {r['med_first_pay']:.0f} paid ${r['mean_paid']:.0f}")

POLS = [Policy(ev_frac=ef, fu_frac=ff, ev_max=em, fu_max=fm, stop_after_win=saw)
        for ef in (0.10, 0.15, 0.20, 0.25, 0.33) for ff in (0.10, 0.15, 0.20, 0.25, 0.33)
        for em in (10, 20) for fm in (10,) for saw in (False, True)]

if __name__ == '__main__':
    days, pool, tr = build_pool(Params(**FINAL), 'is')
    t = time.time(); res = grid(pool, POLS); print(f'{len(POLS)} policies in {time.time()-t:.0f}s')
    print('FROZEN strategy, IN-SAMPLE bootstrap, 12-month horizon, best policies:')
    show(res)
