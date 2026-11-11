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

## Teil 5 – „Erste Reaktion + zweiter Sweep“ (Setup wie im Gold-Chart, `sweep.py`)

Ergebnisse liegen in `results/sweep/`. Getestet ist NQ bzw. der NAS100-CFD; Gold-Daten sind nicht vorhanden.

**Regeln**
1. **Sweep & Reclaim:** Der Preis kommt von der einen Seite, handelt durch das Level, und innerhalb von ≤ 10 1-Minuten-Kerzen (Variante: ≤ 3) **schließt** eine Kerze wieder auf der Ausgangsseite.
2. **Erste Reaktion des Tages:** der erste Sweep & Reclaim
   * des ganzen Clusters 2–2.25–2.5 (äußerstes Level 2.5 gesweept),
   * oder des Clusters 4–4.25–4.5,
   * oder einzeln des 3.5-Levels,
   * oder einer Box-Kante. Die 08:30-Kante zählt erst, wenn der Preis sich 0,5 h entfernt hat, denn er eröffnet genau dort.

   Daraus ergibt sich die Richtung: Ist Support gesweept und reclaimed → bullisch, ist es Resistance → bärisch.
3. **Entry:** Der nächste Sweep & Reclaim eines **anderen** Levels (Stdv oder Box-Kante) in dieselbe Richtung. Einstieg zum Schlusskurs der Reclaim-Kerze.
4. **SL:** hinter dem Extrem dieses Sweeps (+ 1 Tick).
5. **TP:** das Hoch bzw. Tief zwischen erster Reaktion und zweitem Sweep („Zwischenhoch“). Variante: der nächste bestätigte 1-Minuten-Pivot (5/5).
6. Nur Setups mit geplantem RR > 1. Maximal ein Trade pro Tag, Kosten 1 Punkt.
7. **Kontrolle:** der erste Sweep & Reclaim irgendeines Levels, **ohne** die Bedingung „erste Reaktion“, mit denselben SL/TP-Regeln.

**Ergebnis (Ø R pro Trade)**

| Variante | NQ alle | NQ Box ≥ 0,2 | CFD alle | CFD Box ≥ 0,2 |
|---|---|---|---|---|
| Setup, TP Zwischenhoch | −0,28 (689) | −0,21 (250) | −0,38 (1.387) | −0,10 (531) |
| Setup, TP Pivot | −0,22 (674) | −0,32 (247) | −0,30 (1.348) | −0,05 (522) |
| Setup, auch gleiches Level erlaubt | −0,31 | −0,11 | −0,37 | −0,15 |
| Setup, Reclaim ≤ 3 Kerzen | −0,30 | −0,24 | −0,34 | −0,04 |
| Kontrolle ohne erste Reaktion | −0,39 (704) | −0,35 (264) | −0,39 (1.427) | −0,33 (572) |

Winrate 21–28 % bei durchschnittlich geplantem RR von 5–10.

* Die Bedingung „erste Reaktion“ verbessert das Ergebnis gegenüber der Kontrolle in beiden Datensätzen, um ≈ +0,1 bis +0,3 R. Insgesamt bleibt das Setup aber negativ.
* **Größter Bremsklotz sind sehr enge Stops.** Trades mit SL ≤ 3 Punkten liegen bei −0,6 bis −0,8 R, weil Kosten und Rauschen dominieren. Mit **SL ≥ 6 Punkten** (nachträglich gewählter Filter):

| SL ≥ 6 Pkt | NQ alle | NQ Box ≥ 0,2 | CFD alle | CFD Box ≥ 0,2 |
|---|---|---|---|---|
| Setup, TP Zwischenhoch | −0,05 (361) | +0,04 (165) | +0,23 (353) | +0,33 (188) |
| Setup, TP Pivot | +0,04 (348) | −0,05 (167) | +0,09 (381) | +0,22 (201) |
| Kontrolle | −0,17 (303) | −0,29 (151) | −0,04 (341) | +0,01 (205) |

  Auf NQ liegt das ungefähr bei 0, im CFD leicht positiv (t ≈ 1,3–1,6). In beiden Datensätzen ist es besser als die Kontrolle. Der Mindest-Stop wurde allerdings nachträglich festgelegt, und 6 Punkte entsprechen bei den niedrigeren CFD-Kursen 2016–2022 relativ mehr Risiko als bei NQ 2023–2025.
