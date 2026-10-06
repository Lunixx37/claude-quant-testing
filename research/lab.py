"""V6 lab: daily table, generic exit simulator, signal generators for strategy families F1-F10 (PROTOCOL_V6.md).

Conventions: every signal is decided at the close of bar `sig_i` (or at a daily close) using data <= that bar.
The entry fills at the open of bar `e` (> sig_i) plus slippage. Daily-table columns used before the session
are shifted so that they only contain completed days.
"""
import math, pickle
import numpy as np, pandas as pd
from features import load
from engine import prepare
import ict

SPREAD, SLIP, COMM, TICK, SWAP = 1.2, 0.25, 0.75, 0.25, 0.05


class DS:
    def __init__(self, name, start='2016-12-01', end='2025-12-31'):
        df = load(name)
        self.name, self.df, self.f = name, df, prepare(df)
        self.d = build_daily(df)
        self.d = self.d[(self.d.index >= start) & (self.d.index <= end)]


def build_daily(df):
    m = df['mod'].to_numpy()
    r = df[(m >= 570) & (m < 960)]
    g = r.groupby('sdate')
    d = pd.DataFrame({'i_open': g.apply(lambda x: x.index[0]), 'i_close': g.apply(lambda x: x.index[-1]),
                      'o': g.o.first(), 'h': g.h.max(), 'l': g.l.min(), 'c': g.c.last()})
    d = d[(d.i_close - d.i_open) > 200]                                   # full sessions only (no half days)
    d['rg'] = d.h - d.l
    d['pc'] = d.c.shift(1)
    d['atr14'] = d.rg.rolling(14).mean().shift(1)                          # completed days only
    for n in (5, 20, 50, 200):
        d[f'sma{n}'] = d.c.rolling(n).mean()                               # includes today's close (use at close)
    dlt = d.c.diff(); up = dlt.clip(lower=0); dn = (-dlt).clip(lower=0)
    rs = up.ewm(alpha=1 / 2, adjust=False).mean() / dn.ewm(alpha=1 / 2, adjust=False).mean()
    d['rsi2'] = 100 - 100 / (1 + rs)
    for n in (10, 20, 55):
        d[f'hh{n}'] = d.h.rolling(n).max().shift(1); d[f'll{n}'] = d.l.rolling(n).min().shift(1)
    # opening ranges and other intraday reference points
    for L in (5, 15, 30):
        x = r[(r['mod'] >= 570) & (r['mod'] < 570 + L)].groupby('sdate')
        d[f'orh{L}'] = x.h.max(); d[f'orl{L}'] = x.l.min(); d[f'ore{L}'] = x.apply(lambda y: y.index[-1])
    x = df[(m >= 510) & (m < 515)].groupby('sdate')
    d['nh'] = x.h.max(); d['nl'] = x.l.min()                              # 08:30-08:35 "news" range
    x = r[r['mod'] == 599].groupby('sdate')
    d['c1000'] = x.c.last(); d['i1000'] = x.apply(lambda y: y.index[-1])
    for t in (900, 930):
        x = r[r['mod'] == t - 1].groupby('sdate')
        d[f'i{t}'] = x.apply(lambda y: y.index[-1])                       # bar before 15:00 / 15:30 (close = decision)
    d['orw15_med'] = (d.orh15 - d.orl15).rolling(20).median().shift(1)
    mo = d.index.to_period('M')
    d['tdm'] = d.groupby(mo).cumcount() + 1                               # trading day of month
    d['tdm_rev'] = d.groupby(mo).cumcount(ascending=False) + 1            # 1 = last trading day
    d['trend'] = np.sign(d.pc - d.sma20.shift(1))                          # known before the open
    return d


