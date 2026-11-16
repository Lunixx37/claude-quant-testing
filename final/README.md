# NQ Open-Drive: Strategie, Optimierung und Forward-Test

Ziel: Trefferquote über 60 %, mehr als 2 Trades pro Woche, positiver Erwartungswert, stabil über beide Datensätze.

## Stand nach der Optimierung

Der Einstieg bleibt, wie er war. Verbessert hat sich nur der Ausstieg: einen Teil der Position laufen lassen. Filter, Wochentage und veränderte Einstiege haben die Gegenprobe nicht bestanden.

**Einstieg (unverändert, „R1“)**

| Regel | Wert |
|---|---|
| ATR | Durchschnitt der Tagesspanne der letzten 14 abgeschlossenen Handelstage |
| Signal | erste 1-Min-Kerze ab 09:31 New York, die 0,3 ATR über (Long) oder unter (Short) dem 09:30-Eröffnungskurs schließt |
| Filter | Tagesspanne seit 09:30 beim Signal höchstens 0,5 ATR; Signal bis 15:29 |
| Einstieg | Schlusskurs der Signalkerze, höchstens 1 Trade pro Tag |

**Ausstiegs-Modi** (alle im Pine-Skript wählbar; 3,2 bis 3,4 Trades pro Woche; Kosten 1 Punkt je Kontrakt und Trade)

| Modus | Datensatz | Trefferquote | Ø Gewinn / Ø Verlust | E je Trade | R pro Jahr | Max. Drawdown | Längste Verlustserie |
|---|---|---|---|---|---|---|---|
| **R1**: Stop 0,15 ATR, alles bei 0,5 × Stop | CFD 2016–22 | 73,2 % | +0,48 / −1,01 R | +0,078 R | +12,5 | −10,1 R | 6 |
| | NQ 2023–25 | 70,5 % | +0,48 / −1,00 R | +0,041 R | +6,9 | −10,3 R | 5 |
| **V2a**: halbe Position bei 0,5 × Stop, danach Stop auf Einstand, Rest bis 15:59 | CFD 2016–22 | 73,1 % | +0,57 / −1,01 R | +0,145 R | +23,3 | −15,4 R | 6 |
| | NQ 2023–25 | 70,5 % | +0,51 / −1,00 R | +0,064 R | +10,8 | −10,8 R | 5 |
| **V2a-75**: wie V2a, Teilverkauf bei 0,75 × Stop | CFD 2016–22 | 62,4 % | +0,85 / −1,00 R | +0,152 R | +24,3 | −19,1 R | 7 |
| | NQ 2023–25 | 60,4 % | +0,78 / −1,00 R | +0,077 R | +13,1 | −14,7 R | 6 |
| **Trend**: Stop 0,08 ATR, kein Ziel, bis 15:59 halten | CFD 2016–22 | 22,8 % | +5,14 / −1,03 R | +0,372 R | +59,5 | −33,8 R | 18 |
| | NQ 2023–25 | 20,2 % | +5,56 / −1,04 R | +0,298 R | +50,4 | −25,2 R | 24 |

![Kapitalkurven](modes_equity.png)

### Wichtigste Einschränkung

**Die Modi mit hoher Trefferquote haben seit Juli 2024 nichts mehr verdient.** Über die letzten 244 Trades auf NQ: R1 +1,3 R, V2a −1,2 R, V2a-75 +1,1 R. R1 und V2a trafen dabei 68 %; nötig sind 67,8 %. Der Trend-Modus kam im selben Zeitraum auf +64 R; sein zweites Halbjahr 2025 war mit −2,7 R ebenfalls flach.

Der Vorteil sitzt also in den wenigen Tagen, an denen der Kurs nach dem Ausbruch bis zum Schluss weiterläuft, nicht in den ersten 20 bis 25 Punkten.

### Jahr für Jahr (E je Trade in R)

| Modus | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|
| R1 | 0,00 | +0,09 | +0,16 | +0,05 | +0,09 | +0,08 | +0,02 | +0,09 | +0,01 |
| V2a | +0,07 | +0,26 | +0,17 | +0,06 | +0,13 | +0,16 | +0,11 | +0,08 | 0,00 |
| V2a-75 | +0,06 | +0,26 | +0,17 | 0,00 | +0,24 | +0,18 | +0,11 | +0,14 | −0,02 |
| Trend | +0,34 | +0,67 | +0,44 | −0,08 | +0,40 | +0,36 | +0,31 | +0,40 | +0,18 |

### Kosten (NQ 2023–25, E je Trade)

| Kosten je Trade | V2a | Trend |
|---|---|---|
| 1 Punkt | +0,064 R | +0,298 R |
| 2 Punkte | +0,040 R | +0,254 R |
| 3 Punkte | +0,016 R | +0,209 R |

