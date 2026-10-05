"""Frozen V1_FINAL and V2_FINAL, unchanged, on CFD 2017-2022 (never used before) + CFD 2023-25."""
import numpy as np, pandas as pd
from features import load
from engine import Params, run, prepare, stats
from candidates import FINAL, V2_FINAL
fc = prepare(load('cfd'))
def bt(prm, a, b):
    t = run(fc, prm, a, b); t['sdate'] = fc['sdate'][t.sig_i]; return t
for name, kw in (('V1_FINAL', FINAL), ('V2_FINAL', V2_FINAL)):
    print(f'=== {name} on CFD (relvol quantile-mapped; CFD approximation, see v3_overlap.txt)')
    for a, b in (('2017-01-01', '2017-12-31'), ('2018-01-01', '2018-12-31'), ('2019-01-01', '2019-12-31'), ('2020-01-01', '2020-12-31'),
                 ('2021-01-01', '2021-12-31'), ('2022-01-01', '2022-12-31'), ('2017-01-01', '2022-12-31'), ('2023-01-01', '2025-09-30')):
        t = bt(Params(**kw), a, b); s = stats(t)
        weeks = (pd.Timestamp(b) - pd.Timestamp(a)).days / 7
        print(f"  {a[:4]}..{b[:4]}: n={s['n']:4d} ({s['n']/weeks:.1f}/week) PF={s['pf']:.2f} win={s['win']:.2f} E={s['expR']:+.3f} DD={s['maxdd_R']:.1f}R sumR={s['sumR']:+.1f}")
