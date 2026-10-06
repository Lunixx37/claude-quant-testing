"""V11: high win-rate exit grid over all entry families (PROTOCOL_V11.md). Stores trades per (family, entry, m, rho)."""
import pickle, sys, time
from multiprocessing import Pool
import lab

MS = (1, 2, 3)
RHOS = (0.10, 0.15, 0.20, 0.25, 0.33, 0.50)


def entry_sets():
    E = []
    for k in (0.2, 0.3, 0.35, 0.4, 0.5):
        for fl in ('none', 'trend', 'lowvol'):
            for side in ('both', 'long'):
                E.append(('VBO', 'F7b VBO refined', dict(k=k, sm=1.0, tgt=2, filt=fl, side=side)))
    for L in (5, 15, 30):
        for sm in ('opp', 'mid'):
            for fl in ('none', 'narrow', 'trend'):
                E.append(('ORB', 'F1 ORB', dict(L=L, stop_mode=sm, tgt=1, filt=fl)))
    for k in (0.1, 0.2, 0.3):
        for mode in ('fade', 'cont'):
            for sm in (0.5, 1.0):
                E.append(('Gap', 'F3 Gap', dict(k=k, mode=mode, tgt='full', stopm=sm)))
    for sk in (0.1, 0.2):
        for fl in ('none', 'trend'):
            E.append(('PDH/PDL', 'F4 PDH/PDL', dict(stopk=sk, tgt=1, filt=fl)))
    for mode in ('break', 'fade'):
        E.append(('News', 'F8 NewsRange', dict(mode=mode, tgt=1)))
    for sw in ('open', 'prevclose'):
        for et in (900, 930):
            for th in (0.0, 0.0025, 0.005):
                E.append(('IntradayMom', 'F2 IntradayMom', dict(sigwin=sw, entry_t=et, thr=th)))
    for th in (5, 10):
        for side in ('long', 'both'):
            E.append(('RSI2', 'F6 RSI2', dict(thr=th, side=side, exit_mode='days5')))
    for s in lab.ict.SETUPS:
        for fl in lab.F10_FILTERS:
            E.append(('ICT ' + s, 'F10', dict(setup=s, stop_pts=40.0, exit_='TP2', hold=1, filt=fl)))
    return E


G = {}


def init(name, a, b):
    G['ds'] = lab.DS(name, a, b)
    G['cand'] = lab.f10_candidates(G['ds'])


def job(es):
    fam_short, fam, kw = es
    ds = G['ds']
    try:
        ent = lab.fam_f10(ds, G['cand'], **kw) if fam == 'F10' else lab.GEN[fam](ds, **kw)
    except Exception as ex:
        return es, repr(ex)
    md = 2 if fam == 'F10' else 1
    out = {}
    for m in MS:
        for rho in RHOS:
            e2 = [(si, e, d, m * sp, rho * m * sp, dl, False) for si, e, d, sp, tpp, dl, tr in ent]
            t = lab.run_entries(ds, e2, max_day=md)
            out[(m, rho)] = t[['sdate', 'e', 'x_i', 'dir', 'stop', 'pts', 'why', 'Rc', 'Rf']]
    if fam == 'F6 RSI2':                                   # native mean-reversion exits (no TP, stop 3 ATR)
        for ex in ('sma5', 'days5'):
            t = lab.run_entries(ds, lab.GEN[fam](ds, **dict(kw, exit_mode=ex)), max_day=1)
            out[('native', ex)] = t[['sdate', 'e', 'x_i', 'dir', 'stop', 'pts', 'why', 'Rc', 'Rf']]
    return es, out


if __name__ == '__main__':
    name, a, b = sys.argv[1:4]
    E = entry_sets(); t0 = time.time()
    with Pool(4, initializer=init, initargs=(name, a, b)) as p:
        res = p.map(job, E, chunksize=1)
    errs = [(c, r) for c, r in res if isinstance(r, str)]
    print(f'{name}: {len(E)} entry sets in {time.time()-t0:.0f}s, errors {len(errs)}', errs[:3])
    R = {}
    for (fs, fam, kw), out in res:
        if isinstance(out, str):
            continue
        for ex, t in out.items():
            R[(fs, tuple(sorted(kw.items())), ex)] = t
    pickle.dump(R, open(f'cache/v11_trades_{name}.pkl', 'wb'))