* Erste Reaktion am Cluster 4–4.5 war in beiden Datensätzen positiv (NQ +0,24 R, CFD +0,72 R), aber nur bei 25 bzw. 29 Trades. Erste Reaktion an der Box-Kante (der häufigste Fall) ist in beiden negativ.

## Teil 6 – Systematische Suche nach den besten 5 Strategien (`search_events.py`, `search.py`)

Ergebnisse liegen in `results/search/`. Der erste, fehlerhafte Lauf ist in `results/search_v1_optimistic/` dokumentiert.

### Aufbau

**Ereignistabelle.** Für jeden Tag (08:30–16:00) und jedes Level (Box-Kanten, Stdv ±2 … ±4.5, jeweils als Support **und** als Resistance) werden bis zu 3 Berührungen erfasst. Daraus ergeben sich rund 120.000 mögliche Einstiege im CFD-Datensatz und 62.000 auf NQ.

| Baustein | Varianten |
|---|---|
| Entry | **T** = Limit am Level · **R** = Reclaim (durchhandeln, dann 1-Minuten-Schluss zurück innerhalb von 10 Kerzen) |
| Stop (T) | 0,25 h · 0,5 h · 0,03 ATR · 0,06 ATR hinter dem Level |
| Stop (R) | Struktur (Sweep-Extrem) · Struktur mit mindestens 0,02 ATR · 0,03 ATR · 0,06 ATR |
| Exit | 1R · 1,5R · 2R · 3R · 5R · Box-Mitte · Trailing 1R · Trailing 2R · BE@1R → 3R · BE@1R → Mitte |
| Box-Filter | ≥ 0 / 0,1 / 0,2 ATR |
| Level-Gruppe | alle · Kanten · 00:00-Kante · Cluster 2–2.5 · 3.5 · Cluster 4–4.5 · alle Stdv · außen (3.5–4.5) |
| Mindest-Stop | 0 / 0,01 / 0,02 / 0,03 ATR |
| Zusatzfilter (bis zu 2) | natürliche Seite / Flip (Level als Retest) · mit / gegen Box-Richtung · Tageszeit (5 Fenster) · ICT-Zone · VWAP gedehnt / mit VWAP · vorherige Reaktion gleiche Richtung / Gegenrichtung / keine · erster Touch / wiederholt · Psych-50 · Momentum-Kerze |

Das ergibt rund **830.000 Kombinationen** mit mindestens 0,5 Trades pro Tag. Die Statistik läuft auf **Tagesbasis**, sodass mehrere Trades am selben Tag den t-Wert nicht aufblähen.

**Konservative Ausführung.**
* Limit-Orders füllen nur, wenn der Preis einen Tick **durch** das Level handelt.
* Liegen Stop und Ziel in derselben Kerze, zählt der Stop.
* Wird ein Trailing- oder Break-even-Stop in einer Kerze nachgezogen und erreicht dieselbe Kerze ihn, gilt er als ausgelöst.
* Kosten: NQ 0,5 Punkte (Limit) bzw. 1 Punkt (Market). CFD: derselbe Betrag relativ zur ATR.

**Drei getrennte Stufen.** A = Suche auf CFD 2016–2020. B = Bestätigung auf CFD 2021–2022. C = einmaliger Endtest auf NQ 2023–2025. Die Auswahl wurde vor dem Endtest committet.

### Ein Fehler im ersten Lauf (transparent dokumentiert)

Im ersten Lauf bestand eine Strategie (Limit am Retest-Level, Trailing 1R) den NQ-Endtest mit t = 3,05. Das war ein **Simulationsartefakt**: Mit 1-Minuten-Kerzen und einem Stop von nur ≈ 10 Punkten wurde ein innerhalb der Kerze nachgezogener Trailing-Stop zu optimistisch behandelt, und Limit-Fills bei bloßer Berührung waren ebenfalls zu günstig. Nach der konservativen Korrektur ist Trailing 1R das **schlechteste** Ausstiegsmodell (Ø t = −6,9). Der gesamte Ablauf wurde danach mit derselben mechanischen Auswahlregel wiederholt.

### Ergebnis des 3-Stufen-Tests