def sim_trade(f, e, d, stop_pts, tp_pts, deadline, trail=False, lag=1.25):
    o, h, l, c, sd = f['o'], f['h'], f['l'], f['c'], f['sdate']
    ep = o[e] + d * SLIP
    st = ep - d * stop_pts
    tp = ep + d * tp_pts if tp_pts and tp_pts > 0 else np.nan
    k, mfe, nights = e, 0.0, 0
    n = len(o)
    while True:
        mfe = max(mfe, (h[k] - ep) if d == 1 else (ep - l[k]))
        if (d == 1 and l[k] <= st) or (d == -1 and h[k] >= st):
            gap = (o[k] <= st) if d == 1 else (o[k] >= st)
            x, why = (o[k] if gap else st) - d * SLIP, 'stop'; break
        if not np.isnan(tp) and ((d == 1 and h[k] >= tp + TICK) or (d == -1 and l[k] <= tp - TICK)):
            x, why = tp, 'tp'; break
        if k >= deadline or k + 1 >= n:
            x, why = c[k] - d * SLIP, 'time'; break
        if trail:
            s_ = math.floor(mfe / stop_pts + 1e-9)
            if s_ >= 1:
                ns = ep + d * (s_ - lag) * stop_pts
                if (d == 1 and ns > st) or (d == -1 and ns < st):
                    st = ns
        if sd[k + 1] != sd[k]:
            nights += int((sd[k + 1] - sd[k]).astype('timedelta64[D]').astype(int))
        k += 1
    return ep, x, k, why, nights


def run_entries(ds, entries, max_day=1):
    """entries: list of (sig_i, e, dir, stop_pts, tp_pts, deadline, trail). One position at a time."""
    f = ds.f
    sd = f['sdate']
    out, last_exit, cnt = [], -1, {}
    for sig_i, e, d, sp, tpp, dl, tr in sorted(entries, key=lambda x: x[1]):
        if e <= last_exit or not (sp > 0) or cnt.get(sd[e], 0) >= max_day or dl < e:
            continue
        ep, x, k, why, nights = sim_trade(f, e, d, sp, tpp, dl, tr)
        pts = (x - ep) * d
        swap = ep * SWAP / 365 * nights
        out.append((sd[e], e, k, d, sp, pts, why, nights, (pts - SPREAD - swap) / sp, (pts - COMM) / sp))
        cnt[sd[e]] = cnt.get(sd[e], 0) + 1
        last_exit = k
    return pd.DataFrame(out, columns=['sdate', 'e', 'x_i', 'dir', 'stop', 'pts', 'why', 'nights', 'Rc', 'Rf'])


# ------------------------------------------------------------------ family generators
def _rows(d):
    return d.dropna(subset=['atr14']).itertuples()


def fam_orb(ds, L, stop_mode, tgt, filt):
    f, d = ds.f, ds.d
    c, mod = f['c'], f['mod']
    ent = []
    for r in _rows(d):
        if np.isnan(getattr(r, f'orh{L}')):
            continue
        hi, lo, i0 = getattr(r, f'orh{L}'), getattr(r, f'orl{L}'), int(getattr(r, f'ore{L}'))
        if filt == 'narrow' and not ((hi - lo) < r.orw15_med * (L / 15) ** 0.5):
            continue
        for i in range(i0 + 1, int(r.i_close)):
            if mod[i] >= 720:
                break
            dd = 1 if c[i] > hi else -1 if c[i] < lo else 0
            if dd == 0:
                continue
            if filt == 'trend' and dd != r.trend:
                break
            sp = (c[i] - (lo if dd == 1 else hi)) * dd if stop_mode == 'opp' else (c[i] - (hi + lo) / 2) * dd
            sp = max(sp, 0.02 * r.atr14)
            tpp = 0 if tgt == 'eod' else tgt * sp
            ent.append((i, i + 1, dd, sp, tpp, int(r.i_close), False))
            break
    return ent


def fam_imom(ds, sigwin, entry_t, thr):
    f, d = ds.f, ds.d
    ent = []
    for r in _rows(d):
        if np.isnan(r.c1000) or np.isnan(getattr(r, f'i{entry_t}')):
            continue
        ref = r.o if sigwin == 'open' else r.pc
        ret = r.c1000 / ref - 1
        if abs(ret) <= thr:
            continue
        dd = 1 if ret > 0 else -1
        i = int(getattr(r, f'i{entry_t}'))
        ent.append((i, i + 1, dd, 0.005 * r.c, 0, int(r.i_close), False))
    return ent


def fam_gap(ds, k, mode, tgt, stopm):
    f, d = ds.f, ds.d
    ent = []
    for r in _rows(d):
        gap = r.o - r.pc
        if np.isnan(gap) or abs(gap) < k * r.atr14:
            continue
        dd = -np.sign(gap) if mode == 'fade' else np.sign(gap)
        i = int(r.i_open)
        sp = max(stopm * abs(gap), 0.05 * r.atr14)
        tpp = (abs(gap) * (1.0 if tgt == 'full' else 0.5)) if mode == 'fade' else (2 * sp if tgt == 'full' else 0)
        ent.append((i, i + 1, int(dd), sp, tpp, int(r.i_close), False))       # gap known at the 09:30 print -> fill at 09:31 open
    return ent