Auf NQ lag der Stop bei V2a im Schnitt bei 47 Punkten (Teilziel 23,5 Punkte), im Trend-Modus bei 25 Punkten.

## Was die Optimierung ergeben hat

Vorgehen: Alles wurde nur auf CFD 2016–2022 ausgewählt (Stufe A 2016–2020, Stufe B 2021–2022), dann eingefroren und committet (`opt_selection.json`) und erst danach auf NQ 2023–2025 geprüft.

### Ausstiege

- **Teil laufen lassen** ist die einzige bestätigte Verbesserung. Gegenüber R1 bringt V2a je Trade +0,071 R (CFD A), +0,061 R (CFD B) und +0,023 R (NQ); über alle 1.434 Trades +0,052 R (t = 2,8). Die Trefferquote bleibt gleich.
- **Engere Stops** bringen bei kleinem Ziel nichts: Ein Viertel der späteren Gewinner läuft vorher mehr als 0,10 ATR gegen den Einstieg. Stops unter 0,10 ATR sind mit Zielen bis 1 × Stop auf CFD A negativ oder praktisch null.
- **Zeit-Stops** (Ausstieg nach 10 bis 180 Minuten) verschlechtern das Ergebnis.
- **Nachgezogene Stops** (Trailing, VWAP-Nachzug) sind schlechter als der Rest ohne Ziel mit Stop auf Einstand.
- **Struktur-Stops** (hinter Signalkerze, hinter dem Tief der letzten 5 bis 20 Kerzen, hinter dem Ausbruchs-Level) sind schlechter als der feste Stop.
- Alle 22 geprüften Abwandlungen von V2a (Stop 0,10 bis 0,22 ATR, Teilverkauf 33 bis 67 %, Teilziel 0,4 bis 1,0 × Stop, Signal 0,25 und 0,35 ATR, mit und ohne Spannen-Filter) sind in allen drei Datensätzen positiv.

### Nachgezogene Stops für offene Positionen (`trail_study.py`)

Offene Positionen geben tatsächlich viel wieder ab. Von den Positionen, die mindestens 1 × Stop im Gewinn lagen, blieb bis 15:59 im Schnitt weniger als die Hälfte des Höchststands:

| Position | lag mindestens im Gewinn | Anteil der Trades | Ø Höchststand | Ø Ergebnis bei Halten bis 15:59 | behalten |
|---|---|---|---|---|---|
| V2a-Rest | 1 R | 37 % | +2,87 R | +1,24 R | 43 % |
| V2a-Rest | 3 R | 12 % | +5,25 R | +3,35 R | 64 % |
| Trend | 1 R | 55 % | +4,57 R | +1,48 R | 32 % |
| Trend | 3 R | 28 % | +7,18 R | +3,65 R | 51 % |

Ein engerer Nachzug holt davon aber nichts zurück. Unterschied zum Halten bis 15:59 in R je Trade, alle Datensätze zusammen:

| Regel (aktiv, sobald der Trade so weit im Gewinn schließt) | V2a | Trend | Stop 0,15 ohne Ziel |
|---|---|---|---|
| Stop auf das Open jeder 1-Min-Kerze in Trade-Richtung, ab 1 R | −0,035 | −0,235 | −0,110 |
| erst nach 2 Kerzen in Folge (Open der ersten), ab 1 R | −0,032 | −0,225 | −0,097 |
| erst nach 3 Kerzen in Folge, ab 1 R | −0,029 | −0,209 | −0,096 |
| 5-Min-Kerzen, ab 1 R | −0,032 | −0,217 | −0,096 |
| 30-Min-Kerzen, ab 1 R | −0,023 | −0,145 | −0,081 |
| 1-Min-Kerzen, erst ab 3 R | −0,018 | −0,151 | −0,053 |
| Stop hinter das Tief/Hoch der letzten 10 Minuten, ab 1 R | −0,033 | −0,216 | −0,096 |
| Stop hinter das Tief/Hoch der letzten 60 Minuten, ab 1 R | −0,020 | −0,115 | −0,066 |
| 50 % des höchsten offenen Gewinns absichern, ab 2 R | −0,010 | −0,197 | −0,037 |
| spätestens 14:00 aussteigen | −0,008 | −0,055 | −0,041 |
| spätestens 15:30 aussteigen | +0,001 | −0,007 | −0,001 |