* Stufe A: 231 von 829.538 Kombinationen bestanden (t ≥ 2,5 und mindestens 3 von 4 Jahren positiv).
* Stufe B: 43 davon bestätigt (20 %, bei reinem Zufall wären 6,7 % zu erwarten). Fast alle stammen aus einer Familie: **Reclaim am Cluster 4–4.5 mit ICT-Zone, Stop 0,06 ATR, Ziel 1,5–3R**.
* Stufe C (NQ, einmalig):

| | Strategie | CFD 2016–22 Ø R (t) | **NQ 2023–25 Ø R (t)** | Trades/Woche NQ |
|---|---|---|---|---|
| S1 | Reclaim, 4–4.5, Box ≥ 0,1, ICT + vorher Gegenreaktion, Stop 0,06 ATR, 1,5R | +0,076 (2,4) | **−0,028 (−0,6)** | 4,4 |
| S2 | Reclaim, 4–4.5, Box ≥ 0,1, ICT + erster Touch, Stop 0,06 ATR, 3R | +0,202 (2,9) | **−0,040 (−0,4)** | 2,1 |
| S3 | Reclaim, 4–4.5, Box ≥ 0,1, natürliche Seite + ICT, Stop 0,06 ATR, 2R | +0,113 (2,3) | **−0,001 (0,0)** | 2,7 |
| S4 | Reclaim, 00:00-Kante, mit VWAP + vorher Gegenreaktion, Struktur-Stop ≥ 0,03 ATR, 3R | +0,163 (2,6) | **−0,173 (−2,0)** | 2,6 |
| S5 | Reclaim, 3.5–4.5, Box ≥ 0,1, mit Box-Richtung + ICT, Stop 0,03 ATR, 3R | +0,167 (2,4) | **+0,011 (0,1)** | 2,2 |

**Keine der 5 Strategien besteht den Out-of-Sample-Test.** Auf NQ sind sie mit echten Leveln auch nicht besser als mit Fake-Leveln (verschoben um ± 0,07 ATR).

### Gegenprobe: dieselbe Suche auf Fake-Leveln (alle Daten)

Dieselben ≈ 825.000 Kombinationen wurden auf CFD 2016–2022 **und** NQ 2023–2025 zusammen ausgewertet, einmal mit den echten Leveln und zweimal mit Leveln, die um ± 0,07 ATR verschoben sind:

| | bester t-Wert (alle Daten) | Kombinationen mit t ≥ 3 | „robuste“ Kombinationen* |
|---|---|---|---|
| **Echte Level** | **3,14** | 5 | 62 |
| Fake +0,07 ATR | 3,18 | 8 | 19 |
| Fake −0,07 ATR | 2,47 | 0 | 16 |

\* In beiden Datensätzen t ≥ 1,5 und mindestens 7 von 9 Jahren positiv.

Die beste Strategie auf den echten Leveln ist **nicht besser als die beste auf zufällig verschobenen Leveln**. Bei 825.000 Versuchen ist ein t von etwa 3 reiner Suchgewinn. Ein echtes Edge müsste deutlich darüber liegen (≈ 4,5–5). Einziger schwacher Hinweis: Mit echten Leveln gibt es 3- bis 4-mal so viele „robuste“ Kombinationen. Das sind aber wenige, stark überlappende Familien.

### Top 5 über alle Daten (in-sample, nur als Kandidaten für einen Forward-Test)

Ausgewählt aus den 62 robusten Kombinationen nach t-Wert, mit geringer gegenseitiger Korrelation und mindestens 2 Trades pro Woche in beiden Datensätzen (mit maximal einer offenen Position):

| | Regel | CFD Ø R | NQ Ø R | Winrate | Trades/Woche | Ø R auf Fake-Leveln (CFD / NQ) |
|---|---|---|---|---|---|---|
| K1 | **Limit** an Stdv-Level, 11:00–13:30, in ICT-Zone, Stop 0,06 ATR (≥ 0,01), Ziel **Box-Mitte** | +0,046 | +0,215 | 29–33 % | 3,3–3,6 | −0,02 … +0,01 / +0,07 … +0,08 |
| K2 | **Reclaim** am 3.5-Level mit Momentum-Kerze, vorher Gegenreaktion, Struktur-Stop ≥ 0,02 ATR, Ziel **Box-Mitte** | +0,144 | +0,196 | 41–44 % | 2,3–2,4 | −0,05 … −0,04 / −0,15 … +0,03 |
| K3 | **Limit** an 3.5–4.5, 11:00–13:30, erster Touch, Stop 0,06 ATR, Ziel **3R** | +0,055 | +0,137 | 27–29 % | 2,0–2,4 | +0,01 / −0,16 … +0,02 |
| K4 | **Reclaim** an 3.5–4.5, Box ≥ 0,2 ATR, ICT-Zone, Struktur-Stop ≥ 0,02 ATR, Ziel **5R** | +0,107 | +0,165 | 22–24 % | 2,4–2,9 | +0,01 … +0,11 / −0,07 … +0,14 |
| K5 | wie K1, Ziel **5R** | +0,072 | +0,140 | 20–22 % | 4,9–5,4 | 0,00 … +0,02 / +0,03 … +0,10 |

