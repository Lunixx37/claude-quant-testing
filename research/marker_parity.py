"""Bar-by-bar replica of pine/NY_VolBreakout_Marker.pine (gap filter on), compared with research trades (v10 base + v8 gapfilter, NQ)."""
import sys, math, pickle, numpy as np, pandas as pd
sys.path.insert(0, '/home/user/larp-larp-larp-sahur/research')
import lab
ds = lab.DS('nq', '2023-01-01', '2025-12-11'); f = ds.f
o, h, l, c, mod, sd = f['o'], f['h'], f['l'], f['c'], f['mod'], f['sdate']
K, SM, LAG, SLIP, MAXT = 0.35, 0.75, 1.25, 0.25, 2
rthH = rthL = prevRange = open930 = np.nan
lastC = pc = np.nan; hist = []
tradesToday = 0; pos = 0; pend = 0; trades = []
prev_in = False
for i in range(len(o)):
    inR = 570 <= mod[i] < 960
    start = inR and (not prev_in or (i > 0 and sd[i] != sd[i - 1]))
    if start:
        pc = lastC
        if not np.isnan(rthH):
            prevRange = rthH - rthL; hist = (hist + [prevRange])[-14:]
        rthH, rthL, open930, tradesToday = h[i], l[i], o[i], 0
    elif inR:
        rthH, rthL = max(rthH, h[i]), min(rthL, l[i])
    prev_in = inR
    if inR: lastC = c[i]
    up, dn = open930 + K * prevRange, open930 - K * prevRange
    exited = False
    if pend:
        pos, ep, R, mfe, e_i, fl = pend, o[i] + pend * SLIP, pR, 0.0, i, pf
        st = ep - pos * R; pend = 0
    if pos:
        mfe = max(mfe, h[i] - ep if pos == 1 else ep - l[i]); x = None
        if (pos == 1 and l[i] <= st) or (pos == -1 and h[i] >= st):
            g = o[i] <= st if pos == 1 else o[i] >= st
            x = (o[i] if g else st) - pos * SLIP
        elif mod[i] >= 959 or not inR:
            x = (c[i] if inR else o[i]) - pos * SLIP
        else:
            n = math.floor(mfe / R + 1e-9)
            if n >= 1:
                ns = ep + pos * (n - LAG) * R
                st = max(st, ns) if pos == 1 else min(st, ns)
        if x is not None:
            trades.append((sd[e_i], e_i, pos, round((x - ep) * pos, 4), fl)); pos = 0; exited = True
    if inR and mod[i] < 959 and pos == 0 and pend == 0 and not exited and not np.isnan(prevRange) and tradesToday < MAXT:
        d = 1 if h[i] >= up else -1 if l[i] <= dn else 0
        if d:
            pend, pR = d, SM * K * prevRange; tradesToday += 1
            atr = np.mean(hist) if len(hist) == 14 else np.nan
            g = (open930 - pc) / atr * d if atr > 0 else np.nan
            pf = bool(g > -0.405 and g <= 0.079)
M = pd.DataFrame(trades, columns=['sdate', 'e', 'dir', 'pts', 'fl'])
M = M[~M.fl]
from v8_combo import gapfilter
B = gapfilter(pickle.load(open('cache/v10_trades_nq.pkl', 'rb'))['base'], 'nq', ('2023-01-01', '2025-12-11'))
B = B.assign(pts=B.pts.round(4))
j = M.merge(B[['e', 'dir', 'pts']], on='e', how='outer', suffixes=('_m', '_b'), indicator=True)
same = (j._merge == 'both') & (j.dir_m == j.dir_b) & (abs(j.pts_m - j.pts_b) < 1e-6)
print(f'marker {len(M)} trades, research {len(B)}; identical {same.sum()}; only marker {(j._merge=="left_only").sum()}, only research {(j._merge=="right_only").sum()}, differ {((j._merge=="both") & ~same).sum()}')
print(j[~same].head(12).to_string())
