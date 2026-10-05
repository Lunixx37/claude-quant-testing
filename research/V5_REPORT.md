# V5: Verfeinerung des FVG-Kandidaten + Geldmanagement nach User-Plan

## Ergebnis in Kürze
- **Keine Verfeinerung hat ehrlich verbessert.**
  - Filter: Keiner der 28 Filter (Kerzenrichtung/-größe, Gap-Größe, Impulsstärke, FVG-Alter, Trend, 9:30-Bias, Uhrzeit, erstes Signal, Volatilität) verbessert Training **und** Validierung.
  - Swing-Variante: Die beste und robusteste Variante (Stop 60 Punkte, TP 2R, Haltedauer bis 2 Sessions) war im Training gut, im Test aber **schlechter** als die Basis (2022 +0,02 R, 2023–25 −0,01 bis −0,03 R).
  - ATR-Stops: schlechter als feste Stops (Hypothese widerlegt).
- **Bester Testkandidat bleibt das unverfeinerte FVG:** intraday, Stop 40 Punkte, TP 3R. Test 2022 +0,18 R, 2023–25 (NQ, inkl. 1,2 Punkte Spread) +0,06 R.
- **Kelly-Fraktion** für diesen Kandidaten: ca. **2,3 %** Risiko pro Trade (alle Jahre). Mit den Entwicklungsjahren allein: 0,9 %.

## Phase A: Einzelfilter (E nach CFD-Kosten, Basis: Training +0,018 / Validierung +0,014)
Siehe `v5_phaseA.txt`.
- Typisches Muster: Filter, die im Training helfen, schaden in der Validierung, und umgekehrt.
  - Kerzen-Körper ≥ 60 %: Training −0,025, Validierung +0,057.
  - Spanne ≥ 1,5× Durchschnitt: Training +0,047, Validierung −0,066.
- **0 Filter behalten.**

## Phase C: Stops, Ziele, Haltedauer (135 Varianten)
Siehe `v5_phaseC.txt` und `v5_selection.txt`.

| Ebene | Ergebnis |
|---|---|
| Haltedauer intraday / 2 / 5 Sessions | Training −0,037 / −0,040 / −0,048 R, Validierung +0,006 / +0,026 / +0,016 R |
| Stops | fest 40–80 Punkte am besten; ATR-Stops und strukturelle Stops deutlich schlechter |

Gewählt (Plateau, alle Nachbarn positiv): fest 60 Punkte, TP 2R, Haltedauer bis 2 Sessions.

## Phase D: einmaliger Test der Verfeinerung
| Zeitraum | Trades/Woche | Trefferquote | E (CFD) | E (Futures) |
|---|---|---|---|---|
| Training | 3,6 | 43,9 % | +0,063 | +0,084 |
| Validierung | 6,3 | 36,2 % | +0,032 | +0,049 |
| **Test 2022** | 7,9 | 34,7 % | **+0,016** | +0,025 |
| **Test 2023–25 NQ** | 6,8 | 33,6 % | **−0,027** | −0,013 |

Die Verfeinerung hat versagt. Der unverfeinerte Kandidat ist besser.

## Phase E: Geldmanagement (bester Testkandidat: FVG intraday, Stop 40, TP 3R)
**Ablauf:**
- 100 $ Start.
- Nach „Monat 1“: Ist das Konto ≥ 1,5× Basis, werden 0,5× Basis entnommen.
- Nach „Monat 2“: +100 $ Einzahlung, neue Basis.

**Simulation:** 36 Monate, 2.000 Pfade, Monats-Block-Bootstrap. „Netto/Monat“ = (Entnahmen + Endstand − alle Einzahlungen) / 36.
Eingezahlt werden in 3 Jahren 1.900 $.

| Datenbasis | Risiko/Trade | Netto/Monat Median | 10 %..90 % | Entnahmen/Monat (Median) | P(Verlust nach 3 J.) | Endstand Median |
|---|---|---|---|---|---|---|
| alle Jahre 2017–25 | ½ Kelly 1,1 % | +17 $ | −6..+54 $ | 0 $ | 18 % | 2.504 $ |
| alle Jahre 2017–25 | **Kelly 2,3 %** | **+27 $** | −15..+119 $ | 5 $ | 23 % | 2.410 $ |
| alle Jahre 2017–25 | 5 % | +18 $ | −30..+261 $ | 20 $ | 38 % | 1.607 $ |
| alle Jahre 2017–25 | 10 % | **−18 $** | −41..+147 $ | 18 $ | **65 %** | 442 $ |
| 2023–25 (NQ) | ½ Kelly 1,1 % | +21 $ | −8..+76 $ | 0 $ | 20 % | 2.650 $ |
| 2023–25 (NQ) | **Kelly 2,3 %** | **+31 $** | −16..+157 $ | 24 $ | 23 % | 2.045 $ |
| 2023–25 (NQ) | 5 % | +23 $ | −29..+417 $ | 33 $ | 35 % | 1.362 $ |
| 2023–25 (NQ) | 10 % | **−11 $** | −40..+292 $ | 24 $ | **57 %** | 370 $ |

**Einordnung:**
- **Kelly (~2–2,5 %) ist im Median am besten.** 5 % erhöht die Streuung stark und senkt den Median. 10 % verliert im Median Geld.
- **Die Entnahmen pro Monat sind klein (0–33 $).** Der Großteil des Wertzuwachses bleibt im Konto und stammt zu einem
  guten Teil aus den eigenen Einzahlungen von ~53 $/Monat.
- Diese Zahlen setzen voraus, dass die gemessene Edge (+0,06 bis +0,18 R) **real ist und bleibt**. Sie ist klein und statistisch nur
  mäßig belegt. Bei Edge = 0 wären alle Mediane negativ (Kosten).

## Fazit
Ein realistisches passives Einkommen lässt sich aus 100 $ plus 50 $/Monat nicht erzielen. Bei Kelly-Risiko liegt der Medianzuwachs
bei rund 25–30 $/Monat, mit einer Verlustwahrscheinlichkeit von ~1 zu 4 über 3 Jahre. Für spürbares Einkommen braucht
es entweder deutlich mehr Kapital (der Ertrag skaliert linear mit dem eingesetzten Kapital) oder eine stärkere, belegte Edge.
