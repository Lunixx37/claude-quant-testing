# V4: alle Confluence-Kombinationen ohne VWAP/Orderflow (Ziel: Bot für ein 100-$-Konto)

## Kurzfassung
- **Getestet:** 124 Kombinationen aus FVG, Rejection Block, Order Block, Market Structure Shift, Liquidity
  Sweep und Mental Levels, jeweils × 3 Stops × 9 Exits = **3.348 Konfigurationen**. Kosten: CFD-Spread 1,2 Punkte
  bzw. MNQ-Kommission und Slippage.
- **Kleine Ziele (0,1–0,5R)** bringen hohe Trefferquoten (65–88 %), sind nach Kosten aber im Mittel
  **negativ**. Das ist mathematisch zu erwarten: Ohne Edge liegt die Trefferquote bei kleinem Ziel genau an der
  Gewinnschwelle, und die Kosten machen das Ergebnis negativ.
- **Über das gesamte Grid gibt es keine verlässliche Rangfolge:** Die Korrelation von E zwischen Training und
  Validierung beträgt 0,02. 6,7 % der Konfigurationen sind in beiden Zeiträumen positiv, bei reinem Zufall wären 5,1 % zu erwarten.
- **Laut Protokoll hat keine Konfiguration bestanden.** Kein Kandidat hatte durchgehend positive Nachbarwerte.
- **Einziges konsistentes Muster:** FVG-Retest (Fortsetzung nach Impuls) mit **weitem Stop (40–60 Punkte)
  und fernem Ziel (2–4R oder Trailing)**. Es ist in 6–7 von 9 Jahren positiv und liefert +0,02 bis +0,07 R pro Trade nach Kosten.
  Long und Short sind beide positiv.

## Bester Kandidat: FVG-Retest, Stop 40 Punkte, TP 3R (nicht offiziell bestanden)
| Zeitraum | Trades/Woche | Trefferquote | E nach Kosten |
|---|---|---|---|
| Training 2017–06/2020 (CFD) | 5,6 | 42,7 % | +0,018 R |
| Validierung 07/2020–2021 (CFD) | 7,7 | 32,2 % | +0,014 R |
| **Test 2022 (CFD)** | 8,4 | 31,5 % | **+0,175 R** |
| **Test 2023–25 (NQ, echte Futures)** | 7,7 | 29,8 % | **+0,071 R** |
| Test 2023–25 (CFD) | 7,8 | 30,4 % | +0,071 R |

**Statistische Einordnung:** Auf den Testjahren (2022 CFD + 2023–25 NQ) liegt der Erwartungswert bei ~+0,10 R mit t ≈ 2.
Der Kandidat wurde aber aus 3.348 Konfigurationen ausgewählt. Das spricht für eine **kleine, mäßig belegte Edge** und nicht für eine bestätigte Strategie.

**Jahre (E nach Kosten, Stop 40, TP 3R):**

| 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|
| −0,02 | +0,01 | +0,05 | −0,03 | +0,06 | +0,18 | +0,02 | +0,14 | +0,05 |

Vollständige Nachbarschaft (Stops 25/40/60 × TP 1/2/3/4R/Trailing) in `v4_fvg_robustness.txt`.

## 100-$-CFD-Konto (Bootstrap der Testtrades 2022–2025, 1 Jahr)
Annahme: 1,00 Lot = 1 $ pro Punkt, Mindest-Lot 0,01. **Bitte beim eigenen Broker prüfen.**

| Risiko pro Trade | Median-Kontostand nach 1 Jahr | P(Verlust nach 1 J.) | P(Drawdown ≥ 50 %) | Median max. DD | P(+20 % in 6 Mon.) |
|---|---|---|---|---|---|
| 1 % | 133 $ | 15 % | 0 % | 20 % | 59 % |
| 2 % | 171 $ | 21 % | 25 % | 41 % | 81 % |

**Ehrliche Hinweise:**
- Diese Zahlen beruhen auf den *Testjahren*, die bisher am besten liefen (2022 und 2024). Mit dem 9-Jahres-Durchschnitt
  von +0,058 R wären sie spürbar schwächer.
- Bei 30 % Trefferquote sind Serien von 10–20 Verlusten normal. Bei 2 % Risiko bedeutet das einen Drawdown von 20–35 %.
- Das 100-$-Konto ist nur über einen CFD mit Mikro-Lots handelbar. Bei Brokern mit Mindest-Lot 0,1 wäre das Risiko 4 % pro Trade statt 1 %.

## Dateien
- **Pine:** `pine/NY_FVG_Continuation_Bot.pine` mit denselben Regeln, Risiko in % vom Konto und Kontostart 100 $.
  Syntax geprüft, aber nicht in TradingView kompiliert.
- **Code:** `v4_grid.py`, `v4_analyze.py`, `v4_account.py`
- **Ergebnisse:** `v4_grid_train.csv`, `v4_grid_valid.csv`, `v4_analysis.txt`, `v4_test_result.txt`, `v4_fvg_robustness.txt`

## Empfehlung
Vor echtem Geld **1–3 Monate Paper Trading oder Demo** mit genau diesen Regeln. Erst dann zeigt sich, ob die echten
Spreads und Fills des Brokers zur Simulation passen. Bei +0,05 R pro Trade machen schon 0,5 Punkte mehr Spread einen großen Teil der Edge zunichte.
