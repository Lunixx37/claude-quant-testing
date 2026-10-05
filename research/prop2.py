"""Prop simulation for the user's specific account rules (see PROP_REPORT.md).

Eval:   start 50,000 | static min balance 48,000 checked on EOD balance | target 53,000 |
        no consistency | daily loss limit 1,200.
Funded: start 50,000 | min balance 48,000 | max DD 2,000 from peak EOD balance (EOD trailing) |
        payout: >= 5 winning days (day P&L >= $250), balance >= 52,600, best day <= 50% of profit,
        daily loss limit 1,000.

Assumptions where the rules are not specific (all conservative unless stated):
  * Daily loss limit = HARD fail, checked intraday on unrealized P&L (bar extremes, adverse
    extreme assumed). `dll_mode='soft'` = liquidate and stop for the day instead.
  * Drawdown / min balance checked on the EOD balance only ("EOD drawdown").
  * Funded threshold = max(48,000, peak EOD balance - 2,000), no lock.
  * Payout = balance - 52,600 (withdraw down to the payout minimum); the peak is reset to the
    post-payout balance (withdrawals are not trading losses). Counters reset after a payout.
  * Success = eval passed AND first payout reached within `horizon` trading days from eval start.
"""
import math
from dataclasses import dataclass, field
import numpy as np

MNQ_PT = 2.0


@dataclass
class Phase:
    floor: float = 48_000
    trail_dd: float = 0.0          # 0 = static floor; >0 = EOD trailing from peak
    target: float = 0.0            # eval target balance
    dll: float = 1_200
    win_amt: float = 250.0
    win_days: int = 0
    pay_min_bal: float = 0.0
    consistency: float = 0.0


@dataclass
class Env:
    start: float = 50_000
    ev: Phase = field(default_factory=lambda: Phase(floor=48_000, target=53_000, dll=1_200))
    fu: Phase = field(default_factory=lambda: Phase(floor=48_000, trail_dd=2_000, dll=1_000, win_amt=250,
                                                     win_days=5, pay_min_bal=52_600, consistency=0.5))
    dll_mode: str = 'hard'
    comm_rt: float = 1.50          # $ per MNQ round turn
    max_mnq: int = 50
    fee_month: float = 0.0         # optional, for cost reporting


@dataclass(frozen=True)
class Policy:
    """Risk per trade = frac * (balance - threshold), capped; plus DLL/EOD guards."""
    ev_frac: float = 0.15
    fu_frac: float = 0.15
    ev_max: int = 10
    fu_max: int = 10
    r_usd: float = 50.0            # 1R per MNQ in $ (100 ticks); scaled by trade's own risk ticks
    guard: float = 1.05            # size so a full stop (x guard for gaps/slippage) cannot breach DLL / EOD floor
    stop_after_win: bool = False
    ev_coast: bool = False         # eval: size down so one average winner does not overshoot needlessly
    fu_payout_mode: bool = False   # funded: once balance >= pay_min_bal, trade minimum size to collect win days
    risk_usd: float = 0.0          # >0: fixed $ risk per trade in both phases (n = floor(risk_usd / R$))
    no_starve: bool = False        # if the EOD-floor guard says 0 contracts, still trade 1 (stalling = failing anyway)
    ev_min: int = 1                # minimum contracts (guards still apply)
    fu_min: int = 1


def contracts(bal, thr, day_left, frac, cap, pol, env, risk_mult, mn=1):
    r = pol.r_usd * risk_mult
    if pol.risk_usd > 0:
        n = max(int(pol.risk_usd / r), 1)
    else:
        n = max(int(frac * (bal - thr) / r), mn)
        n = min(n, cap)
    n = min(n, env.max_mnq)
    # guards: a full stop-out must not breach the DLL or the EOD threshold
    n = min(n, int((day_left - 5) / (r * pol.guard + env.comm_rt)))
    n_eod = int((bal - thr - 5) / (r * pol.guard + env.comm_rt))
    n = min(n, max(n_eod, 1) if pol.no_starve else n_eod)
    return max(n, 0)


