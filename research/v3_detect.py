import pickle, time
from multiprocessing import Pool
from features import load
from engine import prepare
import ict
JOBS = [('cfd', '2017-01-01', '2018-12-31'), ('cfd', '2019-01-01', '2020-06-30'), ('cfd', '2020-07-01', '2021-12-31'),
        ('cfd', '2022-01-01', '2022-12-31'), ('cfd', '2023-01-01', '2025-09-30'), ('nq', '2023-01-01', '2025-12-11')]
def job(a):
    name, s, e = a
    df = load(name); f = prepare(df)
    return a, ict.detect(f, df, s, e)
if __name__ == '__main__':
    t = time.time()
    with Pool(4) as p: res = p.map(job, JOBS)
    pickle.dump(dict(res), open('cache/v3_candidates.pkl', 'wb'))
    for a, c in res: print(a, len(c))
    print(f'{time.time()-t:.0f}s')
