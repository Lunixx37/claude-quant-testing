# Protocol V2: Mental levels instead of GEX (written before the first V2 run)

## Change request (user)
- Replace the GEX confluence with **mental levels**: prices divisible by 50 or 100, with special
  weight on 1000s (and 500s). Treat them as possible reversal levels and pair them with
  VWAP / VWAP bands where possible.
- Same prop environment as before (eval 50k / floor 48k EOD / target 53k / DLL 1,200; funded floor 48k,
  2,000 EOD trailing from peak, DLL 1,000, 5 winning days >= $250, payout at >= 52,600, consistency 50%).
- Risk **$250 per trade**, max 2 trades per day. Goal: first payout ideally within **1-2 months**.
- Fixed-RR exits are allowed if they produce the better result.

## Data split (unchanged)
- Training 2023-02-01..2024-06-30
- Validation 2024-07-01..2024-12-31
- "Forward" 2025-01-01..2025-12-11

**Honesty note:** 2025 was already evaluated once for the V1 strategy. It is therefore **not pristine**
out-of-sample data. V2 design and parameter decisions use Training/Validation only. The frozen V2 is
run on 2025 exactly once and reported as "Forward (pseudo-OOS)".

## Definitions fixed in advance
- **Mental level strength:** 1000 > 500 > 100 > 50 (largest step that divides the price).
- **Kinds:**
  - `MV` = mental level with a VWAP-family level within the confluence tolerance (preferred when present),
  - `M` = mental level alone,
  - `V` = VWAP-family level alone (V1 behaviour).
- Manipulation, absorption, distribution, structure rule, session, the 2-trades/day limit, market
  entries and the cost model are unchanged from V1.
- **Sizing:** $250 risk per trade = floor(250 / (stop ticks x $0.50)) MNQ, e.g. 5 MNQ at 100 ticks.
  The DLL/EOD guards stay on.
- **Exits tested:** R-step trailing (V1), fixed RR targets, and hybrids. Limit fills need a 1-tick
  trade-through. Within a bar, the stop is assumed to fill before the target.

## Acceptance criteria (net of costs)
- **IS (Train+Valid):** PF >= 1.2, E >= +0.08 R, >= 150 trades, max DD <= 20 R. Validation alone must be E > 0.
- **Robustness:** key parameters at +-1 grid step keep PF > 1.05 in Training.
- **Forward 2025 (pseudo-OOS, one run):** PF >= 1.1, E > 0, >= 60 trades.
- **Prop goal (user):** P(first payout within 42 trading days from eval start) >= 50 %.
  Also reported for 21 / 63 / 252 days.
