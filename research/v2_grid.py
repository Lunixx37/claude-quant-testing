import sys
from multiprocessing import Pool
from run import backtest
from engine import Params, stats
from candidates import FINAL
LEVELS = {
 'V only (V1)':                 dict(),
 'V + all mental (MV prio)':    dict(mental_on=True),
 'V + MV only (mental needs VWAP)': dict(mental_on=True, kinds=('MV', 'V')),
 'V + mental>=100':             dict(mental_on=True, mental_min=100),
 'V + mental>=500':             dict(mental_on=True, mental_min=500),
 'V + mental: <500 need VWAP':  dict(mental_on=True, mental_need_vwap=500),
 'mental only (M+MV)':          dict(mental_on=True, kinds=('MV', 'M')),
 'MV only':                     dict(mental_on=True, kinds=('MV',)),
}
EXITS = {
 'trail1.25':      dict(),
 'TP1.5':          dict(tp_r=1.5, trail_on=False),
 'TP2':            dict(tp_r=2.0, trail_on=False),
 'TP3':            dict(tp_r=3.0, trail_on=False),
 'TP3+trail':      dict(tp_r=3.0),
 'TP2+trail':      dict(tp_r=2.0),
}
def job(a):
    ln, en, sp = a
    t = backtest(Params(**{**FINAL, **LEVELS[ln], **EXITS[en]}), sp)
    return ln, en, stats(t), len(t)
if __name__ == '__main__':
    sp = sys.argv[1] if len(sys.argv) > 1 else 'train'
    jobs = [(l, e, sp) for l in LEVELS for e in EXITS]
    with Pool(4) as p: res = p.map(job, jobs)
    cur = None
    for ln, en, s, n in res:
        if ln != cur: print(f'-- {ln}'); cur = ln
        print(f"   {en:10s} n={s['n']:3d} PF={s['pf']:.2f} win={s['win']:.2f} E={s['expR']:+.3f} DD={s['maxdd_R']:5.1f} sumR={s['sumR']:+.1f}")
