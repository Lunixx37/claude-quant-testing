import pickle, time, sys
import numpy as np, pandas as pd
from multiprocessing import Pool
import lab, vbo_sess as V
G = {}
def init(name, a, b):
    G['S'] = V.Sess(lab.DS(name, a, b))
def job(cfg):
    m, kw = cfg
    return cfg, V.run_model(G['S'], m, **kw)
if __name__ == '__main__':
    name, a, b = sys.argv[1:4]
    t0 = time.time()
    with Pool(4, initializer=init, initargs=(name, a, b)) as p:
        res = p.map(job, V.grid(), chunksize=2)
    pickle.dump({(m, tuple(sorted(kw.items()))): t for (m, kw), t in res}, open(f'cache/v7_trades_{name}.pkl', 'wb'))
    print(name, len(res), f'{time.time()-t0:.0f}s')
