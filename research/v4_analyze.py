import numpy as np, pandas as pd
tr = pd.read_csv('v4_grid_train.csv'); va = pd.read_csv('v4_grid_valid.csv')
m = tr.merge(va, on=['combo', 'stop', 'exit'], suffixes=('_tr', '_va'))
m = m[(m.n_cfd_tr > 0) & (m.n_cfd_va > 0)]
EX = ['TP0.1', 'TP0.2', 'TP0.3', 'TP0.5', 'TP1', 'TP1.5', 'TP2', 'TP3', 'Trail']
print(f'configs evaluated: {len(m)}')
print('E (CFD costs) train vs valid correlation across configs: %.2f' % m.E_cfd_tr.corr(m.E_cfd_va))
print('share with E_cfd>0: train %.1f%%, valid %.1f%%, both %.1f%%' % (100*(m.E_cfd_tr>0).mean(), 100*(m.E_cfd_va>0).mean(), 100*((m.E_cfd_tr>0)&(m.E_cfd_va>0)).mean()))
print('if train and valid were independent, expected "both": %.1f%%' % (100*(m.E_cfd_tr>0).mean()*(m.E_cfd_va>0).mean()))
print('\nMean E (CFD) by exit, train/valid:')
print(m.groupby('exit')[['win_cfd_tr', 'E_cfd_tr', 'win_cfd_va', 'E_cfd_va']].mean().reindex(EX).round(3).to_string())
print('\nMean E (CFD) by stop:'); print(m.groupby('stop')[['E_cfd_tr', 'E_cfd_va']].mean().round(3).to_string())
c = m[(m.E_cfd_tr > 0) & (m.E_cfd_va > 0) & (m.per_week_cfd_tr >= 2) & (m.per_week_cfd_va >= 2)].copy()
c['minE'] = c[['E_cfd_tr', 'E_cfd_va']].min(axis=1)
def neighbours_ok(r):
    ei = EX.index(r.exit); st = [15.0, 25.0, 40.0]; si = st.index(r.stop)
    nb = [(r.combo, r.stop, EX[j]) for j in (ei - 1, ei + 1) if 0 <= j < len(EX)] + \
         [(r.combo, st[j], r.exit) for j in (si - 1, si + 1) if 0 <= j < 3]
    sub = m.set_index(['combo', 'stop', 'exit'])
    return all(k in sub.index and sub.loc[k, 'E_cfd_tr'] > 0 and sub.loc[k, 'E_cfd_va'] > 0 for k in nb)
c['nb_ok'] = c.apply(neighbours_ok, axis=1)
cols = ['combo', 'stop', 'exit', 'per_week_cfd_tr', 'win_cfd_tr', 'E_cfd_tr', 'pf_cfd_tr', 'dd_cfd_tr', 'per_week_cfd_va', 'win_cfd_va', 'E_cfd_va', 'E_mnq_tr', 'E_mnq_va', 'minE', 'nb_ok']
print(f'\ncandidates positive in both (>=2/week): {len(c)}, with all neighbours positive: {int(c.nb_ok.sum())}')
print(c.sort_values('minE', ascending=False)[cols].head(25).round(3).to_string(index=False))
c.to_csv('v4_candidates.csv', index=False)