Am saubersten ist **K2**: in beiden Datensätzen einzeln p < 0,03, Winrate über 40 %, auf Fake-Leveln negativ. Aber auch K2 ist das Maximum aus 825.000 Versuchen und damit **nicht** von Zufall unterscheidbar. Diese 5 sind Hypothesen für einen Forward-Test, keine bestätigten Strategien.

### Stop- und Exit-Modelle im Überblick (Ø t-Wert über alle Kombinationen, Stufe A / B)

| Stop | Ø t | | Exit | Ø t |
|---|---|---|---|---|
| 0,06 ATR | −2,3 / −2,0 | | Box-Mitte | −0,8 / −1,0 |
| Struktur (mind. 0,02 ATR) | −2,8 / −2,8 | | 5R | −0,8 / −1,1 |
| Struktur | −2,9 / −2,8 | | 3R | −1,3 / −1,5 |
| 0,5 h | −3,4 / −2,9 | | 2R | −2,1 / −2,1 |
| 0,03 ATR | −4,8 / −4,0 | | 1,5R | −3,0 / −2,6 |
| 0,25 h | −5,1 / −4,1 | | 1R | −4,7 / −3,7 |
| | | | Trailing 2R | −4,4 / −3,6 |
| | | | BE@1R → Mitte | −4,6 / −4,2 |
| | | | BE@1R → 3R | −6,0 / −4,8 |
| | | | Trailing 1R | −6,9 / −5,7 |

Als Muster stabil sind:
* Weite Stops (0,06 ATR ≈ 19 NQ-Punkte, oder Struktur mit Mindestabstand) sind besser als enge.
* Weite Ziele (Mitte, 3–5R) sind besser als nahe.
* Break-even und enges Trailing kosten deutlich. Unter konservativer Annahme wird man auf 1-Minuten-Basis zu oft ausgestoppt.
* Reclaim-Entries sind besser als blinde Limits.
* Größere Boxen und äußere Level (3.5–4.5) sind besser als kleine Boxen und der Cluster 2–2.5.

Im Durchschnitt bleibt trotzdem alles negativ.

## Teil 7 – K2 als TradingView-Strategie, mehr Trades, 50k-Eval

### `k2_strategy.pine`

Das ist eine Pine-v6-**Strategie** für den **1-Minuten-Chart**. Sie zeichnet Box, Mitte und Level, setzt die K2-Trades mit Stop und Ziel, und der Strategy Tester zeigt die Statistik. Die Regeln stehen im Kopf des Skripts und entsprechen dem Python-Backtest. Die Lockerungen sind als Einstellungen schaltbar, die Positionsgröße ergibt sich aus „Risiko pro Trade ($)“.

Kleine Abweichungen zum Backtest sind möglich: TradingView nimmt innerhalb einer Kerze eine eigene Reihenfolge an, die Daten bzw. der Kontrakt-Rollover können abweichen, und die ATR kommt aus TradingView-Tageskerzen.

### Kriterien lockern (`k2_relax.py`, `results/k2/k2_relaxations.csv`)