- Getestet wurden je Modus 112 Kerzen-Regeln (Kerzenlänge 1 bis 30 Minuten, 1 bis 3 Kerzen in Folge, Tief der letzten 3 bis 120 Minuten, aktiv ab 1 bis 5 R). **Keine der 336 Kombinationen ist in allen drei Datensätzen besser** als Halten bis 15:59; 183 sind deutlich schlechter (t < −2).
- Je enger und je früher der Nachzug, desto größer der Verlust. Die lockersten Regeln (3 Kerzen in Folge auf 10- oder 30-Min-Kerzen, erst ab 3 bis 5 R) liegen bei null.
- Der Grund: Ein Rücksetzer, der einen engen Stop auslöst, ist meist nur eine Pause. Die großen Gewinner brauchen diesen Spielraum.
- **Was der Nachzug ändert, ist das Profil:** Im Trend-Modus steigt die Trefferquote mit dem 1-Min-Nachzug ab 1 R von 22 % auf 49 %, die längste Verlustserie fällt von 18 bis 24 auf 7 und der größte Drawdown von −34 R auf −22 R. Der Ertrag fällt dabei von +0,37 / +0,30 R auf +0,11 / +0,12 R je Trade (CFD / NQ).
- Die letzte halbe Stunde bringt nichts: Ausstieg um 15:30 oder 15:45 ist gleichwertig mit 15:59.

### Einstiege (CFD, E je Trade mit V2a-Ausstieg: Stufe A / Stufe B)

| Variante | Ergebnis |
|---|---|
| bisheriger Einstieg | +0,145 / +0,147 |
| Stop-Order direkt am Level (ohne Schlusskurs-Bestätigung) | +0,133 / +0,047 |
| zwei Schlusskurse in Folge jenseits des Levels | +0,074 / +0,149 |
| Bestätigung: Stop-Order über der Signalkerze | +0,155 / +0,203, aber 10 % weniger Trades; Gesamtertrag in A niedriger |
| Rücksetzer-Limit am Level (15 bis 120 Minuten gültig) | +0,04 / +0,09 |
| tageszeitabhängige Schwelle (mittlere Bewegung der letzten 14 Tage zur selben Uhrzeit) | gleichwertig, nicht besser |
| andere feste Schwellen (0,15 bis 0,5 ATR) | keine ist in beiden Stufen besser als 0,3 ATR |

Keine Variante ist in beiden Stufen besser.

### Filter

- Geprüft wurden 38 Merkmale: Uhrzeit, Tagesspanne, Gegenbewegung, Größe und Schluss der Signalkerze, Momentum, Abstand zur VWAP, Lücke, Overnight-Richtung und -Spanne, Vorbörse, 08:30-Ausschlag, Stdv-Box (Richtung, Größe, Lage), Vortageshoch/-tief, Vortagesspanne, 1-, 5- und 20-Tage-Trend, Volatilitäts-Regime, enge und weite Vortage, Inside Days, relatives Volumen, Long gegen Short.
- Auf dem CFD waren 7 Merkmale auffällig (p < 0,05). Am stärksten war die **Lage der Eröffnung in der Overnight-Spanne**: Trades in Richtung der Overnight-Bewegung brachten +0,27 / +0,24 R, die übrigen +0,03 / +0,04 R, in beiden Stufen gleich.
- **Auf NQ ist davon nichts übrig:** +0,067 R gegen +0,060 R (p = 0,94). Keines der 7 Merkmale ist auf NQ signifikant.
- Kontrolle: CFD und NQ liefern im gemeinsamen Zeitraum 2023–2025 praktisch dieselben Trades (gleiche Richtung 100 %, gleicher Ausgang 97 %). Der Unterschied liegt also am Zeitraum, nicht an der Datenquelle.
- Kreuzvalidiert über alle neun Jahre (Modell auf acht Jahren trainiert, auf dem neunten getestet) trennt eine Kombination aller Merkmale die Trades kaum: obere gegen untere Hälfte +0,04 R (t = 0,8).

### Wochentage (E je Trade mit V2a-Ausstieg)

| Tag | CFD 2016–20 | CFD 2021–22 | NQ 2023–25 |
|---|---|---|---|
| Montag | +0,27 | +0,33 | +0,02 |
| Dienstag | +0,09 | +0,11 | +0,10 |
| Mittwoch | +0,13 | −0,11 | +0,04 |
| Donnerstag | +0,09 | +0,21 | +0,03 |
| Freitag | +0,14 | +0,19 | +0,12 |

Kein Wochentag ist verlässlich besser oder schlechter (Varianzanalyse p = 0,61 / 0,16 / 0,93). Der Montags-Vorteil auf dem CFD verschwindet auf NQ. Einzelne Tage wegzulassen senkt nur die Zahl der Trades.

### Long gegen Short (V2a)

Longs sind in allen drei Datensätzen besser als Shorts (+0,19 / +0,19 / +0,11 R gegen +0,10 / +0,11 / +0,02 R). Beide Seiten sind positiv; in einem fallenden Markt kann sich das umkehren, deshalb bleibt beides aktiv.

