"""
Tagesextreme + Stdv-Box (Box = Open 00:00 ET / Open 08:30 ET, Level = Mitte +- k*h).

Daten:  CFD 2016-2022 (Zip, Brokerzeit Europe/Athens -> New York)  = Training / Gegenprobe
        NQ  2023-2025 (Futures-CSV)                                = Test
Alle Zeitstempel = Bar-OPEN in New Yorker Zeit. Tagesextrem = Hoch/Tief 09:30-16:00.

A  Wiederholung auf 9 Jahren: Zeitpunkt der Extreme, EMA-100-Handel
B  Landen Tageshoch/-tief auf den Stdv-Leveln? (echte Level vs. Zwischen-Level)
C  Prognose "bisheriges Extrem haelt": M1 (Uhrzeit, Abstand, Zeit seit Extrem)
   vs. M1 + Box vs. M1 + Placebo-Box (Opens 02:00 / 07:00)
D  Haelt ein Extrem, das an einem Stdv-Level entstanden ist, oefter als M1 erwartet?
E  K2-Trades (aus dem Branch claude/hopeful-hamilton-gxoy9x) nach M1-Wahrscheinlichkeit,
   EMA-100-Richtung und Uhrzeit aufgeteilt

Aufruf:  python stdv_box_extrema.py
"""
import io
import subprocess
import zipfile

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score

LEVELS = np.array([2.0, 2.25, 2.5, 3.5, 4.0, 4.25, 4.5])
FAKES = np.array([2.125, 2.375, 2.75, 3.25, 3.75, 4.125, 4.375])   # zwischen den echten Leveln
M = 390
K2_BRANCH = "origin/claude/hopeful-hamilton-gxoy9x"
pd.set_option("display.width", 200)


# ------------------------------------------------------------------ Daten
def load_nq():
    df = pd.read_csv("Dataset_NQ_1min_2022_2025.csv", usecols=["timestamp ET", "open", "high", "low", "close"])
    df.index = pd.to_datetime(df.pop("timestamp ET"), format="%m/%d/%Y %H:%M") - pd.Timedelta("1min")
    df = df[~df.index.duplicated()].sort_index()
    return df[df.index >= "2023-01-01"]


def load_cfd():
    parts = []
    for i in (1, 2):
        with zipfile.ZipFile(f"1m_data_part{i}.zip") as z:
            parts.append(pd.read_csv(z.open(f"1m_data_part{i}.csv"), sep="\t"))
    df = pd.concat(parts)
    broker = pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S")
    et = pd.DatetimeIndex(broker).tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="NaT") \
        .tz_convert("America/New_York").tz_localize(None)
    out = pd.DataFrame({"open": df.Open.values, "high": df.High.values, "low": df.Low.values,
                        "close": df.Close.values, "old_et": (broker - pd.Timedelta("7h")).values}, index=et)
    out = out[~out.index.isna()]
    out = out[~out.index.duplicated()].sort_index()
    return out[out.index < "2023-01-01"]


def build(bars):
    """Tagesmatrizen (Tage x 390 RTH-Minuten) plus Box je Tag."""
    logp = np.log(bars["close"].values)
    ret = np.diff(logp, prepend=logp[0])
    vol = pd.Series(ret).ewm(span=390, min_periods=100).std().values
    a = 2 / 101
    ema = pd.Series(ret).ewm(alpha=a, adjust=False).mean().values / (vol * np.sqrt(a / (2 - a)))
    b = bars.assign(vol=vol, ema=ema)
    hm = b.index.strftime("%H:%M")
    day = b.index.normalize()

    def opens(t):
        s = b.loc[hm == t, "open"]
        s.index = s.index.normalize()
        return s

    box = pd.concat({"o0": opens("00:00"), "o830": opens("08:30"),
                     "p0": opens("02:00"), "p1": opens("07:00")}, axis=1, sort=True).dropna()
    rth = b[(hm >= "09:30") & (hm < "16:00")]
    grid = pd.timedelta_range("09:30:00", "15:59:00", freq="1min")
    days, mats = [], {c: [] for c in ("open", "high", "low", "close", "vol", "ema")}
    for d, g in rth.groupby(rth.index.normalize()):
        if len(g) < 380 or d not in box.index or d.dayofweek > 4:
            continue
        g = g.set_index(g.index - d).reindex(grid)
        g[["close", "vol", "ema"]] = g[["close", "vol", "ema"]].ffill().bfill()
        for c in ("open", "high", "low"):
            g[c] = g[c].fillna(g["close"])
        days.append(d)
        for c in mats:
            mats[c].append(g[c].values)
    X = {c: np.array(v) for c, v in mats.items()}
    days = pd.DatetimeIndex(days)
    bx = box.loc[days]
    C, H, L = X["close"], X["high"], X["low"]
    X["sig"] = (X["vol"][:, :1] * np.sqrt(M)) * X["open"][:, :1]          # erwartete Tagesschwankung, Punkte
    for pre, (u, v) in (("", ("o0", "o830")), ("p_", ("p0", "p1"))):
        X[pre + "mid"] = ((bx[u] + bx[v]) / 2).values[:, None]
        X[pre + "h"] = np.maximum((bx[u] - bx[v]).abs().values[:, None] / 2, 1e-9)
        X[pre + "dir"] = np.sign(bx[v] - bx[u]).values[:, None]
    X["runlo"], X["runhi"] = np.minimum.accumulate(L, 1), np.maximum.accumulate(H, 1)
    idx = np.arange(M)
    X["since_lo"] = idx - np.maximum.accumulate(np.where(L <= X["runlo"], idx, 0), 1)
    X["since_hi"] = idx - np.maximum.accumulate(np.where(H >= X["runhi"], idx, 0), 1)
    X["lo_in"] = X["runlo"] <= L.min(1, keepdims=True)
    X["hi_in"] = X["runhi"] >= H.max(1, keepdims=True)
    return days, X