def simulate(seq, pool, env: Env, pol: Policy, horizon=252):
    """Returns (passed_eval, eval_days, first_payout_day or -1, payouts list, dead_phase)."""
    phase = 'ev'
    P = env.ev
    bal = env.start
    peak = env.start
    thr = P.floor
    ev_days = -1
    payouts = []
    wins = 0
    best = 0.0
    base = env.start
    first_pay = -1
    for k in range(min(horizon, len(seq))):
        trades = pool[seq[k]]
        day0 = bal
        if trades:
            for (fav, adv, pts, risk_ticks) in trades:
                rm = risk_ticks / 100.0
                frac = pol.ev_frac if phase == 'ev' else pol.fu_frac
                cap = pol.ev_max if phase == 'ev' else pol.fu_max
                if phase == 'fu' and pol.fu_payout_mode and bal >= P.pay_min_bal and wins < P.win_days:
                    # need only win days now: smallest size that still makes a +0.75R winner >= win_amt
                    need = math.ceil((P.win_amt + 1) / (0.75 * pol.r_usd * rm * 1.0 - env.comm_rt))
                    cap = min(cap, max(need, 1))
                if phase == 'ev' and pol.ev_coast:
                    remaining = P.target - bal
                    need = math.ceil(remaining / (1.75 * pol.r_usd * rm))   # one +1.75R winner finishes
                    cap = min(cap, max(need, 1))
                mn = pol.ev_min if phase == 'ev' else pol.fu_min
                n = contracts(bal, thr, P.dll + (bal - day0), frac, cap, pol, env, rm, mn)
                if n <= 0:
                    break
                c = env.comm_rt * n
                b0 = bal - c
                stop_day = False
                for j in range(len(adv)):
                    low = b0 + adv[j] * MNQ_PT * n
                    if low - day0 <= -P.dll:
                        if env.dll_mode == 'hard':
                            return phase == 'fu', ev_days, first_pay, payouts, phase
                        bal = day0 - P.dll
                        stop_day = True
                        break
                if stop_day:
                    break
                bal = b0 + pts * MNQ_PT * n
                if pol.stop_after_win and pts > 0:
                    break
        # ---- end of day
        pnl = bal - day0
        if bal <= thr:            # EOD drawdown / min balance breach
            return phase == 'fu', ev_days, first_pay, payouts, phase
        if phase == 'ev':
            if bal >= P.target:
                phase, P = 'fu', env.fu
                ev_days = k + 1
                bal = peak = base = env.start
                thr = max(P.floor, peak - P.trail_dd) if P.trail_dd > 0 else P.floor
                wins, best = 0, 0.0
            continue
        peak = max(peak, bal)
        thr = max(P.floor, peak - P.trail_dd) if P.trail_dd > 0 else P.floor
        if trades:
            best = max(best, pnl)
            if pnl >= P.win_amt:
                wins += 1
        prof = bal - base
        if (wins >= P.win_days and bal >= P.pay_min_bal and prof > 0 and
                (P.consistency <= 0 or best <= P.consistency * prof)):
            amt = bal - P.pay_min_bal
            if amt > 0:
                payouts.append(amt)
                if first_pay < 0:
                    first_pay = k + 1
                bal -= amt
                peak = base = bal
                thr = max(P.floor, peak - P.trail_dd) if P.trail_dd > 0 else P.floor
                wins, best = 0, 0.0
    return phase == 'fu', ev_days, first_pay, payouts, None


def run_paths(paths, pool, env, pol, horizon=252):
    out = np.zeros((len(paths), 5))
    for i, seq in enumerate(paths):
        ok, evd, fp, pays, dead = simulate(seq, pool, env, pol, horizon)
        out[i] = (ok, evd, fp, sum(pays), {None: 0, 'ev': 1, 'fu': 2}[dead])
    passed = out[:, 0] == 1
    pay = out[:, 2] > 0
    return dict(p_payout=pay.mean(), p_pass=passed.mean(), p_ev_blow=(out[:, 4] == 1).mean(),
                p_fu_blow_before_pay=((out[:, 4] == 2) & ~pay).mean(),
                med_ev_days=float(np.median(out[passed, 1])) if passed.any() else np.nan,
                med_first_pay=float(np.median(out[pay, 2])) if pay.any() else np.nan,
                p_pay21=((out[:, 2] > 0) & (out[:, 2] <= 21)).mean(),
                p_pay42=((out[:, 2] > 0) & (out[:, 2] <= 42)).mean(),
                p_pay63=((out[:, 2] > 0) & (out[:, 2] <= 63)).mean(),
                mean_paid=out[:, 3].mean())
