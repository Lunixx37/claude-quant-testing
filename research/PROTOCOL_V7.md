# Protocol V7: more trades per month - VolBreakout adapted to the prop environment

Written before any V7 run.

## Prop rules (user, updated)
- **Eval:** start 50,000, min balance 48,000 (EOD), target 53,000, DLL 1,200, no consistency rule.
- **Funded:** start 50,000.
  - Min balance 48,000 and max DD 2,000 from the peak EOD balance.
  - DLL 1,000.
  - 5 winning days (>= $250).
  - Consistency: best day <= 50 % of profit since the last payout.
- **Payout:** allowed at balance >= 52,600; everything above 52,100 can be withdrawn.
  - Caps: 1,500 / 2,000 / 2,500 / 3,000 / then 3,500 (hard cap).
  - After a payout the peak is reset to the new balance.
- **Lifecycle:** when an account is blown (eval or funded), a new eval starts the next day.
  The number of evals used is reported.

## Main metrics
Per 12 and 24 months of operation:
- expected **total payouts ($)**, number of payouts, number of evals bought
- P(first payout <= 1 / 2 / 3 months), median days to the first payout
- trades/month

Sizing is chosen per phase from a fixed grid.

## Frequency ideas (fixed list)
| # | Model | Definition |
|---|---|---|
| M0 | NY VBO (reference) | k 0.3, stop 1x(k x prior RTH range), R-trailing, 1/day, both |
| M1 | NY VBO re-entry | after an exit, the next trigger touch (either side) enters again; max 2 / 3 trades/day |
| M2 | Asia VBO | anchor 18:00 open, range = prior RTH range; window 18:00-02:59 |
| M3 | London VBO | anchor 03:00 open, range = Asia range (18:00-02:59) or prior RTH range; window 03:00-09:29 |
| M4 | Afternoon VBO | anchor 13:00 open, range = 09:30-12:59 range; window 13:00-15:59 |
| M5 | Hourly VBO | anchor at each hour 10:00..15:00, range = previous hour; window = that hour + 60 min |

**Grid for M2-M5:**
- k {0.2, 0.3, 0.4, 0.5} (M5 also 0.75, 1.0)
- stop {0.75, 1.0} x (k x range)
- exit R-trailing or window end
- side both / long-only

**Costs:**
- Off-hours (M2, M3) use doubled slippage: 2 ticks per fill. CFD spread there is 2.5 pts instead of 1.2.
- RTH costs as before.

## Data use
| Step | Data |
|---|---|
| Model and parameter choice | CFD 2017-2022 only (positive E, t >= 2, plateau: neighbours positive) |
| Test | CFD 2023-25 and NQ futures 2023-25 (NQ 2023-25 includes off-hours) |

Portfolio = M0 + the models that pass. Prop sizing is chosen on the CFD 2017-22 pool and reported on NQ 2023-25.
