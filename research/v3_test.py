"""One-time Test A/B of V3_FINAL + live-account and prop evaluation (also for V1/V2 on NQ)."""
import pickle, numpy as np, pandas as pd
from features import load
from engine import prepare, Params, run
import ict
from candidates import V3_FINAL, FINAL, V2_FINAL
from prop import block_bootstrap
from prop2 import Policy, Env, run_paths, simulate as psim
C = pickle.load(open('cache/v3_candidates.pkl', 'rb'))
F = {'cfd': prepare(load('cfd')), 'nq': prepare(load('nq'))}
cfg = V3_FINAL
def v3(key):
    f = F[key[0]]
    t = ict.simulate(f, C[key], cfg['setup'], cfg['stop_mode'], cfg['tp_r'], cfg['trail'], fallback=True)
    return f, t
def live(t, risk_usd, label):
    """$50k live account, fixed $ risk per trade in MNQ (n = floor(risk / (R_pts * $2)))."""
    n = np.floor(risk_usd / (t.R_pts * 2.0)).clip(lower=1)
    usd = n * 2.0 * t.pts - n * 1.5
    eq = 50_000 + usd.cumsum()
    dd = (eq.cummax() - eq).max()
    mon = usd.groupby(pd.to_datetime(t.sdate).dt.to_period('M')).sum()
    yrs = (pd.to_datetime(t.sdate).max() - pd.to_datetime(t.sdate).min()).days / 365.25
    return f"  LIVE {label:9s}: net ${usd.sum():9,.0f} ({usd.sum()/50_000/yrs:+.1%}/yr), max DD ${dd:7,.0f}, worst month ${mon.min():7,.0f}, positive months {(mon > 0).mean():.0%}"
def pool_from(f, t, sd_from, sd_to):
    sd = f['sdate']; m = (f['mod'] == 570) & (sd >= np.datetime64(sd_from)) & (sd <= np.datetime64(sd_to))
    days = list(np.unique(sd[m])); by = {d: [] for d in days}
    for r in t.itertuples():
        idx = np.arange(r.entry_i, r.exit_i + 1)
        adv = (f['l'][idx] - r.entry) if r.dir > 0 else (r.entry - f['h'][idx])
        if r.why == 'stop': adv[-1] = max(adv[-1], r.pts)
        if r.sdate in by: by[r.sdate].append((None, adv, r.pts, r.R_pts * 4))
    return [by[d] for d in days]
def prop(pool, label):
    paths = block_bootstrap(len(pool), 252, 2000, seed=21)
    r = run_paths(paths, pool, Env(), Policy(risk_usd=250, no_starve=True), 252)
    return (f"  PROP {label:9s}: payout <=1M {r['p_pay21']:.1%}  <=2M {r['p_pay42']:.1%}  <=3M {r['p_pay63']:.1%}  <=12M {r['p_payout']:.1%} | "
            f"eval pass {r['p_pass']:.1%}, eval blown {r['p_ev_blow']:.1%}")
out = []
for lab, key, a, b in (('Test A 2022 (CFD, pristine)', ('cfd', '2022-01-01', '2022-12-31'), '2022-01-01', '2022-12-31'),
                       ('Test B 2023-25 (NQ futures)', ('nq', '2023-01-01', '2025-12-11'), '2023-01-01', '2025-12-11'),
                       ('Test B 2023-25 (CFD)', ('cfd', '2023-01-01', '2025-09-30'), '2023-01-01', '2025-09-30')):
    f, t = v3(key)
    s = ict.summarize(t, (pd.Timestamp(b) - pd.Timestamp(a)).days / 7)
    out.append(f"V3_FINAL {lab}: n={s['n']} ({s['per_week']:.1f}/week) win={s['win']:.1%} avg winner {s['avg_win_gross']:.2f}R gross "
               f"E={s['E']:+.3f}R PF={s['pf']:.2f} DD={s['dd']:.1f}R | primary E {t[t.kind=='primary'].R.mean():+.3f}, fallback/forced E {t[t.kind!='primary'].R.mean():+.3f} (n={int((t.kind!='primary').sum())})")
    out.append(live(t, 250, '$250')); out.append(live(t, 500, '1% $500'))
    out.append(prop(pool_from(f, t, a, b), '$250'))
# reference: V1/V2 on NQ 2023-25 (their own data), live + prop
for name, kw in (('V1_FINAL', FINAL), ('V2_FINAL', V2_FINAL)):
    f = F['nq']; t = run(f, Params(**kw), '2023-02-01', '2025-12-11'); t['sdate'] = f['sdate'][t.sig_i]
    t['R_pts'] = t.risk; t['pts'] = t.pts; t['why'] = t.why
    out.append(f"{name} NQ 2023-02..2025-12 (development+2025): n={len(t)} ({len(t)/149:.1f}/week) win={(t.R>0).mean():.1%} E={t.R.mean():+.3f}R")
    out.append(live(t, 250, '$250'))
print('\n'.join(out))
