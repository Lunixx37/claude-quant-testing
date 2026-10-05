"""V5 lab: FVG continuation candidate - filters, stops, exits, swing holding (PROTOCOL_V5.md)."""
import math, pickle
import numpy as np, pandas as pd
from features import load
from engine import prepare
import ict

SPREAD, COMM, SLIP, TICK = 1.2, 0.75, 0.25, 0.25
SWAP_YR = 0.05
KEYS = {'train': [('cfd', '2017-01-01', '2018-12-31'), ('cfd', '2019-01-01', '2020-06-30')],
        'valid': [('cfd', '2020-07-01', '2021-12-31')],
        'test22': [('cfd', '2022-01-01', '2022-12-31')],
        'test_nq': [('nq', '2023-01-01', '2025-12-11')],
        'test_cfd': [('cfd', '2023-01-01', '2025-09-30')]}
WEEKS = {k: sum((pd.Timestamp(e) - pd.Timestamp(s)).days for _, s, e in v) / 7 for k, v in KEYS.items()}
_F, _D, _C = {}, {}, None


def data(name):
    if name not in _F:
        df = load(name)
        _F[name] = prepare(df)
        _D[name] = daily(df)
    return _F[name], _D[name]


def daily(df):
    r = df[(df['mod'] >= 570) & (df['mod'] < 960)]
    g = r.groupby('sdate').agg(o930=('o', 'first'), cl=('c', 'last'), hi=('h', 'max'), lo=('l', 'min'))
    g['rg'] = g.hi - g.lo
    g['prev_cl'] = g.cl.shift(1)
    g['sma20'] = g.cl.rolling(20).mean().shift(1)
    g['sma50'] = g.cl.rolling(50).mean().shift(1)
    g['prev_up'] = (g.cl > g.cl.shift(1)).shift(1)
    g['volreg'] = g.rg.shift(1) / g.rg.rolling(20).mean().shift(2)
    g['atr14'] = g.rg.rolling(14).mean().shift(1)
    return g


def candidates(split):
    """FVG candidate rows with features for all keys of a split."""
    global _C
    if _C is None:
        _C = pickle.load(open('cache/v3_candidates.pkl', 'rb'))
    out = []
    for key in KEYS[split]:
        f, dd = data(key[0])
        c = _C[key]
        c = c[(c.fl & ict.BIT['fvg']) > 0].copy()
        i = c.i.to_numpy()
        o, h, l, cl = f['o'][i], f['h'][i], f['l'][i], f['c'][i]
        rng = h - l
        ar20 = pd.Series(f['h'] - f['l']).rolling(20).mean().shift(1).to_numpy()[i]
        c['body'] = np.abs(cl - o); c['bodyfrac'] = np.where(rng > 0, c.body / rng, 0)
        c['rngratio'] = rng / ar20
        c['mod'] = f['mod'][i]
        sd = pd.to_datetime(f['sdate'][i])
        x = dd.reindex(sd)
        d = c.dir.to_numpy()
        c['trend20'] = np.sign(x.prev_cl.to_numpy() - x.sma20.to_numpy()) * d
        c['trend50'] = np.sign(x.prev_cl.to_numpy() - x.sma50.to_numpy()) * d
        c['prevdir'] = np.where(x.prev_up.to_numpy() == True, 1, -1) * d
        c['bias'] = np.sign(cl - x.o930.to_numpy()) * d
        c['volreg'] = x.volreg.to_numpy(); c['atr14'] = x.atr14.to_numpy()
        c['key'] = [key] * len(c)
        out.append(c)
    return pd.concat(out, ignore_index=True)


FILTERS = {  # name -> (column, op, value)
    'F1 body>=2': ('body', '>=', 2), 'F1 body>=4': ('body', '>=', 4), 'F1 body>=6': ('body', '>=', 6),
    'F2 bodyfrac>=.4': ('bodyfrac', '>=', .4), 'F2 bodyfrac>=.6': ('bodyfrac', '>=', .6), 'F2 bodyfrac>=.8': ('bodyfrac', '>=', .8),
    'F3 rng>=.75avg': ('rngratio', '>=', .75), 'F3 rng>=1avg': ('rngratio', '>=', 1.0), 'F3 rng>=1.5avg': ('rngratio', '>=', 1.5),
    'F4 gap>=1': ('zgap', '>=', 1), 'F4 gap>=2': ('zgap', '>=', 2), 'F4 gap>=4': ('zgap', '>=', 4),
    'F5 disp>=2': ('zdisp', '>=', 2), 'F5 disp>=2.5': ('zdisp', '>=', 2.5), 'F5 disp>=3': ('zdisp', '>=', 3),
    'F6 age<=5': ('zage', '<=', 5), 'F6 age<=10': ('zage', '<=', 10), 'F6 age<=20': ('zage', '<=', 20),
    'F7 trend SMA20': ('trend20', '>', 0), 'F7 trend SMA50': ('trend50', '>', 0), 'F7 prev day dir': ('prevdir', '>', 0),
    'F8 with 9:30 move': ('bias', '>', 0), 'F8 against 9:30 move': ('bias', '<', 0),
    'F9 before 10:00': ('mod', '<', 600), 'F9 before 10:30': ('mod', '<', 630),
    'F10 first signal only': None,
    'F11 high vol regime': ('volreg', '>', 1), 'F11 low vol regime': ('volreg', '<', 1),
}


