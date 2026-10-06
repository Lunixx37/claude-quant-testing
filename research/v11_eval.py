"""V11 evaluation: discovery metrics, selection (PROTOCOL_V11.md), one-time tests of the finalists."""
import pickle, numpy as np, pandas as pd
from v11 import RHOS

C = pickle.load(open('cache/v11_trades_cfd.pkl', 'rb'))
N = pickle.load(open('cache/v11_trades_nq.pkl', 'rb'))
FS = np.linspace(0.0025, 1.0, 400)


def kelly(r):
    best = (0.0, 0.0)
    for f in FS:
        x = 1 + f * r
        if x.min() <= 0:
            break
        g = np.log(x).mean()
        if g > best[1]:
            best = (f, g)
    return best[0]


def streak(x):
    b = c = 0
    for v in x:
        c = c + 1 if v else 0; b = max(b, c)
    return b


def metrics(t, col, months):
    r = t[col].to_numpy()
    if len(r) < 20:
        return None
    w, l = r[r > 0], r[r <= 0]
    f = kelly(r)
    tpm = len(r) / months
    g_half = np.log1p(f / 2 * r).mean() * tpm if f > 0 else 0.0
    g_full = np.log1p(f * r).mean() * tpm if f > 0 else 0.0
    yrs = pd.Series(r, index=pd.to_datetime(t.sdate).dt.year.to_numpy()).groupby(level=0).mean()
    return dict(n=len(r), tpm=tpm, win=(r > 0).mean(), avgwin=w.mean() if len(w) else 0, avgloss=l.mean() if len(l) else 0,
                E=r.mean(), kelly=f, G_half=g_half, G_full=g_full, pos_years=int((yrs > 0).sum()), n_years=len(yrs),
                streak=streak(r <= 0), min_r=r.min())


def fam_of(key):
    return 'ICT' if key[0].startswith('ICT') else key[0]


rows = []
for key, t in C.items():
    t = t.assign(sdate=pd.to_datetime(t.sdate))
    dev = t[t.sdate < '2023-01-01']
    m = metrics(dev, 'Rc', 72)
    if m:
        rows.append(dict(key=key, fam=fam_of(key), setup=key[0], entry=dict(key[1]), exit=key[2], **m))
D = pd.DataFrame(rows)
D.to_pickle('cache/v11_dev.pkl')

# plateau: neighbouring rho (same entry, same m) with E > 0
E_by = {(r.key[0], r.key[1], r.exit): r.E for r in D.itertuples()}


def plateau(r):
    if r.exit[0] == 'native':
        return np.nan                                          # no rho neighbours (reported separately)
    m, rho = r.exit; i = RHOS.index(rho)
    nb = [RHOS[j] for j in (i - 1, i + 1) if 0 <= j < len(RHOS)]
    return all(E_by.get((r.key[0], r.key[1], (m, x)), -1) > 0 for x in nb)


D['plateau'] = [plateau(r) for r in D.itertuples()]
out = []
P = lambda s: out.append(s)
P(f'V11 discovery (CFD 2017-22): {len(D)} configurations')
P(f'  win >= 80 %: {(D.win >= .8).sum()} | win >= 80 % and E > 0: {((D.win >= .8) & (D.E > 0)).sum()} | '
  f'+ n >= 300: {((D.win >= .8) & (D.E > 0) & (D.n >= 300)).sum()} | + >= 4/6 years: '
  f'{((D.win >= .8) & (D.E > 0) & (D.n >= 300) & (D.pos_years >= 4)).sum()} | + plateau: '
  f'{((D.win >= .8) & (D.E > 0) & (D.n >= 300) & (D.pos_years >= 4) & (D.plateau == True)).sum()}')
P('\nWin rate vs E by rho (all configs, discovery): mean win, mean E, share E>0')
D['rho'] = [x[1] if x[0] != 'native' else np.nan for x in D.exit]
D['m'] = [x[0] if x[0] != 'native' else np.nan for x in D.exit]
P(D.groupby(['m', 'rho']).agg(win=('win', 'mean'), E=('E', 'mean'), share_pos=('E', lambda x: (x > 0).mean()), n=('E', 'size')).round(3).to_string())
P('\nBest per family among win >= 80 %, n >= 300 (discovery, by G_half; regardless of the other criteria):')
cand = D[(D.win >= .8) & (D.n >= 300)].sort_values('G_half', ascending=False)
P(cand.groupby('fam').head(1)[['fam', 'setup', 'entry', 'exit', 'n', 'tpm', 'win', 'avgwin', 'avgloss', 'E', 'kelly', 'G_half', 'pos_years', 'plateau']]
  .round(3).to_string(index=False))
sel = D[(D.win >= .8) & (D.E > 0) & (D.n >= 300) & (D.pos_years >= 4) & ((D.plateau == True) | D.plateau.isna())]
sel = sel.sort_values('G_half', ascending=False)
fin = sel.groupby('fam').head(1).head(5)
D.to_pickle('cache/v11_dev.pkl')
P(f'\nAll eligible configurations (discovery):')
P(sel[['setup', 'entry', 'exit', 'n', 'win', 'E', 'kelly', 'G_half', 'pos_years', 'plateau']].round(3).to_string(index=False))
P(f'\nEligible (all criteria): {len(sel)}  -> finalists (max 1 per family, top 5 by G_half):')
P(fin[['fam', 'setup', 'entry', 'exit', 'n', 'tpm', 'win', 'avgwin', 'avgloss', 'E', 'kelly', 'G_half', 'pos_years', 'streak', 'plateau']].round(3).to_string(index=False))

P('\nOne-time tests of the finalists:')
tests = {}
for r in fin.itertuples():
    t = C[r.key].assign(sdate=lambda x: pd.to_datetime(x.sdate)); n = N[r.key]
    tc = metrics(t[t.sdate >= '2023-01-01'], 'Rc', 33)
    tn = metrics(n, 'Rf', 35.4)
    tests[r.key] = (tc, tn)
    ok = lambda m: m and m['win'] >= .8 and m['E'] > 0
    near = lambda m: m and m['win'] >= .75 and m['E'] > 0
    verdict = 'PASS' if ok(tc) and ok(tn) else ('near pass' if near(tc) and near(tn) else 'FAIL')
    P(f'  {r.setup} {r.entry} exit {r.exit}: {verdict}')
    for lab_, m in (('dev CFD', dict(r._asdict())), ('test CFD 23-25', tc), ('test NQ 23-25', tn)):
        if m:
            P(f'     {lab_:15s} n={m["n"]:5d} ({m["tpm"]:.1f}/mo) win={m["win"]:.1%} avgwin={m["avgwin"]:+.3f} avgloss={m["avgloss"]:+.3f} '
              f'E={m["E"]:+.3f} kelly={m["kelly"]:.2f} G_half/mo={m["G_half"]:.3f} streak={m["streak"]}')
pickle.dump(dict(fin=fin, tests=tests), open('cache/v11_finalists.pkl', 'wb'))
txt = '\n'.join(out)
open('v11_eval_result.txt', 'w').write(txt + '\n')
print(txt)