def fam_pdhl(ds, stopk, tgt, filt):
    f, d = ds.f, ds.d
    c, mod = f['c'], f['mod']
    dprev = d.shift(1)
    ent = []
    for (r, p) in zip(_rows(d), dprev.loc[d.dropna(subset=['atr14']).index].itertuples()):
        if np.isnan(p.h):
            continue
        for i in range(int(r.i_open), int(r.i_close)):
            if mod[i] >= 720:
                break
            dd = 1 if c[i] > p.h else -1 if c[i] < p.l else 0
            if dd == 0:
                continue
            if filt == 'trend' and dd != r.trend:
                break
            sp = stopk * r.atr14
            ent.append((i, i + 1, dd, sp, 0 if tgt == 'eod' else tgt * sp, int(r.i_close), False))
            break
    return ent


def fam_donchian(ds, n_in, n_out, side):
    f, d = ds.f, ds.d
    dd_ = d.dropna(subset=['atr14', f'hh{n_in}'])
    idx = list(dd_.index)
    ent = []
    pos_until = None
    for j, day in enumerate(idx[:-1]):
        r = dd_.loc[day]
        if pos_until is not None and day <= pos_until:
            continue
        dirn = 1 if r.c > r[f'hh{n_in}'] else (-1 if (side == 'both' and r.c < r[f'll{n_in}']) else 0)
        if dirn == 0:
            continue
        # exit: first later close beyond the opposite n_out channel
        exit_day = None
        for k in range(j + 1, len(idx)):
            q = dd_.loc[idx[k]]
            if (dirn == 1 and q.c < q[f'll{n_out}']) or (dirn == -1 and q.c > q[f'hh{n_out}']):
                exit_day = idx[k]; break
        if exit_day is None:
            exit_day = idx[-1]
        e = int(dd_.loc[idx[j + 1]].i_open)
        ent.append((int(r.i_close), e, dirn, 2 * r.atr14, 0, int(dd_.loc[exit_day].i_close), False))
        pos_until = exit_day
    return ent


def fam_rsi2(ds, thr, side, exit_mode):
    f, d = ds.f, ds.d
    dd_ = d.dropna(subset=['atr14', 'sma200', 'rsi2'])
    idx = list(dd_.index)
    ent = []
    for j, day in enumerate(idx[:-1]):
        r = dd_.loc[day]
        dirn = 1 if (r.c > r.sma200 and r.rsi2 < thr) else (-1 if (side == 'both' and r.c < r.sma200 and r.rsi2 > 100 - thr) else 0)
        if dirn == 0:
            continue
        exit_day = idx[min(j + 5, len(idx) - 1)]
        if exit_mode == 'sma5':
            for k in range(j + 1, min(j + 11, len(idx))):
                q = dd_.loc[idx[k]]
                if (dirn == 1 and q.c > q.sma5) or (dirn == -1 and q.c < q.sma5):
                    exit_day = idx[k]; break
        e = int(dd_.loc[idx[j + 1]].i_open)
        ent.append((int(r.i_close), e, dirn, 3 * r.atr14, 0, int(dd_.loc[exit_day].i_close), False))
    return ent


def fam_vbo(ds, k, stopm):
    f, d = ds.f, ds.d
    h, l, mod = f['h'], f['l'], f['mod']
    dprev = d.rg.shift(1)
    ent = []
    for r in _rows(d):
        pr = dprev.get(r.Index, np.nan)
        if np.isnan(pr):
            continue
        up, dn = r.o + k * pr, r.o - k * pr
        for i in range(int(r.i_open), int(r.i_close)):
            dd = 1 if h[i] >= up else -1 if l[i] <= dn else 0
            if dd == 0:
                continue
            sp = (up - dn) if stopm == 'opp' else k * pr
            # stop-entry filled at the trigger on bar i: modelled as a fill at the next bar's open (conservative)
            ent.append((i, i + 1, dd, sp, 0, int(r.i_close), False))
            break
    return ent


