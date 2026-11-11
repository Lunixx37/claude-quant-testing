"""
"First reaction + second sweep" setup (as marked on the gold chart), 08:30-16:00 ET, 1-min bars.

Sweep & reclaim of level L (support, bullish): a bar trades below L coming from above (previous close >= L),
and within RECLAIM_BARS bars a 1-min candle CLOSES back above L.  Resistance (bearish) is the mirror.

1. First reaction of the day = first sweep & reclaim of a QUALIFYING trigger:
     cluster 2-2.25-2.5  (all three swept -> reference = 2.5 level)
     cluster 4-4.25-4.5  (reference = 4.5 level)
     single 3.5 level
     box edges (top / bottom)
   Direction D = +1 if a support was swept & reclaimed (bullish), -1 for resistance.
2. Entry: next sweep & reclaim, after the first reaction, of ANOTHER level (any stdv level or box edge,
   "strict": different from the first reaction's reference level) in the SAME direction D.
   Entry at the close of the reclaim candle.
3. Stop: beyond the extreme of that second sweep (+/- 1 tick).
4. Target:
     "swing_between": the high (long) / low (short) between the first reaction and the second sweep
     "pivot"        : nearest confirmed 1-min pivot (5/5) beyond entry, formed since 08:30
   Only trades with reward/risk > 1 (MIN_RR). If a second sweep does not qualify, the next one is checked.
   Max. one trade per day, exit at target / stop / 15:59 close. Stop wins if both inside one bar.

Control: same entry/stop/target rules on the FIRST sweep & reclaim of any single level (no first-reaction
condition), to see whether the first-reaction filter adds anything.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import followup as fu      # noqa: E402
import stdv_box as m       # noqa: E402

OUT = Path(__file__).parent / "results" / "sweep"
TICK = 0.25
COST = 1.0
MIN_RR = 1.0
PIV = 5


def sweep_events(H, L, C, O, lvl, side, n_bars, start=0):
    """All sweep&reclaim events of one level. side +1 = support (swept below, reclaimed above)."""
    ev = []
    n = len(C)
    if side == 1:
        below = L < lvl
    else:
        below = H > lvl
    idx = np.flatnonzero(below)
    last_r = -1
    for s in idx:
        if s < start or s <= last_r:
            continue
        prev = C[s - 1] if s > 0 else O[0]
        if (prev < lvl) if side == 1 else (prev > lvl):       # must come from the other side
            continue
        seg = C[s:min(s + n_bars + 1, n)]
        ok = np.flatnonzero(seg > lvl) if side == 1 else np.flatnonzero(seg < lvl)
        if not len(ok):
            continue
        r = s + ok[0]
        ext = L[s:r + 1].min() if side == 1 else H[s:r + 1].max()
        ev.append((r, s, ext))
        last_r = r
    return ev


def pivots(H, L):
    n = len(H)
    ph, pl = [], []
    for i in range(PIV, n - PIV):
        w = slice(i - PIV, i + PIV + 1)
        if H[i] == H[w].max() and H[i] > H[i - PIV:i].max():
            ph.append(i)
        if L[i] == L[w].min() and L[i] < L[i - PIV:i].min():
            pl.append(i)
    return np.array(ph, dtype=int), np.array(pl, dtype=int)


def level_set(b):
    lv = {f"+{k}": (b.mid + k * b.h) for k in m.STDV_LEVELS}
    lv.update({f"-{k}": (b.mid - k * b.h) for k in m.STDV_LEVELS})
    lv["top"], lv["bot"] = b.top, b.bot
    return lv


def start_830(d):
    """The 08:30 edge only counts once price has moved 0.5 h away from it (it opens exactly there)."""
    b = d["b"]
    i = np.flatnonzero((d["H"] >= b.o830 + 0.5 * b.h) | (d["L"] <= b.o830 - 0.5 * b.h))
    return int(i[0]) + 1 if len(i) else 10**9


def triggers(d):
    """qualifying first-reaction triggers: name -> [(level, side, earliest bar)]."""
    b = d["b"]
    s830 = start_830(d)
    edges = [(b.o0, sd, 0) for sd in (1, -1)] + [(b.o830, sd, s830) for sd in (1, -1)]
    return {"Cluster 2–2.5": [(b.mid - 2.5 * b.h, 1, 0), (b.mid + 2.5 * b.h, -1, 0)],
            "Cluster 4–4.5": [(b.mid - 4.5 * b.h, 1, 0), (b.mid + 4.5 * b.h, -1, 0)],
            "3.5": [(b.mid - 3.5 * b.h, 1, 0), (b.mid + 3.5 * b.h, -1, 0)],
            "Box-Kante": edges}


def make_trade(d, side, r2, s2, ext, tp, tag):
    H, L, C = d["H"], d["L"], d["C"]
    entry = C[r2]
    stop = ext - side * TICK
    risk = abs(entry - stop)
    if tp is None or risk < TICK:
        return None
    rr = (tp - entry) * side / risk
    if rr <= MIN_RR:
        return None
    js = np.flatnonzero((L[r2 + 1:] <= stop) if side == 1 else (H[r2 + 1:] >= stop))
    jt = np.flatnonzero((H[r2 + 1:] >= tp) if side == 1 else (L[r2 + 1:] <= tp))
    js = js[0] if len(js) else 10**9
    jt = jt[0] if len(jt) else 10**9
    if js == jt == 10**9:
        px, why = C[-1], "time"
    elif js <= jt:
        px, why = stop, "stop"
    else:
        px, why = tp, "target"
    pnl = side * (px - entry) - COST
    return {"day": d["day"], "side": side, "entry": entry, "stop": stop, "tp": tp, "rr": rr,
            "exit": px, "why": why, "pts": pnl, "R": pnl / risk, "risk": risk, "level2": tag, "bar": r2}


def day_setup(d, tp_mode, strict=True, n_bars=10, control=False):
    b, O, H, L, C = d["b"], d["O"], d["H"], d["L"], d["C"]
    lv = level_set(b)
    ph, pl = pivots(H, L)
    if control:
        r1, side, ref, kind = -1, None, None, "Kontrolle"
    else:
        first = []
        for kind, lst in triggers(d).items():
            for lvl, side, st in lst:
                ev = sweep_events(H, L, C, O, lvl, side, n_bars, start=st)
                if ev:
                    first.append((ev[0][0], ev[0][1], side, lvl, kind))
        if not first:
            return None
        r1, s1, side, ref, kind = min(first)
    # candidate second sweeps
    cands = []
    s830 = start_830(d)
    for name, lvl in lv.items():
        st = r1 + 1 if abs(lvl - b.o830) > 1e-9 else max(r1 + 1, s830)
        if strict and ref is not None and abs(lvl - ref) < 1e-9:
            continue
        sides = [side] if side is not None else [1, -1]
        for sd in sides:
            for r2, s2, ext in sweep_events(H, L, C, O, lvl, sd, n_bars, start=st):
                cands.append((r2, s2, ext, sd, name))
    for r2, s2, ext, sd, name in sorted(cands):
        if tp_mode == "swing_between":
            if control or s2 <= r1 + 1:
                continue
            seg = slice(r1, s2)
            tp = H[seg].max() if sd == 1 else L[seg].min()
        else:
            piv = ph if sd == 1 else pl
            piv = piv[piv + PIV <= r2]
            px = H[piv] if sd == 1 else L[piv]
            ok = px[(px - C[r2]) * sd > 0]
            tp = (ok.min() if sd == 1 else ok.max()) if len(ok) else None
        t = make_trade(d, sd, r2, s2, ext, tp, name)
        if t is not None:
            t["first"] = kind
            return t
    return None


def run(days, name):
    rows, trades = [], []
    configs = [("swing_between", True, 10, False), ("pivot", True, 10, False),
               ("swing_between", False, 10, False), ("swing_between", True, 3, False),
               ("pivot", True, 10, True)]
    for tp_mode, strict, nb, control in configs:
        tr = [t for d in days if (t := day_setup(d, tp_mode, strict, nb, control)) is not None]
        tr = pd.DataFrame(tr)
        if tr.empty:
            continue
        tr = tr.merge(pd.DataFrame({"day": [d["day"] for d in days], "rel": [d["b"].rel for d in days]}), on="day")
        label = ("KONTROLLE (ohne erste Reaktion)" if control else "Setup") + \
            f" | TP={tp_mode} | {'anderes Level' if strict else 'auch gleiches Level'} | Reclaim≤{nb} Bars"
        for f in (0.0, 0.1, 0.2, 0.3):
            t = tr[tr.rel >= f]
            rows.append({"Daten": name, "Config": label, "Box ≥ ATR×": f,
                         "Tage": sum(d["b"].rel >= f for d in days), **fu.summarize(t),
                         "Ø RR geplant": round(t.rr.mean(), 2) if len(t) else np.nan})
        tr["config"] = label
        trades.append(tr)
    return pd.DataFrame(rows), pd.concat(trades)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sets = {"NQ_2023_2025": ("NQ", "2022-12-01", "2026-01-01", "2023-01-01"),
            "CFD_2016_2022": ("CFD", "2016-11-01", "2023-01-01", "2016-11-16")}
    allr = []
    for name, (kind, a, z, fd) in sets.items():
        days, _ = fu.prepare(kind, a, z)
        days = [d for d in days if d["day"] >= pd.Timestamp(fd)]
        res, tr = run(days, name)
        allr.append(res)
        tr.to_csv(OUT / f"{name}_trades.csv", index=False)
        pd.set_option("display.width", 250)
        print(f"\n######## {name}: {len(days)} Tage")
        print(res.to_string(index=False))
        main_tr = tr[tr.config.str.startswith("Setup | TP=swing_between | anderes")]
        for col in ("first", "level2", "side"):
            g = main_tr[main_tr.rel >= 0.1].groupby(col).apply(lambda x: pd.Series(fu.summarize(x)), include_groups=False)
            print(g[["n", "Win %", "Ø R", "t"]].to_string())
            g.to_csv(OUT / f"{name}_by_{col}.csv")
        rb = pd.cut(main_tr.risk, [0, 3, 6, 10, 20, 1e9])
        g = main_tr.groupby(rb, observed=True).apply(lambda x: pd.Series(fu.summarize(x)), include_groups=False)
        print(g[["n", "Win %", "Ø R", "t"]].to_string())
        g.to_csv(OUT / f"{name}_by_risk.csv")
    pd.concat(allr).to_csv(OUT / "summary.csv", index=False)


if __name__ == "__main__":
    main()
