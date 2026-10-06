"""Live-account comparison of the VBO variants: fixed-fractional risk on equity, real trade order (no bootstrap)."""
import pickle, numpy as np, pandas as pd
from v6_wf import live
from v6_eval import kelly
from v8_combo import gapfilter

v6c, v6n = pickle.load(open('cache/v6_trades_cfd.pkl', 'rb')), pickle.load(open('cache/v6_trades_nq.pkl', 'rb'))
v10c, v10n = pickle.load(open('cache/v10_trades_cfd.pkl', 'rb')), pickle.load(open('cache/v10_trades_nq.pkl', 'rb'))
key = lambda s: ('F7b VBO refined', (('filt', 'none'), ('k', 0.3), ('side', s), ('sm', 1.0), ('tgt', 'trail')))
CFDP, NQP = ('2017-01-01', '2025-09-30'), ('2023-01-01', '2025-12-11')
C = {
    'V6 long-only 1/Tag (k0.3)': (v6c[key('long')], v6n[key('long')]),
    'V6 beide 1/Tag (k0.3)': (v6c[key('both')], v6n[key('both')]),
    'V7 beide 2/Tag (Prop-Basis)': (v10c['base'], v10n['base']),
    'V7 + Gap-Filter': (gapfilter(v10c['base'], 'cfd', CFDP), gapfilter(v10n['base'], 'nq', NQP)),
    'V7 + Cut 0.9R': (v10c['cut 0.9R'], v10n['cut 0.9R']),
    'V7 + TP 4R ohne Trailing': (v10c['fixed TP 4R (no trail)'], v10n['fixed TP 4R (no trail)']),
}
rows = []
for name, (c, n) in C.items():
    c = c.assign(sdate=pd.to_datetime(c.sdate), w=1.0); n = n.assign(sdate=pd.to_datetime(n.sdate), w=1.0)
    # R relative to the actual $ risk taken (cut variants: stop column = R*cut, so rescale to 'per $ risked')
    rs = lambda t, col: t[col] * (t.stop / t.stop) if 'cut' not in name else t[col] / 0.9
    sets = {'dev': (c[c.sdate < '2023-01-01'], 'Rc'), 'cfd23': (c[c.sdate >= '2023-01-01'], 'Rc'), 'nq': (n, 'Rf')}
    kel = kelly(rs(sets['dev'][0], 'Rc').to_numpy())
    r = dict(variant=name, kelly_dev=kel)
    yrs = c.groupby(c.sdate.dt.year)['Rc'].sum()
    r['pos_years_cfd'] = f'{(yrs > 0).sum()}/{len(yrs)}'
    for s, (t, col) in sets.items():
        t = t.assign(**{col: rs(t, col)})
        r[f'{s}_tr_mo'] = len(t) / max(1, t.sdate.dt.to_period('M').nunique())
        r[f'{s}_E'] = t[col].mean()
        L1 = live(t, 0.01, col); LH = live(t, kel / 2, col)
        r[f'{s}_1%_mo'] = L1['avg_month']; r[f'{s}_1%_dd'] = L1['maxdd']
        r[f'{s}_hk_mo'] = LH['avg_month']; r[f'{s}_hk_dd'] = LH['maxdd']; r[f'{s}_hk_posm'] = LH['pos_months']
    rows.append(r)
df = pd.DataFrame(rows)
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 40)
with open('v10_live_result.txt', 'w') as fh:
    fh.write('Live comparison: fixed-fractional risk on equity, real trade order. 1% = 1% risk/trade; hk = half Kelly (Kelly from dev CFD 2017-22).\n'
             'Cut 0.9R: R rescaled to the $ actually risked (stop = 0.9R). Monthly returns = arithmetic mean of monthly % returns.\n\n')
    fh.write(df.round(3).to_string(index=False) + '\n')
print(df.round(3).to_string(index=False))
