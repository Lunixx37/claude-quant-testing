"""V7: volatility breakout anchored at different sessions, with optional re-entry (PROTOCOL_V7.md).

Session position pos = minutes since the 18:00 NY reopen (0 .. 1379). One NY trading date = one session.
Signals: first bar in the window whose high >= anchor_open + k*range (long) / low <= anchor_open - k*range (short).
Entry at the next bar's open, stop = sm*k*range, R-step trailing (lag 1.25) or hold to the window end.
"""
import numpy as np, pandas as pd
import lab

MODELS = {   # name: (anchor_pos, signal_end_pos, exit_pos, range_source, off_hours)
    'M0/M1 NY':       (930, 1319, 1319, 'prevRTH', False),
    'M2 Asia':        (0, 539, 539, 'prevRTH', True),
    'M3 London/asia': (540, 929, 929, 'asia', True),
    'M3 London/prev': (540, 929, 929, 'prevRTH', True),
    'M4 Afternoon':   (1140, 1319, 1319, 'morning', False),
}
HOURS = [(h * 60 - 1080) % 1440 for h in range(10, 16)]      # hourly anchors 10:00..15:00 NY
OFF_EXTRA = 0.5                                             # extra slippage pts per round trip off-hours
OFF_SPREAD = 2.5                                            # CFD spread off-hours


class Sess:
    def __init__(self, ds):
        self.ds = ds
        df = ds.df
        self.pos = ((df['mod'].to_numpy() - 1080) % 1440)
        sd = df.sdate.to_numpy()
        starts = np.r_[0, np.flatnonzero(sd[1:] != sd[:-1]) + 1]
        ends = np.r_[starts[1:], len(sd)]
        keep = pd.to_datetime(sd[starts]).isin(ds.d.index)          # sessions inside the dataset period
        self.sessions = [(s, e) for s, e, k in zip(starts, ends, keep) if k]

    def win(self, s, e, p0, p1):
        """bar indices of session [s, e) with p0 <= pos < p1"""
        a = s + np.searchsorted(self.pos[s:e], p0, 'left')
        b = s + np.searchsorted(self.pos[s:e], p1, 'left')
        return a, b


def run_model(S, model, k, sm, exitm, side, maxtr=1, lag=1.25, tp_r=0.0):
    ds = S.ds; f = ds.f
    o, h, l = f['o'], f['h'], f['l']
    hourly = model == 'M5 Hourly'
    specs = [(p, p + 59, min(p + 119, 1319), 'prevhour', False) for p in HOURS] if hourly else [MODELS[model]]
    out = []
    prev_rth = np.nan
    for s, e in S.sessions:
        ra, rb = S.win(s, e, 930, 1320)
        rth_range_today = (h[ra:rb].max() - l[ra:rb].min()) if rb - ra > 200 else np.nan
        last_exit = -1
        for p0, p_sig, p_exit, src, off in specs:
            a, b = S.win(s, e, p0, p_sig + 1)
            xa, xb = S.win(s, e, p0, p_exit + 1)
            if b - a < 5 or xb <= a:
                continue
            if src == 'prevRTH':
                rg = prev_rth
            elif src == 'asia':
                qa, qb = S.win(s, e, 0, 540); rg = h[qa:qb].max() - l[qa:qb].min() if qb > qa else np.nan
            elif src == 'morning':
                qa, qb = S.win(s, e, 930, 1140); rg = h[qa:qb].max() - l[qa:qb].min() if qb > qa else np.nan
            else:
                qa, qb = S.win(s, e, p0 - 60, p0); rg = h[qa:qb].max() - l[qa:qb].min() if qb - qa >= 30 else np.nan
            if not (rg > 0):
                continue
            up, dn = o[a] + k * rg, o[a] - k * rg
            sp = sm * k * rg
            deadline = xb - 1
            n_tr, i = 0, a
            while i < b and n_tr < maxtr:
                if i <= last_exit:
                    i += 1; continue
                dd = 1 if h[i] >= up else -1 if l[i] <= dn else 0
                if dd == 0:
                    i += 1; continue
                if side == 'long' and dd == -1:
                    break
                if i + 1 > deadline:
                    break
                ep, x, xi, why, nights = lab.sim_trade(f, i + 1, dd, sp, tp_r * sp, deadline, exitm == 'trail', lag)
                pts = (x - ep) * dd - (OFF_EXTRA if off else 0.0)
                spread = OFF_SPREAD if off else lab.SPREAD
                out.append((f['sdate'][i + 1], i + 1, xi, dd, sp, pts, why, model, (pts - spread) / sp, (pts - lab.COMM) / sp))
                n_tr += 1; last_exit = xi; i = xi + 1
        if not np.isnan(rth_range_today):
            prev_rth = rth_range_today
    return pd.DataFrame(out, columns=['sdate', 'e', 'x_i', 'dir', 'stop', 'pts', 'why', 'model', 'Rc', 'Rf'])


def grid():
    G = []
    for mx in (1, 2, 3):
        for k in (0.25, 0.3, 0.35):
            for sm in (0.75, 1.0):
                G.append(('M0/M1 NY', dict(k=k, sm=sm, exitm='trail', side='both', maxtr=mx)))
    for m in ('M2 Asia', 'M3 London/asia', 'M3 London/prev', 'M4 Afternoon'):
        for k in (0.2, 0.3, 0.4, 0.5):
            for sm in (0.75, 1.0):
                for ex in ('trail', 'end'):
                    for side in ('both', 'long'):
                        G.append((m, dict(k=k, sm=sm, exitm=ex, side=side)))
    for k in (0.2, 0.3, 0.4, 0.5, 0.75, 1.0):
        for sm in (0.75, 1.0):
            for ex in ('trail', 'end'):
                for side in ('both', 'long'):
                    G.append(('M5 Hourly', dict(k=k, sm=sm, exitm=ex, side=side)))
    return G
