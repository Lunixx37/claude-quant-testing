"""Bar-by-bar backtest engine for the NY-open Manipulation -> Absorption -> Distribution strategy.

Written as the same state machine the Pine script implements. All decisions at bar i
use only data of bars <= i. Levels used for the sweep test come from bar i-1.
Entries fill at the open of bar i+1.
"""
import math
from dataclasses import dataclass, field, asdict
import numpy as np
import pandas as pd

TICK = 0.25
PT_VALUE = 20.0

SPLITS = {
    'warmup': ('2022-12-27', '2023-01-31'),
    'train': ('2023-02-01', '2024-06-30'),
    'valid': ('2024-07-01', '2024-12-31'),
    'forward': ('2025-01-01', '2025-12-31'),
}


@dataclass
class Params:
    win_start: int = 9 * 60 + 30      # first bar (open time, ET minutes) where setups may form
    win_end: int = 11 * 60            # signal bar must open before this
    flat_time: int = 15 * 60 + 55     # flat at close of this bar (or last bar of session)
    max_trades: int = 2
    # levels
    band_k: tuple = (1.0, 2.0)        # ETH-VWAP stdev bands
    mult_pct: tuple = (0.5,)          # multiplicative ETH-VWAP bands, percent
    use_rth_vwap: bool = True
    use_liq_levels: bool = False      # ONH/ONL, PDH/PDL (OHLCV liquidity pools, NOT GEX)
    conf_tol_ticks: int = 8           # levels within this distance count as confluence
    # manipulation
    pen_min_ticks: int = 4            # sweep = trade at least this far beyond the level
    pen_max_ticks: int = 60           # deeper than this = real break, setup invalid
    touch_ticks: int = 4              # B-tier level test: low within this of level
    setup_bars: int = 10              # setup expires this many bars after the sweep/touch
    # absorption
    rv_min: float = 1.5               # relative volume (vs same-minute EMA) on absorption bar
    wick_min: float = 0.40            # rejection wick / range
    cl_min: float = 0.60              # OR close location in direction of the trade
    er_max: float = 0.0               # effort-vs-result: relrange / relvol <= er_max (0 = off)
    # distribution (A-tier displacement quality)
    disp_body: float = 0.50
    disp_cl: float = 0.70
    allow_b: bool = True
    trigger: str = 'abs_break'        # 'abs_break': close beyond absorption bar extreme; 'reclaim': close beyond level,
                                      # in trade direction, beyond absorption bar midpoint
    struct_filter: bool = False       # stop must lie beyond the manipulation extreme (+ buffer)
    struct_buffer_ticks: int = 4
    struct_ref_ticks: int = 0         # 0 = filter against the actual stop; >0 = fixed reference distance
    # risk
    stop_ticks: int = 100
    hp_stop_ticks: int = 50
    use_hp: bool = True
    hp_buffer_ticks: int = 4          # HP needs structural extreme inside the 50t stop minus buffer
    trail_lag: float = 1.0            # at +kR MFE: stop = entry + (k - lag) R
    partial_r: float = 0.0            # prop variant: scale out partial_frac at +partial_r R (limit, needs 1-tick trade-through)
    partial_frac: float = 0.5
    # costs
    slip_ticks: int = 1
    comm_rt: float = 4.50
    # direction
    allow_long: bool = True
    allow_short: bool = True


def _levels(f, i, p):
    """Level values known at the close of bar i (used by bar i+1)."""
    ve, se = f['vwapE'][i], f['sdE'][i]
    out = [('VWAP', ve)]
    for k in p.band_k:
        out.append((f'+{k:g}sd', ve + k * se))
        out.append((f'-{k:g}sd', ve - k * se))
    for m in p.mult_pct:
        out.append((f'x+{m:g}%', ve * (1 + m / 100)))
        out.append((f'x-{m:g}%', ve * (1 - m / 100)))
    if p.use_rth_vwap and not math.isnan(f['vwapR'][i]):
        out.append(('rVWAP', f['vwapR'][i]))
    if p.use_liq_levels:
        for k in ('onh', 'onl', 'pdh', 'pdl'):
            out.append((k.upper(), f[k][i]))
    return out


@dataclass
class Setup:
    dirn: int                 # +1 long (sweep below level), -1 short
    name: str
    level: float
    bar: int
    extreme: float
    swept: bool               # penetration >= pen_min (true manipulation) vs touch only
    conf: int
    abs_bar: int = -1
    abs_hi: float = float('nan')
    abs_lo: float = float('nan')


