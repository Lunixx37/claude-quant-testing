# V8: Gewinn-/Verlust-Muster, Filter und Trefferquote (Modell V7 M1, NY-VBO, max. 2 Trades/Tag)

## Datenbasis
| Datensatz | Zeitraum | Trades | Trefferquote | E pro Trade |
|---|---|---|---|---|
| Entwicklung (Mustersuche) | CFD 2017–2022 | **2.254** | 37,7 % | +0,124 R |
| Test A | CFD 2023–09/2025 | **1.042** | 38,3 % | +0,133 R |
| Test B | NQ-Futures 2023–12/2025 | **1.124** | 38,2 % | +0,137 R |

Gesamt **4.420 Trades**. Pro Bucket (Quintil) sind es 150–450 Trades. Ein Filter zählt nur, wenn er in **allen drei** Datensätzen wirkt.

## Was die Muster zeigen (`v8_scan_result.txt`)
- **Uhrzeit:** 09:30–10:00 bringt den höchsten Ertrag pro Trade (+0,18 / +0,23 / +0,23 R).
  - Ab 11 Uhr steigt die Trefferquote (14–16 Uhr: 45–47 %), aber die Gewinne werden kleiner. Der Ertrag pro Trade fällt in den Tests auf ~0.
  - Der Wiedereinstieg selbst ist in der Entwicklung gleich gut, in den Tests schwächer (+0,03 R).
- **Position in der Vortagesrange:** Die Extreme sind am besten. Q1 (Einstieg aus dem unteren Bereich) und Q5 (weit über Vortages-H/L hinaus) liefern +0,15 bis +0,20 R. Die Mitte (Q3) ist schwach (+0,02 bis +0,06 R). Ein stabiler Filter ergibt sich daraus nicht.
- **Position in der heutigen Range:** nicht konsistent.
- **Gap (Eröffnungslücke / ATR14, in Trade-Richtung):** Tage mit **kleinem Gap** (−0,4 bis +0,08 ATR) sind schwach.
  Große Gaps sind in beiden Richtungen gut.
- **Tagestrend:** Trades in Trendrichtung (Vortagesschluss über/unter SMA20) sind etwas besser (+0,15 bis +0,19 R gegenüber +0,09 bis +0,10 R).
- **Wochentag:** Freitag ist am besten (+0,22 bis +0,34 R), Mittwoch am schwächsten. Das ist wahrscheinlich Zufall und wird nicht genutzt.

## Filter nach Regel (bester Mindest-Effekt über alle 3 Datensätze)
1. Gegen den Tagestrend auslassen.
2. und 3. Kleine Gaps auslassen (Q2 + Q3).

| | Trades/Monat | Trefferquote | E | Ertrag/Monat |
|---|---|---|---|---|
| ohne Filter | 31–32 | 38 % | +0,13 R | **3,9–4,4 R** |
| alle 3 Filter | 9 | 42–44 % | +0,22 bis +0,27 R | 2,0–2,6 R |

Die Filter verbessern die Qualität pro Trade, kosten aber zu viele Trades.

## Exit-Design (bestimmt die Trefferquote am stärksten)
| Exit | Trefferquote (Entw. / Test CFD / NQ) | E (NQ) | Ø Gewinn / Ø Verlust (NQ) |
|---|---|---|---|
| Trailing Lag 1,25 (Basis) | 37,7 / 38,3 / 38,2 % | +0,137 R | 1,64 / −0,79 R |
| Lag 1,0 (Break-even bei +1R) | 35,2 / 34,9 / 34,9 % | +0,127 R | 1,67 / −0,70 R |
| **Lag 0,75 (+0,25R sichern bei +1R)** | **52,7 / 52,2 / 52,6 %** | +0,112 R | 1,07 / −0,95 R |
| Lag 0,5 | 53,3 / 52,8 / 52,7 % | +0,091 R | 1,03 / −0,95 R |
| TP 1R + Trailing | 53,1 / 53,1 / 54,0 % | +0,056 R | 0,92 / −0,96 R |
| TP 1,5R + Trailing | 43,4 / 44,0 / 43,2 % | +0,088 R | 1,28 / −0,82 R |

## Prop-Vergleich (Positionsgröße auf CFD 2017–22 gewählt, Ergebnis NQ 2023–25, deine Auszahlungsregeln)
| Variante | Trades/Mon. | Trefferquote | Auszahlungen 12 Mon. (Ø / Median) | 24 Mon. | Evals/24 Mon. | 1. Payout ≤ 2 / ≤ 3 Mon. | Median bis 1. Payout |
|---|---|---|---|---|---|---|---|
| **A** Basis | 32 | 38 % | **5.645 $** / 4.882 $ | **13.614 $** | 6,7 | 14 / 35 % | 84 Tage |
| **B** Lag 0,75 | 33 | **53 %** | 5.518 $ / 4.254 $ | 13.017 $ | 8,7 | **18** / 36 % | 84 Tage |
| **C** Gap-Filter | 19 | 40 % | 4.559 $ / 3.500 $ | 12.363 $ | **3,2** | 6 / 21 % | 104 Tage |
| **D** Gap-Filter + Lag 0,75 | 20 | **53–56 %** | 4.066 $ / 3.089 $ | 10.747 $ | 3,8 | 6 / 18 % | 112 Tage |
| alle 3 Filter | 9 | 42 % | 2.450 $ / 1.500 $ | 8.275 $ | 1,9 | 1 / 5 % | 149 Tage |

**Eval-Gebühren entscheiden zwischen A und C.** C spart ~3,5 Evals in 24 Monaten. Bei Gebühren über ~350 $ pro Eval ist C netto besser als A.

## Pine
`pine/NY_VolBreakout_Bot.pine` enthält neue Schalter:
- „Skip small-gap days“: Gap-Filter mit den Grenzen −0,405 / +0,079 ATR14.
- Trailing-Lag: 1,25 = maximale Auszahlungen, 0,75 = ~53 % Trefferquote.
