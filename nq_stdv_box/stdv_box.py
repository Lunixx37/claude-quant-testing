"""
NQ "Stdv Box" indicator + backtest.

Indicator (per trading day, times in America/New_York):
  * O0   = open of the 1-min candle that opens at 00:00 ET  (06:00 German time)
  * O830 = open of the 1-min candle that opens at 08:30 ET  (14:30 German time)
  * Box  = [min(O0, O830), max(O0, O830)],  Mid = 50 % of the box
  * Leg  = half box height h = (top - bottom) / 2
       leg "bottom -> mid" (fib 1 = bottom, 0 = mid) projects BELOW the box:  mid - k*h
       leg "top -> mid"    (fib 1 = top,    0 = mid) projects ABOVE the box:  mid + k*h
  * k in STDV_LEVELS (k = 1 is exactly the box edge)

Data:
  * Dataset_NQ_1min_2022_2025.csv : NQ futures, ET, timestamp = bar CLOSE time
                                    -> shifted by -1 min to get bar OPEN time
  * 1m_data_part*.zip            : NAS100 CFD, broker time = ET + 7h, timestamp = bar OPEN time
"""
from __future__ import annotations

import argparse
import itertools
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

STDV_LEVELS = [2.0, 2.25, 2.5, 3.5, 4.0, 4.25, 4.5]
BOX_START = "00:00"
BOX_END = "08:30"
EVAL_END = "16:00"          # levels are evaluated from 08:30 until this time (ET)
COST_PTS = 0.5              # round-turn cost per trade in index points (commission + slippage)

ROOT = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------------- data
def load_nq() -> pd.DataFrame:
    df = pd.read_csv(ROOT / "Dataset_NQ_1min_2022_2025.csv")
    t = pd.to_datetime(df["timestamp ET"], format="%m/%d/%Y %H:%M") - pd.Timedelta("1min")
    out = df[["open", "high", "low", "close"]].copy()
    out.index = t
    return out.sort_index()


def load_cfd() -> pd.DataFrame:
    parts = []
    for i in (1, 2):
        with zipfile.ZipFile(ROOT / f"1m_data_part{i}.zip") as z:
            with z.open(f"1m_data_part{i}.csv") as f:
                parts.append(pd.read_csv(f, sep="\t"))
    df = pd.concat(parts)
    t = pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S") - pd.Timedelta("7h")
    out = pd.DataFrame({"open": df.Open.values, "high": df.High.values,
                        "low": df.Low.values, "close": df.Close.values}, index=t)
    out = out[~out.index.duplicated()]
    return out.sort_index()


# ----------------------------------------------------------------------------- indicator
def build_boxes(bars: pd.DataFrame, levels=STDV_LEVELS) -> pd.DataFrame:
    """One row per day with box + stdv level prices."""
    hm = bars.index.strftime("%H:%M")
    o0 = bars.loc[hm == BOX_START, "open"]
    o830 = bars.loc[hm == BOX_END, "open"]
    o0.index = o0.index.normalize()
    o830.index = o830.index.normalize()
    box = pd.concat({"o0": o0, "o830": o830}, axis=1, sort=True).dropna()
    box = box[box.index.dayofweek < 5]
    box["top"] = box[["o0", "o830"]].max(axis=1)
    box["bot"] = box[["o0", "o830"]].min(axis=1)
    box["mid"] = (box.top + box.bot) / 2
    box["h"] = (box.top - box.bot) / 2
    box["dir"] = np.sign(box.o830 - box.o0)          # +1: 08:30 opened above 00:00
    for k in levels:
        box[f"up_{k}"] = box.mid + k * box.h
        box[f"dn_{k}"] = box.mid - k * box.h
    return box


_CACHE: dict = {}


