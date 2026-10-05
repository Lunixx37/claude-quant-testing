# V3: Gesamtauswertung mit den neuen Daten (2016–2025)

## Kurzfassung
1. **Die neuen Daten sind ein NASDAQ-100-CFD, kein NQ-Future.**
   - Die Bewegung stimmt mit NQ überein (Korrelation 0,99).
   - Das „Volumen“ ist gedeckeltes Tick-Volumen, also praktisch ohne Information.
   - Volumenbasierte Bausteine (Absorption, VWAP-Gewichtung) lassen sich darauf nur näherungsweise testen.
2. **V1 und V2 bestätigen sich auf 2017–2022 nicht:** V1 +0,02 R, V2 −0,02 R, 2022 jeweils −0,28 R.
3. **Daily-Reset-VWAP (18:00 NY) als Umkehr-Level:** Keine Variante hat eine stabile Edge, das Training liegt zwischen −0,07 und +0,03 R.
4. **ICT-Kombinationen und Level-Rejections bei ≥ 4 Trades/Woche: 0 von 132 Konfigurationen erreichen das Ziel** (Trefferquote > 50 % bei 2–3 RR).
   - Die maximale Trefferquote mit TP ≥ 2R liegt bei 43 % (Training) bzw. 37 % (Validierung).
   - Kein Setup ist in allen Zeiträumen profitabel.
5. Die beste vorab gewählte Konfiguration (V3) ist auf dem unberührten Jahr 2022 klar negativ.

**Eine Strategie mit > 50 % Trefferquote bei 2–3 RR wurde nicht gefunden.**

## 1. Datenprüfung
| Prüfung | Ergebnis |
|---|---|
| Format | MetaTrader-Export, tab-getrennt, 3.077.548 Bars, 15.11.2016–01.10.2025, keine Duplikate, OHLC konsistent |
| Instrument | NASDAQ-100-CFD (Kassa-Index): Preise in 0,1-Schritten, Niveau ≈ NDX, Minutenrenditen 0,99 korreliert mit NQ |
| Zeitzone | Server = Europe/Helsinki (EET/EEST). Umgerechnet nach NY liegt die Tagespause sauber bei 17:00–18:00. Ein fixer Versatz von 7 h wäre in den Wochen um die Zeitumstellung falsch. |
| Volumen | `Volume` = 0, `TickVolume` in der RTH auf ~500/min gedeckelt. Korrelation des relativen Volumens mit echtem NQ-Volumen 0,44. |
| Notbehelf | Quantil-Abbildung des Tick-Volumens auf die NQ-Volumenverteilung, kalibriert nur auf der Volumenverteilung 2023–25 |
| Gegenprobe 2023–25 | Nur 5–8 % der V1/V2-Trades auf NQ entstehen auch auf dem CFD. Ohne Volumenfilter sind es 31 %, weil das tick-gewichtete VWAP im Median um 13 Punkte abweicht. Auf dem CFD bringt V1 +0,06 R statt +0,27 R auf NQ. |

## 2. Unveränderte V1/V2 auf neuen Jahren (CFD-Näherung)
| | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | **2017–22** | 2023–25 (CFD) |
|---|---|---|---|---|---|---|---|---|
| V1 E (R) | +0,04 | +0,02 | −0,06 | +0,21 | +0,07 | −0,28 | **+0,02** (939 Trades) | +0,11 |
| V2 E (R) | −0,01 | +0,01 | −0,03 | +0,11 | −0,03 | −0,28 | **−0,02** (1.013 Trades) | +0,09 |

**Einordnung:** Auf CFD-Daten verlieren V1/V2 selbst 2023–25 etwa 0,15 R gegenüber NQ (fehlendes echtes Volumen). Ganz fair ist der Test deshalb nicht. Eine **nachweisbare** Edge außerhalb von 2023–25 gibt es aber nicht.

## 3. Daily-Reset-VWAP (Reset 18:00 NY = nach der Stunde Pause)
**Innerhalb der V1-Logik** (Training 2017–06/2020 / Validierung 07/2020–2021):

| Level-Set | Training | Validierung |
|---|---|---|
| nur VWAP18 | −0,04 R (250) | +0,34 R (52) |
| VWAP18 + 1/2σ-Bänder | +0,01 R (609) | +0,02 R (191) |
| nur RTH-VWAP | −0,07 R (429) | +0,40 R (90) |
| V1-Level-Set | +0,03 R (656) | +0,08 R (213) |

**Als reine Rejection-Strategie** (S1/S2 im Grid unten): Training −0,13 bis +0,05 R, Validierung −0,08 bis +0,05 R. Kein robuster Vorteil.

## 4. Suche mit hoher Frequenz (ICT + Levels), 132 vorab festgelegte Konfigurationen
- **Bausteine:** FVG, Rejection Block, Order Block, Market Structure Shift, Liquidity Sweep (PDH/PDL, ONH/ONL, Asia, London), VWAP18 und Bänder, Mental Levels (100/500/1000), Absorption.
- **Ablauf:** Einstieg zwischen 09:30 und 11:00, höchstens 2 Trades pro Tag.
  - Ab 10:30 Fallback-Trade ohne volles Setup: das erste verfügbare Signal mit einer Confluence.
  - Um 10:59 Zwangs-Trade, falls bis dahin kein Trade lief.
- **Kosten:** als MNQ (1 Tick Slippage, 1,50 $ pro Round Turn).

