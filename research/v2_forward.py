"""ONE-TIME 2025 run of the frozen V2_FINAL (pseudo-OOS, see PROTOCOL_V2.md)."""
from dataclasses import replace
import numpy as np, pandas as pd
from multiprocessing import Pool
from run import backtest, report
from engine import Params, stats
from candidates import V2_FINAL
from prop2 import Policy, Env, run_paths, simulate
from prop2_run import build_pool
from prop import block_bootstrap
p = Params(**V2_FINAL)
for sp, lab in (('train', 'TRAIN'), ('valid', 'VALIDATION'), ('is', 'IN-SAMPLE')):
    report(backtest(p, sp), f'V2 {lab}')
tr = backtest(p, 'forward', allow_forward=True)
report(tr, 'V2 FORWARD 2025 (pseudo-OOS, one run)')
tr.to_csv('v2_forward_trades.csv', index=False)
for k, g in tr.groupby('kind'):
    print('  kind', k, stats(g)['n'], 'E', round(g.R.mean(), 3))
for sl in (2, 3):
    s = stats(backtest(replace(p, slip_ticks=sl), 'forward', allow_forward=True)); print(f'  2025 slippage {sl}t: PF {s["pf"]} E {s["expR"]}')
pol = Policy(risk_usd=250, no_starve=True)
G = {}
def init(pool, paths): G.update(pool=pool, paths=paths)
def job(x): return run_paths(G['paths'], G['pool'], Env(), x, 252)
for split, af in (('is', False), ('forward', True)):
    _, pool, _ = build_pool(p, split, allow_forward=af)
    paths = block_bootstrap(len(pool), 252, 2000, seed=21)
    with Pool(1, initializer=init, initargs=(pool, paths)) as pp:
        r = pp.map(job, [pol])[0]
    hist = []
    for s0 in range(0, len(pool) - 21, 5):
        ok, evd, fp, pays, dead = simulate(list(range(s0, len(pool))), pool, Env(), pol, 252)
        hist.append((ok, fp))
    h = np.array(hist, dtype=float)
    print(f"PROP $250/trade [{split}] bootstrap: payout<=42d {r['p_pay42']:.1%} <=63d {r['p_pay63']:.1%} <=252d {r['p_payout']:.1%} "
          f"pass {r['p_pass']:.1%} medEvalDays {r['med_ev_days']:.0f} med1stPay {r['med_first_pay']:.0f} | historical starts: "
          f"pass {h[:,0].mean():.1%} payout {(h[:,1]>0).mean():.1%} payout<=42d {((h[:,1]>0)&(h[:,1]<=42)).mean():.1%} (n={len(h)})")
