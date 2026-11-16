"""
Stdv-Box levels + confluence (VWAP / psychological numbers) + mean-reversion entry with
momentum confirmation.

Setup (per day, 08:30 - 16:00 ET, 1-min bars, times = bar OPEN):
  1. Price touches a level L for the first time that day
       STDV levels: mid +/- k*h  (k = 2, 2.25, 2.5, 3.5, 4, 4.25, 4.5) -> upper = short, lower = long
  2. Filter (variant):
       stdv_only   : no filter
       stdv_vwap   : |L - VWAP line| <= TOL at the touch bar, VWAP lines =
                     ETH-VWAP (18:00 anchor), ETH-VWAP +/-1 sd, +/-2 sd, RTH-VWAP (09:30), VWAP anchored 08:30
       stdv_psych  : |L - nearest multiple of 100| <= TOL   (psych50: multiple of 50)
     controls without stdv:
       psych_only  : fade first touch of every round 100 number
       vwapband_only: fade first touch of ETH-VWAP +/-2 sd (dynamic) after 08:30 (one per side per day)
  3. Momentum trigger within MOM_BARS bars after the touch (touch bar included):
       short: close < L  and close < low[prev bar] and close < open   (mirror for long)
     entry = close of trigger bar, stop = extreme since touch +/- 1 tick
  4. Exit: target (1R / 2R / ETH-VWAP), stop, or 15:59 close. One position at a time.
     Conservative fills: stop wins if stop and target are inside the same bar.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import stdv_box as m  # noqa: E402

TICK = 0.25
TOL = 5.0            # confluence tolerance in points
MOM_BARS = 15        # bars after touch in which the momentum trigger must appear
MAX_RISK = 50.0      # skip setups whose stop is wider than this (points)
COST = 1.0           # round-turn cost in points (commission + slippage, market entry)
OUT = Path(__file__).parent / "results"


# ----------------------------------------------------------------------------- data + vwap
def load(kind: str) -> pd.DataFrame:
    if kind == "NQ":
        df = pd.read_csv(m.ROOT / "Dataset_NQ_1min_2022_2025.csv")
        t = pd.to_datetime(df["timestamp ET"], format="%m/%d/%Y %H:%M") - pd.Timedelta("1min")
        out = pd.DataFrame({c: df[c].values for c in ["open", "high", "low", "close", "volume"]}, index=t)
    else:
        import zipfile
        parts = []
        for i in (1, 2):
            with zipfile.ZipFile(m.ROOT / f"1m_data_part{i}.zip") as z, z.open(f"1m_data_part{i}.csv") as f:
                parts.append(pd.read_csv(f, sep="\t"))
        df = pd.concat(parts)
        t = pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S") - pd.Timedelta("7h")
        out = pd.DataFrame({"open": df.Open.values, "high": df.High.values, "low": df.Low.values,
                            "close": df.Close.values, "volume": df.TickVolume.values.astype(float)}, index=t)
        out = out[~out.index.duplicated()]
    out = out.sort_index()
    return add_vwaps(out)


def _anchored(df, mask, key):
    px = (df.high + df.low + df.close) / 3
    v = df.volume.where(mask, 0.0).astype(float)
    g = key
    cv = v.groupby(g).cumsum()
    pv = (px * v).groupby(g).cumsum()
    p2v = (px * px * v).groupby(g).cumsum()
    vw = (pv / cv).where(mask & (cv > 0))
    sd = np.sqrt((p2v / cv - vw ** 2).clip(lower=0)).where(mask & (cv > 0))
    return vw, sd


def add_vwaps(df):
    t = df.index
    eth_key = (t + pd.Timedelta("6h")).normalize()          # session starting 18:00 -> next date
    day = t.normalize()
    hm = t.strftime("%H:%M")
    df["vw_eth"], df["sd_eth"] = _anchored(df, pd.Series(True, index=t), eth_key)
    df["vw_rth"], _ = _anchored(df, pd.Series((hm >= "09:30") & (hm < "16:00"), index=t), day)
    df["vw_830"], _ = _anchored(df, pd.Series((hm >= "08:30") & (hm < "16:00"), index=t), day)
    return df


VWAP_LINES = {
    "ETH-VWAP": lambda s: s.vw_eth.values,
    "ETH+1sd": lambda s: (s.vw_eth + s.sd_eth).values, "ETH-1sd": lambda s: (s.vw_eth - s.sd_eth).values,
    "ETH+2sd": lambda s: (s.vw_eth + 2 * s.sd_eth).values, "ETH-2sd": lambda s: (s.vw_eth - 2 * s.sd_eth).values,
    "RTH-VWAP": lambda s: s.vw_rth.values, "VWAP@08:30": lambda s: s.vw_830.values,
}


# ----------------------------------------------------------------------------- setups
def first_touch(H, L, level, side):
    idx = np.flatnonzero(H >= level) if side == -1 else np.flatnonzero(L <= level)
    return idx[0] if len(idx) else None


def momentum_trigger(O, H, L, C, i0, level, side, n=MOM_BARS):
    """First bar j in [i0, i0+n] that closes back through the level with momentum."""
    for j in range(max(i0, 1), min(i0 + n + 1, len(C))):
        if side == -1 and C[j] < level and C[j] < L[j - 1] and C[j] < O[j]:
            return j
        if side == 1 and C[j] > level and C[j] > H[j - 1] and C[j] > O[j]:
            return j
    return None


def day_events(day, b, s, variant, tol=TOL):
    """Return list of candidate setups for one day: dict(j_trig, side, level, tag)."""
    O, H, L, C = s.open.values, s.high.values, s.low.values, s.close.values
    lines = {k: f(s) for k, f in VWAP_LINES.items()}
    cands = []
    if variant in ("stdv_only", "stdv_vwap", "stdv_psych", "stdv_psych50"):
        for k in m.STDV_LEVELS:
            for side, lvl in ((-1, b.mid + k * b.h), (1, b.mid - k * b.h)):
                i0 = first_touch(H, L, lvl, side)
                if i0 is None:
                    continue
                tag = f"{k}"
                if variant == "stdv_vwap":
                    d = {n: abs(lvl - v[i0]) for n, v in lines.items() if not np.isnan(v[i0])}
                    near = [n for n, x in d.items() if x <= tol]
                    if not near:
                        continue
                    tag = min(near, key=d.get)
                elif variant in ("stdv_psych", "stdv_psych50"):
                    step = 100 if variant == "stdv_psych" else 50
                    if abs(lvl - round(lvl / step) * step) > tol:
                        continue
                cands.append((i0, side, lvl, tag))
    elif variant == "psych_only":
        p0 = O[0]
        lo, hi = np.floor(L.min() / 100) * 100, np.ceil(H.max() / 100) * 100
        for lvl in np.arange(lo, hi + 1, 100):
            if abs(lvl - p0) < TICK:
                continue
            side = -1 if lvl > p0 else 1
            i0 = first_touch(H, L, lvl, side)
            if i0 is not None:
                cands.append((i0, side, lvl, "psych"))
    elif variant == "vwapband_only":
        up, dn = lines["ETH+2sd"], lines["ETH-2sd"]
        for side, line in ((-1, up), (1, dn)):
            hit = np.flatnonzero(H >= line) if side == -1 else np.flatnonzero(L <= line)
            if len(hit):
                i0 = hit[0]
                cands.append((i0, side, line[i0], "ETH±2sd"))
    out = []
    for i0, side, lvl, tag in cands:
        j = momentum_trigger(O, H, L, C, i0, lvl, side)
        if j is not None:
            out.append({"i0": i0, "j": j, "side": side, "level": lvl, "tag": tag})
    return sorted(out, key=lambda e: e["j"])


def simulate_day(s, events, target):
    H, L, C = s.high.values, s.low.values, s.close.values
    vw = s.vw_eth.values
    trades, busy_until = [], -1
    for e in events:
        j, side = e["j"], e["side"]
        if j <= busy_until:
            continue
        entry = C[j]
        ext = H[e["i0"]:j + 1].max() if side == -1 else L[e["i0"]:j + 1].min()
        stop = ext + TICK if side == -1 else ext - TICK
        risk = abs(stop - entry)
        if risk > MAX_RISK or risk < TICK:
            continue
        if target == "VWAP":
            tgt_arr = vw
            if (vw[j] - entry) * side <= 0:          # vwap already behind entry -> no mean-reversion room
                continue
        else:
            tgt_arr = np.full(len(C), entry + side * float(target[:-1]) * risk)
        k_exit, px, why = len(C) - 1, C[-1], "time"
        for i in range(j + 1, len(C)):
            if (H[i] >= stop) if side == -1 else (L[i] <= stop):
                k_exit, px, why = i, stop, "stop"; break
            t = tgt_arr[i]
            if (L[i] <= t) if side == -1 else (H[i] >= t):
                k_exit, px, why = i, t, "target"; break
        pnl = side * (px - entry) - COST
        trades.append({**e, "entry": entry, "stop": stop, "exit": px, "why": why,
                       "pts": pnl, "R": pnl / risk, "risk": risk})
        busy_until = k_exit
    return trades


def backtest(bars, variant, target, tol=TOL):
    bars_s = bars[["open", "high", "low", "close"]]
    box = m.build_boxes(bars_s)
    sess = m.session_slices(bars, box)
    rows = []
    for day, b, s in sess:
        ev = day_events(day, b, s, variant, tol)
        for t in simulate_day(s, ev, target):
            t["day"] = day
            rows.append(t)
    return pd.DataFrame(rows), len(sess)


def summarize(tr, n_days):
    if tr.empty:
        return {"Trades": 0}
    r = tr.R
    eqR = r.cumsum()
    gp, gl = tr.pts[tr.pts > 0].sum(), -tr.pts[tr.pts < 0].sum()
    return {"Trades": len(tr), "Trades/Tag": round(len(tr) / n_days, 2),
            "Winrate %": round((tr.pts > 0).mean() * 100, 1),
            "Ø R": round(r.mean(), 3), "t-Stat": round(r.mean() / r.std(ddof=1) * np.sqrt(len(r)), 2) if len(r) > 2 else np.nan,
            "Σ R": round(r.sum(), 1), "PF": round(gp / gl, 2) if gl else np.inf,
            "Σ Punkte": round(tr.pts.sum(), 0), "Max DD (R)": round((eqR - eqR.cummax()).min(), 1),
            "Ø Risiko Pkt": round(tr.risk.mean(), 1)}


VARIANTS = ["stdv_only", "stdv_vwap", "stdv_psych", "stdv_psych50", "psych_only", "vwapband_only"]
TARGETS = ["1R", "2R", "VWAP"]


def main():
    OUT.mkdir(exist_ok=True)
    datasets = {"NQ_2023_2025": ("NQ", "2023-01-01", None),
                "CFD_2016_2022": ("CFD", "2016-11-16", "2023-01-01")}
    allrows = []
    for name, (kind, a, z) in datasets.items():
        bars = load(kind)
        bars = bars[(bars.index >= a) & ((bars.index < z) if z else True)]
        print(f"\n################ {name}")
        for target in TARGETS:
            for v in VARIANTS:
                tr, n = backtest(bars, v, target)
                row = {"Daten": name, "Target": target, "Variante": v, **summarize(tr, n)}
                allrows.append(row)
                print(row)
                if target == "2R":
                    tr.to_csv(OUT / f"conf_{name}_{v}_{target}_trades.csv", index=False)
        # tolerance sensitivity (2R)
        for tol in (2.5, 10.0):
            for v in ("stdv_vwap", "stdv_psych"):
                tr, n = backtest(bars, v, "2R", tol)
                row = {"Daten": name, "Target": f"2R tol={tol}", "Variante": v, **summarize(tr, n)}
                allrows.append(row)
                print(row)
    res = pd.DataFrame(allrows)
    res.to_csv(OUT / "confluence_summary.csv", index=False)
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()
