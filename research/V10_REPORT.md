# V10: Verluste früher begrenzen? Ideales RR

**Einstiege:** V7 M1 (NY-VBO, k 0,35, Stop 0,75 × (k × Vortagesspanne), beide Richtungen, max. 2/Tag, R-Trailing mit Abstand 1,25).
**Protokoll:** PROTOCOL_V10.md, vor allen Läufen committet.
**Kosten:** CFD 1,2 Pkt. Spread + 0,25 Slippage. NQ 0,75 Pkt. Kommission + 1 Tick Slippage.

**Datenbasis (Basis-Trades):**
| Datensatz | Trades |
|---|---|
| Entwicklung: CFD 2017–22 | 2.254 |
| Test: CFD 2023–25 | 1.042 |
| Test: NQ 2023–25 | 1.124 |

Je nach Variante sind es etwas mehr oder weniger Trades, weil nach einem früheren Ausstieg ein zweiter Einstieg möglich wird.

## 1. MAE-Analyse: Wie tief laufen Gewinner ins Minus?
MAE = größter offener Verlust vor dem Ausstieg, in R.

> **Korrektur:** Der erste MAE-Lauf hatte einen Fehler: Bei Stop-Ausstiegen wurde die MAE überschrieben. Dadurch sah es so aus, als würden Gewinner kaum ins Minus laufen (Median −0,04R). Korrigiert in `v10.py`. Nur `v10_mae.txt` ist gültig. In `v10_result.txt` und `v10_cut_explained.txt` sind die betroffenen Teile markiert.

| MAE erreicht | Anteil Trades Entw. / NQ | davon noch Gewinner Entw. / NQ | Ø Endergebnis danach Entw. / NQ | E bei Cut dort (gleiche Trades) Entw. / NQ |
|---|---|---|---|---|
| ≤ −0,3R | 74 / 72 % | 27,2 / 26,1 % | −0,22 / −0,26 R | +0,000 / +0,090 |
| ≤ −0,5R | 60 / 63 % | 18,0 / 20,5 % | −0,52 / −0,43 R | +0,083 / +0,077 |
| ≤ −0,7R | 51 / 52 % | 10,0 / 11,1 % | −0,77 / −0,68 R | +0,111 / +0,114 |
| ≤ −0,9R | 44 / 45 % | 2,8 / 3,6 % | −0,99 / −0,92 R | +0,122 / +0,131 |
| **Basis (kein Cut)** | | | | **+0,124 / +0,137** |

**NQ im Detail:**
- **Gewinner:** Median-MAE −0,30R. 25 % aller Gewinner laufen tiefer als −0,59R ins Minus.
- **Verlierer:** Median-MAE −1,00R.
- **Zeit bis zur MAE:** Gewinner 4 Min., Verlierer 22 Min.
- **Haltedauer:** Gewinner 177 Min., Verlierer 32 Min.

**Fazit:**
- Ein Trade, der −0,5R erreicht, endet zwar im Mittel bei −0,5R. Schneidet man ihn dort ab, verliert man aber die 18–20 % späteren Gewinner. Diese bringen im Schnitt etwa +1,6R.
- **Es gibt keine Drawdown-Schwelle, ab der ein Cut den Erwartungswert erhöht.** Jede Schwelle liegt unter der Basis.
- Je näher die Schwelle am Stop liegt, desto kleiner der Schaden: Bei −0,9R ist er praktisch null.

## 2. Vollsimulation (inklusive geänderter Re-Entries)
| Variante | Trefferquote NQ | Ø Gewinn / Ø Verlust NQ | E Entw. / NQ | **R/Monat Entw. / Test CFD / NQ** |
|---|---|---|---|---|
| **Basis** | 38,2 % | 1,64 / −0,79 R | +0,124 / +0,137 | **3,87 / 4,19 / 4,35** |
| Cut −0,9R | 37,1 % | 1,65 / −0,74 R | +0,119 / +0,149 | 3,77 / 4,52 / 4,77 |
| Cut −0,75R | 33,8 % | 1,66 / −0,65 R | +0,112 / +0,131 | 3,60 / 4,72 / 4,25 |
| Cut −0,6R | 30,0 % | 1,69 / −0,55 R | +0,091 / +0,121 | 2,99 / 4,38 / 4,02 |
| Cut −0,5R | 26,5 % | 1,71 / −0,48 R | +0,072 / +0,099 | 2,42 / 3,52 / 3,35 |
| Cut −0,3R | 19,5 % | 1,78 / −0,32 R | +0,018 / +0,094 | 0,63 / 3,44 / 3,29 |
| Zeit-Cut 5 Min. (< 0R) | 25,7 % | 1,71 / −0,46 R | +0,066 / +0,098 | 2,28 / 3,45 / 3,36 |
| Zeit-Cut 15 Min. (< 0R) | 29,9 % | 1,74 / −0,56 R | +0,094 / +0,128 | 3,18 / 3,84 / 4,30 |
| Zeit-Cut 30 Min. (< 0R) | 31,5 % | 1,71 / −0,62 R | +0,111 / +0,116 | 3,69 / 3,95 / 3,89 |
| Zeit-Cut 60 Min. (< 0R) | 34,2 % | 1,69 / −0,68 R | +0,119 / +0,134 | 3,88 / 4,05 / 4,42 |
| Engerer Stop sm 0,6 (gleiches $-Risiko) | 36,6 % | 1,84 / −0,80 R | +0,093 / +0,169 | 3,04 / 6,11 / 5,67 |
| Engerer Stop sm 0,5 | 33,6 % | 1,98 / −0,79 R | +0,056 / +0,140 | 1,91 / 5,64 / 4,87 |
| Weiterer Stop sm 1,0 | 41,5 % | 1,36 / −0,77 R | +0,087 / +0,114 | 2,53 / 2,81 / 3,33 |