| Variante | CFD Trades/Wo | CFD Ø R | CFD R/Woche | NQ Trades/Wo | NQ Ø R | NQ R/Woche |
|---|---|---|---|---|---|---|
| **K2 Basis** | 2,4 | +0,144 | 0,35 | 2,3 | +0,196 | 0,46 |
| ohne „vorherige Gegenreaktion“ | 2,6 | +0,142 | 0,37 | 2,5 | +0,162 | 0,41 |
| Reclaim-Fenster 30 statt 10 Kerzen | 2,9 | +0,148 | 0,43 | 2,7 | +0,137 | 0,38 |
| **K2+ : bis 6 statt 3 Touches pro Level** | **3,7** | +0,114 | 0,42 | **3,6** | +0,145 | **0,52** |
| K2-breit: ohne Vorreaktion, Fenster 30, 6 Touches | 4,6 | +0,090 | 0,42 | 4,5 | +0,082 | 0,37 |
| Momentum nur „Kerzenfarbe“ | 4,8 | −0,019 | −0,09 | 4,9 | +0,075 | 0,36 |
| zusätzlich Level 4–4.5 | 9,1 | −0,009 | −0,08 | 8,7 | −0,010 | −0,09 |
| alle Stdv-Level bzw. ohne Momentum | 10–30 | ≤ 0 | < 0 | 10–30 | ≈ 0 | ≤ 0 |

* Die **Momentum-Kerze** und das **3.5-Level** sind der Kern. Lockert man sie, ist der Ertrag weg.
* Sinnvoll lockern lässt sich nur die **Zahl der Touches pro Level** (K2+): ≈ 3,6 Trades pro Woche, Ertrag pro Woche gleich oder besser.
* K2-breit bringt ≈ 4,5 Trades pro Woche, aber nur noch ≈ 0,09 R pro Trade. Es ist damit deutlich kostenempfindlicher.
* Diese Lockerungen wurden im Nachhinein auf denselben Daten gewählt und sind damit genauso unbestätigt wie K2 selbst.

### 50k-Eval-Simulation (`eval_sim.py`, `results/k2/eval_simulation*.csv`)

Monte-Carlo-Simulation: Handelstage werden zufällig aus dem Backtest gezogen (CFD + NQ, inklusive Tagen ohne Trade), mit festem Dollar-Risiko pro Trade.

**Annahmen (bitte an deine Firma anpassen):**
* **Regel A** (Topstep-ähnlich): Ziel +3.000 $, maximaler Verlust 2.000 $ nachlaufend auf den Tagesend-Stand (endet beim Startkapital), bester Tag ≤ 50 % des Gewinns.
* **Regel B** (Apex-ähnlich): Ziel +3.000 $, 2.500 $ nachlaufend auf das Hoch. Hier wird nur nach jedem geschlossenen Trade geprüft, was leicht optimistisch ist. Keine Konsistenzregel.

Bestehenswahrscheinlichkeit binnen 250 Handelstagen (in Klammern: mittlere Dauer in Handelstagen):

**K2+ (≈ 3,6 Trades/Woche)**

| Risiko pro Trade | Regel A: Kante wie Backtest | A: halbe Kante | A: keine Kante | Regel B: wie Backtest | B: halbe Kante | B: keine Kante |
|---|---|---|---|---|---|---|
| 0,2 % (100 $) | 44 % (144) | 29 % | 17 % | 49 % (144) | 33 % | 20 % |
| **0,3 % (150 $)** | **50 % (98)** | 34 % | 22 % | **59 % (94)** | 44 % | 31 % |
| 0,4 % (200 $) | 45 % (70) | 32 % | 21 % | 57 % (59) | 43 % | 32 % |
| 0,5 % (250 $) | 41 % (54) | 30 % | 20 % | 53 % (42) | 42 % | 32 % |
| 0,75 % (375 $) | 34 % (36) | 24 % | 18 % | 47 % (21) | 40 % | 32 % |
| 1,0 % (500 $) | 28 % (30) | 22 % | 16 % | 44 % (13) | 39 % | 34 % |

**K2 Basis (≈ 2,3 Trades/Woche):** Das Optimum liegt etwas höher, bei 0,3–0,4 %: Regel A ≈ 48 % (≈ 100–130 Tage), Regel B ≈ 57–60 % (≈ 90–120 Tage).

