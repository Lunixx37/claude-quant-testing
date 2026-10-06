"""V6 walk-forward selection over the whole universe (PROTOCOL_V6.md) + live and prop evaluation of the OOS result."""
import pickle, sys
import numpy as np, pandas as pd
from multiprocessing import Pool

YEARS = list(range(2019, 2026))


def load_trades(name='cfd'):
    T = pickle.load(open(f'cache/v6_trades_{name}.pkl', 'rb'))
    for k, t in T.items():
        t['sdate'] = pd.to_datetime(t.sdate)
    return T


def score(t, Y, track):
    h = t[(t.sdate >= '2017-01-01') & (t.sdate < f'{Y}-01-01')]
    n = len(h)
    weeks = (pd.Timestamp(f'{Y}-01-01') - pd.Timestamp('2017-01-01')).days / 7
    if track == 'HF' and (n < 100 or n / weeks < 1.0):
        return -np.inf
    if track == 'LF' and n < 30:
        return -np.inf
    last = h[h.sdate >= pd.Timestamp(f'{Y}-01-01') - pd.Timedelta(days=365)]
    if len(last) and last.Rc.mean() <= 0:
        return -np.inf
    sd = h.Rc.std()
    return h.Rc.mean() / sd * np.sqrt(n) if sd > 0 else -np.inf


def walk_forward(T, track, top=1):
    picks, oos = {}, []
    for Y in YEARS:
        sc = sorted(((score(t, Y, track), k) for k, t in T.items()), key=lambda x: x[0], reverse=True)
        chosen, fam_cnt = [], {}
        for s, k in sc:
            if s == -np.inf or len(chosen) >= top:
                break
            if fam_cnt.get(k[0], 0) >= 2:
                continue
            chosen.append((k, s)); fam_cnt[k[0]] = fam_cnt.get(k[0], 0) + 1
        picks[Y] = chosen
        for k, s in chosen:
            t = T[k]
            y = t[(t.sdate >= f'{Y}-01-01') & (t.sdate < f'{Y + 1}-01-01')].copy()
            y['w'] = 1.0 / max(len(chosen), 1); y['cfg'] = str(k); y['year'] = Y
            oos.append(y)
    oos = pd.concat(oos, ignore_index=True).sort_values(['sdate', 'e']) if oos else pd.DataFrame()
    return picks, oos


def summarize(o, col='Rc'):
    x = o[col]; w = x[x > 0]; l = x[x <= 0]
    months = (o.sdate.max() - o.sdate.min()).days / 30.44
    by_y = o.groupby('year')[col].mean()
    return dict(n=len(o), trades_month=len(o) / months, win=(x > 0).mean(), E=x.mean(),
                t=x.mean() / x.std() * np.sqrt(len(x)), avg_win=w.mean(), avg_loss=l.mean(),
                rr=w.mean() / -l.mean() if len(l) else np.inf, pos_years=int((by_y > 0).sum()), years=len(by_y),
                by_year=by_y.round(3).to_dict())


def live(o, risk, col='Rc'):
    """Fixed-fractional risk on equity, weights for portfolios. Returns monthly stats."""
    eq, peak, mdd = 1.0, 1.0, 0.0
    o = o.assign(m=o.sdate.dt.to_period('M'))
    mret = []
    for m, g in o.groupby('m'):
        start = eq
        for r, w in zip(g[col].to_numpy(), g.w.to_numpy()):
            eq *= (1 + risk * w * r)
            peak = max(peak, eq); mdd = max(mdd, 1 - eq / peak)
        mret.append(eq / start - 1)
    allm = pd.period_range(o.m.min(), o.m.max(), freq='M')
    mret = np.array(mret + [0.0] * (len(allm) - len(mret)))
    return dict(avg_month=mret.mean(), median_month=np.median(mret), pos_months=(mret > 0).mean(), maxdd=mdd,
                cagr=eq ** (12 / len(allm)) - 1)


if __name__ == '__main__':
    T = load_trades('cfd')
    for track in ('HF', 'LF'):
        for top in (1, 5):
            picks, o = walk_forward(T, track, top)
            print(f'\n######## track {track}, top-{top}')
            for Y, ch in picks.items():
                print(f'  {Y}: ' + '; '.join(f'{k[0]} {dict(k[1])} (t={s:.2f})' for k, s in ch))
            if len(o) == 0:
                print('  no eligible configs'); continue
            s = summarize(o)
            print(f"  OOS 2019-2025: n={s['n']} ({s['trades_month']:.1f}/month) win={s['win']:.1%} E={s['E']:+.3f}R t={s['t']:.2f} "
                  f"avgwin={s['avg_win']:.2f}R avgloss={s['avg_loss']:.2f}R RR={s['rr']:.2f} positive years {s['pos_years']}/{s['years']}")
            print(f"  by year: {s['by_year']}")
            for rk in (0.01, 0.02):
                lv = live(o, rk)
                print(f"  live risk {rk:.0%}: avg/month {lv['avg_month']:+.2%} median {lv['median_month']:+.2%} positive months {lv['pos_months']:.0%} maxDD {lv['maxdd']:.1%} CAGR {lv['cagr']:+.1%}")
            o.to_pickle(f'cache/v6_oos_{track}_top{top}.pkl')