def fam_vbo2(ds, k, sm, tgt, filt, side):
    """F7b: refined volatility breakout. Stop = sm x (k x prior RTH range)."""
    f, d = ds.f, ds.d
    h, l = f['h'], f['l']
    dprev = d.rg.shift(1)
    vr = d.rg.shift(1) / d.rg.rolling(20).mean().shift(2)
    ent = []
    for r in _rows(d):
        pr = dprev.get(r.Index, np.nan)
        if np.isnan(pr):
            continue
        if filt == 'lowvol' and not (vr.get(r.Index, np.nan) < 1):
            continue
        up, dn = r.o + k * pr, r.o - k * pr
        for i in range(int(r.i_open), int(r.i_close)):
            dd = 1 if h[i] >= up else -1 if l[i] <= dn else 0
            if dd == 0:
                continue
            if (side == 'long' and dd == -1) or (filt == 'trend' and dd != r.trend):
                break
            sp = sm * k * pr
            tpp, tr = (0, False) if tgt == 'eod' else (0, True) if tgt == 'trail' else (tgt * sp, False)
            ent.append((i, i + 1, dd, sp, tpp, int(r.i_close), tr))
            break
    return ent


def fam_news(ds, mode, tgt):
    f, d = ds.f, ds.d
    c, mod = f['c'], f['mod']
    ent = []
    for r in _rows(d):
        if np.isnan(r.nh):
            continue
        for i in range(int(r.i_open), int(r.i_close)):
            if mod[i] >= 720:
                break
            br = 1 if c[i] > r.nh else -1 if c[i] < r.nl else 0
            if br == 0:
                continue
            dd = br if mode == 'break' else -br
            sp = max(r.nh - r.nl, 0.05 * r.atr14)
            ent.append((i, i + 1, dd, sp, tgt * sp, int(r.i_close), False))
            break
    return ent


def fam_tom(ds, variant):
    f, d = ds.f, ds.d
    dd_ = d.dropna(subset=['atr14'])
    idx = list(dd_.index)
    ent = []
    for j, day in enumerate(idx[:-1]):
        r = dd_.loc[day]
        if r.tdm_rev != 2:
            continue
        k = j + 1
        while k < len(idx) and not (dd_.loc[idx[k]].tdm == (3 if variant == 'tdm3' else 1)):
            k += 1
        if k >= len(idx):
            break
        ent.append((int(r.i_close), int(r.i_close) + 1, 1, 3 * r.atr14, 0, int(dd_.loc[idx[k]].i_close), False))
    return ent


# ------------------------------------------------------------------ F10: earlier setups + refinements
CAND_KEYS = [('cfd', '2017-01-01', '2018-12-31'), ('cfd', '2019-01-01', '2020-06-30'), ('cfd', '2020-07-01', '2021-12-31'),
             ('cfd', '2022-01-01', '2022-12-31'), ('cfd', '2023-01-01', '2025-09-30')]


def f10_candidates(ds):
    C = pickle.load(open('cache/v3_candidates.pkl', 'rb'))
    keys = CAND_KEYS if ds.name == 'cfd' else [('nq', '2023-01-01', '2025-12-11')]
    c = pd.concat([C[k] for k in keys], ignore_index=True)
    f, d = ds.f, ds.d
    i = c.i.to_numpy()
    rng = f['h'][i] - f['l'][i]
    c['bodyfrac'] = np.where(rng > 0, np.abs(f['c'][i] - f['o'][i]) / rng, 0)
    c['mod'] = f['mod'][i]
    x = d.reindex(pd.to_datetime(f['sdate'][i]))
    c['trend'] = x.trend.to_numpy() * c.dir.to_numpy()
    c['bias'] = np.sign(f['c'][i] - x.o.to_numpy()) * c.dir.to_numpy()
    c['volreg'] = (x.rg.shift(0).to_numpy())  # placeholder, replaced below
    rg = d.rg; vr = (rg.shift(1) / rg.rolling(20).mean().shift(2))
    c['volreg'] = vr.reindex(pd.to_datetime(f['sdate'][i])).to_numpy()
    c['i_close'] = x.i_close.to_numpy()
    nxt = d.i_close.shift(-1)
    c['i_close_next'] = nxt.reindex(pd.to_datetime(f['sdate'][i])).to_numpy()
    return c.dropna(subset=['i_close'])


F10_FILTERS = {'none': lambda c: np.ones(len(c), bool), 'trend': lambda c: c.trend.to_numpy() > 0,
               'with930': lambda c: c.bias.to_numpy() > 0, 'lowvol': lambda c: c.volreg.to_numpy() < 1,
               'body60': lambda c: c.bodyfrac.to_numpy() >= 0.6}


