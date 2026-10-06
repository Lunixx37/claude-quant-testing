"""V11 build-up simulation: monthly block bootstrap of NQ 2023-25 trades, fixed-fractional risk (PROTOCOL_V11.md)."""
import pickle, numpy as np, pandas as pd
from v8_combo import gapfilter

N = pickle.load(open('cache/v11_trades_nq.pkl', 'rb')); C = pickle.load(open('cache/v11_trades_cfd.pkl', 'rb'))
fin = pickle.load(open('cache/v11_finalists.pkl', 'rb'))['fin']
hw = fin.iloc[0]
v10n = pickle.load(open('cache/v10_trades_nq.pkl', 'rb'))
S = {
    'HW: VBO long k0.5, TP 0.2x stop (Winrate ~80 %)': (N[hw.key], 'Rf', hw.kelly),
    'Ref: VBO-Live (V7 + Gap-Filter)': (gapfilter(v10n['base'], 'nq', ('2023-01-01', '2025-12-11')), 'Rf', 0.106),
}
rng = np.random.default_rng(11)
out = []
for name, (t, col, kel) in S.items():
    t = t.assign(m=pd.to_datetime(t.sdate).dt.to_period('M'))
    months = pd.period_range(t.m.min(), t.m.max(), freq='M')
    blocks = [t.loc[t.m == m, col].to_numpy() for m in months]
    r = t[col].to_numpy()
    tstat = r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))
    out.append(f'\n=== {name}: NQ n={len(r)}, win {(r > 0).mean():.1%}, E {r.mean():+.3f} R (t = {tstat:.2f}), Kelly (dev) {kel:.3f}')
    out.append(f'{"risk/trade":>12s} {"median 6M":>10s} {"median 12M":>11s} {"10% quantile 12M":>17s} {"P(2x in 6M)":>12s} {"P(DD>=50%)":>11s} {"P(<start 12M)":>14s}')
    for risk in (0.02, 0.05, 0.10, 0.20, kel / 2):
        e6, e12, dd50, dbl = [], [], 0, 0
        for _ in range(2000):
            eq, peak, mdd, hit2 = 1.0, 1.0, 0.0, False
            for mi in range(12):
                for x in blocks[rng.integers(len(blocks))]:
                    eq *= max(1 + risk * x, 0.0)
                    peak = max(peak, eq); mdd = max(mdd, 1 - eq / peak if peak > 0 else 1)
                    if mi < 6 and eq >= 2:
                        hit2 = True
                if mi == 5:
                    e6.append(eq)
            e12.append(eq); dd50 += mdd >= .5; dbl += hit2
        e12 = np.array(e12)
        lab_ = f'{risk:.1%}' + (' (Kelly/2)' if risk == kel / 2 else '')
        out.append(f'{lab_:>12s} {np.median(e6):10.2f}x {np.median(e12):10.2f}x {np.quantile(e12, .1):16.2f}x {dbl / 2000:12.1%} {dd50 / 2000:11.1%} {(e12 < 1).mean():14.1%}')
txt = 'Build-up simulation: 2,000 paths x 12 months, monthly block bootstrap of NQ 2023-25 trades; equity relative to start.\n' + '\n'.join(out)
open('v11_buildup_result.txt', 'w').write(txt + '\n'); print(txt)
