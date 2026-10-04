# Prop-Firm-Anpassung: Ergebnis

**Ziel: mindestens 50 % aller Evals führen zu einem Payout. NICHT erreicht.**
- Bestes ehrliches Ergebnis: ~41 % (In-Sample-Bootstrap).
- Auf den 2025-Daten: ~22 %.
- Historische Rolling-Starts: 17 % (2023–24) bzw. 0 % (2025, durch das Datenende gekappt).

## Simulierte Umgebung (Vorgabe des Users)
- **Eval:** Start 50.000 $, Mindestbalance 48.000 $ (EOD), Ziel 53.000 $, keine Consistency, Daily Loss Limit 1.200 $.
- **Funded:** Start 50.000 $, Mindestbalance 48.000 $, max. 2.000 $ Drawdown vom Peak des EOD-Saldos (EOD-Trailing), Daily Loss Limit 1.000 $.
- **Payout-Bedingungen (Funded):** 5 Winning Days mit mindestens 250 $, Saldo mindestens 52.600 $, Consistency 50 %.

**Annahmen, wo die Regeln offen sind:**
- Das DLL ist ein harter Fail, geprüft intraday auf unrealisierter Equity. Die Sensitivität zeigt: weich oder hart macht keinen Unterschied, weil das Sizing einen DLL-Bruch ausschließt.
- Payout = Saldo minus 52.600 $, danach wird der Peak zurückgesetzt.
- **Erfolg = Eval bestanden UND erster Payout innerhalb von 252 Handelstagen (12 Monaten) ab Eval-Start.**

**Kosten und Ausführung:**
- MNQ mit 1,50 $ round turn und 1 Tick Slippage pro Fill.
- Intraday-Equity wird Bar für Bar rekonstruiert, mit der ungünstigen Reihenfolge innerhalb des Bars.

## Methode
- **Signale:** die eingefrorene Strategie. Einzige Signaländerung ist `cl_min` 0,6 → 0,7. Sie war die *einzige* Einzeländerung, die Training **und** Validierung verbessert hat.
- **Wahl der Prop-Policy:** ausschließlich auf 2023–2024, per Block-Bootstrap mit Blöcken von 10 Tagen und 1.500 Pfaden.
- **Prüfung:** auf 2025 per Bootstrap sowie mit echten, historischen Account-Starts alle 5 Tage.
- **Achtung:** 2025 ist nicht mehr unberührt, denn der Forward-Test der Basisstrategie lief dort bereits einmal. Für die Prop-Parameter ist der Zeitraum aber Out-of-Sample.

## Iterationen
| # | Änderung | IS-Bootstrap Payout 12 M | 2025 Payout | Entscheidung |
|---|---|---|---|---|
| 1 | FINAL, Sizing als Anteil am Puffer (Grid mit 100 Policies) | 18 % | – | Engpass: +0,75R-Gewinner unter 250 $, Frequenz zu niedrig |
| 2 | Größe passend zur Winning-Day-Schwelle (Rechenfehler 7 → 8 MNQ korrigiert), Horizont 12/18/24 M | 20 / 22 / 25 % | – | ein längerer Horizont hilft kaum |
| 3 | Mehr Trades (relVol 1,0/1,25, zusätzliche Bänder, Fenster bis 11:30) | – | – | **verworfen:** alle Varianten in der Validierung negativ (Overfitting) |
| 4 | Scale-out 50 % bei +1R / 0,75R / 33 % | 27–28 % | 13 % | **verworfen:** auf 2025 deutlich schlechter |
| 5 | Breites Grid mit 240 Policies (Eval-Anteil bis 100 %, Funded 3–8 MNQ fix) | 30 % | 21 % | Obergrenze der Prop-Schicht erreicht |
| 6 | Diagnose: nötige Edge | +0,1 R/Trade → 50 %, +0,2 R → 71 % | – | **Für 50 % braucht es ~0,32 R statt 0,22 R pro Trade** |
| 7 | `cl_min` 0,7 (in Training und Validierung besser) | 39,8 % | 21,3 % | übernommen |
| 8 | „No-Starve“: Mindestgröße statt Aufhören nahe der Grenze | 41,0 % | 21,8 % | übernommen (minimal) |

## Beste Konfiguration (Defaults in `pine/NY_Open_MAD_Prop.pine`)
**Eval:**
- Risiko = 33 % des Abstands zur Mindestbalance, 3–10 MNQ.

**Funded:**
- Fix 4 MNQ, also 200 $ Risiko pro Trade bei 100 Ticks. Damit ist nur ein Gewinner ab +1,75R ein Winning Day.

**Für beide Phasen gilt:**
- Schutzregel: Ein voller Stop × 1,05 darf weder das DLL noch die EOD-Grenze reißen.
- Nach einem Gewinntrade wird der Tag beendet.

| | IS-Bootstrap 2023–24 | 2025-Bootstrap | Historisch IS | Historisch 2025 |
|---|---|---|---|---|
| Eval bestanden (12 M) | 70,5 % | 55,3 % | 64 % | 62 % |
| **Payout (12 M)** | **41,0 %** | **21,8 %** | 17 % | 0 %* |
| Eval gesprengt / ausgehungert | 24,8 % | 30,7 % | | |

\* Die historischen Starts 2025 haben im Median nur 154 verbleibende Handelstage, weil die Daten enden. Für einen Payout braucht es im Median rund 150 Tage. Das Ergebnis ist deshalb stark nach unten verzerrt.

## Warum 50 % nicht erreichbar sind (ohne Overfitting)
1. **Frequenz:** 0,32 Trades pro Tag (2023–24) bzw. 0,15 pro Tag (2025). Der erste Payout kommt im Median erst nach etwa 150 Handelstagen.
2. **Ertrag pro Tag:** ca. 0,07 R/Tag. Gebraucht werden etwa 0,10 R/Tag. Alle Wege zu mehr Trades sind in der Validierung durchgefallen.
3. **Drawdown-Profil:** Der Trailing-DD von 2.000 $ entspricht bei 4 MNQ 10R. Die Strategie hat Verlustserien von 5–7R. Bei mehr Kontrakten steigt das Sprengrisiko, bei weniger dauert es zu lange.
4. **Die Regeln sind nicht der Hebel:** Lockert man einzelne Regeln (Winning Day ab 150 $, 3 Tage, keine Consistency, Payout ab 52.000 $, DD 2.500 $, statischer DD, weiches DLL), liegt die Quote immer bei 41–43 %. Der Engpass ist das Signal.

## Was nötig wäre
- **Mehr unabhängige, validierte Signale pro Tag**, z. B. dieselbe Logik auf ES oder auf einem zweiten Markt (Daten fehlen), oder ein anderes Setup im NY-Fenster. Das ist neue Forschung mit frischen Validierungsdaten.
- **Mehr Daten:** Die CSV ist beim Excel-Limit abgeschnitten. Mit NQ 2018–2022 ließe sich die Edge-Schätzung absichern und neu validieren.
- Für eine Einschätzung über einen längeren Zeitraum: Bei 18 bzw. 24 Monaten steigt die Quote nur leicht (Iteration 2).

Reproduzierbar mit `prop2_run.py`, `prop2_scan.py`, `prop2_bound.py`, `prop2_final.py` und `prop2_nostarve.py`. Die Ergebnisse liegen in den `*_result.txt`-Dateien.
