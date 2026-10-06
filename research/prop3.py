"""Prop lifecycle simulator with the user's updated payout rules (PROTOCOL_V7.md).

Day pool format as in prop2: each day = list of trades (fav, adv_pts_array, final_pts, stop_ticks).
One path = consecutive days. Accounts are restarted (new eval) after a breach; payouts are accumulated.
Sizing: fixed $ risk per trade per phase (MNQ, $2/pt, $1.50 RT commission), guards so that a full stop
cannot breach the DLL / EOD floor (trade min 1 contract when the floor guard says 0 = 'no starve').
"""
import numpy as np

MNQ_PT, COMM = 2.0, 1.5


class Rules:
    start = 50_000.0
    ev_floor, ev_target, ev_dll = 48_000.0, 53_000.0, 1_200.0
    fu_floor, fu_trail, fu_dll = 48_000.0, 2_000.0, 1_000.0
    win_amt, win_days, consistency = 250.0, 5, 0.5
    pay_min_bal, pay_keep = 52_600.0, 52_100.0
    caps = (1_500.0, 2_000.0, 2_500.0, 3_000.0, 3_500.0)


def _n(risk_usd, stop_pts, bal, thr, day_left, guard=1.05):
    r = 2.0 * stop_pts                          # $ per MNQ at the stop
    n = max(int(risk_usd / r), 1)
    n = min(n, int((day_left - 5) / (r * guard + COMM)))
    n = min(n, max(int((bal - thr - 5) / (r * guard + COMM)), 1))
    return n


def lifecycle(seq, pool, risk_ev, risk_fu, R=Rules):
    """Returns dict: payouts list of (day, amount), evals used, first payout day, blown counts."""
    phase, bal, peak, thr = 'ev', R.start, R.start, R.ev_floor
    evals, pays, blown_ev, blown_fu = 1, [], 0, 0
    wins, best, base = 0, 0.0, R.start
    for day, j in enumerate(seq):
        day0 = bal
        dll = R.ev_dll if phase == 'ev' else R.fu_dll
        dead = False
        for (_, adv, pts, stop_ticks) in pool[j]:
            sp = stop_ticks / 4.0
            n = _n(risk_ev if phase == 'ev' else risk_fu, sp, bal, thr, dll + (bal - day0))
            if n <= 0:
                break
            b0 = bal - n * COMM
            if (b0 + adv.min() * MNQ_PT * n) - day0 <= -dll:      # hard DLL breach on open P&L
                dead = True; break
            bal = b0 + pts * MNQ_PT * n
        if not dead and bal <= thr:                               # EOD floor / trailing DD breach
            dead = True
        if dead:
            if phase == 'ev': blown_ev += 1
            else: blown_fu += 1
            phase, bal, peak, thr, evals = 'ev', R.start, R.start, R.ev_floor, evals + 1
            continue
        if phase == 'ev':
            if bal >= R.ev_target:
                phase, bal, peak, base, wins, best = 'fu', R.start, R.start, R.start, 0, 0.0
                thr = max(R.fu_floor, peak - R.fu_trail)
            continue
        pnl = bal - day0
        peak = max(peak, bal); thr = max(R.fu_floor, peak - R.fu_trail)
        if pool[j]:
            best = max(best, pnl)
            if pnl >= R.win_amt: wins += 1
        prof = bal - base
        if wins >= R.win_days and bal >= R.pay_min_bal and prof > 0 and best <= R.consistency * prof:
            amt = min(bal - R.pay_keep, R.caps[min(len(pays), len(R.caps) - 1)])
            pays.append((day, amt))
            bal -= amt; peak = base = bal; thr = max(R.fu_floor, peak - R.fu_trail)
            wins, best = 0, 0.0
    return dict(pays=pays, evals=evals, blown_ev=blown_ev, blown_fu=blown_fu)


def evaluate(paths, pool, risk_ev, risk_fu):
    res = [lifecycle(p, pool, risk_ev, risk_fu) for p in paths]
    H = len(paths[0])
    tot = np.array([sum(a for _, a in r['pays']) for r in res])
    tot12 = np.array([sum(a for d, a in r['pays'] if d < 252) for r in res])
    npay = np.array([len(r['pays']) for r in res])
    first = np.array([r['pays'][0][0] + 1 if r['pays'] else np.nan for r in res])
    ev = np.array([r['evals'] for r in res])
    return dict(pay_12m_mean=tot12.mean(), pay_12m_median=np.median(tot12), pay_24m_mean=tot.mean() if H >= 504 else np.nan,
                n_pay_24m=npay.mean(), evals_24m=ev.mean(),
                p_first_1m=np.mean(first <= 21), p_first_2m=np.mean(first <= 42), p_first_3m=np.mean(first <= 63),
                p_first_12m=np.mean(first <= 252), med_first=np.nanmedian(first) if np.isfinite(first).any() else np.nan,
                p_zero_12m=np.mean(tot12 == 0))
