"""Load the CSV, validate, and compute causal per-bar features.

All features at bar i use only bars <= i (cumulative sums / EMAs updated after use).
"""
import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, 'Dataset_NQ_1min_2022_2025.csv')
CACHE = os.path.join(ROOT, 'research', 'cache', 'features.pkl')
RVOL_LEN = 20          # EMA length (days) of same-minute volume profile
RVOL_MIN_OBS = 10      # minute must have >= 10 prior observations before relvol is valid


def build():
    d = pd.read_csv(CSV)
    d.columns = ['ts', 'o', 'h', 'l', 'c', 'v', 'vwap_rth_csv', 'vwap_eth_csv']
    # CSV labels are bar CLOSE times -> convert to bar OPEN times (TradingView convention)
    d['t'] = pd.to_datetime(d.ts, format='%m/%d/%Y %H:%M') - pd.Timedelta(minutes=1)
    assert d.t.is_monotonic_increasing and not d.t.duplicated().any()
    assert (d.h >= d[['o', 'c']].max(axis=1)).all() and (d.l <= d[['o', 'c']].min(axis=1)).all()
    assert (d.v > 0).all() and not d.isna().any().any()

    # NY trading date: bars opening at/after 18:00 ET belong to the next calendar date
    d['sdate'] = (d.t + pd.Timedelta(hours=6)).dt.normalize()
    d['mod'] = d.t.dt.hour * 60 + d.t.dt.minute
    p = (d.h + d.l + d.c) / 3.0
    pv, pv2 = p * d.v, p * p * d.v

    # ETH VWAP anchored at session start (18:00 ET), stdev bands as in ta.vwap
    g = d.sdate
    cv, cpv, cpv2 = d.v.groupby(g).cumsum(), pv.groupby(g).cumsum(), pv2.groupby(g).cumsum()
    d['vwapE'] = cpv / cv
    d['sdE'] = np.sqrt(np.maximum(cpv2 / cv - d.vwapE ** 2, 0))

    # RTH VWAP anchored at 09:30 bar
    rth = d['mod'] >= 570
    rth &= d['mod'] < 18 * 60  # same calendar session, before evening reopen
    key = d.sdate.where(rth)
    v_r, pv_r, pv2_r = d.v.where(rth), pv.where(rth), pv2.where(rth)
    cv, cpv, cpv2 = v_r.groupby(key).cumsum(), pv_r.groupby(key).cumsum(), pv2_r.groupby(key).cumsum()
    d['vwapR'] = cpv / cv
    d['sdR'] = np.sqrt(np.maximum(cpv2 / cv - d.vwapR ** 2, 0))
    chk = d[rth & (d['mod'] < 17 * 60) & (d.vwap_rth_csv > 0)]
    err = (chk.vwapR - chk.vwap_rth_csv).abs().max()
    print(f'RTH VWAP recomputation vs CSV column: max abs diff = {err:.6f} pts')

    # relative volume vs EMA of same minute-of-day volume over previous days (causal)
    avg = np.full(1440, np.nan)
    nobs = np.zeros(1440, dtype=int)
    alpha = 2.0 / (RVOL_LEN + 1)
    mods, vols = d['mod'].to_numpy(), d.v.to_numpy(dtype=float)
    rv = np.full(len(d), np.nan)
    for i in range(len(d)):
        m = mods[i]
        if nobs[m] >= RVOL_MIN_OBS:
            rv[i] = vols[i] / avg[m]
        avg[m] = vols[i] if nobs[m] == 0 else avg[m] + alpha * (vols[i] - avg[m])
        nobs[m] += 1
    d['relvol'] = rv
    # relative range vs EMA of same-minute bar range (causal, same method as relvol)
    avg = np.full(1440, np.nan); nobs[:] = 0
    rngs = (d.h - d.l).to_numpy(dtype=float)
    rr = np.full(len(d), np.nan)
    for i in range(len(d)):
        m = mods[i]
        if nobs[m] >= RVOL_MIN_OBS and avg[m] > 0:
            rr[i] = rngs[i] / avg[m]
        avg[m] = rngs[i] if nobs[m] == 0 else avg[m] + alpha * (rngs[i] - avg[m])
        nobs[m] += 1
    d['relrange'] = rr
    # liquidity levels known before 09:30 (all from completed bars):
    #  ONH/ONL = high/low of the ETH session from 18:00 to 09:29 of the same NY date
    #  PDH/PDL = previous NY date RTH (09:30-15:59) high/low
    pre = d['mod'].lt(570) | d['mod'].ge(18 * 60)
    on = d[pre].groupby('sdate').agg(onh=('h', 'max'), onl=('l', 'min'))
    rth_only = d[(d['mod'] >= 570) & (d['mod'] < 960)].groupby('sdate').agg(rh=('h', 'max'), rl=('l', 'min'))
    rth_only[['pdh', 'pdl']] = rth_only[['rh', 'rl']].shift(1)
    d = d.join(on, on='sdate').join(rth_only[['pdh', 'pdl']], on='sdate')
    # levels only valid from 09:30 onward (ON range complete); mask before
    for k in ['onh', 'onl']:
        d.loc[d['mod'] < 570, k] = np.nan
    d['last_in_session'] = d.sdate.ne(d.sdate.shift(-1))
    cols = ['t', 'sdate', 'mod', 'o', 'h', 'l', 'c', 'v', 'vwapE', 'sdE', 'vwapR', 'sdR',
            'relvol', 'relrange', 'onh', 'onl', 'pdh', 'pdl', 'last_in_session']
    out = d[cols].reset_index(drop=True)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    out.to_pickle(CACHE)
    return out


def load():
    if os.path.exists(CACHE):
        return pd.read_pickle(CACHE)
    return build()


if __name__ == '__main__':
    f = build()
    print(f.tail(3))
    print('days:', f.sdate.nunique())
