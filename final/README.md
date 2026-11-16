# Abschluss-Suche: Strategie mit hoher Trefferquote für NQ

Ziel: Trefferquote über 60 %, mehr als 2 Trades pro Woche, positiver Erwartungswert, stabil über beide Datensätze.

## Ergebnis

Eine Strategie besteht alle Stufen: **R1 „Open-Drive-Fortsetzung“** (`R1_OpenDrive.pine`, Referenz `r1_strategy.py`).

| Regel | Wert |
|---|---|
| ATR | Durchschnitt der Tagesspanne der letzten 14 abgeschlossenen Handelstage |
| Signal | erste 1-Min-Kerze ab 09:31 New York, die 0,3 ATR über (Long) oder unter (Short) dem 09:30-Eröffnungskurs schließt |
| Filter | Tagesspanne seit 09:30 beim Signal höchstens 0,5 ATR; Signal bis 15:29 |
| Einstieg | Schlusskurs der Signalkerze, höchstens 1 Trade pro Tag |
| Stop / Ziel | 0,15 ATR / 0,5 × Stop; spätestens 15:59 glatt |

| | CFD 2016–2022 | NQ 2023–2025 |
|---|---|---|
| Trades (pro Woche) | 949 (3,2) | 485 (3,4) |
| Trefferquote | 73,2 % | 70,5 % |
| Ø Gewinn / Ø Verlust | +0,48 R / −1,01 R | +0,48 R / −1,00 R |
| Erwartungswert je Trade | +0,078 R (t = 3,6) | +0,041 R (t = 1,3) |
| Profitfaktor | 1,29 | 1,14 |
| Ertrag pro Jahr | +12,5 R | +6,9 R |
| Größter Drawdown | −10,1 R | −10,3 R |
| Längste Verlustserie | 6 | 5 |

Kosten: 1 NQ-Punkt je Trade (CFD: derselbe Anteil der ATR). Auf NQ lag der Stop im Schnitt bei 47 Punkten, das Ziel bei 23,5 Punkten.

**Der Vorteil ist klein.** Mit 2 Punkten Kosten bleiben auf NQ +0,017 R je Trade, mit 3 Punkten ist er aufgebraucht. Ein Verlust kostet rund zwei Gewinne.

### Jahr für Jahr (Erwartungswert je Trade in R)

| 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|
| 0,00 | +0,09 | +0,16 | +0,05 | +0,09 | +0,08 | +0,02 | +0,09 | +0,01 |

Kein Jahr ist klar negativ; 2017, 2023 und 2025 sind praktisch null.

### Nachbarschaft (Trefferquote, Erwartungswert in R)

| Variante | NQ | CFD |
|---|---|---|
| Basis | 70,5 %, +0,041 | 73,2 %, +0,078 |
| Signal bei 0,25 ATR | 68,9 %, +0,016 | 69,0 %, +0,017 |
| Signal bei 0,35 ATR | 68,5 %, +0,005 | 70,0 %, +0,034 |
| ohne Spannen-Filter | 69,9 %, +0,033 | 71,5 %, +0,055 |
| Stop 0,12 ATR | 73,0 %, +0,070 | 72,4 %, +0,059 |
| Stop 0,18 ATR | 70,1 %, +0,040 | 72,4 %, +0,072 |
| Ziel 0,75 × Stop | 60,4 %, +0,043 | 62,4 %, +0,071 |
| Ziel 1 × Stop | 53,2 %, +0,052 | 54,8 %, +0,076 |
| Stop 0,1 ATR, Ziel 1 × Stop | 56,5 %, +0,100 | 55,5 %, +0,075 |
| Ziel 2 × Stop | 40,4 %, +0,135 | 40,6 %, +0,117 |

Alle 14 geprüften Nachbarn sind in beiden Datensätzen positiv. Die Signal-Schwelle ist die empfindlichste Stelle: bei 0,25 und 0,35 ATR bleibt mit dem kleinen Ziel wenig übrig. Größere Ziele bringen mehr Ertrag je Trade, aber eine Trefferquote unter 60 %.

## Vorgehen

1. **Ereignistabelle** (`build_events.py`): alle möglichen Einstiege je Tag, rund 205.000 auf dem CFD und 107.000 auf NQ.
   - Reclaims an Leveln: Stdv-Box (Kanten, Mitte, 2 bis 4,5), Psych 100/50, Vortageshoch/-tief/-schluss, Overnight-Hoch/-Tief, Eröffnung, Opening Range, VWAP, Kanten von FVG, iFVG, Order Block und Rejection Block (5 Minuten).
   - Ausbrüche: Abstand zur Eröffnung 0,2 bis 0,5 ATR, Opening Range, neues Tagesextrem, Vortages- und Overnight-Extreme, Indecision-Box.
   - Je Ereignis 25 Ausstiege (4 feste Stops und Struktur-Stop × 5 Ziele) und 26 Zusatzbedingungen (Trend, VWAP-Lage, Konfluenz-Flags am Einstiegskurs, Box, Uhrzeit …).
2. **Suche** (`search.py`): Einstiegsgruppe × Trendbedingung × Zeitfenster × bis zu 2 Zusatzbedingungen × Ausstieg, nur das erste passende Ereignis pro Tag.
   - Stufe A: CFD 2016–2020. Stufe B: CFD 2021–2022.