Alle 30 Varianten stehen in `v10_variants.csv`.

**Ergebnisse:**
- **Keine Variante schlägt die Basis in allen drei Datensätzen.** Das ist die Protokollregel, also wird nichts übernommen.
- **Cut −0,9R:**
  - In der Entwicklung leicht schlechter, im Test leicht besser.
  - Der NQ-Vorteil kommt fast nur aus geänderten zweiten Einstiegen am selben Tag, nicht aus dem Cut selbst (siehe `v10_cut_explained.txt`, Vollsimulation).
  - Wirkt neutral, nicht besser.
- **Zeit-Cuts:** Alle sind schlechter oder gleich. Verlierer brauchen im Median 22 Min. bis zur MAE, Gewinner nur 4 Min. Ein früher Zeit-Cut trifft aber genau die Gewinner, die erst einen Rücksetzer machen.
- **Engerer Stop sm 0,6 (gleiches $-Risiko):** 2023–25 deutlich besser (NQ 5,67 R/Monat), 2017–22 deutlich schlechter (3,04). Das ist ein **Regime-Effekt**: In den letzten Jahren war der Rücksetzer nach dem Breakout kleiner. Nicht robust genug zum Übernehmen.

## 3. Ideales RR (fester TP, kein Trailing, Stop 1R)
| TP | Trefferquote NQ | E Entw. / NQ | R/Monat Entw. / Test CFD / NQ |
|---|---|---|---|
| 0,5R | 67,9 % | −0,039 / +0,017 | −1,40 / 0,04 / 0,61 |
| 1R | 54,0 % | +0,001 / +0,055 | 0,03 / 0,92 / 1,92 |
| 1,5R | 46,5 % | +0,037 / +0,088 | 1,24 / 3,12 / 2,96 |
| 2R | 43,1 % | +0,052 / +0,142 | 1,67 / 4,27 / 4,63 |
| 3R | 38,5 % | +0,102 / +0,140 | 3,15 / 4,04 / 4,27 |
| 4R | 37,7 % | +0,118 / +0,174 | 3,50 / 5,21 / 5,15 |
| 5R | 36,6 % | +0,123 / +0,173 | 3,59 / 4,92 / 5,01 |
| kein TP (bis 16:00) | 35,9 % | +0,111 / +0,166 | 3,07 / 4,47 / 4,58 |
| **Basis-Trailing** | **38,2 %** | **+0,124 / +0,137** | **3,87 / 4,19 / 4,35** |

**Fazit:**
- Der Edge der Strategie steckt im **rechten Rand**, also in den wenigen großen Trend-Tagen.
- **TP ≤ 1R hat keinen Edge.** Die Trefferquote steigt zwar auf 54–68 %, der Erwartungswert fällt aber auf etwa null.
- **Bester fester TP: 4–5R.** Er ist fast so gut wie das Trailing in der Entwicklung und besser 2023–25.
- **Das Basis-Trailing realisiert ≈ 2,1 : 1** (Ø Gewinn 1,64R, Ø Verlust 0,79R, 38 % Treffer). Es ist über alle Zeiträume am gleichmäßigsten.
- **TP 2R** passt nur 2023–25 gut. 2017–22 halbiert es den Ertrag (Regime-Effekt).

## 4. Prop-Lebenszyklus
Sizing gewählt auf der Entwicklung, berichtet auf NQ 2023–25. Regeln wie in V7, Auszahlungsregeln wie in V8.

