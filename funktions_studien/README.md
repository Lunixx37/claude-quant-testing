# Funktions-Studien: Kursverlauf als Funktion, Extrem- und Wendepunkte

Ausgangsfrage: Lässt sich der NQ-Verlauf durch eine Funktion annähern, sodass Ableitungen Hoch-, Tief- und Wendepunkte vorab anzeigen?

Kurzantwort: Nein. Jede Glättung beschreibt nur die Vergangenheit; am rechten Rand, wo gehandelt wird, trägt sie keine Information über die nächsten Kurse. Aus diesen Studien stammt aber der Befund, auf dem die Strategie in `open_drive/` aufbaut: Ist der Kurs weit von der Eröffnung entfernt, läuft er eher weiter, als dass er umkehrt.

Alle Skripte lesen die Daten aus dem Wurzelverzeichnis des Repositories und lassen sich von überall starten, z. B. `python funktions_studien/curve_fit_strategy.py --plot`.

| Skript | Frage | Ergebnis |
|---|---|---|
| `curve_fit_strategy.py` | Polynom über 10 / 50 / 100 Tage, Handel nach Steigung und Krümmung | Keine Variante schlägt Kaufen und Halten. Mit Zukunftswissen Sharpe 6,7, ohne etwa null. |
| `smoothing_strategy.py` | Gauß, EMA, Kalman statt Polynom, mit Unsicherheitsband | Beste Varianten erreichen den Sharpe von Kaufen und Halten, nicht mehr. |
| `intraday_extrema.py` | Wann fallen Tageshoch und -tief, und lässt sich erkennen, ob sie schon erreicht sind? | 33 % der Tiefs fallen 09:30–10:00. Ob ein Extrem hält, lässt sich aus Uhrzeit und Abstand gut schätzen; Glätter tragen nichts bei. |
| `stdv_box_extrema.py` | Verbessert die Stdv-Box (aus `nq_stdv_box/`) die Extrem-Erkennung? | Nein. Tagesextreme landen nicht häufiger auf den Leveln als dazwischen. |
| `k2_level_scan.py` | Funktioniert K2 an anderen Box-Leveln als 3,5? | 3,5 bleibt das einzige Level, das in beiden Datensätzen klar positiv ist. |
| `wendepunkt_radar.py` | Rollierender Test einer Ampel aus 1. und 2. Ableitung (Savitzky-Golay) | Keine Vorhersagekraft; 40 % der live gemeldeten Wendepunkte sind Fehlalarme. |
| `reversal_events.py` | Zwölf Reversal-Ereignisse unter festgelegten Bedingungen | Keines liegt verlässlich über 50 %. Stabil ist nur die Fortsetzung bei großem Abstand zur Eröffnung. |

`stdv_box_extrema.py` liest die K2-Trade-Listen aus `nq_stdv_box/results/search/`.
