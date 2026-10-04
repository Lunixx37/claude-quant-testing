# Research Protocol (pre-registered before the first backtest)

Written and committed **before** any strategy backtest was run. Changes to this
file after the first run are listed in the "Amendments" section with reasons.

## Data
- Source: `Dataset_NQ_1min_2022_2025.csv` (NQ continuous futures, 1-minute bars, ET).
- Timestamps are **bar-close labels** (verified: `Vwap_RTH` = hlc3 VWAP starting at
  the bar labelled 09:31, so that bar is the 09:30-09:31 minute). The engine shifts
  every timestamp by -1 minute to get TradingView-style bar-open times.
- The file has exactly 1,048,576 lines, which is Excel's row limit, so it is very likely
  truncated. It ends 2025-12-11 20:52 ET.
- The `Vwap_RTH` / `Vwap_ETH` columns are not used directly. VWAPs are recomputed from
  OHLCV (hlc3, volume) so that the Pine script can reproduce them exactly.
  `Vwap_RTH` serves only as a validation check for the recomputation.
- Not in the data: QQQ GEX, order flow / bid-ask delta, QQQ prices. None of these are
  simulated. GEX can only be supplied by the user as an input in Pine; it is **not
  backtested**.

## Split (by NY trading date)
| Segment | Dates | Use |
|---|---|---|
| Warm-up | 2022-12-27 .. 2023-01-31 | indicator warm-up only, no trades counted |
| Training | 2023-02-01 .. 2024-06-30 | development / iteration |
| Validation | 2024-07-01 .. 2024-12-31 | choosing between a few candidate variants |
| Forward (OOS) | 2025-01-01 .. 2025-12-11 | **run exactly once** with the frozen final version |

The forward segment is about 31% of the trading days. The engine refuses to
evaluate it unless explicitly called with `--forward`, and that call happens only
once, after the final version is frozen.

## Execution / cost model (base case)
- 1 NQ contract, tick = 0.25 pt = $5, point = $20.
- Signals are evaluated on bar close. The market entry fills at the **next bar open
  + 1 tick slippage**.
- Stop orders are checked against the bar's high/low. They fill at the stop price
  - 1 tick slippage, or at the bar open - 1 tick if the bar gaps through the stop.
- Trailing-stop updates are computed at bar close and become active on the next bar,
  as in Pine's `strategy.exit` re-issue.
- Session-end flat: close of the bar at flat time (or the last bar of the session),
  -1 tick.
- Commission: $2.25 per side, $4.50 round turn.
- Stress cases: 2 and 3 ticks of slippage per fill.

## Acceptance criteria (net of base costs)
In-sample = Training + Validation:
1. Profit factor >= 1.20, expectancy >= +0.08 R/trade, >= 150 trades.
2. Max drawdown <= 20 R (closed-trade equity).
3. Stress at 2 ticks slippage: expectancy still > 0.
4. Robustness: the key parameters (stop, absorption threshold, band width, time
   window, trailing lag) at ±1 grid step from the chosen value keep PF > 1.05 in
   Training. No single magic value.

Forward (OOS, one run):
5. Profit factor >= 1.10 and expectancy > 0 net, >= 60 trades.
6. Max drawdown <= 25 R.

Structural (code):
7. At most 2 entries per NY date, entries only inside the NY window, flat at
   session end, market entries only, no fixed-RR take-profit, R-step trailing,
   A/B tiers logged, no lookahead (every decision uses only bars <= the current
   closed bar; levels used for the sweep test are taken from the *previous* bar).

If the forward run fails, the result is reported as a failure. The forward segment
then counts as used, and no further tuning on it will be presented as OOS.

## Amendments
(none yet)