**Ergebnis:**
* Das beste Risiko liegt bei **≈ 0,3–0,4 % pro Trade (150–200 $)**. Beim mittleren Stop von ≈ 22,5 NQ-Punkten sind das ≈ 3–4 MNQ.
* Höheres Risiko geht schneller, senkt aber die Bestehensquote deutlich. Bei 1 % sind es nur noch 28 % (Regel A) bzw. 44 % (Regel B).
* Selbst wenn die Backtest-Kante echt wäre, läge die Bestehensquote pro Versuch nur bei **≈ 50 % (A) bzw. ≈ 60 % (B)**, bei einer Dauer von 4–6 Monaten. Ohne echte Kante sind es ≈ 20 % bzw. ≈ 30 %. Ein verlässlich konsistentes Bestehen gibt diese Strategie nicht her, weil der Erwartungswert (≈ 0,1–0,2 R pro Trade bei 2–4 Trades pro Woche) im Verhältnis zum erlaubten Drawdown zu klein ist.

## Teil 8 – K1: Kennzahlen, Lockerungen, 50k-Eval, TradingView-Strategie (`k1_study.py`, `k1_strategy.pine`)

Ergebnisse liegen in `results/k1/`.

**K1-Regeln:** Limit-Order an einem Stdv-Level (unter der Box Long, über der Box Short), nur Touches zwischen 11:00 und 13:30 ET, Level liegt in einer gültigen ICT-Zone passender Richtung (FVG / OB / RB auf 5 Minuten), Stop 0,06 ATR hinter dem Level, Ziel Box-Mitte, maximal 3 Touches pro Level und Tag, 15:59 flat.

### Kennzahlen

| | NQ 2023–2025 | CFD 2016–2022 |
|---|---|---|
| Handelstage | 722 | 1.466 |
| Trades (pro Woche) | 471 (3,3) | 1.068 (3,6) |
| Long / Short | 241 / 230 | 533 / 535 |
| Winrate | 33,3 % | 28,8 % |
| Geplantes Chance-Risiko-Verhältnis (Median) | ≈ 3,5 | ≈ 3,8 |
| Ø Gewinner / Ø Verlierer | +2,70 R / −1,03 R | +2,68 R / −1,02 R |
| **Ø R pro Trade** | **+0,215** | **+0,046** |
| Σ R | +101,1 | +48,7 |
| Profit-Faktor | 1,31 | 1,06 |
| t-Wert (Tagesbasis) | 2,1 | 0,7 |
| Max. Drawdown | −23,4 R | −47,9 R |
| Längste Verlustserie | 15 | 19 |
| Stop (Median) | 16,8 Punkte | 9,7 Punkte |
| Long Ø R / Short Ø R | +0,11 / +0,32 | +0,11 / −0,02 |

Summe R pro Jahr: 2017 −26,3 · 2018 +42,7 · 2019 +4,2 · 2020 +24,1 · 2021 −4,7 · 2022 +6,8 · 2023 +37,9 · 2024 +29,7 · 2025 +33,5.

**K1 ist deutlich wackliger als K2.**
* Im CFD-Datensatz ist der Ertrag fast null (+0,046 R, t = 0,7). Das gute Gesamtbild kommt praktisch nur aus NQ 2023–2025.
* Nach Level aufgeschlüsselt widersprechen sich die Datensätze. Auf NQ tragen die Level 2–2.5 (+0,38 bis +0,74 R), und 4–4.5 verlieren (−0,09 bis −0,64 R). Im CFD ist es umgekehrt: 4–4.5 sind positiv, 2.25 und 3.5 negativ. Ein echtes Muster sähe in beiden Datensätzen ähnlich aus.

### Lockerungen

| Variante | CFD Trades/Wo | CFD Ø R | NQ Trades/Wo | NQ Ø R | NQ R/Woche |
|---|---|---|---|---|---|
| **K1 Basis** | 3,6 | +0,046 | 3,3 | +0,215 | 0,70 |
| bis 6 Touches pro Level | 5,8 | +0,039 | 5,4 | +0,064 | 0,34 |
| Zeit 10:30–14:00 | 5,4 | −0,006 | 4,7 | +0,035 | 0,16 |
| Zeit 10:00–14:30 | 7,9 | −0,024 | 7,3 | +0,011 | 0,08 |
| Zeit 09:30–16:00 | 14,1 | −0,038 | 12,7 | −0,017 | −0,22 |
| ohne ICT-Zone | 5,8 | −0,052 | 5,6 | +0,166 | 0,93 |
| Stop 0,03 ATR | 4,5 | −0,013 | 3,9 | +0,334 | 1,30 |
| Box ≥ 0,1 ATR (strenger) | 2,6 | +0,079 | 2,1 | +0,239 | 0,51 |