def fam_f10(ds, cand, setup, stop_pts, exit_, hold, filt):
    pred = ict.SETUPS[setup]
    c = cand[F10_FILTERS[filt](cand)]
    ok = np.array([pred(fl, md) for fl, md in zip(c.fl.to_numpy(), c['mod'].to_numpy())], bool) if len(c) else np.array([], bool)
    c = c[ok]
    both = c.groupby('i').dir.nunique()
    c = c[~c.i.isin(both[both > 1].index)].drop_duplicates('i')
    tpR, trail = {'TP2': (2.0, False), 'TP3': (3.0, False), 'Trail': (0.0, True)}[exit_]
    ent = []
    for r in c.itertuples(index=False):
        dl = r.i_close if hold == 1 else (r.i_close_next if not np.isnan(r.i_close_next) else r.i_close)
        if r.i + 1 > dl:
            continue
        ent.append((int(r.i), int(r.i) + 1, int(r.dir), stop_pts, tpR * stop_pts, int(dl), trail))
    return ent


def universe():
    U = []
    for L in (5, 15, 30):
        for sm in ('opp', 'mid'):
            for tg in (1, 2, 3, 'eod'):
                for fl in ('none', 'narrow', 'trend'):
                    U.append(('F1 ORB', dict(L=L, stop_mode=sm, tgt=tg, filt=fl)))
    for sw in ('open', 'prevclose'):
        for et in (900, 930):
            for th in (0.0, 0.0025, 0.005):
                U.append(('F2 IntradayMom', dict(sigwin=sw, entry_t=et, thr=th)))
    for k in (0.1, 0.2, 0.3):
        for mode in ('fade', 'cont'):
            for tg in ('full', 'half'):
                for sm in (0.5, 1.0):
                    U.append(('F3 Gap', dict(k=k, mode=mode, tgt=tg, stopm=sm)))
    for sk in (0.1, 0.2):
        for tg in (1, 2, 3, 'eod'):
            for fl in ('none', 'trend'):
                U.append(('F4 PDH/PDL', dict(stopk=sk, tgt=tg, filt=fl)))
    for ni, no in ((20, 10), (55, 20)):
        for side in ('long', 'both'):
            U.append(('F5 Donchian', dict(n_in=ni, n_out=no, side=side)))
    for th in (5, 10):
        for side in ('long', 'both'):
            for ex in ('sma5', 'days5'):
                U.append(('F6 RSI2', dict(thr=th, side=side, exit_mode=ex)))
    for k in (0.3, 0.5, 0.7):
        for sm in ('opp', 'k'):
            U.append(('F7 VolBreakout', dict(k=k, stopm=sm)))
    for mode in ('break', 'fade'):
        for tg in (1, 2, 3):
            U.append(('F8 NewsRange', dict(mode=mode, tgt=tg)))
    for v in ('tdm3', 'tdm1'):
        U.append(('F9 TurnOfMonth', dict(variant=v)))
    for k in (0.2, 0.25, 0.3, 0.35, 0.4):
        for sm in (0.75, 1.0, 1.5):
            for tg in ('eod', 2, 3, 'trail'):
                for fl in ('none', 'trend', 'lowvol'):
                    for side in ('both', 'long'):
                        U.append(('F7b VBO refined', dict(k=k, sm=sm, tgt=tg, filt=fl, side=side)))
    for s in ict.SETUPS:
        for sp in (25.0, 40.0, 60.0):
            for ex in ('TP2', 'TP3', 'Trail'):
                for hold in (1, 2):
                    for fl in F10_FILTERS:
                        U.append(('F10 ' + s, dict(setup=s, stop_pts=sp, exit_=ex, hold=hold, filt=fl)))
    return U


GEN = {'F1 ORB': fam_orb, 'F2 IntradayMom': fam_imom, 'F3 Gap': fam_gap, 'F4 PDH/PDL': fam_pdhl, 'F5 Donchian': fam_donchian,
       'F6 RSI2': fam_rsi2, 'F7 VolBreakout': fam_vbo, 'F8 NewsRange': fam_news, 'F7b VBO refined': fam_vbo2, 'F9 TurnOfMonth': fam_tom}


def run_config(ds, fam, kw, cand=None):
    if fam.startswith('F10'):
        ent = fam_f10(ds, cand, **kw)
        return run_entries(ds, ent, max_day=2)
    return run_entries(ds, GEN[fam](ds, **kw), max_day=1)
