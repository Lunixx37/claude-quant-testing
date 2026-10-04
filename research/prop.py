"""Prop-firm simulation layer on top of the FROZEN strategy signals.

The strategy (entries, stops, trailing) is unchanged. This module only adds:
  * position sizing in MNQ (fixed or as a fraction of the remaining drawdown buffer)
  * an optional day rule (stop trading for the day after a win)
  * the account rules of two generic prop templates (EOD trailing / intraday trailing)

Intraday equity is reconstructed bar by bar inside each trade. Within a bar the
favourable extreme is assumed to happen BEFORE the adverse one, which is the worst
case for trailing drawdowns. The engine's trade prices already include 1 tick of
slippage per fill.
"""
import math
from dataclasses import dataclass, replace
import numpy as np
import pandas as pd
from run import backtest, data
from engine import Params, SPLITS
from candidates import FINAL

MNQ_PT = 2.0                 # $ per point per MNQ contract
R_TICKS = 100
R_USD_MNQ = R_TICKS * 0.25 * MNQ_PT   # 1R per MNQ = $50


@dataclass
class Rules:
    name: str
    start: float = 50_000
    target: float = 3_000
    dd: float = 2_000
    trail: str = 'eod'            # 'eod' = threshold trails closed EOD balance; 'intraday' = trails peak incl. unrealized
    lock_at: float = 0.0          # threshold stops trailing at start + lock_at
    dll: float = 0.0              # soft daily loss limit (liquidate + stop for the day), 0 = none
    eval_min_days: int = 2
    eval_consistency: float = 0.0  # best day <= x * total profit when passing (0 = off)
    pay_win_days: int = 5
    pay_win_amt: float = 150.0
    pay_min_days: int = 0
    pay_consistency: float = 0.0
    pay_mode: str = 'frac'        # 'frac': frac * (balance - start); 'above_buffer': balance - (start + buffer)
    pay_frac: float = 0.5
    pay_buffer: float = 0.0
    pay_min: float = 0.0
    pay_cap: float = 5_000
    split: float = 0.9
    fee_month: float = 50.0       # evaluation subscription per 21 trading days
    activation: float = 0.0
    max_contracts: int = 50       # MNQ
    comm_rt: float = 1.50         # $ per MNQ round turn (commission + exchange fees)


# Generic templates modelled after common 50K futures evaluations. Illustrative only:
# check the CURRENT rules of your firm and plug them in here.
TEMPLATES = {
    'A_EOD': Rules('A: 50K EOD-Trailing (DD 2000, Ziel 3000, DLL 1000)', dd=2_000, trail='eod', lock_at=0,
                   dll=1_000, eval_min_days=2, eval_consistency=0.5, pay_win_days=5, pay_win_amt=150,
                   pay_mode='frac', pay_frac=0.5, pay_cap=5_000, fee_month=50, activation=150),
    'B_INTRA': Rules('B: 50K Intraday-Trailing (DD 2500, Ziel 3000)', dd=2_500, trail='intraday', lock_at=100,
                     dll=0, eval_min_days=1, eval_consistency=0.0, pay_win_days=5, pay_win_amt=50,
                     pay_min_days=8, pay_consistency=0.3, pay_mode='above_buffer', pay_buffer=2_600,
                     pay_min=500, pay_cap=2_000, fee_month=80, activation=0),
}


@dataclass(frozen=True)
class Sizing:
    mode: str = 'fixed'           # 'fixed' -> n contracts; 'buf' -> floor(frac * buffer / R$) contracts
    n: int = 2
    frac: float = 0.25
    nmax: int = 20
    day_rule: str = 'none'        # 'none' | 'stop_after_win'

    def label(self):
        s = f'fix {self.n} MNQ' if self.mode == 'fixed' else f'{self.frac:.0%} Puffer (max {self.nmax})'
        return s + (' +StopNachGewinn' if self.day_rule == 'stop_after_win' else '')

    def contracts(self, bal, thr, rules):
        if self.mode == 'fixed':
            n = self.n
        else:
            n = int(self.frac * (bal - thr) / R_USD_MNQ)
            n = min(n, self.nmax)
        return max(1, min(n, rules.max_contracts))


# ---------------------------------------------------------------- data
def day_pool(split, allow_forward=False):
    """List of NY trading days (incl. days without trades); each day = list of trades,
    each trade = (fav_pts array, adv_pts array, final_pts)."""
    f = data()
    tr = backtest(Params(**FINAL), split, allow_forward=allow_forward)
    a, b = (SPLITS['train'][0], SPLITS['valid'][1]) if split == 'is' else SPLITS[split]
    sd = f['sdate']
    rth = (f['mod'] == 570) & (sd >= np.datetime64(a)) & (sd <= np.datetime64(b))
    days = list(np.unique(sd[rth]))
    by = {d: [] for d in days}
    h, l = f['h'], f['l']
    for r in tr.itertuples():
        e, d = r.entry, r.dir
        idx = np.arange(r.entry_i, r.exit_i + 1)
        fav = (h[idx] - e) if d > 0 else (e - l[idx])
        adv = (l[idx] - e) if d > 0 else (e - h[idx])
        if r.why == 'stop':                       # stop bar: worst point is the actual fill
            adv[-1] = max(adv[-1], r.pts)
        by[r.sdate].append((fav, adv, r.pts))
    return days, [by[d] for d in days], tr


