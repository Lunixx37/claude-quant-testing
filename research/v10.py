"""V10: early loss cutting (price / time), tighter stops with re-sizing, ideal fixed RR (PROTOCOL_V10.md)."""
import math, pickle, sys, time
import numpy as np, pandas as pd
from multiprocessing import Pool
import lab, vbo_sess as V

K, MAXTR, LAG = 0.35, 2, 1.25


def sim10(f, e, d, R, cut, tmin, tthr, tp_r, trail, deadline):
    o, h, l, c = f['o'], f['h'], f['l'], f['c']
    ep = o[e] + d * lab.SLIP
    st = ep - d * cut * R
    tp = ep + d * tp_r * R if tp_r > 0 else np.nan
    k, mfe, mae, k_mae = e, 0.0, 0.0, e
    while True:
        fav = (h[k] - ep) if d == 1 else (ep - l[k])
        adv = (l[k] - ep) if d == 1 else (ep - h[k])
        mfe = max(mfe, fav)
        if (d == 1 and l[k] <= st) or (d == -1 and h[k] >= st):
            gap = (o[k] <= st) if d == 1 else (o[k] >= st)
            x, why = (o[k] if gap else st) - d * lab.SLIP, 'stop'
            adv = max(adv, (x - ep) * d)                 # on the stop bar the open loss cannot exceed the fill
            if adv < mae:
                mae, k_mae = adv, k
            break
        if adv < mae:
            mae, k_mae = adv, k
        if not np.isnan(tp) and ((d == 1 and h[k] >= tp + lab.TICK) or (d == -1 and l[k] <= tp - lab.TICK)):
            x, why = tp, 'tp'; break
        if k >= deadline:
            x, why = c[k] - d * lab.SLIP, 'time'; break
        if tmin > 0 and k - e + 1 == tmin and (c[k] - ep) * d < tthr * R:
            x, why = c[k] - d * lab.SLIP, 'tcut'; break
        if trail:
            m = math.floor(mfe / R + 1e-9)
            if m >= 1:
                ns = ep + d * (m - LAG) * R
                if (d == 1 and ns > st) or (d == -1 and ns < st):
                    st = ns
        k += 1
    return ep, x, k, why, mae / R, mfe / R, k_mae - e


def run10(S, sm=0.75, cut=1.0, tmin=0, tthr=0.0, tp_r=0.0, trail=True):
    f = S.ds.f; o, h, l = f['o'], f['h'], f['l']
    out = []
    prev_rng = np.nan
    for s, e in S.sessions:
        a, b = S.win(s, e, 930, 1320)
        if b - a < 200:
            continue
        rg = prev_rng
        prev_rng = h[a:b].max() - l[a:b].min()
        if not (rg > 0):
            continue
        deadline = b - 1
        up, dn = o[a] + K * rg, o[a] - K * rg
        R = sm * K * rg
        n_tr, i = 0, a
        while i < deadline and n_tr < MAXTR:
            dd = 1 if h[i] >= up else -1 if l[i] <= dn else 0
            if dd == 0:
                i += 1; continue
            ep, x, xi, why, mae, mfe, tm = sim10(f, i + 1, dd, R, cut, tmin, tthr, tp_r, trail, deadline)
            pts = (x - ep) * dd
            out.append((f['sdate'][i + 1], i + 1, xi, dd, R * cut, pts, why, mae, mfe, tm, xi - i,
                        (pts - lab.SPREAD) / R, (pts - lab.COMM) / R))
            n_tr += 1; i = xi + 1
    # 'stop' column = actual initial stop distance (used for prop sizing); R columns in units of R = sm*k*range
    return pd.DataFrame(out, columns=['sdate', 'e', 'x_i', 'dir', 'stop', 'pts', 'why', 'mae_R', 'mfe_R', 't_mae', 'dur', 'Rc', 'Rf'])


CFGS = [('base', {})] + [(f'cut {c}R', dict(cut=c)) for c in (0.3, 0.4, 0.5, 0.6, 0.75, 0.9)] + \
       [(f'time-cut {t}min <{thr}R', dict(tmin=t, tthr=thr)) for t in (5, 10, 15, 30, 60) for thr in (0.0, 0.25)] + \
       [(f'stop sm{s} (re-sized)', dict(sm=s)) for s in (0.4, 0.5, 0.6, 1.0)] + \
       [(f'fixed TP {r}R (no trail)', dict(tp_r=r, trail=False)) for r in (0.5, 0.75, 1, 1.5, 2, 2.5, 3, 4, 5)] + \
       [('no TP, no trail (EOD)', dict(trail=False))]
G = {}


def init(name, a, b):
    G['S'] = V.Sess(lab.DS(name, a, b))


def job(c):
    return c[0], run10(G['S'], **c[1])


if __name__ == '__main__':
    name, a, b = sys.argv[1:4]
    t0 = time.time()
    with Pool(4, initializer=init, initargs=(name, a, b)) as p:
        res = dict(p.map(job, CFGS))
    pickle.dump(res, open(f'cache/v10_trades_{name}.pkl', 'wb'))
    print(name, len(res), f'{time.time()-t0:.0f}s')
