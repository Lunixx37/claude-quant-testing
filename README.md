# NQ-Strategie-Forschung

Backtests und TradingView-Strategien für den Nasdaq-100-Future (NQ / MNQ) auf 1-Minuten-Daten. Das Repository enthält vier Arbeitsstränge, jeder in einem eigenen Ordner mit eigener Dokumentation.

## Wo liegt was

| Ordner | Thema | Einstieg in die Doku | Stand |
|---|---|---|---|
| `research/` und `pine/` | NY-Open-Strategie „MAD“ und breite Strategiesuche V2–V11 (Opening Range, Momentum, Gaps, FVG, Volatility Breakout u. a.) | `research/REPORT.md`, danach `research/V2_REPORT.md` bis `V11_REPORT.md` | MAD im Forward-Test profitabel, mit 35 Trades aber nicht bestätigt. Volatility Breakout (VBO): rund 38 % Treffer, +0,12 bis +0,14 R je Trade in allen drei Datensätzen. |
| `nq_stdv_box/` | Stdv-Box (Open 00:00 / Open 08:30) als Indikator, Strategien K1 und K2 | `nq_stdv_box/README.md` | K2 Best: rund 1,3 Trades pro Woche, 30–38 % Treffer, +0,34 bis +0,61 R je Trade; im Nachhinein ausgewählt. |
| `funktions_studien/` | Kursverlauf als Funktion: Polynome, Glättung, Extrem- und Wendepunkte, Reversal-Ereignisse | `funktions_studien/README.md` | Keine Vorhersagekraft. Liefert den Fortsetzungs-Befund, auf dem `open_drive/` aufbaut. |
| `open_drive/` | Open-Drive-Strategie: Ausbruch 0,3 ATR von der 09:30-Eröffnung, mehrere Ausstiegs-Modi | `open_drive/README.md` | Empfohlen: Trend-Modus, rund 22 % Treffer, +0,30 bis +0,37 R je Trade, 3,2 Trades pro Woche. |

Alle Ergebnisse sind Backtests auf bekannten Daten. Keine der Strategien ist durch einen Forward-Test bestätigt.

## TradingView-Skripte

| Datei | Strategie |
|---|---|
| `open_drive/R1_OpenDrive.pine` | Open-Drive (Trend-Modus als Standard; Nachzug, Teilverkauf und festes Ziel wählbar) |
| `nq_stdv_box/k2_best.pine` | K2 Best mit Profilen „Prop-Eval“ und „Privat“ |
| `nq_stdv_box/k1_k2_strategy.pine` | K1 und K2 in einem Skript |
| `nq_stdv_box/k1_strategy.pine`, `nq_stdv_box/k2_strategy.pine` | K1 und K2 einzeln |
| `nq_stdv_box/stdv_box.pine` | Stdv-Box als Indikator |
| `pine/NY_VolBreakout_Bot.pine`, `pine/NY_VolBreakout_Marker.pine` | Volatility Breakout: Strategie und Trade-Markierung |
| `pine/NY_FVG_Continuation_Bot.pine` | FVG-Fortsetzung |
| `pine/NY_Open_MAD_Strategy.pine`, `pine/NY_Open_MAD_Prop.pine`, `pine/NY_Open_MAD_V2_Mental.pine` | NY-Open-MAD in drei Varianten |

## Daten

Die Daten liegen im Wurzelverzeichnis, weil alle Skripte sie dort erwarten.

| Datei | Inhalt |
|---|---|
| `Dataset_NQ_1min_2022_2025.csv` | NQ-Future, 1 Minute, 12/2022 bis 12/2025, New Yorker Zeit, Zeitstempel = Kerzenschluss |
| `1m_data_part1.zip`, `1m_data_part2.zip` | NAS100-CFD, 1 Minute, 11/2016 bis 10/2025, Brokerzeit (Osteuropa, New York + 7 Stunden), Zeitstempel = Kerzen-Open, nur Tick-Volumen |

Hinweis zur Zeitumrechnung der CFD-Daten: `open_drive/`, `funktions_studien/` und `research/` rechnen mit der europäischen Sommerzeit-Umstellung um. `nq_stdv_box/` zieht fest 7 Stunden ab; in den Wochen, in denen nur die USA Sommerzeit haben, liegt dort alles um eine Stunde verschoben.

## Ausführen

```bash
pip install numpy pandas scipy scikit-learn numba matplotlib
python open_drive/r1_strategy.py              # Kennzahlen aller Open-Drive-Modi
python funktions_studien/curve_fit_strategy.py --plot
python nq_stdv_box/stdv_box.py               # Stdv-Box: Level-Statistik
```

Die genauen Aufrufe stehen in der Doku des jeweiligen Ordners.

## Ordnung im Repository

- `main` enthält den zusammengeführten Stand aller Arbeitsstränge.
- Neue Arbeit entsteht auf einem eigenen Branch und wird danach nach `main` übernommen.
- Jeder Arbeitsstrang bleibt in seinem Ordner; Daten liegen nur im Wurzelverzeichnis.
