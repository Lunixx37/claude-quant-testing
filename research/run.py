"""Run the engine on a split and print the full metric set."""
import sys, json
import numpy as np, pandas as pd
from features import load
from engine import Params, run, prepare, stats, SPLITS

_F = None
def data():
    global _F
    if _F is None:
        _F = prepare(load())
    return _F

def backtest(p, split, allow_forward=False):
    if split == 'forward' and not allow_forward:
        raise SystemExit('forward segment is locked (protocol)')
    f = data()
    if split == 'is':
        a, b = SPLITS['train'][0], SPLITS['valid'][1]
    else:
        a, b = SPLITS[split]
    tr = run(f, p, a, b)
    if len(tr):
        tr['sdate'] = f['sdate'][tr.sig_i]
        tr['entry_t'] = pd.to_datetime(f['t'][tr.entry_i]); tr['exit_t'] = pd.to_datetime(f['t'][tr.exit_i])
        tr['bars'] = tr.exit_i - tr.entry_i + 1
        tr['sig_min'] = f['mod'][tr.sig_i]
    return tr

def report(tr, title, full=True):
    s = stats(tr, label=title)
    print(f"\n=== {title} ===")
    print(json.dumps(s))
    if not full or len(tr) == 0:
        return s
    days = tr.sdate.nunique()
    print(f"trades/trade-day {len(tr)/days:.2f}  max/day {tr.groupby('sdate').size().max()}  "
          f"avg bars held {tr.bars.mean():.1f}  stop-outs {np.mean(tr.why=='stop'):.2%}  "
          f"init-stop losses (R<-0.9) {np.mean(tr.R<-0.9):.2%}  avg MFE R {(tr.mfe/tr.risk).mean():.2f}")
    def grp(col, name=None):
        rows = []
        for k, g in tr.groupby(col):
            st = stats(g); rows.append((k, st['n'], st['net_usd'], st['pf'], st['win'], st['expR']))
        print(f"  by {name or col}: " + " | ".join(f"{k}: n={n} ${u:.0f} pf={pf} wr={w} E={e}R" for k, n, u, pf, w, e in rows))
    tr = tr.assign(side=np.where(tr.dir > 0, 'long', 'short'),
                   tod=pd.cut(tr.sig_min, [0, 600, 630, 660, 2000], labels=['9:30-10', '10-10:30', '10:30-11', '11+'], right=False),
                   year=tr.sdate.astype('datetime64[ns]').dt.year, stopsz=tr.stop_ticks)
    for col in ['side', 'tier', 'stopsz', 'tod', 'level', 'year', 'why']:
        grp(col)
    return s

if __name__ == '__main__':
    p = Params()
    for kv in sys.argv[2:]:
        k, v = kv.split('='); setattr(p, k, type(getattr(p, k))(eval(v)))
    split = sys.argv[1] if len(sys.argv) > 1 else 'train'
    report(backtest(p, split), split)
