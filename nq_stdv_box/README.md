# NQ Stdv Box – Indikator & Backtest

## Indikator

| Element | Definition |
|---|---|
| Box | zwischen Open der Kerze um **00:00 ET** (06:00 DE) und Open der Kerze um **08:30 ET** (14:30 DE) |
| Mittellinie | 50 % der Box |
| h | halbe Boxhöhe = Leg „Box-Kante → Mitte“ |
| Level oben | Mitte + k·h (Leg oben → Mitte) |
| Level unten | Mitte − k·h (Leg unten → Mitte) |
| k | 2, 2.25, 2.5, 3.5, 4, 4.25, 4.5 (k = 1 ist die Box-Kante) |

Abgleich mit dem Screenshot: Box 27.918–27.969, Mitte 27.943,5, h ≈ 25,5 →
3.5 = 28.032,75 (rote Linie), 4.0 = 28.045,5, 4.25 = 28.052, 4.5 = 28.058,
2/2.25/2.5 = 27.994/28.001/28.007 bzw. unten 27.892/27.886/27.880. Diese Werte passen zu den Linien im Chart.

* `stdv_box.pine`: TradingView-Indikator (Pine v6) mit Box, Mitte, Level und optionalen Signalen inkl. Alerts.
* `stdv_box.py`: dieselbe Logik in Python, plus Level-Statistik.
* `analysis.py`: Abhängigkeit von der Boxgröße und Test „echte Level vs. Fake-Level“.
* `confluence.py`: Backtest Stdv-Level + VWAP/Psych + Mean Reversion mit Momentum.
* `results/`: alle Tabellen und Trade-Listen als CSV.

```bash
python3 nq_stdv_box/stdv_box.py && python3 nq_stdv_box/analysis.py && python3 nq_stdv_box/confluence.py
```

## Daten

| Datensatz | Zeitraum | Hinweis |
|---|---|---|
| `Dataset_NQ_1min_2022_2025.csv` | 01/2023 – 12/2025, 731 Tage | NQ-Futures, ET, Zeitstempel = Kerzen-**Schluss** → um −1 min auf Kerzen-Open verschoben |
| `1m_data_part*.zip` | 11/2016 – 12/2022, 1.477 Tage | NAS100-CFD (Cash-Index), Brokerzeit = ET + 7 h (über Korrelation mit NQ verifiziert, ρ = 0,93), nur Tick-Volumen. Wird als **Out-of-Sample**-Test genutzt. |

Ausgewertet wird jeweils 08:30–16:00 ET.

## Teil 1 – Level allein (Statistik)

Wahrscheinlichkeit, dass ein Level zwischen 08:30 und 16:00 erreicht wird (NQ 2023–2025):

| k | oben | unten | irgendeine Seite | gegen Box-Richtung |
|---|---|---|---|---|
| 2.0 | 77 % | 72 % | 98 % | 64 % |
| 2.5 | 70 % | 68 % | 93 % | 59 % |
| 3.5 | 58 % | 58 % | 83 % | 49 % |
| 4.5 | 49 % | 50 % | 74 % | 42 % |

* Die Box ist nicht volatilitätsskaliert. Die halbe Boxhöhe liegt im Median bei 22 Punkten (25 % der Tage unter 10 Punkten). An kleinen und mittleren Boxtagen wird 2.0 praktisch immer auf **beiden** Seiten erreicht.
* Rund 50 % aller Tageshochs bzw. -tiefs liegen jenseits von 4.5 Stdv.
* **Reaktionstest:** Wie oft läuft der Preis nach Erreichen eines Levels noch 0,5 Stdv weiter? An echten Leveln ist das genauso oft der Fall wie an Fake-Leveln direkt daneben. Beispiel NQ: 92,6 % gegenüber 92,9 %; nur große Boxen: 80,6 % gegenüber 83,7 %. Ohne Filter halten die Level also nicht besser als zufällige Preise. Das gilt identisch im CFD-Datensatz 2016–2022.

## Teil 2 – Level + Konfluenz + Mean Reversion mit Momentum (`confluence.py`)

**Setup**
1. Erster Touch eines Stdv-Levels am Tag. Oberes Level → Short, unteres Level → Long.
2. Konfluenz-Filter (Toleranz 5 Punkte, getestet auch 2,5 und 10):
   * **VWAP:** Level liegt beim Touch nahe an ETH-VWAP (Anker 18:00), ETH ±1σ, ±2σ, RTH-VWAP (Anker 09:30) oder an einer ab 08:30 verankerten VWAP.
   * **Psych:** Level liegt nahe an einer runden 100er- (bzw. 50er-) Zahl.
