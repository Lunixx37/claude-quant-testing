# NY Open MAD Strategy (Manipulation → Absorption → Distribution): Endreport

Alle Zahlen sind netto nach Kosten (1 NQ-Kontrakt, Kommission $4,50 round turn, 1 Tick Slippage pro Fill), berechnet mit `research/engine.py` auf `Dataset_NQ_1min_2022_2025.csv`. Jede Zahl lässt sich mit `python3 research/run.py <split>` bzw. `research/forward.py` reproduzieren.

## Status
- **In-Sample:** Alle vorab festgelegten Kriterien sind erfüllt.
- **Forward:** Profitabel, aber mit nur 35 Trades. Das vorab festgelegte Kriterium von mindestens 60 Trades ist **nicht erfüllt**.
- **Gesamturteil:** Die Strategie gilt damit statistisch noch **nicht** als bestätigt. Der t-Wert liegt im Forward bei 1,10 und über alle 193 Trades bei etwa 1,9.

## Strategie-Regeln (eingefrorene Version `candidates.py::FINAL`)
- **Session:** Signale nur von Bars, die zwischen 09:30 und 11:00 New-York-Zeit öffnen. Die Zeitzone ist America/New_York, die Sommerzeit ist berücksichtigt. Glattstellung am Close des 15:55-Bars oder am letzten Bar der Session (Early Close). Keine Overnight-Positionen.
- **Trade-Limit:** maximal 2 Entries pro NY-Handelstag. Der Zähler wird beim Sessionstart um 18:00 ET zurückgesetzt. Es gibt immer nur eine Position, nach einem Exit braucht es ein komplett neues Setup.
- **Levels:** Jeweils der Wert des *vorherigen* Bars:
  - ETH-VWAP (hlc3, verankert 18:00)
  - ±1σ- und ±2σ-Bänder um den ETH-VWAP
  - multiplikative Bänder VWAP × (1 ± 0,5 %)
  - RTH-VWAP (verankert 09:30)
  - optional vom User eingegebene QQQ-GEX-Level (nicht backtestbar)
- **Manipulation:**
  - Der Vorbar schließt auf der einen Seite des Levels, der aktuelle Bar handelt an das Level heran oder darüber hinaus (Toleranz −4 bis +60 Ticks). Gewählt wird das Level, das dem Extrem am nächsten liegt.
  - Als **Sweep** gilt eine Penetration von mindestens 4 Ticks.
  - Liegt das Extrem mehr als 60 Ticks jenseits des Levels, ist es ein echter Bruch, und das Setup verfällt.
  - Das Setup verfällt außerdem 10 Bars nach dem Sweep.
- **Absorption (OHLCV-Proxy):** Ein Bar am Level (innerhalb von 4 Ticks) mit allen drei Bedingungen:
  - relatives Volumen ≥ 1,5 (gegenüber dem EMA-20 des Volumens derselben Minute an den Vortagen),
  - Rejection-Wick ≥ 40 % der Range **oder** Close-Location ≥ 60 % in Trade-Richtung,
  - **Effort vs. Result:** (Range / Ø-Range derselben Minute) / relVol ≤ 1,0, also viel Volumen und wenig Bewegung.

  Bricht ein späterer Bar das Absorptions-Extrem um mehr als 4 Ticks, wird die Absorption verworfen.
- **Distribution (Trigger):** Ein späterer Bar schließt jenseits des Levels und jenseits der Mitte des Absorptions-Bars, mit Body in Trade-Richtung. Der Entry ist eine **Market Order zum Open des nächsten Bars**.
- **Tiers:**
  - **A:** Sweep (≥ 4 Ticks) + Absorption + Trigger-Bar mit Displacement (Body ≥ 50 % der Range, Close-Location ≥ 70 %).
  - **B:** Level-Test oder Sweep ohne Displacement + Absorption + Trigger.
  - B ist implementiert, aber standardmäßig **aus**. Grund: In-Sample kommt B auf PF 1,02 und +0,01 R bei 242 Trades, also keine Edge.
