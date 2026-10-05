# Protocol V3: new data, daily-reset VWAP, ICT confluences, high-frequency search

Written and committed **before** any V3 run.

## Data
- **CFD (new):** `1m_data_part1/2.zip`, NASDAQ-100 CFD from MetaTrader, 2016-11-15..2025-10-01.
  - Server time is Europe/Helsinki and is converted to New York time. Timestamps are bar open times.
  - There is no real volume, so `TickVolume` is used as volume.
  - Prices are cash-index prices, which differ from NQ futures by the basis. This matters only for absolute levels (mental levels).
- **NQ futures (old):** `Dataset_NQ_1min_2022_2025.csv`, 2022-12-26..2025-12-11.

## Splits
| Segment | Data | Status |
|---|---|---|
| Train | CFD 2017-01-01..2020-06-30 | development |
| Validation | CFD 2020-07-01..2021-12-31 | choice among a few candidates |
| Test A | CFD 2022-01-01..2022-12-31 | **pristine**, never used before; run once with the frozen V3 choice |
| Test B | NQ + CFD 2023..2025 | seen by V1/V2 (pseudo-OOS), reported separately |

V1/V2 frozen OOS: V1_FINAL and V2_FINAL are run **unchanged** on CFD 2017-01..2022-12. Everything
before 2023 is new to them. An overlap check (CFD vs NQ, 2023-02..2025-09) comes first.

## Part 2: daily-reset VWAP
The VWAP resets at the 18:00 NY reopen after the one-hour pause (= `vwapE`). Variants inside the V1 logic:
1. VWAP18 only
2. VWAP18 + 1/2 sigma bands
3. RTH VWAP only
4. V1 level set

Developed on Train, compared on Validation.

## Parts 3/4: high-frequency search (ICT + levels)
All building blocks are computed causally on 1-minute bars.

**Building blocks:**
- **LS** (liquidity sweep): trades beyond PDH/PDL, ONH/ONL, Asia H/L (20:00-24:00) or London H/L (02:00-05:00) and closes back inside.
- **MSS:** close beyond the latest confirmed swing (pivot 3/3) against the prior move.
- **FVG:** 3-bar gap with a displacement middle bar (range >= 1.5x the average of the last 20 bars). Valid for 60 bars, until a close beyond the far edge.
- **RB** (rejection block): confirmed swing pivot whose wick is >= 50 % of its range; zone = wick.
- **OB:** last opposite candle (within 5 bars) before an FVG displacement; zone = that candle's range.
- **VWAP:** VWAP18 or its 1/2 sigma bands within the touch tolerance.
- **MENT:** mental level 100/500/1000 within the touch tolerance.
- **ABS:** V1 absorption proxy.

**Entry:** a bar that trades into a zone/level and closes back beyond its midpoint with a body in the
trade direction (rejection), or an MSS close after an LS. Market order at the next open, no limit entries.

**Setups (fixed list):**

| # | Setup | Required confluences |
|---|---|---|
| S1 | VWAP18 rejection | VWAP (VWAP18 only) |
| S2 | VWAP band rejection | VWAP incl. bands |
| S3 | Mental rejection | MENT |
| S4 | FVG retrace | FVG |
| S5 | FVG + RB | FVG and RB |
| S6 | FVG + VWAP | FVG and VWAP |
| S7 | ICT model | LS then MSS (entry on the MSS close or the FVG retrace after it) |
| S8 | OB + FVG | OB and FVG |
| S9 | Silver bullet | FVG + LS, 10:00-11:00 only |
| S10 | V1 absorption | ABS |
| S11 | Confluence score | any block; score >= 2 first, see fallback |

**Frequency rule (user):** at least 4 trades per week, max 2 per day, entries 09:30-11:00 NY.
- **Fallback:** if no trade by 10:30, the first signal with score >= 1 is taken.
- **Forced trade:** if still no trade at 10:59, a market trade in the direction of the 09:30-10:59 move.

Fallback and forced trades are logged separately.

**Stops:** structural (setup extreme +- 2 pts, clamped to 5..40 pts, skipped if > 40) or fixed 25 pts.

**Exits** (fixed RR vs trailing tracked separately):
- TP 1.5R, TP 2R, TP 2.5R, TP 3R
- R-step trailing (lag 1.25)
- TP 3R + trailing

EOD flat at 15:55.

**Grid:** 11 setups x 2 stops x 6 exits = 132 configurations, all reported (multiple-testing transparency).

**Costs:** traded as MNQ.
- 1 tick (0.25 pt) slippage on market and stop fills, none on limit TPs (TPs need a 1-tick trade-through).
- $1.50 round turn per MNQ.
- Results are in net R.

## User target
Win rate > 50 % **and** average winner 2-3 R, with >= 4 trades/week.

A configuration counts only if it meets this on Train **and** Validation **and** on Test A in its single run.

## Account views
- **Live:** $50k account, fixed $250 risk per trade (also 1 % variant). Reports net P&L, max DD,
  worst month and share of positive months.
- **Prop:** user rules as in PROP_REPORT.md, $250 risk per trade. Reports P(payout) <= 1/2/3/12 months.

## Stop rule
The search ends when the fixed grid is evaluated. If nothing meets the target, the result is
reported as "not found" together with the WR/RR frontier. There is no open-ended tweaking until
something passes by chance.