3. Momentum: Innerhalb von 15 Bars (1 min) nach dem Touch braucht es eine Kerze, die zurück durch das Level schließt, unter dem Low der Vorkerze (Long: über dem High) und mit passender Farbe. Einstieg zum Schlusskurs dieser Kerze.
4. Stop: Extrem seit dem Touch ± 1 Tick. Ziel: 1R, 2R oder ETH-VWAP. Spätestens 15:59 wird glattgestellt. Es ist immer nur eine Position offen. Kosten: 1 Punkt pro Round-Turn. Wenn Stop und Ziel in derselben Kerze liegen, zählt der Stop.
5. Kontrollen ohne Stdv: nur Psych-100er-Zahlen (`psych_only`) und nur ETH-VWAP ±2σ (`vwapband_only`).

**Ergebnis, Ziel 2R** (Ø R = durchschnittlicher Gewinn pro Trade in Vielfachen des Risikos; |t| < 2 bedeutet statistisch nicht von 0 unterscheidbar)

| Variante | NQ Trades | NQ Winrate | NQ Ø R netto | NQ t | NQ Ø R **vor Kosten** | CFD Trades | CFD Ø R netto | CFD Ø R vor Kosten |
|---|---|---|---|---|---|---|---|---|
| nur Stdv | 1.864 | 33,5 % | −0,066 | −2,0 | +0,002 | 3.863 | −0,139 | +0,017 |
| Stdv + VWAP | 802 | 32,9 % | −0,085 | −1,7 | −0,012 | 2.212 | −0,164 | +0,034 |
| Stdv + Psych 100 | 272 | 33,1 % | −0,068 | −0,8 | −0,009 | 513 | −0,132 | +0,003 |
| Stdv + Psych 50 | 564 | 35,8 % | **+0,008** | 0,1 | +0,068 | 1.038 | −0,141 | −0,007 |
| Kontrolle: nur Psych 100 | 1.207 | 34,2 % | −0,030 | −0,7 | +0,026 | 1.605 | −0,104 | −0,015 |
| Kontrolle: nur VWAP ±2σ | 594 | 32,3 % | −0,086 | −1,5 | −0,027 | 1.271 | −0,172 | −0,029 |

Mit Ziel 1R oder Ziel VWAP sieht das Bild gleich aus (siehe `results/confluence_summary.csv`). Die Toleranzen 2,5 und 10 Punkte ändern ebenfalls nichts Wesentliches.

**Fazit**
* Vor Kosten liegt der Erwartungswert **aller** Varianten bei ≈ 0 R. Das Setup hat also keine eigene Kante, und nach realistischen Kosten wird es negativ.
* **VWAP-Konfluenz verbessert nichts** (NQ −0,085 R gegenüber −0,066 R ohne Filter). Getrennt nach VWAP-Linie ist auch keine einzelne Linie in beiden Datensätzen positiv.
* **Psych 50 war auf NQ 2023–2025 als einzige Variante leicht positiv** (+0,008 R netto, 564 Trades), aber nicht signifikant (t = 0,14). Out-of-Sample im CFD 2016–2022 ist sie negativ (−0,141 R). Ein Teil davon kommt daher, dass runde Zahlen beim Cash-Index woanders liegen als beim Future. Insgesamt reicht das nicht als Beleg.
* Die Stdv-Level fügen gegenüber den Kontrollen (Psych bzw. VWAP-Band allein) keinen messbaren Mehrwert hinzu.

## Einschränkungen

* Das „Momentum“ ist hier eine einfache, mechanische Regel (Rückschluss durch das Level plus Bruch des Lows bzw. Highs der Vorkerze). Ein diskretionärer Trader filtert anders, etwa über Volumen-Delta, SMT mit ES oder die Marktstruktur.
* Welche VWAP-Linien im Screenshot genau verwendet werden (gelb/grün/blau), ist aus dem Bild nicht eindeutig. Getestet wurden ETH-, RTH- und eine ab 08:30 verankerte VWAP sowie die ETH-σ-Bänder.
* Das CFD-Volumen ist Tick-Volumen, die VWAP dort also nur angenähert.
