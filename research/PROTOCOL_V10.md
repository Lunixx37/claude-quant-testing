# Protocol V10: early loss cutting and the ideal RR (written before any V10 run)

**Entries:** V7 M1 (NY VBO, k 0.35, stop sp = 0.75 x (k x prior range), both sides, max 2/day). R = sp unless stated otherwise.

1. **MAE analysis (base trades):**
   - P(final win | MAE reached -x R) and mean final R for x = 0.1..0.9.
   - Time from entry to MAE, separately for winners and losers.
2. **Price cut, same position size:** initial stop at c x R, c in {0.3, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0}. The trailing logic stays in original R units.
3. **Time cut, same size:** after T in {5, 10, 15, 30, 60} min, exit at market if the open P&L is < 0 R (variant: < +0.25 R).
4. **Tighter stop with re-sizing:** sm in {0.4, 0.5, 0.6, 0.75, 1.0}, base trailing. R = new stop (constant $ risk).
5. **Ideal RR:** fixed TP in {0.5, 0.75, 1, 1.5, 2, 2.5, 3, 4, 5} R without trailing, stop 1R, EOD exit, versus base trailing.

**Metrics:**
- win rate, avg win, avg loss, E (in original R), R/month
- for (4), R/month in units of the constant $ risk

**Selection:**
- A change counts only if it beats the base R/month in discovery (CFD 2017-22) **and** in both tests (CFD 2023-25, NQ 2023-25).
- Neighbouring values must not flip sign.
- **Prop:** lifecycle simulator for the base and the best passing variants (sizing chosen on discovery, reported on NQ).
