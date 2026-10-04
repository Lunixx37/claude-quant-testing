import sys
from dataclasses import replace
from multiprocessing import Pool
from run import backtest
from engine import Params, stats
from candidates import FINAL as BASE
GRID = {
 'rv_min': [1.0, 1.25, 1.5, 2.0, 2.5],
 'wick_min': [0.3, 0.4, 0.5],
 'cl_min': [0.5, 0.6, 0.7],
 'pen_min_ticks': [2, 4, 8, 12],
 'pen_max_ticks': [40, 60, 80, 100],
 'setup_bars': [5, 10, 15, 20],
 'disp_body': [0.3, 0.5, 0.6],
 'disp_cl': [0.6, 0.7, 0.8],
 'band_k': [(1.0,), (2.0,), (1.0, 2.0), (1.0, 2.0, 3.0), (0.5, 1.0, 2.0)],
 'mult_pct': [(), (0.25,), (0.5,), (0.25, 0.5), (1.0,)],
 'use_rth_vwap': [True, False],
 'win_end': [600, 630, 660, 690, 720],
 'stop_ticks': [60, 80, 90, 100, 110, 120, 150],
 'struct_buffer_ticks': [0, 4, 8, 16],
 'trail_lag': [1.0, 1.25, 1.5, 1.75],
 'use_hp': [True, False],
 'touch_ticks': [2, 4, 8],
 'er_max': [0.0, 0.8, 1.0, 1.25, 1.5],
 'slip_ticks': [1, 2, 3],
 'comm_rt': [4.5, 6.0, 9.0],
 'struct_ref_ticks': [80, 90, 100, 110, 120],
 'allow_long': [True, False],
 'allow_short': [True, False],
}
def one(a):
    k, v, split, base = a
    p = replace(Params(**base), **{k: v})
    s = stats(backtest(p, split))
    return k, v, s
if __name__ == '__main__':
    split = sys.argv[1] if len(sys.argv) > 1 else 'train'
    jobs = [(k, v, split, BASE) for k, vs in GRID.items() for v in vs]
    with Pool(4) as pool:
        res = pool.map(one, jobs)
    cur = None
    for k, v, s in res:
        if k != cur: print(f'-- {k}'); cur = k
        mark = ' <base' if v == getattr(Params(**BASE), k) else ''
        print(f"   {str(v):18s} n={s['n']:3d} pf={s['pf']:.2f} E={s['expR']:+.3f} dd={s['maxdd_R']:5.1f} net=${s['net_usd']:.0f}{mark}")
