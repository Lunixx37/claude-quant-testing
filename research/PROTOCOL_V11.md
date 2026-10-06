# Protocol V11: high win rate (>= 80 %) for building up a live account (written before any V11 run)

**Goal:** a mechanical setup with a win rate >= 80 % (after costs) and a positive expectancy, so that a high risk per trade is possible during the build-up phase.
Later the account switches to the VBO bot at 1-2 % risk.

## Search space: all confluences/families from V3-V9
Every family supplies entries with a base stop `sp` (in points). Intraday positions are flat at 16:00; RSI2 is a swing trade, as in V6.

| Family | Entry variants | Base stop sp |
|---|---|---|
| VBO (F7b) | k 0.2 / 0.3 / 0.35 / 0.4 / 0.5 x filter none / trend / lowvol x both / long (1/day) | k x prior range |
| ORB (F1) | 5 / 15 / 30 min x stop opp / mid x filter none / narrow / trend | as in V6 |
| Gap (F3) | k 0.1 / 0.2 / 0.3 x fade / cont x stop 0.5 / 1.0 x gap | as in V6 |
| PDH/PDL breakout (F4) | stop 0.1 / 0.2 ATR x filter none / trend | as in V6 |
| News range 8:30 (F8) | break / fade | range |
| Intraday momentum (F2) | open / prior close x 15:00 / 15:30 x threshold 0 / 0.25 / 0.5 % | 0.5 % of price |
| RSI2 mean reversion (F6) | threshold 5 / 10 x long / both | 3 ATR |
| ICT/level setups (F10) | S1 VWAP18, S2 VWAP bands, S3 Mental, S4 FVG, S5 FVG+RB, S6 FVG+VWAP, S7 Sweep+MSS, S8 OB, S9 Silver Bullet, S10 Absorption, S11 Score>=2 x filter none / trend / with930 / lowvol / body60 (max 2/day) | 40 pts |

## Exit grid for high win rates
- Stop = m x sp, with m in {1, 2, 3}.
- Take profit = rho x stop, with rho in {0.10, 0.15, 0.20, 0.25, 0.33, 0.50}.
- Exit at 16:00 (intraday) or at the family deadline if neither stop nor TP is hit.
- RSI2 additionally keeps its native exits (close > SMA5 / 5 days) with stop 3 ATR.

## Win, costs, metrics
- **Costs:** CFD 1.2 pts spread + 0.25 slippage per market fill (TP = limit, no slippage). NQ/MNQ 0.75 pts commission + slippage.
- **Win** = net R > 0 after costs.
- **Metrics:** win rate, avg win, avg loss, E (R), trades/month, longest losing streak.
- **Growth metric:** Kelly fraction f* = argmax mean log(1 + f R), f in [0, 1].
  - Growth per month at f* (G*) and at f*/2 (G½).

## Data
- **Discovery (selection only):** CFD 2017-2022.
- **One-time tests:** CFD 2023-09/2025 and NQ futures 2023-2025.
  - These periods were already seen in V6-V10 for other configurations, not for the ones in this grid.

## Selection (discovery only)
1. Win rate >= 80 %.
2. n >= 300 (>= ~1 trade/week).
3. E > 0, and >= 4 of 6 years with E > 0.
4. **Plateau:** both neighbouring rho values (same entry, same m) have E > 0. For rho at the edge of the grid, the single neighbour.
5. **Ranking:** by G½ (growth per month at half Kelly). Top 5, at most one per family.
- **Pass:** a finalist passes if, in **both** tests, win rate >= 80 % and E > 0. It counts as "near pass" if the win rate is >= 75 %.

## Build-up simulation
- For each finalist and, as a reference, the VBO live bot (V7 + gap filter):
  - Monthly block bootstrap of the NQ test trades, 2,000 paths x 12 months.
  - Risk 2 / 5 / 10 / 20 % and f*/2.
- **Reported:**
  - median account after 6 / 12 months;
  - P(account doubled within 6 months);
  - P(drawdown >= 50 %);
  - P(below start after 12 months).

If nothing passes, this is reported as such: no relaxing of the criteria after looking at the tests.
