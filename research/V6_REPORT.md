# V6: breite Suche (10+ Strategie-Familien, 1.500 Konfigurationen), ehrlich bewertet per Walk-Forward

## Methode
- **Daten:** CFD 2017–09/2025 (eine durchgehende Reihe), Kosten 1,2 Punkte Spread + Slippage + Übernacht-Finanzierung.
  Gegenprobe auf NQ-Futures 2023–25 mit MNQ-Kosten.
- **Universum (alle Kombinationen vorab festgelegt):**
  - F1 Opening Range Breakout (5/15/30 min)
  - F2 Intraday-Momentum
  - F3 Gap Fade/Fortsetzung
  - F4 Vortages-High/Low-Breakout
  - F5 Donchian-Trendfolge (Swing)
  - F6 RSI2 Mean Reversion (Swing)
  - F7 Volatility Breakout (Williams)
  - F8 „News-Range“ 8:30
  - F9 Turn of Month
  - F10 alle früheren Setups (VWAP, Mental, FVG, RB, OB, MSS, Sweep, Absorption) × V5-Verfeinerungen
  - F7b 360 Verfeinerungen von Volatility Breakout
- **Nicht testbar:** Delta-Flips (keine Orderflow-Daten) und ein echter News-Kalender.
- **Ehrliche Bewertung:** Für jedes Jahr 2019–2025 wird die beste Konfiguration **nur mit den Daten der Vorjahre** gewählt
  (t-Wert, ≥ 100 Trades, ≥ 1/Woche, letzte 12 Monate positiv) und dann das Folgejahr gehandelt. Die Ergebnisse dieser
  Jahre sind out-of-sample für die gesamte Suche, egal wie viele Varianten getestet wurden.

## Familien-Überblick (In-Sample, nur zur Orientierung)
Siehe `v6_family_overview.txt`. Volatility Breakout (F7/F7b) ist die einzige Familie, bei der fast alle Konfigurationen positiv sind.

## Ehrliches Ergebnis (Walk-Forward OOS 2019–2025, CFD, nach Kosten)
| | Trades/Monat | Trefferquote | Erwartungswert | RR (Ø Gewinn/Ø Verlust) | t | positive Jahre |
|---|---|---|---|---|---|---|
| Top-1 | 10,6 | 44,6 % | +0,109 R | 1,56 | 2,51 | 5/7 |
| Top-5 Portfolio | 66 | 38,9 % | +0,075 R | 1,78 | 3,59 | 6/7 |

Ab 2019 wählt die Selektion **in jedem Jahr Volatility Breakout mit Trailing Stop** (k 0,3–0,4, meist nur Long).

## Bester Live-Bot: Volatility Breakout, k = 0,3, Stop = 0,3 × Vortagesspanne, R-Trailing, EOD-Exit
Breites Plateau: alle 30 Varianten (k 0,2–0,4, Stop 0,75–1,5×, Long/Both) sind positiv. Siehe `v6b_vbo_plateau.txt`.

| | Trades/Monat | Trefferquote | E | RR | t | positive Jahre | Live 1 %/Trade: Ø/Monat | max DD |
|---|---|---|---|---|---|---|---|---|
| **Long-only, CFD 2017–25** | 10,1 | 42,1 % | **+0,181 R** | 1,91 | 4,04 | **9/9** | +1,84 % | 13,3 % |
| Long-only, NQ 2023–25 | 10,1 | 44,0 % | +0,219 R | 1,91 | 2,95 | 3/3 | +2,16 % | 10,9 % |
| Both, CFD 2017–25 | 20,0 | 38,6 % | +0,136 R | 2,03 | 4,11 | 8/9 | +2,72 % | 29,2 % |
| Both, NQ 2023–25 | 20,2 | 39,8 % | +0,168 R | 2,05 | 3,06 | 3/3 | +3,37 % | 10,8 % |

**Einordnung:**
- Die Selektion selbst ist im Walk-Forward bewertet (+0,11 R, Live 1 %: +1,1 %/Monat, DD 15 %). Das ist die ehrlichste Erwartung.
- Die Werte des festen Bots (+1,8–3,4 %/Monat bei 1 %) liegen höher, enthalten aber den Vorteil, dass der Bot im Nachhinein ausgewählt wurde.

## Beste Prop-Variante (deine Regeln)
Volatility Breakout, k = 0,3, Trailing, **beide Richtungen**, Risiko **Eval 350 $ / Funded 200 $ pro Trade** (gewählt auf 2017–22).
Geprüft auf NQ 2023–25:

| | Payout ≤ 1 Mon. | ≤ 2 Mon. | ≤ 3 Mon. | ≤ 12 Mon. | Median bis 1. Payout | Eval bestanden | Median Eval |
|---|---|---|---|---|---|---|---|
| VBO Prop-Setup | 0 % | 1,2 % | 5,3 % | **53,8 %** | **117 Handelstage** (~5,5 Monate) | 80 % | 36 Tage |
| Top-5-Portfolio (Eval 350 / Funded 200 $) | 5,3 % | 14,2 % | 16,2 % | 16,6 % | 26 Tage (wenn erfolgreich) | 59 % | – |

**Warum es nicht schneller geht:**
- Eval und Funded verlangen zusammen ~5.600 $ Gewinn.
- Bei ~+0,15 R × 300 $ ≈ 45 $ pro Trade und ~20 Trades/Monat sind das ~900 $/Monat, also im Erwartungswert ~6 Monate.
- Mehr Risiko verkürzt die Zeit, reißt aber häufiger den nachlaufenden DD von 2.000 $.
- Ein Portfolio vieler Setups zahlt im Erfolgsfall schnell aus, aber selten.

## Dateien
- **Pine:** `pine/NY_VolBreakout_Bot.pine` mit denselben Regeln; Long-only/Both, Risiko in % oder fix in $. Syntax geprüft, nicht in TradingView kompiliert.
- **Code:** `lab.py`, `v6_run.py`, `v6_wf.py`, `v6_eval.py`, `v6b_prop.py`, `v6b_prop_portfolio.py`
- **Ergebnisse:** `v6*_result.txt`, `v6b_*.txt`
