"""V8: features per trade of the V7 M1 model + bucket scan (discovery CFD 2017-22, tests CFD/NQ 2023-25)."""
import pickle
import numpy as np, pandas as pd
import lab

KEY = ('M0/M1 NY', (('exitm', 'trail'), ('k', 0.35), ('maxtr', 2), ('side', 'both'), ('sm', 0.75)))


def features(name, period):
    ds = lab.DS(name, *period)
    f, df, d = ds.f, ds.df, ds.d.copy()
    t = pickle.load(open(f'cache/v7_trades_{name}.pkl', 'rb'))[KEY].copy()
    t['sdate'] = pd.to_datetime(t.sdate)
    t = t[t.sdate.isin(d.index)].sort_values('e').reset_index(drop=True)
    d['pdh'], d['pdl'], d['prg'] = d.h.shift(1), d.l.shift(1), d.rg.shift(1)
    x = d.reindex(t.sdate)
    sig = t.e.to_numpy() - 1
    c, h, l = f['c'], f['h'], f['l']
    dirn = t.dir.to_numpy()
    io = x.i_open.to_numpy().astype(int)
    hi_td = np.array([h[a:b + 1].max() for a, b in zip(io, sig)])
    lo_td = np.array([l[a:b + 1].min() for a, b in zip(io, sig)])
    cs = c[sig]

    def directional(p):
        return np.where(dirn > 0, p, 1 - p)
    t['F_a_prev_range_pos'] = directional((cs - x.pdl.to_numpy()) / (x.pdh.to_numpy() - x.pdl.to_numpy()))
    t['F_b_today_range_pos'] = directional(np.where(hi_td > lo_td, (cs - lo_td) / (hi_td - lo_td), 0.5))
    onh, onl = df.onh.to_numpy()[sig], df.onl.to_numpy()[sig]
    t['F_c_overnight_pos'] = directional(np.where(onh > onl, (cs - onl) / (onh - onl), 0.5))
    mod = f['mod'][sig]
    t['F_d_time'] = pd.cut(mod, [0, 600, 630, 660, 720, 840, 2000], right=False,
                           labels=['09:30-10:00', '10:00-10:30', '10:30-11:00', '11:00-12:00', '12:00-14:00', '14:00-16:00']).astype(str)
    t['F_e_trade_no'] = np.where(t.groupby('sdate').cumcount() == 0, '1st', 're-entry')
    t['F_f_gap_atr'] = (x.o.to_numpy() - x.pc.to_numpy()) / x.atr14.to_numpy() * dirn
    t['F_g_vol_regime'] = x.prg.to_numpy() / x.atr14.to_numpy()
    t['F_h_trend'] = np.where(np.sign(x.pc.to_numpy() - x.sma20.shift(0).to_numpy()) * dirn > 0, 'with trend', 'against trend')
    t['F_i_weekday'] = t.sdate.dt.day_name().str[:3]
    t['F_j_bar_vs_range'] = (h[sig] - l[sig]) / x.prg.to_numpy()
    t['R'] = t.Rf if name == 'nq' else t.Rc
    t['win'] = t.R > 0
    return t


CONT = ['F_a_prev_range_pos', 'F_b_today_range_pos', 'F_c_overnight_pos', 'F_f_gap_atr', 'F_g_vol_regime', 'F_j_bar_vs_range']
CAT = ['F_d_time', 'F_e_trade_no', 'F_h_trend', 'F_i_weekday']


def bucketize(sets):
    dev = sets['dev']
    for fcol in CONT:
        edges = np.unique(np.nanquantile(dev[fcol], [0, .2, .4, .6, .8, 1]))
        edges[0], edges[-1] = -np.inf, np.inf
        for k in sets:
            sets[k][fcol + '_q'] = pd.cut(sets[k][fcol], edges, labels=[f'Q{i+1}' for i in range(len(edges) - 1)]).astype(str)
    return sets


if __name__ == '__main__':
    cfd = features('cfd', ('2017-01-01', '2025-09-30')); nq = features('nq', ('2023-01-01', '2025-12-11'))
    sets = {'dev': cfd[cfd.sdate < '2023-01-01'].copy(), 'testCFD': cfd[cfd.sdate >= '2023-01-01'].copy(), 'testNQ': nq}
    sets = bucketize(sets)
    pickle.dump(sets, open('cache/v8_sets.pkl', 'wb'))
    print('Trades: ' + ', '.join(f'{k} n={len(v)} win={v.win.mean():.1%} E={v.R.mean():+.3f}R' for k, v in sets.items()))
    rows = []
    for fcol in [c + '_q' for c in CONT] + CAT:
        for b in sorted(sets['dev'][fcol].dropna().unique()):
            r = dict(feature=fcol, bucket=b)
            for k, v in sets.items():
                g = v[v[fcol] == b]; rest = v[v[fcol] != b]
                r[f'{k}_n'] = len(g); r[f'{k}_win'] = g.win.mean() if len(g) else np.nan; r[f'{k}_E'] = g.R.mean() if len(g) else np.nan
                # effect of EXCLUDING this bucket on the whole set
                r[f'{k}_excl_dwin'] = rest.win.mean() - v.win.mean(); r[f'{k}_excl_dE'] = rest.R.mean() - v.R.mean()
            r['keep_exclusion'] = (r['dev_n'] >= 100 and all(r[f'{k}_excl_dwin'] > 0 and r[f'{k}_excl_dE'] > 0 for k in sets))
            rows.append(r)
    res = pd.DataFrame(rows); res.to_csv('v8_buckets.csv', index=False)
    pd.set_option('display.width', 260); pd.set_option('display.max_rows', 200)
    cols = ['feature', 'bucket', 'dev_n', 'dev_win', 'dev_E', 'testCFD_n', 'testCFD_win', 'testCFD_E', 'testNQ_n', 'testNQ_win', 'testNQ_E', 'keep_exclusion']
    print(res[cols].round(3).to_string(index=False))
    # bucket edges for interpretation
    for fcol in CONT:
        e = np.nanquantile(sets['dev'][fcol], [.2, .4, .6, .8])
        print(f'{fcol} quintile edges (dev): {np.round(e, 3)}')
