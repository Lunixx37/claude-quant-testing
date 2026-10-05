"""$100 CFD account: compounding fixed-fractional risk, bootstrap of the strategy's own trades (R after CFD costs).
CFD contract assumption: 1.00 lot = $1 per point, min lot 0.01, step 0.01 (common NAS100 spec; check your broker)."""
import numpy as np
def account_sim(R, R_pts, trades_per_year, risk_frac, start=100.0, years=1.0, n_paths=5000, seed=1):
    rng = np.random.default_rng(seed)
    n = int(round(trades_per_year * years))
    idx = rng.integers(0, len(R), size=(n_paths, n))
    out = dict(final=[], maxdd=[], t20=[])
    for row in idx:
        eq, peak, mdd, t20 = start, start, 0.0, np.nan
        for k, j in enumerate(row):
            risk_usd = eq * risk_frac
            lots = np.floor(risk_usd / R_pts[j] / 0.01) * 0.01          # $1/pt per lot
            if lots < 0.01:
                lots = 0.01                                               # minimum position
            eq += lots * R_pts[j] * R[j]
            if eq <= 0:
                eq = 0; mdd = 1.0; break
            peak = max(peak, eq); mdd = max(mdd, 1 - eq / peak)
            if np.isnan(t20) and eq >= start * 1.2:
                t20 = (k + 1) / trades_per_year * 12                      # months
        out['final'].append(eq); out['maxdd'].append(mdd); out['t20'].append(t20)
    f, d, t = map(np.array, (out['final'], out['maxdd'], out['t20']))
    return dict(median_final=np.median(f), p_loss=(f < start).mean(), p_dd50=(d >= 0.5).mean(), median_dd=np.median(d),
                p20_6m=(t <= 6).mean(), p20_12m=(t <= 12).mean(), median_months_to_20=np.nanmedian(t) if np.isfinite(t).any() else np.nan)
