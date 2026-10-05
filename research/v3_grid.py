"""Evaluate the pre-registered V3 grid (11 setups x 2 stops x 6 exits) on a split."""
import sys, pickle
import numpy as np, pandas as pd
from multiprocessing import Pool
from features import load
from engine import prepare
import ict
SPLITS = {'train': [('cfd', '2017-01-01', '2018-12-31'), ('cfd', '2019-01-01', '2020-06-30')],
          'valid': [('cfd', '2020-07-01', '2021-12-31')],
          'testA': [('cfd', '2022-01-01', '2022-12-31')],
          'testB_nq': [('nq', '2023-01-01', '2025-12-11')],
          'testB_cfd': [('cfd', '2023-01-01', '2025-09-30')]}
EXITS = {'TP1.5': (1.5, False), 'TP2': (2.0, False), 'TP2.5': (2.5, False), 'TP3': (3.0, False),
         'Trail': (0.0, True), 'TP3+Trail': (3.0, True)}
STOPS = ['struct', 'fixed']
G = {}
def init(split):
    C = pickle.load(open('cache/v3_candidates.pkl', 'rb'))
    G['parts'] = []
    for key in SPLITS[split]:
        G.setdefault(key[0], prepare(load(key[0])))
        G['parts'].append((G[key[0]], C[key]))
    G['weeks'] = sum((pd.Timestamp(e) - pd.Timestamp(s)).days for _, s, e in SPLITS[split]) / 7
def run_cfg(cfg):
    setup, stop, ex = cfg
    tp, tr = EXITS[ex]
    ts = [ict.simulate(f, c, setup, stop, tp, tr, fallback=True) for f, c in G['parts']]
    t = pd.concat(ts, ignore_index=True)
    s = ict.summarize(t, G['weeks'])
    p = t[t.kind == 'primary']
    s['E_primary'] = p.R.mean() if len(p) else np.nan
    s['E_fallback'] = t[t.kind != 'primary'].R.mean() if (t.kind != 'primary').any() else np.nan
    return cfg, s, t
def grid(split, cfgs=None):
    cfgs = cfgs or [(s, st, e) for s in ict.SETUPS for st in STOPS for e in EXITS]
    with Pool(4, initializer=init, initargs=(split,)) as p:
        return p.map(run_cfg, cfgs, chunksize=2)
if __name__ == '__main__':
    split = sys.argv[1]
    res = grid(split)
    rows = []
    for (setup, stop, ex), s, t in res:
        rows.append(dict(setup=setup, stop=stop, exit=ex, **{k: s.get(k) for k in
                    ('n', 'per_week', 'win', 'avg_win_gross', 'avg_win_R', 'E', 'pf', 'dd', 'sumR', 'share_primary', 'E_primary', 'E_fallback')}))
    df = pd.DataFrame(rows)
    df['target'] = (df.win > 0.5) & (df.avg_win_gross >= 2) & (df.avg_win_gross <= 3.2) & (df.per_week >= 4)
    df.to_csv(f'v3_grid_{split}.csv', index=False)
    pd.set_option('display.width', 250); pd.set_option('display.max_rows', 200)
    print(df.round(3).to_string(index=False))
    print('\nconfigs meeting the user target (WR>50%, avg winner 2-3R gross, >=4/week):', int(df.target.sum()), 'of', len(df))
