"""V9: POI targets + step trailing on the V7 M1 entries (PROTOCOL_V9.md)."""
import math, pickle, sys, time
import numpy as np, pandas as pd
from multiprocessing import Pool
import lab, vbo_sess as V

K, SM, MAXTR = 0.35, 0.75, 2


def session_pois(S):
    """Per session: dict of POI lists known before 09:30 (and entry), plus the entry-relevant arrays."""
    ds = S.ds; f, df = ds.f, ds.df
    o, h, l, c = f['o'], f['h'], f['l'], f['c']
    v = df.v.to_numpy(dtype=float); p3 = (h + l + c) / 3
    sd = pd.to_datetime(f['sdate'][[s for s, _ in S.sessions]])
    week = sd.to_period('W-SUN')
    out = []
    prev = None
    nwog = None
    wk_hl = {}
    for (s, e), dt, wk in zip(S.sessions, sd, week):
        ra, rb = S.win(s, e, 930, 1320)
        oa, ob = S.win(s, e, 0, 930)
        aa, ab = S.win(s, e, 0, 540)
        la, lb = S.win(s, e, 540, 930)
        P = {'liq': [], 'gap': [], 'poc': []}
        if ob > oa:
            P['liq'] += [h[oa:ob].max(), l[oa:ob].min()]
        if ab > aa:
            P['liq'] += [h[aa:ab].max(), l[aa:ab].min()]
        if lb > la:
            P['liq'] += [h[la:lb].max(), l[la:lb].min()]
        if prev is not None:
            P['liq'] += [prev['rth_h'], prev['rth_l']]
            P['gap'] += [c[s - 1], o[s]]                                      # NDOG edges
            if prev['poc'] is not None:
                P['poc'] += [prev['poc']]
        pw = wk_hl.get(wk - 1)
        if pw is not None:
            P['liq'] += list(pw)
        # NWOG: first session of this week vs last close of the previous week
        if prev is not None and prev['week'] != wk:
            nwog = (c[s - 1], o[s])
        if nwog is not None:
            P['gap'] += list(nwog)
        rth = (ra, rb) if rb - ra > 200 else None
        rec = dict(s=s, e=e, P=P, rth=rth, prev_range=prev['rng'] if prev else np.nan)
        out.append(rec)
        # update state with this session's completed values (used from the next session on)
        if rth is not None:
            pr = p3[ra:rb]; vv = v[ra:rb]
            w = max(0.25, round(c[rb - 1] * 0.0002 / 0.25) * 0.25)
            bins = np.floor(pr / w)
            u, inv = np.unique(bins, return_inverse=True)
            poc = (u[np.argmax(np.bincount(inv, weights=vv))] + 0.5) * w
            prev = dict(rth_h=h[ra:rb].max(), rth_l=l[ra:rb].min(), rng=h[ra:rb].max() - l[ra:rb].min(), poc=poc, week=wk)
        elif prev is not None:
            prev = dict(prev, week=wk)
        hl = wk_hl.get(wk)
        wk_hl[wk] = (max(hl[0], h[s:e].max()), min(hl[1], l[s:e].min())) if hl else (h[s:e].max(), l[s:e].min())
    return out


def sim(f, e, d, sp, tp_pts, deadline, step, lag):
    o, h, l, c = f['o'], f['h'], f['l'], f['c']
    ep = o[e] + d * lab.SLIP
    st = ep - d * sp
    tp = ep + d * tp_pts if tp_pts > 0 else np.nan
    k, mfe = e, 0.0
    while True:
        mfe = max(mfe, (h[k] - ep) if d == 1 else (ep - l[k]))
        if (d == 1 and l[k] <= st) or (d == -1 and h[k] >= st):
            gap = (o[k] <= st) if d == 1 else (o[k] >= st)
            x, why = (o[k] if gap else st) - d * lab.SLIP, 'stop'; break
        if not np.isnan(tp) and ((d == 1 and h[k] >= tp + lab.TICK) or (d == -1 and l[k] <= tp - lab.TICK)):
            x, why = tp, 'tp'; break
        if k >= deadline:
            x, why = c[k] - d * lab.SLIP, 'time'; break
        if step > 0:
            m = math.floor(mfe / (step * sp) + 1e-9) * step
            if m > 0:
                ns = ep + d * (m - lag) * sp
                if (d == 1 and ns > st) or (d == -1 and ns < st):
                    st = ns
        k += 1
    return ep, x, k, why


def run(S, pois, tset, minR, step, lag):
    f = S.ds.f
    o, h, l = f['o'], f['h'], f['l']
    out = []
    for rec in pois:
        s, e = rec['s'], rec['e']
        rg = rec['prev_range']
        if not (rg > 0):
            continue
        a, b = S.win(s, e, 930, 1320)
        if b - a < 200:
            continue
        deadline = b - 1
        up, dn = o[a] + K * rg, o[a] - K * rg
        sp = SM * K * rg
        lv = []
        if tset != 'none':
            for key in (('liq', 'gap', 'poc') if tset == 'all' else (tset,)):
                if key in rec['P']:
                    lv += rec['P'][key]
        n_tr, i, last_exit = 0, a, -1
        while i < deadline and n_tr < MAXTR:
            dd = 1 if h[i] >= up else -1 if l[i] <= dn else 0
            if dd == 0:
                i += 1; continue
            ep0 = o[i + 1] + dd * lab.SLIP
            tp_pts = 0.0
            if tset != 'none':
                cand = [(x - ep0) * dd for x in lv]
                if tset in ('round', 'all'):
                    base = math.floor(ep0 / 500) * 500
                    cand += [(base + j * 500 - ep0) * dd for j in range(-6, 8)]
                cand = [x for x in cand if minR * sp <= x <= 8 * sp]
                tp_pts = min(cand) if cand else 0.0
            ep, x, xi, why = sim(f, i + 1, dd, sp, tp_pts, deadline, step, lag)
            pts = (x - ep) * dd
            out.append((f['sdate'][i + 1], i + 1, xi, dd, sp, pts, why, tp_pts / sp, (pts - lab.SPREAD) / sp, (pts - lab.COMM) / sp))
            n_tr += 1; i = xi + 1
    return pd.DataFrame(out, columns=['sdate', 'e', 'x_i', 'dir', 'stop', 'pts', 'why', 'tpR', 'Rc', 'Rf'])


TRAILS = [('base s1 lag1.25', 1.0, 1.25), ('no trail', 0.0, 0.0)] + \
         [(f's{s} lag{g}', s, g) for s in (0.25, 0.5, 0.75) for g in (0.5, 0.75, 1.0)]
TARGETS = [('none', 0.0)] + [(t, m) for t in ('liq', 'gap', 'poc', 'round', 'all') for m in (0.5, 1.0, 1.5)]
G = {}


def init(name, a, b):
    S = V.Sess(lab.DS(name, a, b)); G['S'] = S; G['P'] = session_pois(S)


def job(cfg):
    (tset, minR), (tl, step, lag) = cfg
    return cfg, run(G['S'], G['P'], tset, minR, step, lag)


if __name__ == '__main__':
    name, a, b = sys.argv[1:4]
    cfgs = [(t, tr) for t in TARGETS for tr in TRAILS]
    t0 = time.time()
    with Pool(4, initializer=init, initargs=(name, a, b)) as p:
        res = p.map(job, cfgs, chunksize=2)
    pickle.dump(dict(res), open(f'cache/v9_trades_{name}.pkl', 'wb'))
    print(name, len(res), f'{time.time()-t0:.0f}s')