3. **Endtest** (`final_test.py`): fünf Kandidaten, vor dem Test eingefroren und committet (`selection.json`), einmal auf NQ 2023–2025.
4. **Verfeinerung**: drei Zusatzbedingungen für den Sieger, nur anhand der CFD-Daten gewählt, ebenfalls vor dem Test committet. NQ wurde dafür ein zweites Mal verwendet.

## Was die Suche gezeigt hat

| Schritt | Anzahl |
|---|---|
| Konfigurationen mit mindestens 2 Trades pro Woche | 919.025 |
| Trefferquote ≥ 60 % in Stufe A | 194.615 |
| … und Erwartungswert > 0 mit t ≥ 2,5 | 717 |
| … und in Stufe B bestätigt | 371 |

- Von den 717 Stufe-A-Siegern sind 83 % auch in Stufe B positiv; von den übrigen Konfigurationen mit hoher Trefferquote nur 28 %. Das Muster ist also kein reiner Zufallsfund.
- Fast alle 371 folgen demselben Prinzip: **mit der Bewegung handeln, wenn der Kurs mindestens 0,3 ATR von der Eröffnung entfernt ist.** Der Ausbruch bei 0,3 ATR besteht in allen 234 gefundenen Varianten.
- Reclaims **gegen** die Bewegung sind über das ganze Ausstiegsraster negativ.
- Konfluenzen allein reichen nicht: Stdv-Level, Psych-Level, VWAP, FVG, iFVG, Order Block, Rejection Block und Tageslevel bestehen nur zusammen mit der Trendbedingung, und auch dann schlechter als der schlichte Ausbruch.
- Die Indecision-Box besteht in keiner Variante.
- Die einzige Zusatzbedingung mit stabilem Nutzen auf dem CFD ist „keine gegenläufige FVG am Einstieg“; auf NQ brachte sie nichts.

## Endtest auf NQ 2023–2025

| Kandidat | Trades/Woche | Trefferquote | E je Trade | Ergebnis |
|---|---|---|---|---|
| S1 Ausbruch 0,3 ATR von der Eröffnung | 4,5 | 70,0 % | +0,034 R | bestanden |
| S2 wie S1, keine Gegen-FVG | 3,4 | 69,8 % | +0,032 R | bestanden |
| S3 Psych-Level-Reclaim mit der Bewegung | 3,7 | 55,3 % | −0,028 R | nicht bestanden |
| S4 Reclaim an beliebigem Level mit Momentum-Kerze | 3,7 | 57,6 % | +0,007 R | nicht bestanden |
| S5 Kombi S1 + S3, bis 2 Trades pro Tag | 7,7 | 56,9 % | −0,004 R | nicht bestanden |
| R1 S1 + Tagesspanne ≤ 0,5 ATR | 3,4 | 70,5 % | +0,041 R | bestanden |
| R2 R1 + keine Gegen-FVG | 2,5 | 70,5 % | +0,040 R | bestanden |
| R3 R2, nur bis 13:00 | 2,3 | 70,4 % | +0,033 R | bestanden |

## Einschränkungen

- **GEX wurde nicht getestet.** Dafür gibt es in diesem Projekt keine Optionsdaten.
- **Indecision-Box** ist hier so definiert: 5-Min-Kerze mit Körper höchstens 20 % der Spanne und Spanne mindestens 0,03 ATR; Ausbruch per 1-Min-Schluss binnen 30 Minuten. Eine andere Definition kann anders ausfallen.
- **NQ 2023–2025 ist kein unberührter Testdatensatz mehr.** Er wurde in früheren Studien und hier zweimal verwendet. Der Fortsetzungs-Effekt war schon vor dieser Suche aus den NQ-Daten bekannt.
- **Die CFD-VWAP** beruht auf Tick-Volumen.
- **Das Pine-Skript ist nicht in TradingView kompiliert oder gegen die Trade-Liste abgeglichen.** `results/r1_trades_NQ.csv` enthält alle Backtest-Trades zum Vergleich.
- Liegen Stop und Ziel in derselben Minutenkerze, zählt im Backtest der Stop.

## Forward-Test

1. `R1_OpenDrive.pine` auf dem 1-Minuten-Chart von NQ oder MNQ laden, Chart mit vollständiger Handelszeit (nicht nur reguläre Sitzung), damit die ATR stimmt.
2. Im Strategy Tester die Trades der letzten Wochen mit `results/r1_trades_NQ.csv` vergleichen, soweit sich die Zeiträume überschneiden.
3. „Nur ab Startdatum handeln“ einschalten und mindestens 150 Trades sammeln (etwa ein Jahr), bevor die Trefferquote beurteilt wird. Bei 70 % erwarteter Quote liegt die Schwankung über 150 Trades bei etwa ±7 Prozentpunkten.

## Dateien

| Datei | Inhalt |
|---|---|
| `build_events.py` | Ereignistabelle |
| `search.py` | Suche Stufe A und B |
| `selection.json` | eingefrorene Kandidaten |
| `final_test.py` | Endtest auf allen Datensätzen |
| `r1_strategy.py` | eigenständige Nachrechnung von R1, Nachbarschaftstest |
| `R1_OpenDrive.pine` | TradingView-Strategie |
| `results/` | Trade-Listen |

```bash
python final/build_events.py /tmp/ev && python final/search.py /tmp/ev && python final/final_test.py /tmp/ev
python final/r1_strategy.py
```