def session_slices(bars: pd.DataFrame, box: pd.DataFrame):
    """List of (day, box_row, session bars 08:30 <= t < EVAL_END). Cached per (bars, box)."""
    key = (id(bars), id(box))
    if key in _CACHE:
        return _CACHE[key]
    days = bars.index.normalize()
    hm = bars.index.strftime("%H:%M")
    in_sess = (hm >= BOX_END) & (hm < EVAL_END)
    sess = bars[in_sess]
    groups = dict(tuple(sess.groupby(days[in_sess])))
    res = []
    for day, row in box.iterrows():
        s = groups.get(day)
        if row.h <= 0 or s is None or len(s) < 300:   # skip flat boxes / half days / gaps
            continue
        res.append((day, row, s))
    _CACHE[key] = res
    return res


# ----------------------------------------------------------------------------- statistics
def level_stats(bars, box, levels=STDV_LEVELS) -> pd.DataFrame:
    rows = []
    for day, b, s in session_slices(bars, box):
        hi, lo = s.high.max(), s.low.min()
        r = {"day": day, "h": b.h, "box_pct": 2 * b.h / b.mid * 100, "dir": b.dir,
             "ext_up": (hi - b.mid) / b.h, "ext_dn": (b.mid - lo) / b.h,
             "close_k": (s.close.iloc[-1] - b.mid) / b.h}
        rows.append(r)
    return pd.DataFrame(rows).set_index("day")


def hit_table(st: pd.DataFrame, levels=STDV_LEVELS) -> pd.DataFrame:
    """P(level reached), split by side (with / against box direction)."""
    ks = [1.0] + list(levels)
    out = {}
    up_hit = {k: st.ext_up >= k for k in ks}
    dn_hit = {k: st.ext_dn >= k for k in ks}
    for k in ks:
        with_dir = np.where(st.dir > 0, up_hit[k], dn_hit[k])
        against = np.where(st.dir > 0, dn_hit[k], up_hit[k])
        out[k] = {"oben %": up_hit[k].mean() * 100, "unten %": dn_hit[k].mean() * 100,
                  "irgendeine Seite %": (up_hit[k] | dn_hit[k]).mean() * 100,
                  "in Box-Richtung %": with_dir.mean() * 100,
                  "gegen Box-Richtung %": against.mean() * 100}
    t = pd.DataFrame(out).T
    t.index.name = "k (Stdv)"
    # continuation: P(reach next level | reached this level), both sides pooled
    cont = []
    for a, b in zip(ks[:-1], ks[1:]):
        n = (st.ext_up >= a).sum() + (st.ext_dn >= a).sum()
        m = (st.ext_up >= b).sum() + (st.ext_dn >= b).sum()
        cont.append(m / n * 100 if n else np.nan)
    t["P(nächstes Level | dieses Level) %"] = cont + [np.nan]
    return t.round(1)


def extreme_distribution(st: pd.DataFrame, levels=STDV_LEVELS) -> pd.DataFrame:
    """Where does the session high (above box) / low (below box) end, in Stdv buckets."""
    edges = [-np.inf, 1.0] + list(levels) + [np.inf]
    labels = ["innerhalb Box (<1)"] + [f"{a}–{b}" for a, b in zip([1.0] + levels[:-1], levels)] + [f">{levels[-1]}"]
    ext = pd.concat([st.ext_up, st.ext_dn])
    c = pd.cut(ext, edges, labels=labels, right=False).value_counts(sort=False)
    return (c / c.sum() * 100).round(1).to_frame("Anteil Session-Extreme %")