## Wie R1 gefunden wurde (erste Suche)

1. **Ereignistabelle** (`build_events.py`): rund 205.000 mögliche Einstiege auf dem CFD und 107.000 auf NQ. Reclaims an Stdv-Box, Psych-Leveln, Tages- und Overnight-Leveln, VWAP, FVG, iFVG, Order Block und Rejection Block; Ausbrüche von der Eröffnung, aus der Opening Range, über Tagesextreme und aus der Indecision-Box.
2. **Suche** (`search.py`): 919.025 Kombinationen aus Einstieg, Trendbedingung, Zeitfenster, bis zu 2 Zusatzbedingungen und Ausstieg. 717 bestehen CFD 2016–2020, 371 davon auch CFD 2021–2022.
3. **Endtest** (`final_test.py`): fünf eingefrorene Kandidaten auf NQ, zwei bestehen. Danach drei Verfeinerungen, aus denen R1 stammt.

Fast alle 371 Treffer folgen einem Prinzip: mit der Bewegung handeln, wenn der Kurs mindestens 0,3 ATR von der Eröffnung entfernt ist. Einstiege gegen die Bewegung sind durchgehend negativ. Stdv-Level, Psych-Level, VWAP und ICT-Zonen bestehen nur zusammen mit dieser Trendbedingung und dann schlechter als der schlichte Ausbruch; der Psych-Level-Kandidat fiel auf NQ durch. Die Indecision-Box besteht in keiner Variante.

## Einschränkungen

- **NQ 2023–2025 wurde dreimal als Gegenprobe benutzt** und ist kein unberührter Test mehr. Der eigentliche Test ist der Forward-Test.
- **Die Modi wurden im Nachhinein verglichen.** Dass der Trend-Modus zuletzt besser war, ist eine Beobachtung auf bekannten Daten.
- **Der Trend-Modus lebt von wenigen Trades:** Die 10 besten von 1.434 Trades liefern 39 % des Gesamtgewinns. Bei 25 Punkten Stop wiegt zusätzlicher Slippage schwerer als bei V2a.
- **V2a braucht mindestens 2 Kontrakte**, damit der Teilverkauf möglich ist (praktisch: MNQ).
- **GEX wurde nicht getestet** (keine Optionsdaten).
- **Indecision-Box** ist hier definiert als 5-Min-Kerze mit Körper höchstens 20 % der Spanne und Spanne mindestens 0,03 ATR; Ausbruch per 1-Min-Schluss binnen 30 Minuten.
- **Das Pine-Skript ist nicht in TradingView kompiliert oder gegen die Trade-Listen abgeglichen.**
- Liegen Stop und Ziel in derselben Minutenkerze, zählt im Backtest der Stop. Der Stop auf Einstand gilt ab der Kerze nach dem Teilverkauf.

## Forward-Test

1. `R1_OpenDrive.pine` auf dem 1-Minuten-Chart von NQ oder MNQ laden, Chart mit vollständiger Handelszeit (sonst stimmt die ATR nicht).
2. Zwei Instanzen parallel laufen lassen: Modus „Teilverkauf + Runner“ (Stop 0,15) und Modus „Nur Runner“ (Stop 0,08). Der Einstieg ist derselbe; so zeigt sich, welcher Ausstieg trägt.
3. Im Strategy Tester die letzten Wochen mit `results/v2a_trades_NQ.csv` bzw. `results/r1_trades_NQ.csv` vergleichen.
4. „Nur ab Startdatum handeln“ einschalten und mindestens 150 Trades sammeln (etwa ein Jahr). Bei 70 % erwarteter Quote schwankt die Trefferquote über 150 Trades um etwa ±7 Prozentpunkte.

## Dateien

| Datei | Inhalt |
|---|---|
| `R1_OpenDrive.pine` | TradingView-Strategie mit den drei Ausstiegs-Modi |
| `r1_strategy.py` | eigenständige Nachrechnung Kerze für Kerze, Kennzahlen aller Modi, Trade-Listen |
| `plot_modes.py` | Kapitalkurven |
| `opt_data.py`, `opt_lib.py` | Daten-Cache und Werkzeuge der Optimierung |
| `opt_selection.json`, `opt_final.py` | eingefrorene Kandidaten und Gegenprobe |
| `trail_study.py` | Test nachgezogener Stops für offene Positionen |
| `build_events.py`, `search.py`, `selection.json`, `final_test.py` | erste Suche |
| `results/` | Trade-Listen |

```bash
python final/r1_strategy.py && python final/plot_modes.py
python final/opt_data.py /tmp/opt && python final/opt_final.py /tmp/opt
```
