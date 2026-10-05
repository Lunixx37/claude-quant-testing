# Protocol V4: confluence-combination scalper (no VWAP, no order flow)

Written and committed before any V4 run.

## Goal (user)
A mechanical bot with a high win rate and small targets (0.1-0.5 R) for a $100 live account, to be
scaled up later. It should become profitable reasonably fast, not after a year.

## Building blocks
Definitions are unchanged from ict.py and are causal:
- FVG, RB (rejection block), OB (order block), MSS (event), MSSr (MSS within the last 30 bars)
- LS (liquidity sweep within the last 30 bars)
- MENT (mental level 100/500/1000)

**Excluded:** VWAP18, VWAP bands, absorption, (tick-)volume.

**Triggers:** FVG, RB, OB, MENT, MSS. A combination needs at least one trigger.

## Combinations
- Every subset of {FVG, RB, OB, MENT, MSS, LS, MSSr} that contains at least one trigger: **124 combos**.
- A combo fires when all its blocks are present at the signal bar (AND).
- **Direction:** the rejection direction of the zone/level (long at bullish zones/levels, short at bearish).
- **Entry:** market order at the next bar's open, 09:30-11:00 NY, max 2 trades/day, one position at a time.
- No fallback trades (pure mechanical bot).

## Exits
- **Stops:** fixed 15 / 25 / 40 pts.
- **Targets (limit, 1-tick trade-through):** 0.1 / 0.2 / 0.3 / 0.5 R.
- **Ordering:** if the stop and the target fall in the same bar, the stop counts as filled first (conservative).
- **EOD:** flat at 15:55.

124 x 3 x 4 = **1,488 configurations**, all reported.

## Costs (two models)
- **MNQ:** 1 tick slippage on market/stop fills, none on limit targets; $1.50 RT per contract = 0.75 pt.
- **CFD (NAS100, $100 account):** spread 1.2 pts per round trip, plus 0.25 pt slippage on stop and market exits.

## Splits (CFD data)
| Segment | Period | Use |
|---|---|---|
| Train | 2017-01..2020-06 | development |
| Validation | 2020-07..2021-12 | checks the train results |
| Test 2022 | 2022 (CFD) | one run of the frozen choice; used once before, for a single V3 config only |
| Test 2023-25 | NQ and CFD | seen before (pseudo-OOS) |

## Selection
- **Requirements:** positive E after CFD costs in Train **and** Validation, >= 2 trades/week.
- **Ranking:** by min(E_train, E_valid).
- **Robustness:** the neighbouring stop/target values must be positive too.
- The top choice is frozen and run once on the tests.

## Account simulation ($100 CFD account)
- Fixed-fractional risk of 1 % and 2 % of equity per trade, compounded.
- Reports: time to +20 %, max DD %, final equity.

## Stop rule
After evaluating the grid and the single test run, the result is reported. If nothing passes, it is
reported as "not found".
