"""Kapitalkurven der Ausstiegs-Modi (kumulierte R), CFD 2016-2022 und NQ 2023-2025 aneinandergehaengt.

Aufruf:  python open_drive/plot_modes.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from r1_strategy import MODES, run

INK, MUTE, SURF = "#0b0b0b", "#52514e", "#fcfcfb"
COL = {"Trend": "#1baf7a", "Trend + Nachzug": "#eda100", "V2a": "#eb6834", "R1": "#2a78d6"}
SHOW = {"Trend": "Trend: Stop 0,08 ATR, kein Ziel", "Trend + Nachzug": "Trend + Nachzug: 1-Min-Kerzen ab 1 R",
        "V2a": "V2a: 50 % bei 0,5 R, Rest bis Tagesende", "R1": "R1: alles bei 0,5 R"}

if __name__ == "__main__":
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": "#d9d8d2", "axes.labelcolor": MUTE,
                         "xtick.color": MUTE, "ytick.color": MUTE, "text.color": INK})
    fig, ax = plt.subplots(4, 1, figsize=(9, 11.5), facecolor=SURF, sharex=True)
    for a, (short, name) in zip(ax, SHOW.items()):
        t = pd.concat([run(k, **MODES[name])[0] for k in ("CFD", "NQ")])
        x = pd.to_datetime(t.tag)
        eq = t.R.cumsum().values
        dd = (eq - np.maximum.accumulate(eq)).min()
        top = np.sort(t.R.values)[-10:].sum() / t.R.sum()
        print(f"{short}: Summe {eq[-1]:+.0f} R, groesster Drawdown {dd:.0f} R, Anteil der 10 besten Trades am Gesamtgewinn {top:.0%}, "
              f"Median-Gewinn {np.median(t.R[t.R > 0]):+.2f} R")
        a.set_facecolor(SURF)
        a.spines[["top", "right"]].set_visible(False)
        a.grid(axis="y", color="#ebeae5", lw=.8)
        a.plot(x, eq, color=COL[short], lw=2)
        a.axvline(pd.Timestamp("2023-01-01"), color="#8a8983", lw=1, ls=(0, (3, 3)))
        a.set_title(f"{name}  –  {eq[-1]:+.0f} R gesamt, {(t.R > 0).mean():.0%} Treffer, größter Drawdown {dd:.0f} R",
                    loc="left", fontsize=11)
        a.set_ylabel("kumulierte R")
    ax[0].annotate("CFD-Daten", (pd.Timestamp("2022-11-01"), ax[0].get_ylim()[0]), ha="right", va="bottom", color=MUTE,
                   xytext=(-4, 4), textcoords="offset points")
    ax[0].annotate("NQ-Future", (pd.Timestamp("2023-03-01"), ax[0].get_ylim()[0]), ha="left", va="bottom", color=MUTE,
                   xytext=(4, 4), textcoords="offset points")
    fig.tight_layout()
    out = Path(__file__).parent / "modes_equity.png"
    fig.savefig(out, dpi=200, facecolor=SURF)
    print("Grafik gespeichert:", out.name)