# ----------------------------------------------------------------------------- example strategy
def fade_backtest(bars, box, entry_k, stop_k, target_k, min_box_pct=0.0, cost=COST_PTS):
    """
    Fade the FIRST stdv level `entry_k` touched after 08:30 (limit order, either side,
    max 1 trade/day). Stop at `stop_k`, target at `target_k` (0 = mid, 1 = box edge).
    Exit at EVAL_END close otherwise. Conservative: stop wins if stop & target inside
    the same 1-min bar; target is not checked on the entry bar.
    """
    trades = []
    for day, b, s in session_slices(bars, box):
        if 2 * b.h / b.mid * 100 < min_box_pct:
            continue
        up_e, dn_e = b.mid + entry_k * b.h, b.mid - entry_k * b.h
        H, L, C = s.high.values, s.low.values, s.close.values
        touch_up = np.flatnonzero(H >= up_e)
        touch_dn = np.flatnonzero(L <= dn_e)
        iu = touch_up[0] if len(touch_up) else 10**9
        idn = touch_dn[0] if len(touch_dn) else 10**9
        if iu == idn == 10**9:
            continue
        side = -1 if iu <= idn else 1           # short at upper level, long at lower level
        i0 = min(iu, idn)
        entry = up_e if side == -1 else dn_e
        stop = b.mid - side * stop_k * b.h
        tgt = b.mid - side * target_k * b.h
        risk = abs(stop - entry)
        hs = np.flatnonzero((H[i0:] >= stop) if side == -1 else (L[i0:] <= stop))
        ht = np.flatnonzero((L[i0 + 1:] <= tgt) if side == -1 else (H[i0 + 1:] >= tgt)) + 1
        js = hs[0] if len(hs) else 10**9
        jt = ht[0] if len(ht) else 10**9
        if js == jt == 10**9:
            exit_px, reason = C[-1], "time"
        elif js <= jt:                      # stop first (or same bar -> conservative)
            exit_px, reason = stop, "stop"
        else:
            exit_px, reason = tgt, "target"
        pnl = side * (exit_px - entry) - cost
        trades.append({"day": day, "side": side, "entry": entry, "exit": exit_px,
                       "reason": reason, "pnl_pts": pnl, "R": pnl / risk})
    return pd.DataFrame(trades)


def summarize(tr: pd.DataFrame, n_days: int) -> dict:
    if tr.empty:
        return {"trades": 0}
    eq = tr.pnl_pts.cumsum()
    dd = (eq - eq.cummax()).min()
    gp, gl = tr.pnl_pts[tr.pnl_pts > 0].sum(), -tr.pnl_pts[tr.pnl_pts < 0].sum()
    return {"trades": len(tr), "trade/Tag %": round(len(tr) / n_days * 100, 1),
            "winrate %": round((tr.pnl_pts > 0).mean() * 100, 1),
            "avg R": round(tr.R.mean(), 3), "sum R": round(tr.R.sum(), 1),
            "PF": round(gp / gl, 2) if gl else np.inf,
            "Punkte gesamt": round(tr.pnl_pts.sum(), 1), "max DD Punkte": round(dd, 1)}


def strategy_grid(bars, box, n_days, min_box_pct=0.0):
    rows = []
    for e, s in itertools.combinations(STDV_LEVELS, 2):
        for t in (1.0, 0.0):
            tr = fade_backtest(bars, box, e, s, t, min_box_pct)
            rows.append({"entry k": e, "stop k": s, "target": "Box-Kante" if t == 1 else "Mitte",
                         **summarize(tr, n_days)})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- main
def run(name, bars, start=None, end=None, out=None):
    if start: bars = bars[bars.index >= start]
    if end: bars = bars[bars.index < end]
    box = build_boxes(bars)
    st = level_stats(bars, box)
    print(f"\n===== {name}: {st.index.min().date()} .. {st.index.max().date()}  ({len(st)} Tage) =====")
    print("Halbe Boxhöhe h (Punkte):", st.h.describe().round(1).to_dict())
    print(hit_table(st).to_string())
    print(extreme_distribution(st).to_string())
    g = strategy_grid(bars, box, len(st))
    print(g.sort_values("sum R", ascending=False).head(15).to_string(index=False))
    if out:
        out.mkdir(exist_ok=True)
        st.to_csv(out / f"{name}_daily.csv")
        hit_table(st).to_csv(out / f"{name}_hits.csv")
        extreme_distribution(st).to_csv(out / f"{name}_extremes.csv")
        g.to_csv(out / f"{name}_grid.csv", index=False)
    return box, st, g


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "results"))
    a = ap.parse_args()
    out = Path(a.out)
    run("NQ_2023_2025", load_nq(), "2023-01-01", out=out)
    run("CFD_2016_2022", load_cfd(), "2016-11-16", "2023-01-01", out=out)