def run(f, p: Params, start=None, end=None):
    """f: dict of numpy arrays (see prepare). Returns trades DataFrame."""
    o, h, l, c = f['o'], f['h'], f['l'], f['c']
    rv, mod, last = f['relvol'], f['mod'], f['last']
    sd = f['sdate']
    n = len(o)
    t0 = np.searchsorted(sd, np.datetime64(start)) if start else 1
    t1 = np.searchsorted(sd, np.datetime64(end), side='right') if end else n
    t0 = max(t0, 1)
    trades = []
    pos = 0
    day = None
    ntr = 0
    setups = {1: None, -1: None}
    pending = None           # signal waiting for next-bar fill
    tk = TICK
    slip = p.slip_ticks * tk
    for i in range(t0, t1):
        if sd[i] != day:
            day = sd[i]
            ntr = 0
            setups = {1: None, -1: None}
            pending = None if pos == 0 else pending
        # ---- fill pending market entry at this bar's open
        if pending is not None:
            sig = pending
            pending = None
            if pos == 0 and mod[i] < p.flat_time and not last[i - 1]:
                pos = sig['dir']
                ep = o[i] + pos * slip
                st = sig['stop_ticks'] * tk
                stop = ep - pos * st
                tr = dict(sig, entry_i=i, entry=ep, risk=st, stop=stop, mfe=0.0)
                ntr += 1
        # ---- manage open position (stop first, using stop set at previous close)
        if pos != 0:
            tr['mfe'] = max(tr['mfe'], (h[i] - tr['entry']) if pos > 0 else (tr['entry'] - l[i]))
            hit = (l[i] <= tr['stop']) if pos > 0 else (h[i] >= tr['stop'])
            exit_px = None
            if hit:
                gap = (o[i] <= tr['stop']) if pos > 0 else (o[i] >= tr['stop'])
                base = o[i] if gap else tr['stop']
                exit_px, why = base - pos * slip, 'stop'
            elif mod[i] >= p.flat_time or last[i]:
                exit_px, why = c[i] - pos * slip, 'eod'
            if exit_px is None and p.partial_r > 0 and 'part_i' not in tr:
                lvl = tr['entry'] + pos * p.partial_r * tr['risk']
                if (pos > 0 and h[i] >= lvl + tk) or (pos < 0 and l[i] <= lvl - tk):
                    tr['part_i'], tr['part_pts'] = i, p.partial_r * tr['risk']
            if exit_px is not None:
                pts = (exit_px - tr['entry']) * pos
                tr['runner_pts'] = pts
                if 'part_i' in tr:
                    pts = p.partial_frac * tr['part_pts'] + (1 - p.partial_frac) * pts
                usd = pts * PT_VALUE - p.comm_rt
                tr.update(exit_i=i, exit=exit_px, why=why, pts=pts, usd=usd,
                          R=usd / (tr['risk'] * PT_VALUE))
                trades.append(tr)
                pos = 0
                setups = {1: None, -1: None}
            else:
                # R-step trailing, computed at close, active from next bar
                k = math.floor(tr['mfe'] / tr['risk'] + 1e-9)
                if k >= 1:
                    ns = tr['entry'] + pos * (k - p.trail_lag) * tr['risk']
                    if (pos > 0 and ns > tr['stop']) or (pos < 0 and ns < tr['stop']):
                        tr['stop'] = ns
                        tr['trail_steps'] = k
        # ---- setup detection only while flat, in window, trades left
        if mod[i] < p.win_start or mod[i] >= p.win_end or ntr >= p.max_trades or pos != 0:
            continue
        lv = _levels(f, i - 1, p)
        sigs = []
        for dirn in (1, -1):
            if (dirn == 1 and not p.allow_long) or (dirn == -1 and not p.allow_short):
                continue
            s = setups[dirn]
            # update / invalidate
            if s is not None:
                s.extreme = min(s.extreme, l[i]) if dirn == 1 else max(s.extreme, h[i])
                depth = (s.level - s.extreme) * dirn
                if depth > p.pen_max_ticks * tk or i - s.bar > p.setup_bars:
                    s = setups[dirn] = None
                elif depth >= p.pen_min_ticks * tk:
                    s.swept = True
            if s is not None and s.abs_bar >= 0 and i > s.abs_bar:
                # continuation through the absorption bar extreme kills the absorption
                if (dirn == 1 and l[i] < s.abs_lo - p.touch_ticks * tk) or \
                   (dirn == -1 and h[i] > s.abs_hi + p.touch_ticks * tk):
                    s.abs_bar = -1
            # new manipulation / level test
            if s is None:
                best = None
                for name, L in lv:
                    if math.isnan(L):
                        continue
                    if dirn == 1:
                        came_from = c[i - 1] > L
                        pen = L - l[i]
                    else:
                        came_from = c[i - 1] < L
                        pen = h[i] - L
                    if not came_from or pen < -p.touch_ticks * tk or pen > p.pen_max_ticks * tk:
                        continue
                    # choose the level closest to the extreme (where the move stopped)
                    if best is None or pen < best[2]:
                        best = (name, L, pen)
                if best is not None:
                    name, L, pen = best
                    conf = sum(1 for _, x in lv if not math.isnan(x) and abs(x - L) <= p.conf_tol_ticks * tk)
                    s = setups[dirn] = Setup(dirn, name, L, i, l[i] if dirn == 1 else h[i],
                                             pen >= p.pen_min_ticks * tk, conf)
            if s is None:
                continue
            rng = h[i] - l[i]
            # absorption on this bar
            if s.abs_bar < 0 and rng > 0 and not math.isnan(rv[i]):
                at_level = (l[i] <= s.level + p.touch_ticks * tk) if dirn == 1 else \
                           (h[i] >= s.level - p.touch_ticks * tk)
                wick = ((min(o[i], c[i]) - l[i]) if dirn == 1 else (h[i] - max(o[i], c[i]))) / rng
                cl = ((c[i] - l[i]) if dirn == 1 else (h[i] - c[i])) / rng
                er_ok = p.er_max <= 0 or (not math.isnan(f['relrange'][i]) and f['relrange'][i] / rv[i] <= p.er_max)
                if at_level and rv[i] >= p.rv_min and (wick >= p.wick_min or cl >= p.cl_min) and er_ok:
                    s.abs_bar, s.abs_hi, s.abs_lo = i, h[i], l[i]
                    continue  # trigger must come on a later bar
            # distribution trigger
            if s.abs_bar >= 0 and i > s.abs_bar and rng > 0:
                mid = (s.abs_hi + s.abs_lo) / 2
                if dirn == 1:
                    body = (c[i] - o[i]) / rng
                    cl = (c[i] - l[i]) / rng
                    trig = c[i] > s.level and (c[i] > s.abs_hi if p.trigger == 'abs_break' else (c[i] > mid and body > 0))
                else:
                    body = (o[i] - c[i]) / rng
                    cl = (h[i] - c[i]) / rng
                    trig = c[i] < s.level and (c[i] < s.abs_lo if p.trigger == 'abs_break' else (c[i] < mid and body > 0))
                if trig:
                    disp = body >= p.disp_body and cl >= p.disp_cl
                    tier = 'A' if (s.swept and disp) else 'B'
                    if tier == 'B' and not p.allow_b:
                        continue
                    stop_t = p.stop_ticks
                    hp = False
                    room = (c[i] - s.extreme) * dirn + p.hp_buffer_ticks * tk
                    if p.use_hp and tier == 'A' and room <= p.hp_stop_ticks * tk:
                        hp, stop_t = True, p.hp_stop_ticks
                    ref = p.struct_ref_ticks if p.struct_ref_ticks > 0 else stop_t
                    if p.struct_filter and (c[i] - s.extreme) * dirn + p.struct_buffer_ticks * tk > ref * tk:
                        continue
                    sigs.append(dict(dir=dirn, tier=tier, level=s.name, conf=s.conf, hp=hp,
                                     stop_ticks=stop_t, sig_i=i, sweep_i=s.bar, abs_i=s.abs_bar,
                                     swept=s.swept))
        if len(sigs) == 1:
            pending = sigs[0]
            setups = {1: None, -1: None}
        elif len(sigs) > 1:
            setups = {1: None, -1: None}   # conflicting directions: stand aside
    return pd.DataFrame(trades)


