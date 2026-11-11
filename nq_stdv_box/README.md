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

## Teil 3 – Box-Filter, aggressive Entries, Box-Richtung, erste Reaktion, alte Level (`followup.py`)

Ergebnisse liegen in `results/followup/`. NQ 2023–2025 dient zur Suche, CFD 2016–2022 zur Gegenprobe.

**Box-Filter.** Gemessen wird die Boxhöhe im Verhältnis zur ATR14 (Durchschnitt der täglichen ETH-Range der letzten 14 Tage). Der Median liegt bei 0,14 ATR. Filterstufen: ≥ 0,1 (≈ 60 % der Tage), ≥ 0,2 (≈ 35 %), ≥ 0,3 (≈ 20 %).

**Entries.** Limit direkt am Level mit Stop 0,25 h oder 0,5 h dahinter (aggressiv), oder Momentum-Entry wie in Teil 2. Ziele: 2R, 3R, 5R, 8R, Box-Mitte oder Box-Kante. Kosten: 0,5 Punkte (Limit) bzw. 1 Punkt (Momentum).

### Box-Filter (Ø R über alle 18 Entry/Ziel-Kombinationen)

| Box ≥ ATR × | 0 | 0,1 | 0,2 | 0,3 |
|---|---|---|---|---|
| NQ 2023–2025 | −0,164 | −0,076 | −0,063 | **+0,006** |
| CFD 2016–2022 | −0,305 | −0,172 | −0,124 | **−0,087** |

Der Filter wirkt in beiden Datensätzen deutlich und gleichmäßig. Der Hauptgrund: Bei winzigen Boxen sind die Stops so eng, dass Kosten und Rauschen jeden Trade auffressen.

### Aggressive Entries und hohes Chance-Risiko-Verhältnis (nur Box ≥ 0,3 ATR)

| Entry → Ziel | NQ Winrate | NQ Ø R | CFD Winrate | CFD Ø R |
|---|---|---|---|---|
| Limit, Stop 0,25 h → **Box-Mitte** (≈ 6–9R) | 13,3 % | **+0,123** | 14,4 % | **+0,063** |
| Limit, Stop 0,25 h → 8R | 13,7 % | +0,003 | 15,5 % | +0,038 |
| Limit, Stop 0,5 h → 8R | 20,8 % | +0,045 | 20,2 % | +0,034 |
| Momentum → Box-Mitte | 21,6 % | +0,203 | 19,0 % | −0,138 |
| Momentum → 2R | 35,2 % | −0,010 | 32,2 % | −0,161 |

Nur 3 von 72 Kombinationen sind in beiden Datensätzen positiv, und keine ist statistisch signifikant (|t| < 1). Bei 72 Versuchen sind drei positive Treffer auch durch Zufall zu erwarten. Der beste Kandidat ist „große Box, Limit am Level, enger Stop, Ziel Mitte“: Winrate 13–14 % bei ca. +0,06 bis +0,12 R. Das ist ein Lead für Forward-Tests, aber noch kein belastbares Edge.

### Box-Richtung (bearish = 00:00-Open über 08:30-Open)

Die Winrate unterscheidet sich je Richtung nur um 1–5 Prozentpunkte. Auf NQ liefen Trades in Box-Richtung meist etwas besser (z. B. Momentum 3R, Box ≥ 0,2: +0,105 R in Box-Richtung gegenüber −0,105 R dagegen). Im CFD-Datensatz ist es gleich oder umgekehrt (−0,162 gegenüber −0,142). → **Kein stabiler Effekt.**

### Erste Reaktion als Tages-Bias

Das erste Level-Ereignis nach 08:30 ist entweder der Touch der gegenüberliegenden Box-Kante (00:00-Open) oder das 2.0-Level hinter der 08:30-Kante, je nachdem, was zuerst kommt. Als Rejection zählt, wenn der Preis 0,5 h zurückläuft, bevor er 0,5 h durchbricht. Ein Break ist das Gegenteil.

* Auf NQ folgte auf eine Rejection am 2.0-Level meist **keine** Fortsetzung: Nur 42 % der Tage schlossen in Rejection-Richtung, und Gegen-Setups waren klar positiv (+0,79 R, t = 2,3).
* Im CFD-Datensatz kehrt sich das komplett um: Gegen-Setups −0,45 R (t = −3,4), und die Schlusskurse liegen bei 52 % in Rejection-Richtung, also beim Münzwurf.
* Der Beispielfall „Box-Kante von innen rejected → danach Longs besser“ ist in beiden Datensätzen nicht positiv (NQ −0,27 R, CFD −0,20 R mit Limit → Mitte).

→ **Die erste Reaktion sagt nichts Verlässliches über den restlichen Tag aus.** Der NQ-Effekt war Zufall bzw. Regime.

### Alte Box- und Stdv-Level als POI (1–3 Tage zurück)

Untersucht wurde der erste Touch jedes alten Levels zwischen 08:30 und 16:00. Als Rejection zählt, wenn der Preis 0,05 ATR (bzw. 0,1 ATR) zurückläuft, bevor er dieselbe Strecke durchbricht. Zum Vergleich dienen Fake-Level: dieselben Level, um 0,03–0,08 ATR verschoben.

| | NQ echt | NQ fake | CFD echt | CFD fake |
|---|---|---|---|---|
| Box-Kante Rejection % | 69,3 | 68,8 | 66,0 | 67,3 |
| Mitte Rejection % | 67,3 | 65,9 | 65,7 | 67,5 |
| Stdv-Level Rejection % | 69,1 | 68,9 | 65,6 | 65,2 |

