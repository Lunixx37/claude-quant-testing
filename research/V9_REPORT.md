# V9: POI-Ziele und aggressiveres Trailing – maximaler Ertrag

**Einstiege:** Modell V7 M1 (NY-VBO, k 0,35, Stop 0,75×, beide Richtungen, max. 2/Tag).

**Datenbasis:**
| Datensatz | Trades |
|---|---|
| Entwicklung: CFD 2017–22 | ~2.250–2.600 (je Variante) |
| Test: CFD 2023–25 | ~1.050 |
| Test: NQ 2023–25 | ~1.130–1.230 |

176 Varianten = 16 Ziel-Varianten × 11 Trailing-Varianten.

## 1. Trailing (ohne Ziel)
| Trailing | Trefferquote Entw. / NQ | Ø Gewinn Entw. / NQ | Ø Verlust Entw. | E Entw. / NQ | **Ertrag/Monat Entw. / Test CFD / NQ** |
|---|---|---|---|---|---|
| **Basis: je 1R, Abstand 1,25** | 37,7 / 38,2 % | 1,70 / 1,64 R | −0,83 R | +0,124 / +0,137 | **3,87 / 4,19 / 4,35 R** |
| kein Trailing (bis Schluss) | 36,4 / 35,9 % | 2,05 / 2,18 R | −1,00 R | +0,111 / +0,166 | 3,07 / 4,47 / 4,58 R |
| 0,75R / Abstand 1,0 | 40,4 / 39,7 % | 1,37 / 1,43 R | −0,79 R | +0,080 / +0,119 | 2,62 / 4,24 / 3,95 R |
| 0,75R / Abstand 0,5 | **58,4 / 58,7 %** | 0,76 / 0,80 R | −0,96 R | +0,042 / +0,075 | 1,45 / 2,87 / 2,61 R |
| 0,5R / Abstand 0,75 | 44,2 / 44,7 % | 0,97 / 1,06 R | −0,72 R | +0,028 / +0,093 | 0,96 / 3,26 / 3,22 R |
| 0,5R / Abstand 1,0 | 37,3 / 36,8 % | 1,33 / 1,45 R | −0,71 R | +0,052 / +0,124 | 1,71 / 3,61 / 4,16 R |
| 0,25R / Abstand 1,0 | 39,4 / 38,9 % | 1,19 / 1,28 R | −0,68 R | +0,057 / +0,108 | 1,93 / 3,57 / 3,70 R |
| 0,25R / Abstand 0,5 | 39,4 / 37,5 % | 0,71 / 0,80 R | −0,49 R | −0,021 / +0,014 | −0,75 / 1,04 / 0,51 R |

**Ergebnis:** Aggressiveres Nachziehen erhöht die Trefferquote nur in einzelnen Kombinationen (bis 58 %). Es senkt aber immer den Ertrag pro Monat, weil die großen Gewinner abgeschnitten werden.
**Das beste Verhältnis von Trefferquote und Ø Gewinn bleibt die Basis** (38 % / 1,7R).

## 2. POI-Ziele (nächster POI in Trade-Richtung, Mindestabstand 0,5 / 1 / 1,5R)
Mittlerer Ertrag pro Monat in der Entwicklung über alle Trailing-Varianten:

| Zielmenge | Ertrag/Monat |
|---|---|
| keine | 1,58 R |
| POC | 1,61 R |
| runde 500er | 1,48 R |
| Gaps (NDOG/NWOG) | 1,12 R |
| Liquidität (PDH/PDL, ONH/ONL, Asia/London, Vorwoche) | 0,79 R |
| alle zusammen | 0,62 R |

**Liquiditäts- und Gap-Ziele kappen die Gewinner zu früh.** Nur der **Volumen-POC des Vortags ab ≥ 1,5R** liegt gleichauf bzw. leicht besser
(Entw. 3,97 statt 3,87 R/Monat, NQ 4,59 statt 4,35).
Das Plateau-Kriterium besteht er **nicht**: Mit Mindestabstand 1,0R liegt er in der Entwicklung unter der Basis. Er ist daher **optional**.

## 3. Prop-Vergleich (deine Regeln, Positionsgröße auf Entwicklung gewählt, NQ 2023–25)
| Variante | Trefferquote | Ø Gewinn | E | Auszahlungen 12 Mon. (Ø/Median) | 24 Mon. | Evals/24 Mon. | Median 1. Payout |
|---|---|---|---|---|---|---|---|
| Basis | 38,2 % | 1,64 R | +0,137 | 5.645 $ / 4.882 $ | 13.614 $ | 6,7 | 84 Tage |
| **+ POC-Ziel ≥ 1,5R** | 38,4 % | 1,64 R | +0,144 | **6.194 $ / 5.294 $** | **14.904 $** | 6,6 | 79 Tage |
| POC-Ziel ≥ 1R, kein Trailing | 37,1 % | 2,09 R | +0,170 | 4.391 $ / 3.500 $ | 10.871 $ | 11,1 | 91 Tage |
| kein Ziel, kein Trailing | 35,9 % | 2,18 R | +0,166 | 4.180 $ / 3.414 $ | 10.345 $ | 11,7 | 92 Tage |
| hohe Trefferquote (0,75R / 0,5) | 58,7 % | 0,80 R | +0,075 | 4.289 $ / 3.100 $ | 10.161 $ | 6,9 | 102 Tage |

**Hinweis:** Ohne Trailing ist der Erwartungswert pro Trade am höchsten, aber die Schwankungen sprengen fast doppelt so viele Accounts.
Für Prop zählt deshalb nicht der höchste Erwartungswert, sondern die Kombination aus Ertrag und kontrolliertem Drawdown.

## Pine
`pine/NY_VolBreakout_Bot.pine`: neuer optionaler Schalter „Take profit at prior RTH volume POC“ (Mindestabstand 1,5R, max. 8R), Standard aus.
Kleine Abweichungen zur Simulation:
- Die Bin-Breite wird aus der 9:30-Eröffnung statt aus dem Sessionschluss berechnet.
- Der Zielabstand wird mit dem Signal-Close statt mit dem Fill berechnet.
