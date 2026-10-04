"""Engine integrity checks: lookahead (truncation test), trade limit, window, fills, flat at EOD."""
import numpy as np, pandas as pd, sys
from run import data, backtest
from engine import Params, run, TICK

def audit(p, split='train', ntrunc=40, seed=1):
    f = data()
    tr = backtest(p, split)
    ok = True
    def chk(cond, msg):
        nonlocal ok
        print(('PASS ' if cond else 'FAIL ') + msg); ok &= bool(cond)
    chk(tr.groupby('sdate').size().max() <= p.max_trades, f'max {p.max_trades} trades per NY date')
    chk(((tr.sig_min >= p.win_start) & (tr.sig_min < p.win_end)).all(), 'all signals inside NY window')
    chk((tr.entry_i == tr.sig_i + 1).all(), 'entry = bar after signal (market, next open)')
    exp = f['o'][tr.entry_i] + tr.dir * p.slip_ticks * TICK
    chk(np.allclose(tr.entry, exp), 'entry price = next open + slippage')
    chk((f['sdate'][tr.exit_i] == f['sdate'][tr.entry_i]).all(), 'no overnight: exit same NY date as entry')
    chk((f['mod'][tr.exit_i] <= p.flat_time).all() | f['last'][tr.exit_i].all(), 'exit not after flat time')
    ov = (tr.entry_i.values[1:] <= tr.exit_i.values[:-1]).sum()
    chk(ov == 0, 'no overlapping positions')
    chk(set(tr.stop_ticks) <= {p.stop_ticks, p.hp_stop_ticks}, 'initial stops are 100 / 50 ticks only')
    worst = tr.R.min(); chk(worst > -1.0 - (2 * p.slip_ticks * TICK * 20 + p.comm_rt) / (p.hp_stop_ticks * TICK * 20) - 2,
                            f'worst trade {worst:.2f}R (gap risk bounded)')
    # truncation test: cut the data at random bars; every trade signalled before the cut must be identical
    rng = np.random.default_rng(seed)
    full = run(f, p, '2023-02-01', '2024-06-30')
    cuts = rng.choice(full.sig_i.values, size=min(ntrunc, len(full)), replace=False)
    bad = 0
    for cut in cuts:
        g = {k: v[:cut + 1] for k, v in f.items()}
        part = run(g, p, '2023-02-01', '2024-06-30')
        a = full[full.sig_i <= cut][['sig_i', 'dir', 'tier', 'stop_ticks', 'level']].reset_index(drop=True)
        b = part[['sig_i', 'dir', 'tier', 'stop_ticks', 'level']].reset_index(drop=True)
        # the last signal at cut has no fill bar in truncated data -> compare signals before cut
        a = a[a.sig_i < cut].reset_index(drop=True); b = b[b.sig_i < cut].reset_index(drop=True)
        if not a.equals(b): bad += 1
    chk(bad == 0, f'truncation (no-lookahead) test on {len(cuts)} random cut points')
    return ok

if __name__ == '__main__':
    print('ALL OK' if audit(Params()) else 'AUDIT FAILED')