- **Strukturregel:** Signal-Close minus Manipulations-Extrem plus 4 Ticks muss ≤ 100 Ticks sein. Der Stop liegt also jenseits des Sweep-Extrems.
- **Stop:** 100 Ticks (25 Punkte) ab Fill-Preis. Der High-Probability-Stop mit 50 Ticks greift für A-Tier, wenn das Extrem samt 4 Ticks Puffer innerhalb von 50 Ticks liegt. Er ist implementiert, aber **aus**, weil er keinen robusten Vorteil zeigt: In-Sample 13 Trades mit −0,23 R.
- **Trailing:** Kein fester Take-Profit. Bei jedem Bar-Close gilt k = floor(MFE / R). Ab k ≥ 1 wird der Stop auf Entry + (k − 1,25) · R gesetzt und nie gelockert. Der neue Stop wirkt ab dem nächsten Bar.

  | MFE | Stop |
  |---|---|
  | +1R | −0,25R |
  | +2R | +0,75R |
  | +3R | +1,75R |
  | … | … |

## Ergebnisse
| | Training 02/2023–06/2024 | Validierung 07–12/2024 | In-Sample gesamt | **Forward 2025 (einmalig)** |
|---|---|---|---|---|
| Trades | 131 | 27 | 158 | **35** |
| Win-Rate | 35,9 % | 33,3 % | 35,4 % | 37,1 % |
| Profit Factor | 1,47 | 1,24 | 1,43 | **1,70** |
| Netto | +$15.596 | +$1.734 | +$17.329 | **+$6.292** |
| Erwartungswert | +0,24 R | +0,13 R | +0,22 R | **+0,36 R** |
| Ø Gewinn / Ø Verlust | $1.035 / −$393 | $1.003 / −$405 | $1.030 / −$396 | $1.173 / −$407 |
| Max. Drawdown | 6,9 R | 6,2 R | 6,9 R | 6,1 R |
| Long | E +0,42 R | +0,06 R | +0,35 R (n=84) | −0,02 R (n=16) |
| Short | E +0,04 R | +0,21 R | +0,07 R (n=74) | +0,68 R (n=19) |
| Trades pro Handelstag mit Trade | 1,12 | 1,08 | 1,11 | 1,06 |
| Ø Haltedauer | 42 min | 32 min | 40 min | 35 min |
| Volle Stop-Verluste | 44 % | 48 % | 45 % | 46 % |

1 R entspricht 100 Ticks, also $500.

**Tageszeit (In-Sample):**

| Signal | Trades | Erwartungswert |
|---|---|---|
| 09:30–10:00 | 36 | +0,51 R |
| 10:00–10:30 | 63 | +0,11 R |
| 10:30–11:00 | 59 | +0,16 R |

Im Forward ist 09:30–10:00 negativ (n=5). Das Zeitfenster wurde deshalb **nicht** angepasst.

**Regime:**
- Nach Jahr: 2023 E +0,33 R, 2024 E +0,08 R, 2025 E +0,36 R.
- Counter-Trend-Trades (gegen den Vortagestrend Close vs. SMA20) waren in allen In-Sample-Halbjahren positiv. Der Filter wurde trotzdem nicht übernommen, weil er post-hoc gefunden wurde und die Trade-Zahl halbiert.

**Kontrollen:**
- Gleiche Signale in umgekehrter Richtung: +0,04 R.
- Zufällige Entries im Fenster: −0,01 R.

## Robustheit (In-Sample, ein Parameter variiert; Details in `sens_is.txt`)
Alle 93 Varianten haben PF > 1,0. Jede Abweichung um ±1 Rasterschritt hält PF > 1,05.