def feats(X, side, cols, box=""):
    """side='lo'/'hi'. Liefert Basis-Merkmale, Box-Merkmale, Ziel, 'Extrem an Level'-Maske."""
    C, sig = X["close"], X["sig"]
    idx = np.broadcast_to(np.arange(M), C.shape)
    if side == "lo":
        ext, dist, since, y, s = X["runlo"], (C - X["runlo"]) / sig, X["since_lo"], X["lo_in"], -1
    else:
        ext, dist, since, y, s = X["runhi"], (X["runhi"] - C) / sig, X["since_hi"], X["hi_in"], 1
    rng = (X["runhi"] - X["runlo"]) / sig
    base = np.stack([idx, dist, since, rng], -1)
    mid, h = X[box + "mid"], X[box + "h"]
    k_ext = np.clip(s * (ext - mid) / h, -20, 40)                     # Extrem in Box-Einheiten (aussen = positiv)
    k_px = np.clip(s * (C - mid) / h, -40, 40)
    lv = mid[..., None] + s * LEVELS * h[..., None]                   # Level auf der Seite des Extrems
    gap = np.abs(ext[..., None] - lv).min(-1) / sig                   # Abstand Extrem <-> naechstes Level
    bf = np.stack([k_ext, k_px, gap, np.broadcast_to(2 * h / sig, C.shape),
                   np.broadcast_to(s * X[box + "dir"], C.shape)], -1)
    return base[:, cols], bf[:, cols], y[:, cols], gap[:, cols], k_ext[:, cols]


def fit(F, y):
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, min_samples_leaf=200,
                                          random_state=0).fit(F, y)


# ------------------------------------------------------------------ A
def part_a(name, days, X):
    lo_t, hi_t = X["low"].argmin(1), X["high"].argmax(1)
    f = lambda t, a, b: ((t >= a) & (t < b)).mean()
    C = X["close"]
    r = np.diff(C, axis=1) / C[:, :1] * 1e4                             # bp
    t = X["ema"]
    raw = np.where(t > 1, 1.0, np.where(t < -1, -1.0, np.nan))
    pos = pd.DataFrame(raw).ffill(axis=1).fillna(0).values[:, :-1]
    turn = np.abs(np.diff(pos, axis=1, prepend=0)).sum(1) + np.abs(pos[:, -1])
    gross = (pos * r).sum(1)
    net = gross - 0.28 * turn                                           # 0.28 bp ~ 0.5 NQ-Punkte
    sh = lambda x: x.mean() / x.std() * np.sqrt(252)
    yr = pd.Series(net, index=days).groupby(days.year).agg(sh)
    return {"Daten": name, "Tage": len(days), "Tief 09:30-10:00": f(lo_t, 0, 30), "Tief 15:30-16:00": f(lo_t, 360, 390),
            "Hoch 09:30-10:00": f(hi_t, 0, 30), "Hoch 15:30-16:00": f(hi_t, 360, 390),
            "Tief bis 12:00": f(lo_t, 0, 150), "EMA100 brutto bp/Tag": gross.mean(), "netto bp/Tag": net.mean(),
            "Sharpe netto": sh(net), "long-only Sharpe": sh(r.sum(1)),
            "Jahre netto>0": f"{(yr > 0).sum()}/{len(yr)}"}


