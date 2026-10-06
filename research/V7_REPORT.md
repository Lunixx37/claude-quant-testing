# V7: mehr Trades – Volatility Breakout für die Prop-Umgebung

## Ergebnis in Kürze
- **Gewählt:** **Wiedereinstieg in der NY-Session**, also max. 2 Trades/Tag, nach einem Exit beim nächsten Trigger-Kontakt erneut.
  Parameter k = 0,35, Stop = 0,75 × (k × Vortagesspanne), beide Richtungen, R-Trailing.
  - Frequenz: **~32 Trades/Monat** statt 20.
  - E: +0,12 R (CFD 2017–22), +0,13 R (CFD 2023–25), **+0,137 R (NQ-Futures 2023–25, t = 3,1)**.
  - Ertrag pro Monat in R: +50 % gegenüber 1 Trade/Tag.
- **Andere Sessions sind durchweg negativ** (Entwicklungsdaten 2017–22: 0 % der Varianten positiv): Asia, London, Nachmittag (16 % positiv) und stündlicher Breakout.
  Die Edge existiert nur zur NY-Eröffnung. Ein zweites Modell aus diesen Ideen war nicht nötig und auch nicht vorhanden.
- **Prop-Ergebnis** mit deinen neuen Auszahlungsregeln, Risiko **Eval 500 $ / Funded 250 $ pro Trade** (gewählt auf CFD 2017–22),
  auf NQ 2023–25: **Ø 5.645 $ Auszahlungen in 12 Monaten** (Median 4.882 $), **13.614 $ in 24 Monaten**,
  erster Payout im Median nach **84 Handelstagen**.

## Regeln der Simulation (deine Angaben)
- **Eval:** 50.000 $ Start, 48.000 $ Mindestbalance (Tagesschluss), Ziel 53.000 $, Tagesverlustlimit (DLL) 1.200 $.
- **Funded:**
  - 48.000 $ Mindestbalance und 2.000 $ Trailing-DD vom Tagesschluss-Hoch, DLL 1.000 $.
  - 5 Gewinntage ≥ 250 $; Consistency: bester Tag ≤ 50 % des Gewinns seit der letzten Auszahlung.
- **Auszahlung:**
  - ab einem Kontostand von 52.600 $; ausgezahlt wird alles über 52.100 $;
  - Obergrenzen 1.500 / 2.000 / 2.500 / 3.000 $, danach 3.500 $.
- **Neustart:** Nach einem gesprengten Account startet sofort eine neue Eval (Anzahl wird ausgewiesen).
- **Annahmen:**
  - Das DLL ist ein harter Fail und wird auf offener Position geprüft.
  - Kosten: MNQ (1 Tick Slippage, 1,50 $ pro Round Turn).
  - Eval-Gebühren sind **nicht** abgezogen.

## Vergleich (Bootstrap 1.500 Pfade à 24 Monate; Positionsgröße auf CFD 2017–22 gewählt, Werte für NQ 2023–25)
| | 1 Trade/Tag (k 0,3) | **2 Trades/Tag (k 0,35, Stop 0,75×)** |
|---|---|---|
| Trades/Monat | 20 | **32** |
| Trefferquote / E / Gewinn-Verlust-Verhältnis | 39,5 % / +0,16 R / ~2,0 | 38,2 % / +0,14 R / ~2,0 |
| Gewählte Positionsgröße (Eval/Funded) | 500 $ / 300 $ | 500 $ / 250 $ |
| Auszahlungen 12 Mon. (Mittel / Median) | 4.093 $ / 3.077 $ | **5.645 $ / 4.882 $** |
| Auszahlungen 24 Mon. | 9.979 $ | **13.614 $** |
| Anzahl Auszahlungen / 24 Mon. | 5,3 | **6,7** |
| Verbrauchte Evals / 24 Mon. | 6,0 | 6,7 |
| Erster Payout ≤ 1 / 2 / 3 / 12 Mon. | 0 / 8 / 22 / 87 % | 1 / **14 / 35 / 96 %** |
| Median bis zum ersten Payout | 108 Handelstage | **84 Handelstage** |

**Zur Einordnung:**
- In den Entwicklungsjahren (CFD 2017–22) liegen die Auszahlungen niedriger: ~10.900 $ in 24 Monaten.
- 2023–25 war ein gutes Umfeld für Breakouts. **Realistisch sind ca. 400–550 $ pro Monat an Auszahlungen pro gleichzeitig betriebenem Account-Slot**,
  abzüglich der Gebühren für ~3 Evals pro Jahr.
- Mehr Risiko im Funded-Account (300–400 $) erhöht die Auszahlungen auf NQ leicht, verbraucht aber deutlich mehr Evals.

## Dateien
- `vbo_sess.py` (Session-Modelle), `v7_run.py`, `v7_grid_summary.txt` (alle 194 Varianten), `prop3.py` (Lebenszyklus-Simulator), `v7_prop.py`, `v7_prop_result.txt`
- `pine/NY_VolBreakout_Bot.pine`: Standardwerte jetzt k 0,35, Stop 0,75×, beide Richtungen, max. 2 Trades/Tag, Positionsgröße „Prop phase $“ (Eval 500 $ / Funded 250 $).
