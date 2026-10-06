# Protocol V9: POI targets and aggressive trailing for max profit (written before any V9 run)

**Entries:** V7 M1 (NY VBO, k 0.35, stop 0.75 x (k x prior RTH range), both sides, max 2/day).

**Objective:** maximum profit, measured as R/month (= E x trades/month) and as prop payouts.

## POIs (all known before the entry; nearest POI in trade direction becomes the TP)
| Set | Levels |
|---|---|
| liq | PDH/PDL (prior RTH), ONH/ONL (18:00-09:29), Asia H/L (18:00-02:59), London H/L (03:00-09:29), prior-week H/L |
| gap | NDOG edges (prior session close vs 18:00 open), NWOG edges (last close of the prior week vs first open of the week) |
| poc | prior RTH session volume POC (volume by price, bins of 0.02 % of price; CFD = tick volume, NQ = real volume) |
| round | multiples of 500 |
| all | union of the above |

- **TP:** the nearest POI with distance >= minR x stop (minR = 0.5 / 1.0 / 1.5). Ignored if farther than 8R.
- No POI found: no TP; the trailing stop and the EOD exit apply.

## Trailing variants
- **Step-trailing:** m = floor(MFE / (s x R)) x s; stop = entry + (m - lag) x R, never loosened.
  - s = 0.25 / 0.5 / 0.75, lag = 0.5 / 0.75 / 1.0.
- **Base:** s = 1, lag = 1.25. Also tested: no trailing (TP or EOD only).

## Data / selection
- **Selection:** CFD 2017-22 only, by R/month. A choice must sit in a plateau (neighbouring s / lag / minR also above base).
- **Tests:** CFD 2023-25 and NQ futures 2023-25.
- **Prop:** lifecycle simulator (PROTOCOL_V7 rules), sizing grid chosen on dev, reported on NQ. Top 3 vs base.