| Variante | Risiko $ Eval/Funded | Auszahlung 12M (Ø) | 24M (Ø) | Evals/24M | Median 1. Auszahlung | Entw. 24M |
|---|---|---|---|---|---|---|
| **Basis** | 500/250 | $5.645 | $13.614 | 6,7 | 84 T. | $10.874 |
| Cut −0,9R | 500/200 | $5.277 | $13.262 | **4,8** | 87 T. | $11.582 |
| Cut −0,75R | 500/200 | $5.680 | $13.656 | 8,1 | 78 T. | $11.866 |
| Zeit-Cut 60 Min. | 500/250 | $5.435 | $13.459 | 6,0 | 83 T. | $11.261 |
| sm 0,6 | 500/250 | $7.302 | $17.547 | 8,0 | 67 T. | $9.828 |
| TP 4R | 500/300 | $7.281 | $17.029 | 12,4 | 64 T. | $11.659 |
| TP 2R | 500/300 | $8.025 | $18.091 | 8,4 | 64 T. | $7.970 |

**Bewertung:**
- **Cut −0,9R** zahlt etwa gleich aus, verbraucht aber 28 % weniger Evals (4,8 statt 6,7 pro 24 Monate). Das ist ein kleiner, kostenseitiger Vorteil, kein Ertragsvorteil.
- **sm 0,6, TP 4R und TP 2R** zahlen 2023–25 mehr aus. Sie hängen aber vom aktuellen Regime ab:
  - sm 0,6 und TP 2R sind in der Entwicklung schlechter.
  - TP 4R verbraucht fast doppelt so viele Evals.
  - Wer bewusst auf das aktuelle Regime setzt, kann sm 0,6 im Pine-Bot einstellen (`stopMult` 0,60). Das ist nicht abgesichert.

## 5. Pine
Neuer Eingang `cutR` in `pine/NY_VolBreakout_Bot.pine`:
- Er setzt den Anfangsstop auf `cutR × R`.
- Das Trailing rechnet weiter in vollen R.
- **Standard 1,0** = unverändert. **0,9** = die eval-sparende Variante aus Abschnitt 4.
- Die Positionsgröße bleibt auf vollem R. Für gleiches $-Risiko pro Trade das Risiko entsprechend anpassen: Die Prop-Simulation nutzt $500/$200.

## Ehrlichkeitshinweise
- Die Daten 2023–25 wurden in V6–V9 schon mehrfach angesehen. Sie sind kein unberührter Test mehr.
- Die CFD-Daten haben kein echtes Volumen. Das spielt für V10 keine Rolle.
- Alle MAE-Werte basieren auf 1-Minuten-Bars. Innerhalb eines Bars ist die Reihenfolge von Hoch und Tief unbekannt. Stop-Ausstiege werden deshalb konservativ behandelt (Stop vor TP im selben Bar).

## Nachtrag: Live-Vergleich und Statistiken (`v10_live.py`, `v10_stats.py`)
- **Live (1 % Risiko/Trade, Zinseszins, echte Reihenfolge):** siehe `v10_live_result.txt`.
  - Bestes Verhältnis Ertrag/Drawdown: V7 + Gap-Filter (Ø 4,2 / 4,0 / 3,5 %/Monat, max. DD 19 / 14 / 14 %).
  - Der Gap-Filter wurde in V8 mit Blick auf alle drei Datensätze gewählt; seine Testwerte sind nicht ganz sauber.
- **Korrektur:** In der ersten Fassung von `v10_live.py` wurde Cut −0,9R nicht auf das tatsächlich riskierte $ umgerechnet (Groß-/Kleinschreibung im Namensvergleich).
  - Korrigiert: Ø 4,1 / 5,2 / 5,3 %/Monat, max. DD 26 / 23 / 18 %.
  - **Normiert auf gleiches $-Risiko pro Trade** (größere Position, weil der Stop 10 % enger ist) ist Cut −0,9R in allen drei Datensätzen besser als die Basis: R/Monat 4,19 / 5,02 / 5,21 statt 3,87 / 4,19 / 4,28, max. DD 28,7 / 25,3 / 18,9 R statt 30,2 / 25,8 / 20,6 R.
  - Das Protokoll V10 hatte Cuts bei **gleicher Positionsgröße** verglichen. Dieser Vergleich bei gleichem $-Risiko ist nachträglich, also nicht vorab registriert.
  - Im Pine-Bot gilt: Mit `cutR` 0,9 ist das Risiko 10 % kleiner als eingestellt. Für gleiches $-Risiko die Risikoeingabe durch 0,9 teilen (z. B. 278 statt 250 $).
- **Statistiken je Strategie:** `v10_stats_result.txt` (Trefferquote, Ø Gewinn/Verlust, Profit-Faktor, Serien, Drawdown, Monate, Jahre, Long/Short, Haltedauer).
