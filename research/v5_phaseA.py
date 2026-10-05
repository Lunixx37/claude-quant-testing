import pandas as pd
from multiprocessing import Pool
import fvg_lab as L
def job(fname):
    out = {}
    for sp in ('train', 'valid'):
        out[sp] = L.stats(L.run(sp, (fname,) if fname else ()), sp)
    return fname, out
if __name__ == '__main__':
    names = [None] + list(L.FILTERS)
    with Pool(4) as p: res = p.map(job, names)
    base = dict(res)[None]
    rows = []
    for n, o in res:
        rows.append(dict(filter=n or 'BASE', n_tr=o['train']['n'], pw_tr=o['train']['per_week'], win_tr=o['train']['win'], E_tr=o['train']['E'],
                         n_va=o['valid']['n'], pw_va=o['valid']['per_week'], win_va=o['valid']['win'], E_va=o['valid']['E']))
    df = pd.DataFrame(rows)
    df['keep'] = (df.E_tr > base['train']['E']) & (df.E_va > base['valid']['E']) & (df.pw_tr >= 1.5) & (df.pw_va >= 1.5) & (df.filter != 'BASE')
    df.to_csv('v5_phaseA.csv', index=False)
    print(df.round(3).to_string(index=False))
