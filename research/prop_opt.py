"""Optimise the prop layer (sizing + day rule) on IN-SAMPLE days only, then check 2025."""
import sys, math, json, time
from multiprocessing import Pool
import numpy as np
from prop import (TEMPLATES, Sizing, day_pool, block_bootstrap, run_account, evaluate)

N_PATHS, H = 2000, 252
SIZINGS = ([Sizing('fixed', n=n) for n in (1, 2, 3, 4, 5, 6, 8, 10)] +
           [Sizing('buf', frac=f, nmax=m) for f in (0.15, 0.20, 0.25, 0.33, 0.50) for m in (10, 20)])
SIZINGS += [Sizing(s.mode, s.n, s.frac, s.nmax, 'stop_after_win') for s in SIZINGS]

_G = {}
def init(split, allow_fwd, seed):
    days, pool, _ = day_pool(split, allow_fwd)
    _G['pool'] = pool
    _G['paths'] = block_bootstrap(len(pool), H, N_PATHS, seed=seed)

def phase_stats(args):
    tkey, sz, phase = args
    rules, pool = TEMPLATES[tkey], _G['pool']
    out = []
    for seq in _G['paths']:
        r = run_account(seq, pool, rules, sz, phase, H)
        out.append((r['ok'], r['dead'], r['days'], sum(r['payouts']) * rules.split, len(r['payouts'])))
    a = np.array(out, dtype=float)
    ok = a[:, 0] == 1
    if phase == 'eval':
        fees = np.ceil(a[:, 2] / 21) * rules.fee_month + ok * rules.activation
        return tkey, sz, phase, dict(p_pass=ok.mean(), p_fail=a[:, 1].mean(),
                    med_days=float(np.median(a[ok, 2])) if ok.any() else np.nan, fees=fees.mean())
    return tkey, sz, phase, dict(pay=a[:, 3].mean(), p_payout=(a[:, 4] > 0).mean(), n_pay=a[:, 4].mean(),
                p_blow=a[:, 1].mean(), med_pay=float(np.median(a[:, 3])))

def run_grid(split, allow_fwd=False, seed=1, sizings=SIZINGS, templates=TEMPLATES):
    jobs = [(t, s, ph) for t in templates for s in sizings for ph in ('eval', 'fund')]
    with Pool(4, initializer=init, initargs=(split, allow_fwd, seed)) as p:
        res = p.map(phase_stats, jobs, chunksize=4)
    return res

def combine(res):
    ev, fu = {}, {}
    for t, s, ph, d in res:
        (ev if ph == 'eval' else fu)[(t, s)] = d
    table = {}
    for t in TEMPLATES:
        rows = []
        for se in [s for (tt, s) in ev if tt == t]:
            for sf in [s for (tt, s) in fu if tt == t]:
                e, f = ev[(t, se)], fu[(t, sf)]
                rows.append((e['p_pass'] * f['pay'] - e['fees'], se, sf))
        table[t] = sorted(rows, key=lambda x: -x[0])
    return ev, fu, table

if __name__ == '__main__':
    t0 = time.time()
    res = run_grid('is')
    ev, fu, table = combine(res)
    print(f'grid done in {time.time()-t0:.0f}s')
    for t in TEMPLATES:
        print(f'\n######## {TEMPLATES[t].name}  (IN-SAMPLE bootstrap, {N_PATHS} paths, horizon {H} days/phase)')
        print('EVAL phase:')
        for s in sorted([s for (tt, s) in ev if tt == t], key=lambda s: -ev[(t, s)]['p_pass'])[:12]:
            d = ev[(t, s)]; print(f"  {s.label():38s} pass={d['p_pass']:.1%} blown={d['p_fail']:.1%} median days={d['med_days']:.0f} fees=${d['fees']:.0f}")
        print('FUNDED phase (252 days, payouts after split):')
        for s in sorted([s for (tt, s) in fu if tt == t], key=lambda s: -fu[(t, s)]['pay'])[:12]:
            d = fu[(t, s)]; print(f"  {s.label():38s} E[payout]=${d['pay']:.0f} median=${d['med_pay']:.0f} P(>=1 payout)={d['p_payout']:.1%} blown={d['p_blow']:.1%}")
        print('Best combinations by EV per attempt (P(pass)*E[payout] - fees):')
        for evv, se, sf in table[t][:5]:
            print(f"  EV=${evv:7.0f}  eval: {se.label():36s} funded: {sf.label()}")
    import pickle; pickle.dump((ev, fu, table), open('cache/prop_is.pkl', 'wb'))
