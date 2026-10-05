# V2: Mental Levels statt GEX (Prop-Umgebung, 250 $ Risiko pro Trade)

**Ergebnis in Kürze:**
- **Die Strategie bleibt profitabel.** Auf 2025 (pseudo-OOS): PF 1,63, +0,30 R, 44 Trades.
- **Mental Levels bringen als Ergänzung etwas mehr Trades bei gleicher Qualität. Allein haben sie keine Edge.**
- **Ein Payout in 1–2 Monaten ist mit diesem Signal nicht erreichbar:** 0 % bei 250 $ Risiko, höchstens ~5 % bei 600 $ Risiko.

## Definitionen
- **Mental Level:** Preis, der durch 50 teilbar ist. Seine Stärke ist der größte passende Schritt aus 1000 / 500 / 100 / 50. Die Levels werden um den Close des Vorbars erzeugt.
- **Level-Typen:**

  | Typ | Bedeutung |
  |---|---|
  | `MV` | Mental Level mit VWAP/Band/rVWAP/Mult-Band innerhalb von 40 Ticks (10 Punkten). Hat Vorrang, wenn mehrere Levels in Frage kommen. |
  | `M` | Mental Level allein |
  | `V` | VWAP-Level allein (V1) |
- **Unverändert gegenüber V1:** Manipulation, Absorption (Proxy), Reclaim-Trigger, Strukturregel, Session 09:30–11:00 NY, höchstens 2 Trades pro Tag, Market Entries, 100-Tick-Stop.
- **Exit:** Ziel 2R (Limit-Order, gefüllt nur bei 1 Tick Durchlauf) plus R-Trailing (bei +kR wandert der Stop auf (k − 1,25) R). Liegen Stop und Ziel im selben Bar, gilt der Stop als zuerst gefüllt.
- **Prop-Sizing:** 250 $ Risiko pro Trade, das sind 5 MNQ bei 100 Ticks. Dazu die Schutzregeln für DLL und EOD-Grenze sowie Mindestgröße statt Aufhören.

## Iterationen (Entscheidungen nur auf Training/Validierung)
| # | Test | Ergebnis | Entscheidung |
|---|---|---|---|
| 1 | V + alle Mental Levels | MV-Setups ~0 R; 500er/1000er nur 9 Trades | zu breit |
| 2 | 8 Level-Konfigurationen × 6 Exits (Training) | Nur Mental: −0,05 bis +0,07 R. **V + Mental ≥ 100: +0,23 R bei mehr Trades.** Festes RR allein schlechter als Trailing; **TP 2R + Trailing** überall nahe der Spitze | 5 Kandidaten |
| 3 | 5 Kandidaten: Validierung + Prop-Simulation (250 $) | C3 „V + Mental ≥ 100, TP 2R + Trail“: Validierung PF 1,34, Prop 12 M 34,5 %; Payout ≤ 42 Tage bei **allen 0 %** | C3 |
| 4 | Robustheit C3 (Training) | ±1 Rasterschritt überall PF > 1,05; TP 1,75–3R stabil; Slippage 3 Ticks PF 1,34 | eingefroren (`V2_FINAL`, Commit 881f835) |
| 5 | Einmaliger Lauf auf 2025 | siehe unten | – |

## Kennzahlen V2_FINAL (1 NQ, netto, 1R = 500 $)
| | Training | Validierung | In-Sample | **2025 (pseudo-OOS)** |
|---|---|---|---|---|
| Trades | 159 | 29 | 188 | **44** (Kriterium ≥ 60 nicht erfüllt) |
| Win-Rate | 35,8 % | 34,5 % | 35,6 % | 38,6 % |
| Profit Factor | 1,43 | 1,34 | 1,42 | **1,63** |
| Erwartungswert | +0,22 R | +0,17 R | +0,21 R | **+0,30 R** |
| Max. Drawdown | 7,8 R | 6,4 R | 7,8 R | 5,1 R |
| Long / Short | +0,28 / +0,15 R | +0,38 / −0,02 R | +0,29 / +0,12 R | −0,06 / +0,66 R |
| Ziel 2R erreicht | 36 % | 34 % | 36 % | 39 % |

- **2025 nach Level-Typ:** V +0,43 R (n=28), M +0,23 R (n=9), MV −0,16 R (n=7). Die MV-Konfluenz zeigt **keinen** Vorteil.
- **2025 mit Slippage:** 2 Ticks PF 1,50, 3 Ticks PF 1,37.

## Prop-Ergebnis (deine Regeln, 250 $ pro Trade)
| | Payout ≤ 1 M | ≤ 2 M | ≤ 3 M | ≤ 12 M | Eval bestanden | Median Eval-Dauer |
|---|---|---|---|---|---|---|
| In-Sample-Bootstrap | 0 % | 0 % | 0,3 % | 34,5 % | 73,8 % | 108 Tage |
| 2025-Bootstrap | 0 % | 0 % | 0,1 % | 14,5 % | 54,2 % | 132 Tage |
| Historische Starts 2023–24 | – | 0 % | – | 2,1 % | 45 % | – |

**Risiko pro Trade gegen Zeithorizont (In-Sample-Bootstrap):**

| Risiko pro Trade | ≤ 1 M | ≤ 2 M | ≤ 3 M | ≤ 12 M | Eval gesprengt |
|---|---|---|---|---|---|
| 150 $ | 0 % | 0 % | 0 % | 7,9 % | 3,6 % |
| 250 $ | 0 % | 0 % | 0,3 % | 34,5 % | 13,5 % |
| 350 $ | 0 % | 0,2 % | 3,5 % | **39,1 %** | 23,8 % |
| 500 $ | 0,1 % | 3,7 % | 10,1 % | 28,3 % | 32,9 % |
| 600 $ | 0,3 % | 5,2 % | 11,8 % | 24,8 % | 37,5 % |

## Warum 1–2 Monate nicht gehen
- **Benötigter Gewinn:** Eval +3.000 $ plus Funded +2.600 $ sind 5.600 $, also 22R bei 250 $ Risiko.
- **Verfügbare Trades:** Die Strategie erzeugt ~0,4 Trades pro Tag, in 42 Handelstagen also ~17 Trades.
- **Rechnung:** 17 Trades × +0,2 R ergeben im Erwartungswert ~3,5R. Gebraucht werden 22R. Mehr Risiko verkürzt die Zeit, sprengt aber den Drawdown (2.000 $ Abstand zur Grenze).
- **Schlussfolgerung:** Für 1–2 Monate bräuchte es etwa 5- bis 6-mal mehr Ertrag pro Tag. Das geht nur mit deutlich mehr validen Signalen pro Tag, nicht mit Sizing oder Exits.

## Ehrlichkeitshinweise
- 2025 war für V1 schon einmal ausgewertet. Für V2 ist es nur **pseudo-OOS**. Die V2-Entscheidungen fielen ausschließlich auf 2023–2024.
- In TradingView entscheidet die Bar-Path-Annahme des Broker-Emulators, ob Stop oder Ziel im selben Bar zuerst gilt. Meine Simulation nimmt konservativ den Stop zuerst an.
- Das Pine-Script `pine/NY_Open_MAD_V2_Mental.pine` ist syntaktisch geprüft (pynescript), aber nicht in TradingView kompiliert.

Reproduzierbar mit `v2_grid.py`, `v2_eval.py`, `v2_forward.py` und `v2_risk_table.txt`.
