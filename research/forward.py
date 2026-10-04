"""ONE-TIME forward (OOS) evaluation of the frozen FINAL version. Output is saved verbatim."""
from dataclasses import replace
import numpy as np, pandas as pd
from run import backtest, report
from engine import Params, stats
from candidates import FINAL
p = Params(**FINAL)
tr = backtest(p, 'forward', allow_forward=True)
report(tr, 'FORWARD 2025-01-01..2025-12-11 (frozen FINAL, base costs)')
tr.to_csv('forward_trades.csv', index=False)
for sl in [2, 3]:
    s = stats(backtest(replace(p, slip_ticks=sl), 'forward', allow_forward=True))
    print(f"stress slippage {sl} ticks: n={s['n']} pf={s['pf']} E={s['expR']} dd={s['maxdd_R']} net=${s['net_usd']}")
tr['q'] = pd.to_datetime(tr.sdate).dt.quarter
print('by quarter:', {k: (len(g), round(g.R.mean(), 3)) for k, g in tr.groupby('q')})