def apply_filters(c, names):
    m = np.ones(len(c), bool)
    for n in names:
        spec = FILTERS[n]
        if spec is None:
            continue
        col, op, v = spec
        x = c[col].to_numpy()
        m &= (x >= v) if op == '>=' else (x <= v) if op == '<=' else (x > v) if op == '>' else (x < v)
    return c[m]


def simulate(c, stop=('fixed', 40.0), tp_r=3.0, trail=False, hold=1, max_day=2, lag=1.25):
    """c: filtered candidate rows of ONE key (dataset/period). hold = sessions (1 = intraday)."""
    if len(c) == 0:
        return pd.DataFrame()
    f, dd = data(c.key.iloc[0][0])
    o, h, l, cl, mod, sd, last = f['o'], f['h'], f['l'], f['c'], f['mod'], f['sdate'], f['last']
    c = c.sort_values('i')
    # same bar both directions -> stand aside
    both = c.groupby('i').dir.nunique()
    c = c[~c.i.isin(both[both > 1].index)].drop_duplicates('i')
    trades, pos_exit, cnt = [], -1, {}
    for r in c.itertuples(index=False):
        i = r.i
        if i <= pos_exit or i + 1 >= len(o) or sd[i + 1] != sd[i] or cnt.get(sd[i], 0) >= max_day:
            continue
        d, e = r.dir, i + 1
        ep = o[e] + d * SLIP
        kind, val = stop
        if kind == 'fixed':
            R = val
        elif kind == 'struct':
            R = min(max((ep - (r.zfar - d * 2.0)) * d, 10.0), 80.0)
        else:
            if np.isnan(r.atr14):
                continue
            R = min(max(val * r.atr14, 10.0), 150.0)
        st = ep - d * R
        tp = ep + d * tp_r * R if tp_r > 0 else np.nan
        mfe, k, held, nights = 0.0, e, 0, 0
        while True:
            mfe = max(mfe, (h[k] - ep) if d == 1 else (ep - l[k]))
            if (d == 1 and l[k] <= st) or (d == -1 and h[k] >= st):
                gap = (o[k] <= st) if d == 1 else (o[k] >= st)
                x, why = (o[k] if gap else st) - d * SLIP, 'stop'; break
            if tp_r > 0 and ((d == 1 and h[k] >= tp + TICK) or (d == -1 and l[k] <= tp - TICK)):
                x, why = tp, 'tp'; break
            end_of_session = mod[k] >= 955 and mod[k] < 1080 or last[k] or k + 1 >= len(o)
            if end_of_session and held >= hold - 1:
                x, why = cl[k] - d * SLIP, 'time'; break
            if trail:
                s_ = math.floor(mfe / R + 1e-9)
                if s_ >= 1:
                    ns = ep + d * (s_ - lag) * R
                    if (d == 1 and ns > st) or (d == -1 and ns < st):
                        st = ns
            if k + 1 < len(o) and sd[k + 1] != sd[k]:
                held += 1
                nights += int((sd[k + 1] - sd[k]).astype('timedelta64[D]').astype(int))
            k += 1
        pts = (x - ep) * d
        swap = ep * SWAP_YR / 365 * nights
        trades.append(dict(sdate=sd[i], i=i, entry_i=e, exit_i=k, dir=d, R_pts=R, entry=ep, pts=pts, why=why, nights=nights,
                           Rc=(pts - SPREAD - swap) / R, Rf=(pts - COMM) / R))
        cnt[sd[i]] = cnt.get(sd[i], 0) + 1
        pos_exit = k
    return pd.DataFrame(trades)


def run(split, filters=(), stop=('fixed', 40.0), tp_r=3.0, trail=False, hold=1, cand=None):
    cand = candidates(split) if cand is None else cand
    c = apply_filters(cand, filters)
    max_day = 1 if 'F10 first signal only' in filters else 2
    ts = [simulate(g, stop, tp_r, trail, hold, max_day) for _, g in c.groupby(c.key.astype(str))]
    ts = [t for t in ts if len(t)]
    return pd.concat(ts, ignore_index=True) if ts else pd.DataFrame(columns=['Rc', 'Rf'])


def stats(t, split, col='Rc'):
    if len(t) == 0:
        return dict(n=0, per_week=0, win=np.nan, E=np.nan, pf=np.nan, dd=np.nan)
    x = t[col]; eq = x.cumsum(); w = x[x > 0]
    return dict(n=len(t), per_week=len(t) / WEEKS[split], win=(x > 0).mean(), E=x.mean(),
                pf=w.sum() / -x[x <= 0].sum() if (x <= 0).any() else np.inf, dd=(eq.cummax().clip(lower=0) - eq).max(),
                avg_win=w.mean() if len(w) else 0)