→ **Alte Level reagieren genauso wie beliebige Preise.** Die hohe Rejection-Quote von ≈ 66–69 % gilt für **jeden** Preis und ist kein Merkmal dieser Level. Ein Fade daran ist durchgehend negativ.

### Gesamtfazit Teil 3

1. Winzige Boxen herauszufiltern ist sinnvoll und wirkt robust.
2. Selbst mit Filter bleibt das Edge nahe 0. Am vielversprechendsten ist „große Box (≥ 0,3 ATR), Limit am Level, Stop 0,25 h, Ziel Box-Mitte“: in beiden Datensätzen leicht positiv, aber nicht signifikant.
3. Box-Richtung, erste Reaktion und alte Level als POI liefern keinen Mehrwert, der die Gegenprobe übersteht.

## Teil 4 – ICT-Konfluenz (FVG / OB / RB) und nur 4.5-Level (`ict.py`)

Ergebnisse liegen in `results/ict/ict_and_45_grid.csv`.

**Wie die ICT-Zonen erkannt werden** (auf 5-Minuten-Kerzen aus den 1-Minuten-Daten):

| Zone | bullisch | bärisch |
|---|---|---|
| FVG | Low[i] > High[i−2], Zone = Lücke | High[i] < Low[i−2], Zone = Lücke |
| Order Block | letzte rote Kerze vor einer grünen Displacement-Kerze, die über ihr High schließt **und** ein bullisches FVG erzeugt | spiegelbildlich |
| Rejection Block | Swing-Low (2 Kerzen je Seite) mit unterem Docht ≥ 50 % der Range, Zone = Docht | Swing-High mit oberem Docht ≥ 50 %, Zone = Docht |

Eine Zone gilt, sobald das Muster abgeschlossen ist, und bleibt gültig bis zum ersten 5-Minuten-Schlusskurs jenseits der Zone, höchstens 48 h. Konfluenz heißt: Das Level liegt beim ersten Touch in einer gültigen Zone passender Polarität (Toleranz ± 2,5 Punkte). Shorts brauchen eine bärische Zone, Longs eine bullische.

**Box-Kanten:** Die 00:00-Kante zählt beim Touch von innen. Die 08:30-Kante zählt beim ersten Retest, nachdem der Preis sich 0,5 h entfernt hat.

### A) ICT-Konfluenz an Box-Kanten und Stdv-Leveln

Ø R pro Trade, gemittelt über die Entry/Ziel-Kombinationen, Box ≥ 0,2 ATR:

| | ohne ICT | FVG | OB | RB | irgendeine ICT-Zone |
|---|---|---|---|---|---|
| NQ (Box-Kanten + Stdv) | −0,114 | −0,067 | −0,132 | −0,143 | −0,080 |
| CFD (Box-Kanten + Stdv) | −0,124 | −0,097 | −0,158 | +0,005 | −0,082 |

* Box-Kanten sind mit und ohne ICT klar negativ (≈ −0,25 R im Schnitt).
* An den Stdv-Leveln verbessert „irgendeine ICT-Zone“ in beiden Datensätzen leicht, um ≈ +0,03 bis +0,04 R. Beste Kombination: Stdv + ICT, Box ≥ 0,2, Limit mit Stop 0,25 h → Mitte. Das ergibt NQ +0,149 R (t = 0,8) und CFD +0,081 R (t = 0,7), ohne ICT −0,010 bzw. −0,027.
* Einzelne Zonentypen sind nicht konsistent. RB ist im CFD gut, auf NQ nicht. OB ist in beiden schlechter als ohne Filter.

### B) Nur die 4.5-Level, feste Ziele gegen Trailing

Exit-Varianten: fest 2R / 3R / 5R / Box-Mitte, Trailing 1R (ab +1R Stop 1R hinter dem besten Kurs), Trailing 2R (ab +2R), Break-even ab +1R mit Ziel Mitte.

Ohne Filter verlieren die 4.5-Level stark (−0,3 R). Mit Box-Filter (gemittelt):

| | Winrate fest | Winrate Trailing | Ø R fest | Ø R Trailing |
|---|---|---|---|---|
| NQ, Box ≥ 0,2 | 19,5 % | 25,5 % | −0,202 | −0,161 |
| CFD, Box ≥ 0,2 | 24,3 % | 28,9 % | −0,072 | −0,050 |

Trailing hebt die Winrate um 4–6 Prozentpunkte und ist im Schnitt etwas besser als feste Ziele. Ohne ICT bleibt aber beides negativ.

**4.5 + irgendeine ICT-Zone + Box ≥ 0,2 ATR + Limit-Entry** ist die bisher konsistenteste Kombination. 12 von 14 Exit-Varianten sind in **beiden** Datensätzen positiv:

| Exit | NQ (25 Trades) Ø R | CFD (84 Trades) Ø R |
|---|---|---|
| Limit 0,25 h → Mitte | +1,22 | +0,44 |
| Limit 0,25 h → BE@1R → Mitte | +0,86 | +0,47 |
| Limit 0,5 h → Trailing 2R | +0,28 | +0,30 |
| Limit 0,5 h → Trailing 1R | +0,23 | +0,08 |
| Limit 0,25 h → 5R fest | +0,14 | +0,25 |

**Aber:** Das sind nur ≈ 8 (NQ) bzw. ≈ 14 (CFD) Trades pro Jahr. Kein Wert ist signifikant (alle t < 1,2), und die Varianten mit Ziel Mitte leben von wenigen großen Gewinnern (Winrate 8–12 %). Mit Box ≥ 0,3 bricht das Ergebnis im CFD-Datensatz ein. Das ist ein Kandidat für einen Forward-Test, aber noch kein bestätigtes Edge.