def prepare(df):
    return dict(o=df.o.to_numpy(), h=df.h.to_numpy(), l=df.l.to_numpy(), c=df.c.to_numpy(),
                vwapE=df.vwapE.to_numpy(), sdE=df.sdE.to_numpy(), vwapR=df.vwapR.to_numpy(),
                relvol=df.relvol.to_numpy(), relrange=df.relrange.to_numpy(),
                onh=df.onh.to_numpy(), onl=df.onl.to_numpy(), pdh=df.pdh.to_numpy(), pdl=df.pdl.to_numpy(), mod=df['mod'].to_numpy(), last=df.last_in_session.to_numpy(),
                sdate=df.sdate.to_numpy().astype('datetime64[D]'), t=df.t.to_numpy())


def stats(tr, f=None, label=''):
    if len(tr) == 0:
        return dict(label=label, n=0)
    w, ls = tr[tr.usd > 0], tr[tr.usd <= 0]
    eq = tr.R.cumsum()
    dd = (eq.cummax().clip(lower=0) - eq).max()
    days = tr.sdate.nunique() if 'sdate' in tr else np.nan
    return dict(label=label, n=len(tr), net_usd=round(tr.usd.sum(), 0),
                pf=round(w.usd.sum() / -ls.usd.sum(), 3) if len(ls) and ls.usd.sum() < 0 else np.inf,
                win=round(len(w) / len(tr), 3), avg_win=round(w.usd.mean(), 1) if len(w) else 0,
                avg_loss=round(ls.usd.mean(), 1) if len(ls) else 0, expR=round(tr.R.mean(), 3),
                maxdd_R=round(dd, 2), sumR=round(tr.R.sum(), 1))