**K1 lässt sich nicht sinnvoll lockern.** Jede Erweiterung von Zeitfenster oder Touch-Anzahl drückt den Ertrag in mindestens einem Datensatz auf null oder ins Minus. Die Varianten, die auf NQ besser aussehen (ohne ICT, engerer Stop), sind im CFD negativ. Wer mehr Trades will, sollte lieber **K1 und K2+ parallel handeln**, als K1 aufzuweichen. Die tägliche Korrelation der beiden liegt nur bei 0,10–0,16, und zusammen ergeben sie ≈ 7 Trades pro Woche.

### 50k-Eval-Simulation (Annahmen wie in Teil 7, Horizont 250 Handelstage)

Bestehenswahrscheinlichkeit (in Klammern: mittlere Dauer in Handelstagen):

**K1 Basis**

| Risiko pro Trade | Regel A: wie Backtest | A: halbe Kante | A: keine Kante | Regel B: wie Backtest | B: halbe Kante | B: keine Kante |
|---|---|---|---|---|---|---|
| 0,2 % (100 $) | 40 % (127) | 30 % | 22 % | 44 % (130) | 34 % | 25 % |
| 0,25 % (125 $) | 42 % (93) | 33 % | 25 % | 48 % (102) | 39 % | 30 % |
| **0,3 % (150 $)** | **41 % (72)** | 33 % | 25 % | **49 % (76)** | 39 % | 31 % |
| 0,4 % (200 $) | 36 % (46) | 30 % | 24 % | 46 % (46) | 38 % | 32 % |
| 0,5 % (250 $) | 33 % (36) | 28 % | 24 % | 44 % (31) | 37 % | 32 % |
| 0,75 % (375 $) | 27 % (26) | 22 % | 19 % | 42 % (15) | 39 % | 31 % |
| 1,0 % (500 $) | 21 % (23) | 19 % | 16 % | 38 % (10) | 36 % | 34 % |

**K1 + K2+ zusammen** (jede Strategie mit dem genannten Risiko pro Trade)

| Risiko pro Trade | Regel A: wie Backtest | A: halbe Kante | A: keine Kante | Regel B: wie Backtest | B: halbe Kante | B: keine Kante |
|---|---|---|---|---|---|---|
| **0,15 % (75 $)** | **54 % (115)** | 38 % | 24 % | 59 % (118) | 42 % | 27 % |
| **0,2 % (100 $)** | **54 % (75)** | 38 % | 26 % | **61 % (81)** | 46 % | 31 % |
| 0,25 % (125 $) | 47 % (57) | 35 % | 24 % | 57 % (54) | 44 % | 32 % |
| 0,3 % (150 $) | 43 % (44) | 32 % | 23 % | 54 % (39) | 42 % | 32 % |
| 0,5 % (250 $) | 34 % (26) | 26 % | 20 % | 46 % (16) | 39 % | 32 % |

**Ergebnis:**
* K1 allein: Das beste Risiko liegt bei **≈ 0,25–0,3 % pro Trade (125–150 $)**. Beim Stop von ≈ 17 NQ-Punkten sind das ≈ 4 MNQ. Die Bestehensquote liegt nur bei ≈ 41 % (A) bzw. ≈ 49 % (B) und damit schlechter als bei K2+ (50 % / 59 %), weil der gepoolte Ertrag pro Trade kleiner ist (≈ 0,10 R).
* K1 + K2+ zusammen: **≈ 0,15–0,2 % pro Trade (75–100 $)** ergibt ≈ 54 % (A) bzw. ≈ 60 % (B) in ≈ 75–115 Tagen. Das ist eine ähnliche Quote wie K2+ allein, aber etwas schneller.
* Auch hier gilt: Ohne echte Kante liegt die Quote bei 20–30 %. Ein konsistentes Bestehen ist nicht drin.

### `k1_strategy.pine`

Pine-v6-Strategie für den 1-Minuten-Chart. Sie baut die 5-Minuten-ICT-Zonen selbst aus den 1-Minuten-Kerzen und legt Limit-Orders an die qualifizierten Level, mit Stop und Ziel. Ein Fill gilt erst, wenn der Preis einen Tick durchhandelt (`backtest_fill_limits_assumption = 1`). Entry-Fenster, Touch-Anzahl, ICT-Filter, Stop und Risiko sind einstellbar.
