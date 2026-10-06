# V11: Hohe Trefferquote (≥ 80 %) für den Kontoaufbau

**Protokoll:** PROTOCOL_V11.md, vor allen Läufen committet.
**Code:** `v11.py`, `v11_eval.py`, `v11_buildup.py`
**Ergebnisse:** `v11_eval_result.txt`, `v11_buildup_result.txt`

## Suchraum
- **Einstiege:** 137 Varianten aus allen bisherigen Familien:
  - VBO, ORB, Gap Fade/Fortsetzung, PDH/PDL, News-Range 8:30, Intraday-Momentum, RSI2;
  - ICT/Level-Setups: VWAP18, VWAP-Bänder, Mental Levels, FVG, FVG+RB, FVG+VWAP, Sweep+MSS, OB, Silver Bullet, Absorption, Score ≥ 2;
  - jeweils mit Filtern.
- **Ausstiege:** 18 Kombinationen für hohe Trefferquoten: Stop 1/2/3 × Basis-Stop, TP 0,10–0,50 × Stop.
  - RSI2 zusätzlich mit seinen eigenen Ausstiegen.
- **Insgesamt 2.474 Konfigurationen.** Kosten: CFD 1,2 Pkt. Spread + Slippage, NQ MNQ-Kosten.
- **Gewinn** = Ergebnis nach Kosten > 0.

## Ergebnis Entwicklung (CFD 2017–22)
| Schritt | Anzahl |
|---|---|
| Trefferquote ≥ 80 % | 608 |
| … und E > 0 | **58** |
| … und ≥ 300 Trades | 43 |
| … und ≥ 4 von 6 Jahren positiv | 21 |
| … und Plateau (Nachbar-Ziele auch positiv) | **10** (nur VBO Long und ICT Order Block) |

**Warum so wenige:**
- Mit kleinem Ziel steigt die Trefferquote automatisch, auch ohne Edge. Der Erwartungswert aber nicht.
- Im Mittel über alle Einstiege liegt E bei kleinem Ziel zwischen −0,02 und −0,07 R.
- Die Kosten (Spread etwa 1,2 Pkt.) fressen bei einem Ziel von 5–15 Punkten einen großen Teil jedes Gewinns.

## Finalisten und einmaliger Test
| Setup | Datensatz | Trades (pro Monat) | Trefferquote | Ø Gewinn / Ø Verlust | E | Ergebnis |
|---|---|---|---|---|---|---|
| **VBO Long, k 0,5; Stop 0,5 × Vortagesspanne; TP 0,2 × Stop** | Entw. CFD | 568 (7,9) | 83,8 % | +0,16 / −0,71 R | +0,021 R | |
| | Test CFD 23–25 | 271 (8,2) | 80,1 % | +0,18 / −0,69 R | +0,008 R | |
| | Test NQ 23–25 | 285 (8,1) | 80,4 % | +0,19 / −0,65 R | +0,024 R (t = 1,05) | **bestanden** |
| ICT Order Block mit Trend; Stop 120 Pkt.; TP 12 Pkt. | Entw. CFD | 869 (12,1) | 85,8 % | +0,09 / −0,46 R | +0,011 R | |
| | Test CFD 23–25 | 396 | 87,1 % | +0,09 / −0,92 R | −0,040 R | |
| | Test NQ 23–25 | 422 | 86,3 % | +0,09 / −0,87 R | −0,038 R | **nicht bestanden** |

**Bewertung des VBO-Long-Setups:**
- Es besteht die Kriterien formal.
- Die Edge ist aber sehr dünn (+0,01 bis +0,02 R pro Trade) und **statistisch nicht gesichert** (t ≈ 1).
- Ein Verlust kostet etwa 4 Gewinne.

## Kontoaufbau: hohe Trefferquote mit hohem Risiko vs. VBO mit kleinem Risiko
2.000 Pfade über 12 Monate, NQ 2023–25 (Monats-Bootstrap). Kontostand relativ zum Start.

| Strategie | Risiko/Trade | Median nach 12 Mon. | 10-%-Quantil | P(Verdopplung in 6 Mon.) | P(Drawdown ≥ 50 %) | P(unter Start nach 12 Mon.) |
|---|---|---|---|---|---|---|
| Hohe Trefferquote (80 %) | 5 % | 1,10× | 0,87× | 0 % | 0 % | 29 % |
| Hohe Trefferquote (80 %) | 10 % | 1,20× | 0,73× | 0,6 % | 5 % | 31 % |
| Hohe Trefferquote (80 %) | 20 % | 1,14× | 0,44× | 19 % | 58 % | 43 % |
| **VBO-Live (Gap-Filter)** | **2 %** | **2,05×** | **1,22×** | 19 % | **0,1 %** | **4 %** |
| VBO-Live (Gap-Filter) | 5 % | 4,11× | 1,14× | 63 % | 45 % | 8 % |

**Fazit:**
- Eine hohe Trefferquote erlaubt **nicht** automatisch ein hohes Risiko.
- Das sinnvolle Risiko (Kelly) hängt am **Erwartungswert im Verhältnis zur Schwankung**, nicht an der Trefferquote:
  - VBO Long mit 80 % Trefferquote: Kelly 14 %.
  - VBO-Live mit 40 % Trefferquote: Kelly 11 %.
  - Das ist fast dasselbe.
- Weil die Edge der 80-%-Variante so klein ist, wächst das Konto selbst bei 10–20 % Risiko langsamer als mit dem VBO-Bot bei 2 %. Gleichzeitig ist das Risiko höher, unter dem Startkapital zu landen.
- **Empfehlung:**
  - Konto mit dem VBO-Live-Bot (Gap-Filter) bei **2–3 %** aufbauen.
  - Danach auf 1–2 % reduzieren.
  - Mehr als 3 % nur, wenn ein Drawdown von 50 % verkraftbar ist.

## Ehrlichkeitshinweise
- Die VBO-Live-Werte stammen aus NQ 2023–25, einem guten Breakout-Umfeld. Den Gap-Filter habe ich in V8 mit Blick auf diese Daten gewählt. Realistisch ist etwa die Hälfte des Medians.
- Bei der 80-%-Variante sind die Testergebnisse mit E ≈ +0,01–0,02 R nicht von null unterscheidbar. Ein halber Punkt mehr Spread macht sie negativ.
