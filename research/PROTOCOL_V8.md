# Protocol V8: win/loss pattern scan and filters for the prop VBO model (written before any V8 run)

**Model:** V7 M1. NY VBO, k 0.35, stop 0.75 x (k x prior RTH range), both sides, R-trailing, max 2 trades/day.

**Data:**
| Use | Data | Trades |
|---|---|---|
| Discovery | CFD 2017-2022 | ~2,250 |
| Test A | CFD 2023-25 | ~1,040 |
| Test B | NQ futures 2023-25 | ~1,130 |

**Features** (all known at the signal bar close; "directional" = mirrored for shorts, so that higher = further in trade direction):
- **F-a:** position of the signal close in the **prior day's RTH range** (directional): (close - PDL) / (PDH - PDL).
- **F-b:** position in **today's range so far** (09:30..signal bar), directional.
- **F-c:** position relative to the **overnight range** (ONH/ONL), directional.
- **F-d:** time of the signal: 09:30-10:00 / 10:00-10:30 / 10:30-11:00 / 11:00-12:00 / 12:00-14:00 / 14:00-16:00.
- **F-e:** trade number of the day (first vs re-entry).
- **F-f:** opening gap / ATR14, directional.
- **F-g:** volatility regime: prior range / ATR14.
- **F-h:** daily trend: prior close vs SMA20, directional.
- **F-i:** weekday.
- **F-j:** breakout bar range / prior range.

Continuous features are split into quintiles, with the bin edges taken from the discovery data.

**Filter rule:**
- A bucket is **excluded** only if all of the following hold:
  1. it has >= 100 trades in discovery;
  2. excluding it raises **both** win rate and E in discovery;
  3. the same holds in **both** tests.
- At most 3 filters, combined only if each passes on its own.
- The combined filter is then evaluated with the prop lifecycle simulator (sizing grid re-chosen on discovery).

**Note:** Trades are filtered after the fact. A skipped trade could in reality free the slot for a later re-entry; this effect is ignored and stated.

## Amendment 1 (after the scan, before the exit test)
The filters raise the win rate only a little and cut the trades by ~70 %, so R/month drops. Because the
win rate is mainly set by the exit design, an **exit variant test** is added. It uses the same model, decided
on discovery and checked on both tests:
- trailing lag 1.25 (base) / 1.0 / 0.75 / 0.5, so the stop moves to break-even or locks profit at +1R;
- additionally a TP of 1R / 1.5R with trailing lag 1.25.

The prop lifecycle compares: no filter / gap filter only / all 3 filters / best exit variant.