**Ergebnisse:**
- **Frequenz:** 5–9,5 Trades pro Woche, das Ziel ≥ 4/Woche ist überall erfüllt.
- **Ziel erreicht:** 0/132 im Training, 0/132 in der Validierung.
- **Trefferquote:** maximal 46 % (TP 1,5R). Mit TP ≥ 2R maximal 43 % im Training und 37 % in der Validierung.
- **Erwartungswert:** Training −0,21 bis +0,08 R. Die Korrelation zwischen Training und Validierung über alle 132 Konfigurationen beträgt **0,11**, die Rangfolge im Training sagt also fast nichts vorher.
- **Strukturelle (enge) Stops** sind durchweg schlechter als ein fester 25-Punkte-Stop, weil Kosten und Rauschen bei 5–15 Punkten Stop zu viel vom R auffressen.

**Festes RR gegen Trailing** (Mittel über alle 22 Setup/Stop-Kombinationen):

| Exit | Trefferquote Train | Ø Gewinner (brutto) | E Train | Trefferquote Valid | E Valid |
|---|---|---|---|---|---|
| TP 1,5R | 41,3 % | 1,30 R | −0,074 | 40,0 % | −0,050 |
| TP 2R | 36,9 % | 1,60 R | −0,070 | 34,0 % | −0,045 |
| TP 2,5R | 34,3 % | 1,83 R | −0,062 | 29,9 % | −0,033 |
| TP 3R | 32,6 % | 2,01 R | −0,058 | 27,4 % | −0,015 |
| TP 3R + Trailing | 32,9 % | 1,64 R | −0,046 | 28,6 % | −0,024 |
| **Trailing** | 32,9 % | 1,67 R | **−0,040** | 28,6 % | **+0,010** |

Die Trefferquote sinkt fast linear mit dem RR-Ziel. Das entspricht dem Verhalten ohne Edge, wo eine feste 2R-Zielquote zufällig bei etwa 33 % liegt. Trailing ist im Mittel leicht besser als ein festes Ziel.

## 5. Eingefrorene V3-Wahl und einmaliger Test
- **V3_FINAL:** S10 Absorption, fester 25-Punkte-Stop, TP 3R.
- **Auswahlregel:** das beste min(E Train, E Valid) unter den 8 Konfigurationen, die in beiden Zeiträumen positiv waren.

| Zeitraum | Trades/Woche | Trefferquote | Ø Gewinner | E | **Live 50k, 250 $/Trade** | Live 1 % (500 $) | **Prop: Payout ≤ 2 M / ≤ 12 M** |
|---|---|---|---|---|---|---|---|
| Test A 2022 (CFD, unberührt) | 7,4 | 22,6 % | 2,91 R | **−0,15 R** | **−14.600 $**, DD 19.100 $ | −29.200 $ | 1,6 % / 2,1 % (84 % der Evals gesprengt) |
| Test B 2023–25 (NQ) | 6,5 | 28,2 % | 2,85 R | +0,06 R | +13.800 $ (+9 %/J), DD 9.200 $ | +27.600 $, DD 18.400 $ | 7,9 % / 15,4 % |
| Test B 2023–25 (CFD) | 6,2 | 27,4 % | 2,87 R | +0,03 R | +6.800 $ (+5 %/J), DD 8.600 $ | +13.500 $ | 5,5 % / 13,9 % |

**Live gegen Prop:**
- Ein Live-Konto verkraftet die Schwankungen einer schwachen Strategie mit hoher Frequenz eher. Der Drawdown liegt aber beim 4- bis 9-Fachen von V1/V2 (V1/V2 auf NQ 2023–25 live: +10.800 bzw. +11.900 $, DD nur ~2.000 $).
- In der Prop-Umgebung (EOD-DD 2.000 $, DLL 1.000/1.200 $) sprengen viele Trades ohne Edge die Evals schnell. Die Payout-Quote liegt bei 2–15 %.
- **Mehr Trades verbessern die Prop-Chancen nur, wenn jeder Trade eine positive Edge hat.** Sonst beschleunigen sie nur das Sprengen.

## Warum das Ziel (> 50 % Trefferquote bei 2–3 RR, ≥ 4/Woche) nicht erreichbar war
- **Ausgangswert:** Ohne Edge liegt die Trefferquote bei festem 2R-Ziel nach Kosten bei ~33 %, bei 3R bei ~25 %. Genau das zeigt das Grid.
- **Anforderung:** > 50 % bei 2R entspricht mindestens +0,5 R pro Trade. Das wäre eine Edge, die mehr als doppelt so stark ist wie die beste je gemessene (V1 auf NQ 2023–25, ~+0,25 R), und das bei vierfacher Frequenz.
- **Was das Grid zeigt:** Keine der getesteten Kombinationen aus ICT-Bausteinen und Levels kommt in die Nähe. Auch der Zwang zu mehr Trades (Fallback/Zwangs-Trade) erzeugt keine Edge.

## Einschränkungen
- CFD-Daten statt Futures. Kein echtes Volumen 2016–2022. Mental Levels liegen beim CFD auf Kassa-Preisen.
- 1-Minuten-Auflösung. ICT-Definitionen (FVG, RB, OB, MSS) sind objektive Annäherungen und keine diskretionäre Auslegung.
- Fallback und Zwangs-Trade sind eine Regel-Annäherung an „den bestmöglichen Trade“.

Reproduzierbar mit `features.py` (`build_cfd`), `ict.py`, `v3_detect.py`, `v3_grid.py`, `v3_test.py` und `v3_frozen_oos.py`. Rohdaten: `v3_grid_train.csv`, `v3_grid_valid.csv`, `*_result.txt`.
