# Protocol V5: refining the FVG continuation candidate (written before any V5 run)

**Base:** V4_CANDIDATE. FVG rejection, fixed 40-pt stop, TP 3R, intraday, 09:30-11:00 NY, max 2/day.

## Data use
| Decision | Data |
|---|---|
| All refinements (filters, stops, exits, swing) | Train 2017-01..2020-06 and Validation 2020-07..2021-12 (CFD) |
| One run of the frozen refinement | Test 2022 (CFD) + 2023-25 (NQ futures, MNQ costs; and CFD) |

**Honesty note:** 2022-25 already served once as the test of the base candidate.

## Phase A: single filters (each one alone, vs base; Train and Validation)
| # | Filter | Values |
|---|---|---|
| F1 | entry candle body in pts | >= 2 / 4 / 6 |
| F2 | entry candle body / range | >= 0.4 / 0.6 / 0.8 |
| F3 | entry candle range vs 20-bar average | >= 0.75 / 1.0 / 1.5 |
| F4 | FVG gap size in pts | >= 1 / 2 / 4 |
| F5 | displacement ratio | >= 2.0 / 2.5 / 3.0 |
| F6 | FVG age in bars | <= 5 / 10 / 20 |
| F7 | daily trend (with-trend only) | prior RTH close vs SMA20 / SMA50 of RTH closes; prior day direction |
| F8 | intraday bias | with the move since 09:30 / against it |
| F9 | entry time | before 10:00 / before 10:30 |
| F10 | first signal of the day only | yes |
| F11 | volatility regime: prior RTH range / 20-day mean | > 1 / < 1 |

A filter is **kept** when it improves E (CFD costs) in Train **and** Validation and leaves >= 1.5 trades/week.

## Phase B: combinations of kept filters
- All subsets of the kept filters, each at its best Train value.
- Ranking: min(E_train, E_valid) with >= 1.5 trades/week.

## Phase C: stops / exits / swing on the Phase B filter set
- **Stops:** fixed 30 / 40 / 50 / 60 / 80 pts; structural (FVG far edge -2 pts, clamped 10..80); daily ATR14 x 0.10 / 0.15 / 0.20.
- **Exits:** TP 2 / 3 / 4 / 5 R, R-step trailing.
- **Holding:** intraday (flat 15:55), swing up to 2 sessions, swing up to 5 sessions (exit at 15:55 of the last session).
- **Swing costs:**
  - CFD overnight financing 5 %/yr of notional per night (x3 over weekends), for longs and shorts (conservative).
  - Futures: no financing.
- **Ranking:** min(E_train, E_valid). A choice must sit in a plateau (neighbouring stop and exit also positive in both).

## Phase D
The frozen choice runs once on the tests.

## Phase E: money management (user plan)
- $100 start; risk 1 / 2 / 3 / 5 / 10 % of equity per trade.
- **Withdrawal rule:** when equity reaches 1.5x the base, withdraw the profit (base stays). Variant: withdraw 0.5 %.
- **Deposits:** +$100 at the start of each month.
- **Horizon:** 3 years, block bootstrap of the strategy's trades. Two inputs:
  - all years 2017-2025 (conservative),
  - test years only.
- **Reports:** median and quantiles of total withdrawals per month, P(account wipe-out), Kelly fraction.
