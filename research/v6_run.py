"""Simulate the whole V6 universe on CFD 2017-01..2025-09 and NQ 2023-01..2025-12; store trades per config."""
import pickle, time, sys
from multiprocessing import Pool
import lab
G = {}
def init(name, a, b):
    G['ds'] = lab.DS(name, a, b)
    G['cand'] = lab.f10_candidates(G['ds'])
def job(cfg):
    fam, kw = cfg
    try:
        t = lab.run_config(G['ds'], fam, kw, G['cand'])
    except Exception as e:
        return cfg, repr(e)
    return cfg, t
if __name__ == '__main__':
    name, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
    U = lab.universe(); t0 = time.time()
    with Pool(4, initializer=init, initargs=(name, a, b)) as p:
        res = p.map(job, U, chunksize=4)
    errs = [(c, r) for c, r in res if isinstance(r, str)]
    print(f'{name}: {len(U)} configs in {time.time()-t0:.0f}s, errors: {len(errs)}', errs[:3])
    pickle.dump({(c[0], tuple(sorted(c[1].items()))): r for c, r in res if not isinstance(r, str)}, open(f'cache/v6_trades_{name}.pkl', 'wb'))
