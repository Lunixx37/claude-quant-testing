"""V3 price-action engine: ICT building blocks + level rejections, high-frequency search.

Phase 1 (`detect`): one causal pass over the bars that marks, for each bar in the entry window and
each direction, which building blocks fire at that bar's close.
Phase 2 (`simulate`): for one configuration (setup, stop mode, exit), the bar-by-bar trade
simulation with gating (one position at a time, max 2 per day, fallback / forced trade, EOD flat).

All definitions follow PROTOCOL_V3.md. Everything at bar i uses bars <= i only, and levels come
from bar i-1. Entries are market orders at the next bar's open.
"""
import math
import numpy as np
import pandas as pd

TICK = 0.25
SLIP = 0.25                 # 1 tick per market / stop fill
COMM_PTS = 0.75             # $1.50 per MNQ round turn = 0.75 pt
CFD_SPREAD = 1.2            # NAS100 CFD spread per round trip (pts), spread-only account
WIN_START, WIN_END, FALLBACK_T, FORCED_T, FLAT_T = 570, 660, 630, 659, 955
STATE_START = 510           # build zones / structure from 08:30
LEVEL_TOL = 2.0             # pts: level touch tolerance
LEVEL_PEN_MAX = 25.0        # pts: deeper than this through a level = break, not a rejection
FLAGS = ['fvg', 'rb', 'ob', 'v18', 'vb', 'm', 'mss', 'ls', 'mss_recent', 'abs']
BIT = {k: 1 << n for n, k in enumerate(FLAGS)}
TRIGGERS = BIT['fvg'] | BIT['rb'] | BIT['ob'] | BIT['vb'] | BIT['m'] | BIT['mss']


def _extras(df):
    """Asia (20:00-24:00) and London (02:00-05:00) highs/lows per NY trading date (known before 09:30)."""
    m = df['mod']
    asia = df[m >= 1200].groupby('sdate').agg(ash=('h', 'max'), asl=('l', 'min'))
    lon = df[(m >= 120) & (m < 300)].groupby('sdate').agg(lnh=('h', 'max'), lnl=('l', 'min'))
    x = df[['sdate']].join(asia, on='sdate').join(lon, on='sdate')
    return {k: x[k].to_numpy() for k in ('ash', 'asl', 'lnh', 'lnl')}


def _pivots(h, l, k=3):
    """Pivot high/low at j (k bars each side), CONFIRMED at bar j+k. Returns arrays indexed by the
    confirmation bar: price of the confirmed pivot (nan where none) and the pivot bar index."""
    n = len(h)
    ph = np.full(n, np.nan); pl = np.full(n, np.nan); phj = np.full(n, -1); plj = np.full(n, -1)
    from numpy.lib.stride_tricks import sliding_window_view as sw
    if n < 2 * k + 1:
        return ph, pl, phj, plj
    wh, wl = sw(h, 2 * k + 1), sw(l, 2 * k + 1)
    c = np.arange(k, n - k)
    hi_ok = (h[c] > wh[:, :k].max(1)) & (h[c] >= wh[:, k + 1:].max(1))
    lo_ok = (l[c] < wl[:, :k].min(1)) & (l[c] <= wl[:, k + 1:].min(1))
    conf = c + k
    ph[conf[hi_ok]] = h[c[hi_ok]]; phj[conf[hi_ok]] = c[hi_ok]
    pl[conf[lo_ok]] = l[c[lo_ok]]; plj[conf[lo_ok]] = c[lo_ok]
    return ph, pl, phj, plj


