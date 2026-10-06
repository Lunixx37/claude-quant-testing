"""Prop (user rules) and live evaluation of the V6 results."""
import numpy as np, pandas as pd
from multiprocessing import Pool
import lab
from v6_wf import load_trades, summarize, live
from prop import block_bootstrap
from prop2 import Policy, Env, run_paths

DS = {}
def ds(name):
    if name not in DS:
        DS[name] = lab.DS(name, '2017-01-01', '2025-12-31')
    return DS[name]

def pool_from(name, t):
    """Day pools for the prop simulator (all RTH days in the trades' period; adverse path from 1-min bars)."""
    d = ds(name); f = d.f
    days = [x for x in d.d.index if t.sdate.min() <= x <= t.sdate.max()]
    by = {x: [] for x in days}
    for r in t.itertuples():
        idx = np.arange(r.e, r.x_i + 1)
        ep = f['o'][r.e] + r.dir * lab.SLIP
        adv = (f['l'][idx] - ep) if r.dir > 0 else (ep - f['h'][idx])
        if r.why == 'stop': adv[-1] = max(adv[-1], r.pts)
        if r.sdate in by: by[r.sdate].append((None, adv, r.pts, r.stop * 4))
    return [by[x] for x in days]

G = {}
def init(pool): G['pool'] = pool; G['paths'] = block_bootstrap(len(pool), 252, 2000, seed=21)
def job(risk): return risk, run_paths(G['paths'], G['pool'], Env(), Policy(risk_usd=risk, no_starve=True), 252)

def kelly(R):
    fs = np.linspace(0.001, 0.3, 300)
    g = [np.mean(np.log1p(f * R)) if (1 + f * R).min() > 0 else -np.inf for f in fs]
    return fs[int(np.argmax(g))]

if __name__ == '__main__':
    TC, TN = load_trades('cfd'), load_trades('nq')
    vbo = ('F7 VolBreakout', (('k', 0.3), ('stopm', 'k')))
    wf = pd.read_pickle('cache/v6_oos_HF_top1.pkl')
    cases = [('WF top-1 OOS 2019-2025 (CFD)', 'cfd', wf, 'Rc'),
             ('VolBreakout k0.3 CFD 2017-2025', 'cfd', TC[vbo].assign(w=1.0, year=TC[vbo].sdate.dt.year), 'Rc'),
             ('VolBreakout k0.3 NQ futures 2023-2025', 'nq', TN[vbo].assign(w=1.0, year=TN[vbo].sdate.dt.year), 'Rf')]
    for lab_, name, t, col in cases:
        s = summarize(t, col)
        k = kelly(t[col].to_numpy())
        print(f"\n=== {lab_}")
        print(f"  trades {s['n']} ({s['trades_month']:.1f}/month), win {s['win']:.1%}, E {s['E']:+.3f}R (t={s['t']:.2f}), avg win {s['avg_win']:.2f}R, "
              f"avg loss {s['avg_loss']:.2f}R, RR {s['rr']:.2f}, positive years {s['pos_years']}/{s['years']}")
        print(f"  Kelly fraction {k:.1%}")
        for rk in (k / 2, 0.01, 0.02):
            lv = live(t, rk, col)
            print(f"  LIVE risk {rk:.2%}/trade: avg return/month {lv['avg_month']:+.2%} (median {lv['median_month']:+.2%}), positive months {lv['pos_months']:.0%}, maxDD {lv['maxdd']:.1%}, CAGR {lv['cagr']:+.1%}")
        pool = pool_from(name, t)
        with Pool(4, initializer=init, initargs=(pool,)) as p:
            res = p.map(job, [150, 250, 350, 500])
        for risk, r in res:
            print(f"  PROP ${risk}/trade: payout <=1M {r['p_pay21']:.1%} <=2M {r['p_pay42']:.1%} <=3M {r['p_pay63']:.1%} <=12M {r['p_payout']:.1%} | "
                  f"median days to 1st payout {r['med_first_pay']:.0f} | eval pass {r['p_pass']:.1%} (median {r['med_ev_days']:.0f} days), eval blown {r['p_ev_blow']:.1%}")
