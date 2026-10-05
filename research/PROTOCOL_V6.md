# Protocol V6: broad strategy search, evaluated honestly by walk-forward selection

Written before any V6 run.

## Why walk-forward
There is no untouched data left: 2022-25 has been used as test data several times. A broad search over
many configurations would always produce an in-sample "winner".

The honest estimate is therefore a **walk-forward of the whole search procedure**:
- For each year Y = 2019..2025, the configuration(s) to trade in Y are chosen using only trades from 2017..Y-1.
- The stitched results of years Y are out-of-sample for the selection process, however many configurations are searched.

Data: CFD 2017-01..2025-09 (one consistent series). NQ futures 2023-25 is used as a cross-check.

## Universe (all configurations are simulated over 2017-2025 once; selection happens only inside the walk-forward)

**F1 Opening range breakout**
- OR of 5 / 15 / 30 min from 09:30.
- Entry: first 1-min close beyond the OR until 12:00.
- Stop: opposite side or OR mid.
- Target: 1 / 2 / 3 R or EOD.
- Filter: none / OR narrower than its 20-day median / prior-day trend.

**F2 Intraday momentum (Gao et al.)**
- Signal: return 09:30-10:00, or prior close -> 10:00, with |ret| > 0 / 0.25 % / 0.5 %.
- Entry at 15:00 or 15:30 in that direction, exit at 15:59.
- Stop: 0.5 % (for sizing).

**F3 Gap fade / continuation**
- Opening gap vs prior RTH close > 0.1 / 0.2 / 0.3 x ATR14.
- Fade towards prior close (full fill / half fill), or continuation.
- Stop: 0.5 / 1.0 x gap beyond the open. EOD exit.

**F4 Prior-day high/low breakout**
- 09:30-12:00 close beyond PDH/PDL.
- Stop: 0.1 / 0.2 x ATR14.
- Target: 1 / 2 / 3 R or EOD.
- Optional daily-trend filter.

**F5 Daily trend following (swing)**
- Donchian 20 / 55-day breakout, exit on opposite 10 / 20-day channel.
- Long-only or both. Initial stop 2 x ATR14.
- CFD financing 5 %/yr per night.

**F6 Daily mean reversion (Connors RSI2)**
- Long when RSI2 < 5 / 10 above SMA200 (short mirrored below SMA200 if "both").
- Exit at close > SMA5 or after 5 days. Stop 3 x ATR14.

**F7 Volatility breakout (Williams)**
- Stop entry at open +/- k x prior day range (k = 0.3 / 0.5 / 0.7).
- Exit EOD. Stop at the opposite trigger or k x range.

**F8 "News range" proxy**
- High/low of 08:30-08:35 (the economic-release minute; no calendar data).
- After 09:30: breakout or fade. Target 1 / 2 / 3 R.

**F9 Turn of month**
- Long from the close of the 2nd-to-last trading day to the close of the 3rd trading day.

**F10 Earlier setups (S1-S11: VWAP, mental, FVG, RB, OB, MSS, sweeps, absorption) with the V5 refinements**
- Stops: 25 / 40 / 60 pts.
- Exits: TP 2R / 3R / trailing.
- Hold: intraday / 2 sessions.
- Filters: none / daily trend SMA20 / with 09:30 move / low-vol regime / body >= 60 %.

**Not testable:** delta flips (no order-flow data), true news calendar.

## Costs
- **CFD:** 1.2 pt spread per round trip, 0.25 pt slippage on market/stop fills, financing 5 %/yr of notional per night held (x3 at weekends).
- **NQ futures (cross-check):** 0.75 pt commission per round trip plus slippage.

## Walk-forward selection rule (fixed now)
- **Score at the start of year Y:** t-statistic of the mean net R over 2017..Y-1.
  - Requires >= 100 trades and >= 1 trade/week on average.
  - The last 12 months before Y must also be positive.
- **Portfolios traded in Y:**
  - Top-1: the highest score.
  - Top-5: the five highest scores, at most 2 per family, each at 1/5 risk.

## Reported for the walk-forward results
- **Trade statistics:** win rate, expectancy (R), average RR (avg win / avg loss), trades/month.
- **Live account:** average return/month at Kelly/2 risk; max drawdown.
- **Prop (user rules):** P(payout <= 1 / 2 / 3 / 12 months), median days to first payout; risk per trade from a fixed grid, chosen inside the walk-forward too.

## Stop rule
The search continues with new families as long as there are untested, well-defined ideas. A result is
called "working" only if its walk-forward OOS expectancy is clearly > 0 (t >= 2) **and** positive in most OOS years.
