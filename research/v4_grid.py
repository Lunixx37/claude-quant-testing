"""V4: all confluence combinations (no VWAP / order flow) x stops x exits, MNQ and CFD costs."""
import sys, pickle, itertools, time
import numpy as np, pandas as pd
from multiprocessing import Pool
from features import load
from engine import prepare
import ict
from v3_grid import SPLITS
BLOCKS = ['fvg', 'rb', 'ob', 'm', 'mss', 'ls', 'mss_recent']
TRIG = {'fvg', 'rb', 'ob', 'm', 'mss'}
COMBOS = [c for r in range(1, 8) for c in itertools.combinations(BLOCKS, r) if TRIG & set(c)]
STOPS = [15.0, 25.0, 40.0]
EXITS = {'TP0.1': (0.1, False), 'TP0.2': (0.2, False), 'TP0.3': (0.3, False), 'TP0.5': (0.5, False), 'TP1': (1.0, False),
         'TP1.5': (1.5, False), 'TP2': (2.0, False), 'TP3': (3.0, False), 'Trail': (0.0, True)}
G = {}
def init(split):
    C = pickle.load(open('cache/v3_candidates.pkl', 'rb'))
    G['parts'] = []
    for key in SPLITS[split]:
        G.setdefault(key[0], prepare(load(key[0])))
        G['parts'].append((G[key[0]], C[key]))
    G['weeks'] = sum((pd.Timestamp(e) - pd.Timestamp(s)).days for _, s, e in SPLITS[split]) / 7
def mask_of(combo):
    return sum(ict.BIT[b] for b in combo)
def stats(t, col, weeks):
    if len(t) == 0:
        return dict(n=0)
    x = t[col]; w = x[x > 0]; eq = x.cumsum()
    return dict(n=len(t), per_week=len(t) / weeks, win=(x > 0).mean(), avg_win=w.mean() if len(w) else 0,
                avg_loss=x[x <= 0].mean() if (x <= 0).any() else 0, E=x.mean(),
                pf=w.sum() / -x[x <= 0].sum() if (x <= 0).any() and x[x <= 0].sum() < 0 else np.inf,
                dd=(eq.cummax().clip(lower=0) - eq).max(), sd=x.std())
def run_cfg(cfg):
    combo, stop, ex = cfg
    m = mask_of(combo); tp, tr = EXITS[ex]
    pred = lambda fl, md: (fl & m) == m
    ts = [ict.simulate(f, c, pred, 'fixed', tp, tr, fallback=False, fixed_pts=stop) for f, c in G['parts']]
    t = pd.concat(ts, ignore_index=True) if any(len(x) for x in ts) else pd.DataFrame(columns=['R', 'Rc'])
    return cfg, stats(t, 'Rc', G['weeks']), stats(t, 'R', G['weeks'])
def grid(split, cfgs=None):
    cfgs = cfgs or [(c, s, e) for c in COMBOS for s in STOPS for e in EXITS]
    with Pool(4, initializer=init, initargs=(split,)) as p:
        return p.map(run_cfg, cfgs, chunksize=8)
if __name__ == '__main__':
    split = sys.argv[1]
    t0 = time.time(); res = grid(split)
    rows = []
    for (combo, stop, ex), sc, sm in res:
        rows.append(dict(combo='+'.join(combo), stop=stop, exit=ex,
                         **{f'{k}_cfd': v for k, v in sc.items()}, **{f'{k}_mnq': v for k, v in sm.items() if k in ('E', 'win', 'pf')}))
    df = pd.DataFrame(rows); df.to_csv(f'v4_grid_{split}.csv', index=False)
    print(f'{split}: {len(df)} configs in {time.time()-t0:.0f}s; combos={len(COMBOS)}')
