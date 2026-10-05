import pandas as pd
from multiprocessing import Pool
import fvg_lab as L
STOPS = [('fixed', 30.0), ('fixed', 40.0), ('fixed', 50.0), ('fixed', 60.0), ('fixed', 80.0), ('struct', 0), ('atr', 0.10), ('atr', 0.15), ('atr', 0.20)]
EXITS = [('TP2', 2.0, False), ('TP3', 3.0, False), ('TP4', 4.0, False), ('TP5', 5.0, False), ('Trail', 0.0, True)]
HOLDS = [1, 2, 5]
_c = {}
def job(cfg):
    st, ex, hold = cfg
    out = {}
    for sp in ('train', 'valid'):
        if sp not in _c: _c[sp] = L.candidates(sp)
        t = L.run(sp, (), st, ex[1], ex[2], hold, cand=_c[sp])
        out[sp] = L.stats(t, sp)
    return cfg, out
if __name__ == '__main__':
    cfgs = [(s, e, h) for s in STOPS for e in EXITS for h in HOLDS]
    with Pool(4) as p: res = p.map(job, cfgs, chunksize=2)
    rows = [dict(stop=f'{s[0]}{s[1]:g}', exit=e[0], hold=h, pw_tr=o['train']['per_week'], win_tr=o['train']['win'], E_tr=o['train']['E'],
                 dd_tr=o['train']['dd'], win_va=o['valid']['win'], E_va=o['valid']['E'], dd_va=o['valid']['dd'], avgwin_va=o['valid']['avg_win'])
            for (s, e, h), o in res]
    df = pd.DataFrame(rows); df['minE'] = df[['E_tr', 'E_va']].min(axis=1)
    df.to_csv('v5_phaseC.csv', index=False)
    print('by holding period (mean over stops/exits):'); print(df.groupby('hold')[['E_tr', 'E_va']].mean().round(3).to_string())
    print('by stop:'); print(df.groupby('stop')[['E_tr', 'E_va']].mean().round(3).to_string())
    print('by exit:'); print(df.groupby('exit')[['E_tr', 'E_va']].mean().round(3).to_string())
    print('\npositive in both:', int(((df.E_tr > 0) & (df.E_va > 0)).sum()), 'of', len(df))
    print(df.sort_values('minE', ascending=False).head(15).round(3).to_string(index=False))