def block_bootstrap(n_days, length, n_paths, block=10, seed=0):
    rng = np.random.default_rng(seed)
    nb = math.ceil(length / block)
    starts = rng.integers(0, n_days - block, size=(n_paths, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_paths, -1)[:, :length]
    return idx


# ---------------------------------------------------------------- account simulation
def run_account(seq, pool, rules: Rules, sz: Sizing, phase, horizon):
    """Simulate one account over day indices `seq`. Returns dict and the number of days used."""
    bal = rules.start
    thr = rules.start - rules.dd
    peak = rules.start
    traded = 0
    best_day = 0.0
    # payout bookkeeping (funded)
    win_days = 0
    days_since = 0
    best_since = 0.0
    base_since = rules.start
    payouts = []
    used = 0
    lock = rules.start + rules.lock_at
    for k in range(min(horizon, len(seq))):
        used = k + 1
        trades = pool[seq[k]]
        day0 = bal
        dead = False
        if trades:
            for fav, adv, pts in trades:
                n = sz.contracts(bal, thr, rules)
                c = rules.comm_rt * n
                base = bal - c
                stopped_day = False
                for j in range(len(fav)):
                    if rules.trail == 'intraday':
                        up = base + fav[j] * MNQ_PT * n
                        if up > peak:
                            peak = up
                            thr = max(thr, min(peak - rules.dd, lock))
                    low = base + adv[j] * MNQ_PT * n
                    if low <= thr:
                        dead = True
                        break
                    if rules.dll and low - day0 <= -rules.dll:
                        bal = day0 - rules.dll          # soft breach: liquidated at the limit
                        stopped_day = True
                        break
                if dead:
                    bal = thr
                    break
                if stopped_day:
                    break
                bal = base + pts * MNQ_PT * n
                if sz.day_rule == 'stop_after_win' and pts > 0:
                    break
            traded += 1
        if dead:
            return dict(ok=False, dead=True, days=used, traded=traded, bal=bal, payouts=payouts)
        # end of day
        pnl = bal - day0
        if rules.trail == 'eod' or bal > peak:
            peak = max(peak, bal)
            thr = max(thr, min(peak - rules.dd, lock))
        if trades:
            best_day = max(best_day, pnl)
        if phase == 'eval':
            prof = bal - rules.start
            if (prof >= rules.target and traded >= rules.eval_min_days and
                    (rules.eval_consistency <= 0 or best_day <= rules.eval_consistency * prof)):
                return dict(ok=True, dead=False, days=used, traded=traded, bal=bal, payouts=payouts)
        else:
            if trades:
                days_since += 1
                best_since = max(best_since, pnl)
                if pnl >= rules.pay_win_amt:
                    win_days += 1
            prof_since = bal - base_since
            if (win_days >= rules.pay_win_days and days_since >= rules.pay_min_days and prof_since > 0 and
                    (rules.pay_consistency <= 0 or best_since <= rules.pay_consistency * prof_since)):
                if rules.pay_mode == 'frac':
                    amt = min(rules.pay_frac * (bal - rules.start), rules.pay_cap)
                else:
                    amt = min(bal - (rules.start + rules.pay_buffer), rules.pay_cap)
                if amt >= max(rules.pay_min, 1.0):
                    bal -= amt
                    payouts.append(amt)
                    win_days = days_since = 0
                    best_since = 0.0
                    base_since = bal
    return dict(ok=False, dead=False, days=used, traded=traded, bal=bal, payouts=payouts)


def evaluate(pool, paths, rules, sz_eval, sz_fund, horizon_eval=252, horizon_fund=252):
    """Eval phase then (if passed) funded phase on the continuing day sequence."""
    res = []
    for seq in paths:
        e = run_account(seq, pool, rules, sz_eval, 'eval', horizon_eval)
        months = math.ceil(e['days'] / 21)
        fees = months * rules.fee_month
        pay = 0.0
        fdead = False
        npay = 0
        if e['ok']:
            fees += rules.activation
            f = run_account(seq[e['days']:], pool, rules, sz_fund, 'fund', horizon_fund)
            pay = sum(f['payouts']) * rules.split
            npay = len(f['payouts'])
            fdead = f['dead']
        res.append((e['ok'], e['dead'], e['days'], fees, pay, npay, fdead))
    r = np.array(res, dtype=float)
    passed = r[:, 0] == 1
    return dict(p_pass=passed.mean(), p_fail=r[:, 1].mean(),
                p_timeout=1 - passed.mean() - r[:, 1].mean(),
                days_pass_med=float(np.median(r[passed, 2])) if passed.any() else np.nan,
                fees=r[:, 3].mean(), pay=r[:, 4].mean(),
                p_payout=(r[:, 5] > 0).mean(), n_pay=r[passed, 5].mean() if passed.any() else 0,
                p_fund_blow=r[passed, 6].mean() if passed.any() else np.nan,
                ev=(r[:, 4] - r[:, 3]).mean())