def detect(f, df, start, end):
    """Return a DataFrame of candidate rows (bar i, dir, flags bitmask, structural stop price)."""
    o, h, l, c = f['o'], f['h'], f['l'], f['c']
    mod, sd = f['mod'], f['sdate']
    ve, se, rv, rr = f['vwapE'], f['sdE'], f['relvol'], f['relrange']
    pdh, pdl, onh, onl = df.pdh.to_numpy(), df.pdl.to_numpy(), df.onh.to_numpy(), df.onl.to_numpy()
    ex = _extras(df)
    rng = h - l
    ar20 = pd.Series(rng).rolling(20).mean().shift(1).to_numpy()     # previous 20 bars
    ph, pl, phj, plj = _pivots(h, l, 3)
    i0 = max(np.searchsorted(sd, np.datetime64(start)), 25)
    i1 = np.searchsorted(sd, np.datetime64(end), side='right')
    rows = []
    day = None
    for i in range(i0, i1):
        if sd[i] != day:
            day = sd[i]
            fvgs, rbs = [], []                 # active zones: (dir, bot, top, born, ob_bot, ob_top)
            last_sh = last_sl = np.nan         # latest confirmed swing high / low
            sweep = {1: (-10**9, np.nan), -1: (-10**9, np.nan)}
            mss_ev = {1: -10**9, -1: -10**9}
        md = mod[i]
        if md < STATE_START or md >= WIN_END:
            continue
        # ---- structure updates known at close of bar i
        if not np.isnan(ph[i]):
            last_sh = ph[i]
            j = phj[i]
            if rng[j] > 0 and (h[j] - max(o[j], c[j])) / rng[j] >= 0.5:
                rbs.append((-1, max(o[j], c[j]), h[j], i))
        if not np.isnan(pl[i]):
            last_sl = pl[i]
            j = plj[i]
            if rng[j] > 0 and (min(o[j], c[j]) - l[j]) / rng[j] >= 0.5:
                rbs.append((1, l[j], min(o[j], c[j]), i))
        # liquidity sweep events (levels known before the session)
        liq_lo = [x for x in (pdl[i], onl[i], ex['asl'][i], ex['lnl'][i]) if not np.isnan(x)]
        liq_hi = [x for x in (pdh[i], onh[i], ex['ash'][i], ex['lnh'][i]) if not np.isnan(x)]
        if md >= WIN_START:
            if any(l[i] < L < c[i] for L in liq_lo):
                ext = l[i] if sweep[1][0] < i - 30 else min(l[i], sweep[1][1])
                sweep[1] = (i, ext)
            if any(h[i] > L > c[i] for L in liq_hi):
                ext = h[i] if sweep[-1][0] < i - 30 else max(h[i], sweep[-1][1])
                sweep[-1] = (i, ext)
        # MSS events: close through the latest confirmed swing
        mss_now = {1: (not np.isnan(last_sh)) and c[i] > last_sh >= c[i - 1],
                   -1: (not np.isnan(last_sl)) and c[i] < last_sl <= c[i - 1]}
        # ---- entry-window evaluation (zones born before this bar)
        if md >= WIN_START:
            V = ve[i - 1]; S = se[i - 1]
            vb_lv = [V] + ([V + S, V - S, V + 2 * S, V - 2 * S] if not np.isnan(S) else [])
            ment = [m for m in range(int((c[i - 1] - 150) // 100) * 100, int(c[i - 1] + 150), 100)]
            for d in (1, -1):
                flags = 0
                r = rng[i]
                if r <= 0:
                    continue
                body_ok = (c[i] > o[i]) if d == 1 else (c[i] < o[i])

                def zone_rej(bot, top):
                    if d == 1:
                        return l[i] <= top and h[i] >= bot and c[i] > (bot + top) / 2 and body_ok
                    return h[i] >= bot and l[i] <= top and c[i] < (bot + top) / 2 and body_ok

                def lvl_rej(L):
                    if d == 1:
                        return c[i - 1] > L and l[i] <= L + LEVEL_TOL and l[i] >= L - LEVEL_PEN_MAX and c[i] > L and body_ok
                    return c[i - 1] < L and h[i] >= L - LEVEL_TOL and h[i] <= L + LEVEL_PEN_MAX and c[i] < L and body_ok

                zl = []
                for z in fvgs:
                    if z[0] == d and z[3] < i and zone_rej(z[1], z[2]):
                        flags |= BIT['fvg']; zl.append(z[1] if d == 1 else z[2])
                    if z[0] == d and z[3] < i and not np.isnan(z[4]) and zone_rej(z[4], z[5]):
                        flags |= BIT['ob']; zl.append(z[4] if d == 1 else z[5])
                for z in rbs:
                    if z[0] == d and z[3] < i and zone_rej(z[1], z[2]):
                        flags |= BIT['rb']; zl.append(z[1] if d == 1 else z[2])
                if not np.isnan(V) and lvl_rej(V):
                    flags |= BIT['v18'] | BIT['vb']
                elif any(lvl_rej(L) for L in vb_lv[1:]):
                    flags |= BIT['vb']
                if any(lvl_rej(float(m)) for m in ment):
                    flags |= BIT['m']
                if mss_now[d]:
                    flags |= BIT['mss']
                    mss_ev[d] = i
                if i - sweep[d][0] <= 30:
                    flags |= BIT['ls']
                if i - mss_ev[d] <= 30:
                    flags |= BIT['mss_recent']
                if not np.isnan(rv[i]) and rv[i] >= 1.5 and not np.isnan(rr[i]) and rr[i] / rv[i] <= 1.0:
                    wick = ((min(o[i], c[i]) - l[i]) if d == 1 else (h[i] - max(o[i], c[i]))) / r
                    cl = ((c[i] - l[i]) if d == 1 else (h[i] - c[i])) / r
                    if wick >= 0.4 or cl >= 0.6:
                        flags |= BIT['abs']
                if flags & TRIGGERS:
                    if d == 1:
                        st = min(l[max(i - 2, 0):i + 1].min(), *(zl or [np.inf]))
                        if flags & BIT['ls']:
                            st = min(st, sweep[1][1])
                        st -= 2.0
                    else:
                        st = max(h[max(i - 2, 0):i + 1].max(), *(zl or [-np.inf]))
                        if flags & BIT['ls']:
                            st = max(st, sweep[-1][1])
                        st += 2.0
                    rows.append((i, d, flags, st))
        # ---- new FVGs formed at bar i (usable from bar i+1)
        if not np.isnan(ar20[i - 1]) and rng[i - 1] >= 1.5 * ar20[i - 1]:
            if l[i] - h[i - 2] >= 0.5 and c[i - 1] > o[i - 1]:
                ob = next(((l[k], h[k]) for k in range(i - 2, i - 7, -1) if c[k] < o[k]), (np.nan, np.nan))
                fvgs.append((1, h[i - 2], l[i], i, ob[0], ob[1]))
            if l[i - 2] - h[i] >= 0.5 and c[i - 1] < o[i - 1]:
                ob = next(((l[k], h[k]) for k in range(i - 2, i - 7, -1) if c[k] > o[k]), (np.nan, np.nan))
                fvgs.append((-1, h[i], l[i - 2], i, ob[0], ob[1]))
        # expire / invalidate zones
        fvgs = [z for z in fvgs if i - z[3] <= 60 and not ((z[0] == 1 and c[i] < z[1]) or (z[0] == -1 and c[i] > z[2]))]
        rbs = [z for z in rbs if i - z[3] <= 120 and not ((z[0] == 1 and c[i] < z[1]) or (z[0] == -1 and c[i] > z[2]))]
    return pd.DataFrame(rows, columns=['i', 'dir', 'fl', 'stop'])


def has(fl, *names):
    return all(fl & BIT[n] for n in names)


def score(fl):
    return bin(fl & (BIT['fvg'] | BIT['rb'] | BIT['ob'] | BIT['vb'] | BIT['m'] | BIT['ls'] | BIT['mss_recent'] | BIT['abs'])).count('1')


SETUPS = {
    'S1 VWAP18':        lambda fl, md: has(fl, 'v18'),
    'S2 VWAP bands':    lambda fl, md: has(fl, 'vb'),
    'S3 Mental':        lambda fl, md: has(fl, 'm'),
    'S4 FVG':           lambda fl, md: has(fl, 'fvg'),
    'S5 FVG+RB':        lambda fl, md: has(fl, 'fvg', 'rb'),
    'S6 FVG+VWAP':      lambda fl, md: has(fl, 'fvg', 'vb'),
    'S7 Sweep+MSS':     lambda fl, md: has(fl, 'mss', 'ls'),
    'S8 OB(+FVG)':      lambda fl, md: has(fl, 'ob'),
    'S9 SilverBullet':  lambda fl, md: has(fl, 'fvg', 'ls') and md >= 600,
    'S10 Absorption':   lambda fl, md: has(fl, 'abs') and bool(fl & (BIT['vb'] | BIT['m'] | BIT['fvg'] | BIT['rb'] | BIT['ob'])),
    'S11 Score>=2':     lambda fl, md: score(fl) >= 2,
}


def simulate(f, cand, setup, stop_mode='struct', tp_r=2.0, trail=False, fallback=True, max_day=2, lag=1.25, fixed_pts=25.0):
    """Trade simulation for one configuration. Returns a DataFrame of trades (R net of costs)."""
    o, h, l, c, mod, sd, last = f['o'], f['h'], f['l'], f['c'], f['mod'], f['sdate'], f['last']
    pred = setup if callable(setup) else SETUPS[setup]
    by_day = {}
    for r in cand.itertuples(index=False):
        by_day.setdefault(sd[r.i], []).append(r)
    days = np.unique(sd[cand.i.to_numpy()]) if len(cand) else []
    # all trading days in range (also days without candidates, for forced trades)
    lo, hi = (cand.i.min(), cand.i.max()) if len(cand) else (0, 0)
    win_idx = np.where((mod >= WIN_START) & (mod < WIN_END))[0]
    win_idx = win_idx[(win_idx >= lo - 400) & (win_idx <= hi + 400)]
    trades = []
    pos_exit = -1
    for day in np.unique(sd[win_idx]):
        dbars = win_idx[sd[win_idx] == day]
        if len(dbars) == 0:
            continue
        open930 = o[dbars[0]]
        cands = {}
        for r in by_day.get(day, []):
            cands.setdefault(r.i, []).append(r)
        n_today = 0
        for i in dbars:
            if n_today >= max_day or i <= pos_exit or i + 1 >= len(o) or sd[i + 1] != day:
                continue
            md = mod[i]
            picks = []
            for r in cands.get(i, []):
                if pred(r.fl, md):
                    picks.append((r, 'primary'))
                elif fallback and n_today == 0 and md >= FALLBACK_T:
                    picks.append((r, 'fallback'))
            dirs = {p[0].dir for p in picks}
            kind = None
            if len(dirs) == 1:
                prim = [p for p in picks if p[1] == 'primary']
                r, kind = (prim[0] if prim else picks[0])
                d, stp = r.dir, r.stop
            elif fallback and n_today == 0 and md == FORCED_T:
                d = 1 if c[i] >= open930 else -1
                stp, kind = np.nan, 'forced'
            if kind is None:
                continue
            e = i + 1
            ep = o[e] + d * SLIP
            if stop_mode == 'fixed' or np.isnan(stp):
                R = fixed_pts
            else:
                R = (ep - stp) * d
                if R > 40:
                    continue
                R = max(R, 5.0)
            stop = ep - d * R
            tp = ep + d * tp_r * R if tp_r > 0 else np.nan
            mfe = 0.0
            k = e
            while True:
                mfe = max(mfe, (h[k] - ep) if d == 1 else (ep - l[k]))
                if (d == 1 and l[k] <= stop) or (d == -1 and h[k] >= stop):
                    gap = (o[k] <= stop) if d == 1 else (o[k] >= stop)
                    x, why = (o[k] if gap else stop) - d * SLIP, 'stop'
                    break
                if tp_r > 0 and ((d == 1 and h[k] >= tp + TICK) or (d == -1 and l[k] <= tp - TICK)):
                    x, why = tp, 'tp'
                    break
                if mod[k] >= FLAT_T or last[k] or sd[k + 1] != day:
                    x, why = c[k] - d * SLIP, 'eod'
                    break
                if trail:
                    st = math.floor(mfe / R + 1e-9)
                    if st >= 1:
                        ns = ep + d * (st - lag) * R
                        if (d == 1 and ns > stop) or (d == -1 and ns < stop):
                            stop = ns
                k += 1
            pts = (x - ep) * d
            trades.append(dict(sdate=day, sig_i=i, entry_i=e, exit_i=k, dir=d, kind=kind, R_pts=R,
                               entry=ep, exit=x, why=why, pts=pts, R=(pts - COMM_PTS) / R, Rc=(pts - CFD_SPREAD) / R, Rg=pts / R, mfe_R=mfe / R, sig_min=md))
            n_today += 1
            pos_exit = k
    return pd.DataFrame(trades)


def summarize(t, weeks):
    if len(t) == 0:
        return dict(n=0)
    w = t[t.R > 0]
    eq = t.R.cumsum()
    return dict(n=len(t), per_week=len(t) / weeks, win=len(w) / len(t), avg_win_R=w.R.mean() if len(w) else 0,
                avg_win_gross=w.Rg.mean() if len(w) else 0,
                avg_loss_R=t[t.R <= 0].R.mean(), E=t.R.mean(),
                pf=w.R.sum() / -t[t.R <= 0].R.sum() if (t.R <= 0).any() else np.inf,
                dd=(eq.cummax().clip(lower=0) - eq).max(), sumR=t.R.sum(),
                share_primary=(t.kind == 'primary').mean())