# ------------------------------------------------------------------ B
def part_b(name, X):
    out = []
    big = (2 * X["h"] / X["sig"] >= 0.3).ravel()
    k_hi = ((X["high"].max(1) - X["mid"].ravel()) / X["h"].ravel())
    k_lo = ((X["mid"].ravel() - X["low"].min(1)) / X["h"].ravel())
    for lab, m in (("alle Boxen", np.ones_like(big)), ("grosse Boxen", big)):
        k = np.r_[k_hi[m], k_lo[m]]
        hit = lambda ks: (np.abs(k[:, None] - ks).min(1) <= 0.05).mean()
        out.append({"Daten": name, "Boxen": lab, "Tage": int(m.sum()), "Extrem an echtem Level": hit(LEVELS),
                    "an Zwischen-Level": hit(FAKES), "Extrem jenseits 4.5": (k > 4.5).mean(),
                    "Extrem innerhalb 2.0": (k < 2).mean()})
    return out


# ------------------------------------------------------------------ C + D
def part_cd(sets):
    cols = np.arange(4, M - 1, 5)
    rows, drows, models = [], [], {}
    for side, lab in (("lo", "Tief"), ("hi", "Hoch")):
        data = {}
        for n, (_, X) in sets.items():
            b, bf, y, gap, kx = feats(X, side, cols)
            _, pf, _, pgap, _ = feats(X, side, cols, "p_")
            data[n] = dict(b=b.reshape(-1, 4), bf=bf.reshape(-1, 5), pf=pf.reshape(-1, 5), y=y.ravel(),
                           gap=gap.ravel(), pgap=pgap.ravel(), kx=kx.ravel())
        for tr, te in (("CFD", "NQ"), ("NQ", "CFD")):
            A, B = data[tr], data[te]
            for mname, key in (("M1 Uhrzeit+Abstand+Zeit seit Extrem", None), ("M1 + Stdv-Box", "bf"),
                               ("M1 + Placebo-Box 02:00/07:00", "pf")):
                Ftr = A["b"] if key is None else np.c_[A["b"], A[key]]
                Fte = B["b"] if key is None else np.c_[B["b"], B[key]]
                clf = fit(Ftr, A["y"])
                p = clf.predict_proba(Fte)[:, 1]
                rows.append(dict(Ziel=lab, Training=tr, Test=te, Modell=mname, AUC=roc_auc_score(B["y"], p),
                                 Brier=brier_score_loss(B["y"], p)))
                if key is None:
                    models[(side, te)] = clf
                    # D: Extrem liegt an einem Level (<= 0.03 sigma) und Kurs ist schon >= 0.1 sigma weg
                    away = B["b"][:, 1] >= 0.1
                    for dl, g in (("echtes Stdv-Level", B["gap"]), ("Placebo-Level", B["pgap"])):
                        m = away & (g <= 0.03)
                        drows.append(dict(Ziel=lab, Test=te, Extrem_an=dl, Faelle=int(m.sum()),
                                          haelt=B["y"][m].mean(), M1_erwartet=p[m].mean(),
                                          Mehr=B["y"][m].mean() - p[m].mean()))
                    for lo, hi, gl in ((1.9, 2.6, "2-2.5"), (3.4, 3.6, "3.5"), (3.9, 4.6, "4-4.5")):
                        m = away & (B["gap"] <= 0.03) & (B["kx"] >= lo) & (B["kx"] <= hi)
                        drows.append(dict(Ziel=lab, Test=te, Extrem_an=f"  davon Level {gl}", Faelle=int(m.sum()),
                                          haelt=B["y"][m].mean(), M1_erwartet=p[m].mean(),
                                          Mehr=B["y"][m].mean() - p[m].mean()))
    print("== C: Verbessert die Box die Prognose 'Extrem haelt'? ==")
    print(pd.DataFrame(rows).to_string(index=False, formatters={"AUC": "{:.3f}".format, "Brier": "{:.4f}".format}), "\n")
    print("== D: Extrem an einem Level entstanden - haelt es oefter als M1 erwartet? ==")
    print(pd.DataFrame(drows).to_string(index=False, formatters={
        "haelt": "{:.1%}".format, "M1_erwartet": "{:.1%}".format, "Mehr": "{:+.1%}".format}), "\n")
    return models


