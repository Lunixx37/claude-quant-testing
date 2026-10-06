"""Full trade statistics of the recommended VBO variants (live: V7 + gap filter, prop: V7 base) and alternatives."""
import pickle, numpy as np, pandas as pd
from v8_combo import gapfilter

v10c, v10n = pickle.load(open('cache/v10_trades_cfd.pkl', 'rb')), pickle.load(open('cache/v10_trades_nq.pkl', 'rb'))
v9c, v9n = pickle.load(open('cache/v9_trades_cfd.pkl', 'rb')), pickle.load(open('cache/v9_trades_nq.pkl', 'rb'))
poc = (('poc', 1.5), ('base s1 lag1.25', 1.0, 1.25))
CFDP, NQP = ('2017-01-01', '2025-09-30'), ('2023-01-01', '2025-12-11')
C = {
    'LIVE: V7 + Gap-Filter': (gapfilter(v10c['base'], 'cfd', CFDP), gapfilter(v10n['base'], 'nq', NQP), 1.0),
    'PROP: V7 Basis': (v10c['base'], v10n['base'], 1.0),
    'Alt: V7 + Cut 0.9R': (v10c['cut 0.9R'], v10n['cut 0.9R'], 0.9),
    'Alt: V7 + POC-Ziel >=1.5R': (v9c[poc], v9n[poc], 1.0),
}


def streak(x):
    best = cur = 0
    for v in x:
        cur = cur + 1 if v else 0; best = max(best, cur)
    return best


def stats(t, col, cut):
    t = t.assign(sdate=pd.to_datetime(t.sdate))
    r = t[col].to_numpy() / cut                     # in units of the $ actually risked
    w, l = r[r > 0], r[r <= 0]
    eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
    m = pd.Series(r, index=t.sdate).groupby(t.sdate.dt.to_period('M').to_numpy()).sum()
    allm = pd.period_range(m.index.min(), m.index.max(), freq='M'); m = m.reindex(allm, fill_value=0)
    y = pd.Series(r, index=t.sdate).groupby(t.sdate.dt.year.to_numpy()).sum()
    dur = (t.x_i - t.e + 1).to_numpy()
    lg, sh = r[t.dir.to_numpy() == 1], r[t.dir.to_numpy() == -1]
    return {
        'Trades': len(r), 'Trades/Monat': len(r) / len(allm), 'Trefferquote': (r > 0).mean(),
        'Ø Gewinn (R)': w.mean(), 'Ø Verlust (R)': l.mean(), 'RR (Ø Gew./Ø Verl.)': w.mean() / -l.mean(),
        'Erwartungswert (R/Trade)': r.mean(), 'Profit-Faktor': w.sum() / -l.sum(),
        'Größter Gewinn (R)': r.max(), 'Gewinne >= 3R': (r >= 3).mean(),
        'Längste Verlustserie': streak(r <= 0), 'Max. Drawdown (R)': dd,
        'R/Monat': m.mean(), 'Positive Monate': (m > 0).mean(), 'Schlechtester Monat (R)': m.min(), 'Bester Monat (R)': m.max(),
        'Positive Jahre': f'{(y > 0).sum()}/{len(y)}',
        'Long: n / E': f'{len(lg)} / {lg.mean():+.3f}', 'Short: n / E': f'{len(sh)} / {sh.mean():+.3f}',
        'Haltedauer Median (Min.)': np.median(dur),
    }


out = []
for name, (c, n, cut) in C.items():
    c = c.assign(sdate=pd.to_datetime(c.sdate))
    for ds, t, col in (('Entw. CFD 2017-22', c[c.sdate < '2023-01-01'], 'Rc'), ('Test CFD 2023-25', c[c.sdate >= '2023-01-01'], 'Rc'), ('Test NQ 2023-25', n, 'Rf')):
        out.append(pd.Series(stats(t, col, cut), name=(name, ds)))
df = pd.DataFrame(out).T
pd.set_option('display.width', 300); pd.set_option('display.max_columns', 20)
with open('v10_stats_result.txt', 'w') as fh:
    for name in C:
        s = df[[c for c in df.columns if c[0] == name]]; s.columns = [c[1] for c in s.columns]
        txt = s.map(lambda v: f'{v:.3f}' if isinstance(v, float) else v).to_string()
        fh.write(f'=== {name} (R = $ actually risked per trade; CFD net of spread, NQ net of MNQ costs)\n{txt}\n\n'); print(f'=== {name}\n{txt}\n')