| Parameter | Ergebnis |
|---|---|
| Stop 60 / 80 / 90 / **100** / 110 / 120 / 150 Ticks | PF 1,01 / 1,16 / 1,30 / **1,43** / 1,39 / 1,15 / 1,13. Plateau bei 90–110, kein Kliff. |
| relVol 1,0–2,5 | PF 1,19–3,4. Alle positiv, höhere Schwelle bedeutet weniger Trades. |
| Effort/Result 0 / 0,8 / **1,0** / 1,25 / 1,5 | PF 1,37 / 1,55 / **1,43** / 1,40 / 1,39 |
| Bänder σ {1} / {2} / **{1,2}** / {1,2,3} | PF 1,44 / 1,43 / **1,43** / 1,46 |
| Multiplikative Bänder aus / 0,25 % / **0,5 %** / 1 % | PF 1,41 / 1,54 / **1,43** / 1,44 |
| Fensterende 10:00 / 10:30 / **11:00** / 11:30 | PF 2,39 / 1,51 / **1,43** / 1,56. Die Verlängerung auf 11:30 fiel in der Validierung durch. |
| Trailing-Lag 1,0 / **1,25** / 1,5 / 1,75 | PF 1,25 / **1,43** / 1,36 / 1,21 |
| Slippage 1 / 2 / 3 Ticks | In-Sample E +0,22 / +0,15 / +0,13 R, Forward PF 1,70 / 1,50 / 1,21 |
| Kommission $4,5 / $6 / $9 round turn | E +0,22 / +0,22 / +0,21 R |
| Nur Long / nur Short | In-Sample PF 1,75 / 1,16. Instabil: im Forward umgekehrt. |

## Probleme und Limitierungen (ehrlich)
1. **Zu wenige Trades für statistische Sicherheit.** Es sind etwa 6–8 Trades pro Monat. Der Forward-Test hat 35 statt der geforderten 60 Trades, der t-Wert liegt bei 1,1. Ein positives Ergebnis kann noch Glück sein.
2. **Die CSV ist abgeschnitten** (genau 1.048.576 Zeilen, das Excel-Limit). Es gibt keine unbenutzten Daten mehr für einen zweiten Out-of-Sample-Test. Weitere Optimierung würde den Forward-Zeitraum kontaminieren und wurde deshalb **nicht** vorgenommen.
3. **Keine GEX-Daten.** Die CSV enthält keine QQQ-GEX-Werte, und Pine hat keine zuverlässige Quelle dafür. GEX-Levels können nur per Input eingetragen werden (für den aktuellen Tag oder als datierte Liste) und werden über die NQ/QQQ-Schlusskurse von 16:00 umgerechnet. **Diese Funktion ist nicht backtestet.** Im CSV-Backtest stammt A-Tier ausschließlich aus VWAP-Levels.
4. **Kein Orderflow.** Delta und Bid/Ask sind nicht verfügbar. Absorption ist ein OHLCV-Proxy (relVol, Wick, Close-Location, Effort vs. Result) und kein echter Absorptionsnachweis.
5. **Ausführung auf 1-Minuten-Basis.** Die Reihenfolge innerhalb eines Bars ist unbekannt. Stops werden konservativ mit dem bereits aktiven Stop geprüft, Trailing wirkt erst ab dem nächsten Bar. Gaps über den Stop werden zum Open gefüllt. Bei schnellen Bewegungen zum NY Open kann die echte Slippage über 1 Tick liegen. Bei 3 Ticks bleibt die Strategie positiv, verliert aber gut die Hälfte des Erwartungswerts.
6. **Pine-Kompilierung nicht verifiziert.** In dieser Umgebung gibt es keinen TradingView-Zugang. Der Code wurde mit einem Pine-Parser (pynescript) syntaktisch geprüft und manuell gegen die Engine abgeglichen. Die Typprüfung durch den TradingView-Compiler steht aus.
7. **Abweichungen TradingView vs. CSV.** Die Rollmethode des Continuous Contract ist unbekannt. Die Volumen-EMAs pro Minute brauchen etwa 10–20 Handelstage Vorlauf und hängen vom Historienbeginn des Charts ab. Kleine Unterschiede in der Trade-Liste sind daher zu erwarten.
8. **Instabile Long/Short-Aufteilung.** Die Gesamt-Edge kann nicht eindeutig einer Seite zugeordnet werden.

## Nächster sinnvoller Schritt
Die eingefrorene Version **unverändert** auf neuen Daten testen, zum Beispiel NQ 1-Minute 2018–2022 oder Daten ab dem 12.12.2025, vollständig exportiert ohne Excel. Erst wenn auch dieser zweite Out-of-Sample-Test positiv ist und mindestens 60 Trades enthält, gilt die Grundidee als bestätigt.