# ------------------------------------------------------------------ E
def part_e(sets, raw, models):
    print("== E: K2-Trades aufgeteilt nach unseren Merkmalen zum Einstieg (R je Trade) ==")
    allrows = []
    for kind in ("CFD", "NQ"):
        txt = subprocess.run(["git", "show", f"{K2_BRANCH}:nq_stdv_box/results/search/trades_K2_{kind}.csv"],
                             capture_output=True, text=True).stdout
        if not txt:
            print("K2-Tradeliste nicht gefunden (Branch nicht geholt)"); return
        tr = pd.read_csv(io.StringIO(txt), parse_dates=["day"])
        days, X = sets[kind]
        bars = raw[kind]
        # Bar-Position des alten Laufs -> echte New Yorker Zeit
        old = pd.DatetimeIndex(bars["old_et"]) if kind == "CFD" else bars.index
        ohm = old.strftime("%H:%M")
        sel = (ohm >= "08:30") & (ohm < "16:00")
        sess = pd.Series(bars.index[sel], index=old[sel]).groupby(old[sel].normalize())
        pos = {d: v.values for d, v in sess}
        dmap = {d: i for i, d in enumerate(days)}
        for _, t in tr.iterrows():
            v = pos.get(t.day)
            if v is None or t.bar >= len(v):
                continue
            ts = pd.Timestamp(v[t.bar])
            c = (ts.hour - 9) * 60 + ts.minute - 30
            di = dmap.get(ts.normalize())
            if di is None or c < 5 or c >= M:
                allrows.append(dict(kind=kind, R=t.R, grp="vor 09:35 / Tag fehlt")); continue
            side = "lo" if t.side == 1 else "hi"
            b, *_ = feats(X, side, np.array([c]))
            p = models[(side, kind)].predict_proba(b[di])[0, 1]
            allrows.append(dict(kind=kind, R=t.R, grp="ok", p=p, ema=t.side * X["ema"][di, c], minute=c,
                                dist=b[di, 0, 1]))
    r = pd.DataFrame(allrows)
    ok = r[r.grp == "ok"].copy()
    print(f"Trades gesamt {len(r)}, davon ab 09:35 auswertbar {len(ok)}; "
          f"nicht auswertbar: {len(r) - len(ok)} mit Ø R {r[r.grp != 'ok'].R.mean():+.3f}")

    def tab(col, bins, labels, title):
        ok["b"] = pd.cut(ok[col], bins, labels=labels)
        t = ok.groupby(["b", "kind"], observed=True).R.agg(["count", "mean", lambda x: (x > 0).mean()]).unstack()
        t.columns = [f"{k} {n}" for n, k in zip(["Trades"] * 2 + ["Ø R"] * 2 + ["Winrate"] * 2, list(t.columns.get_level_values(1)))]
        allr = ok.groupby("b", observed=True).R.agg(["mean", "sem"])
        t["beide Ø R"] = allr["mean"]; t["t-Wert"] = allr["mean"] / allr["sem"]
        t.index.name = title
        print(t.to_string(float_format="{:+.2f}".format), "\n")

    q = ok.p.quantile([1 / 3, 2 / 3]).values
    tab("p", [-1, q[0], q[1], 2], [f"niedrig (<{q[0]:.0%})", f"mittel", f"hoch (>{q[1]:.0%})"],
        "M1: P(Extrem in Trade-Richtung haelt)")
    tab("ema", [-99, -1, 0, 1, 99], ["klar gegen Trade", "leicht gegen", "leicht mit", "klar mit Trade"],
        "EMA-100-Steigung relativ zur Trade-Richtung")
    tab("minute", [0, 30, 150, 330, 400], ["09:35-10:00", "10:00-12:00", "12:00-15:00", "15:00-16:00"], "Uhrzeit Einstieg")


def main():
    raw = {"CFD": load_cfd(), "NQ": load_nq()}
    sets = {k: build(v) for k, v in raw.items()}
    f = {c: "{:.1%}".format for c in ("Tief 09:30-10:00", "Tief 15:30-16:00", "Hoch 09:30-10:00", "Hoch 15:30-16:00",
                                      "Tief bis 12:00", "Extrem an echtem Level", "an Zwischen-Level",
                                      "Extrem jenseits 4.5", "Extrem innerhalb 2.0")}
    print("== A: Wiederholung auf beiden Datensaetzen ==")
    print(pd.DataFrame([part_a(k, *v) for k, v in sets.items()]).T.to_string(header=False, float_format="{:.3f}".format), "\n")
    print("== B: Landen Tageshoch/-tief auf den Stdv-Leveln? (Toleranz +-0.05 k) ==")
    print(pd.DataFrame(sum((part_b(k, v[1]) for k, v in sets.items()), [])).to_string(index=False, formatters=f), "\n")
    models = part_cd(sets)
    part_e(sets, raw, models)


if __name__ == "__main__":
    main()
