"""Hjælper til den nemme vej: stopnavne pr. retning og en beregnet config med bump-vinduer.

Functionality:
    stopnavne: læser data\\A (Details.csv + List.csv) og skriver pr. kørselsretning stoppestederne i den
        rækkefølge, bussen kører dem (den hyppigste rækkefølge). Er p1 og p2 udfyldt i config, markeres
        stoppestederne nær strækningen, og der foreslås start- og slutstop pr. retning, klar til at kopiere.
        Siger også, hvis retning 1 kører fra p2 mod p1 (så skal p1 og p2 byttes).
    config: skriver resultat\\config_beregnet.yaml = config.yaml med absolutte datastier og
        komfort.bump_vinduer regnet ud fra hvert bumps koordinat og radius (radius_m, standard 30 m).
        Står bump_vinduer allerede udfyldt i config.yaml, bruges de.
Uses: pandas, pyyaml (som resten af værktøjet). Geometrien er komfort_v1.0's (lokal flad projektion).
Dependencies: config.yaml i analysemappen. Kaldes af koer_analyse.bat.
Debugging points: stopnavne læser kun stop-rækker (Stop-nummer udfyldt). Varierer turene (fx kortere
    ture), bruges den hyppigste rækkefølge; antallet af ture med den står i filen.
"""
import argparse
import math
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml

EARTH_R = 6371000.0
STANDARD_RADIUS_M = 30.0
PLADSHOLDER = (55.0, 8.0)


def lokal_xy(lat, lon, lat0, lon0):
    k = math.pi / 180.0 * EARTH_R
    return (lon - lon0) * k * math.cos(math.radians(lat0)), (lat - lat0) * k


def s_langs(p_fra, p_til, lat, lon):
    """Meter langs den rette linje fra p_fra mod p_til (samme geometri som komfort_v1.0)."""
    x1, y1 = lokal_xy(p_til["lat"], p_til["lon"], p_fra["lat"], p_fra["lon"])
    L = math.hypot(x1, y1)
    x, y = lokal_xy(lat, lon, p_fra["lat"], p_fra["lon"])
    return (x * x1 + y * y1) / L, L


def afstand(a, b):
    x, y = lokal_xy(b["lat"], b["lon"], a["lat"], a["lon"])
    return math.hypot(x, y)


def laes_config(sti):
    return yaml.safe_load(Path(sti).read_text(encoding="utf-8")) or {}


def udfyldt(pt):
    return pt and (round(float(pt["lat"]), 4), round(float(pt["lon"]), 4)) != PLADSHOLDER


def sti_rel(cfg_sti, s):
    p = Path(s)
    return p if p.is_absolute() else (Path(cfg_sti).resolve().parent / p)


# ------------------------------------------------------------------ stopnavne

def rens(df):
    df.columns = [c.strip().strip('"').strip() for c in df.columns]
    return df


def stopnavne(cfg_sti, ud):
    cfg = laes_config(cfg_sti)
    d = cfg["data"]["Periode_A"]
    det, lst = sti_rel(cfg_sti, d["details_csv"]), sti_rel(cfg_sti, d["list_csv"])
    for f in (det, lst):
        if not f.exists():
            sys.exit(f"Filen findes ikke: {f}\nLæg HAFAS-eksporten i data\\A (se config.yaml, punkt 2).")
    liste = rens(pd.read_csv(lst, sep=";", encoding="utf-8", dtype=str))
    retning = dict(zip(liste["Turnummer"].str.strip(), liste["Retningsflag"].str.strip().str.split(".").str[0]))
    kol = ["Turreference", "Stop-navn", "Stop-nummer", "Breddegrad (PLANLAGT)", "Længdegrad (PLANLAGT)"]
    hoved = rens(pd.read_csv(det, sep=";", encoding="utf-8", nrows=0))
    brug = [c for c in pd.read_csv(det, sep=";", encoding="utf-8", nrows=0).columns
            if c.strip().strip('"').strip() in kol]
    if len(brug) < len(kol):
        sys.exit(f"Details.csv mangler kolonner: {sorted(set(kol) - set(hoved.columns))}")
    stykker = []
    for ch in pd.read_csv(det, sep=";", encoding="utf-8", usecols=brug, dtype=str, chunksize=500_000):
        ch = rens(ch)
        ch = ch[ch["Stop-nummer"].notna() & (ch["Stop-nummer"].str.strip() != "")]
        stykker.append(ch)
    df = pd.concat(stykker, ignore_index=True)
    df["Stop-navn"] = df["Stop-navn"].str.strip()
    for c in ("Breddegrad (PLANLAGT)", "Længdegrad (PLANLAGT)"):
        df[c] = pd.to_numeric(df[c].str.replace(",", "."), errors="coerce")
    df["retning"] = df["Turreference"].str.strip().map(retning)
    pos = df.groupby("Stop-navn")[["Breddegrad (PLANLAGT)", "Længdegrad (PLANLAGT)"]].median()

    pts = cfg.get("points") or {}
    p1, p2 = pts.get("p1"), pts.get("p2")
    med_punkter = udfyldt(p1) and udfyldt(p2)
    linjer = ["Stoppesteder pr. kørselsretning, i den rækkefølge bussen kører dem (periode A).",
              "Navnene kan være forskellige i de to retninger, og stoppene kan ligge forskelligt (fx et stop på hver",
              "side af vejen). Vælg derfor start og slut for hver retning for sig, og kopiér navnene præcist.",
              "Meter før/efter er målt i ret linje langs strækningen; svinger ruten, er tallet kun vejledende.", ""]
    forslag, byt = {}, []
    for r in sorted(x for x in df["retning"].dropna().unique() if x in ("1", "2")):
        sek = Counter(tuple(g["Stop-navn"]) for _, g in df[df["retning"] == r].groupby("Turreference", sort=False))
        (raekke, n), ture = sek.most_common(1)[0], sum(sek.values())
        linjer.append(f"=== Retning {r}: {len(raekke)} stoppesteder (rækkefølgen for {n} af {ture} ture) ===")
        if med_punkter:
            st = [{"lat": pos.loc[s].iloc[0], "lon": pos.loc[s].iloc[1]} for s in raekke]
            i1 = min(range(len(st)), key=lambda i: afstand(st[i], p1))
            i2 = min(range(len(st)), key=lambda i: afstand(st[i], p2))
            foerst, sidst = (p1, p2) if i1 < i2 else (p2, p1)
            if (r == "1") != (i1 < i2):
                byt.append(r)
            s_vals = [s_langs(foerst, sidst, x["lat"], x["lon"]) for x in st]
            L = s_vals[0][1]
            ia, ib = min(i1, i2), max(i1, i2)
            # første stop uden for strækningen i hver ende, plus ét stop ekstra som margin
            start = next((i for i in range(ia, -1, -1) if s_vals[i][0] < 0), None)
            slut = next((i for i in range(ib, len(st)) if s_vals[i][0] > L), None)
            start = None if start is None else max(start - 1, 0)
            slut = None if slut is None else min(slut + 1, len(st) - 1)
            for i, navn in enumerate(raekke):
                s = s_vals[i][0]
                sted = f"{-s:.0f} m før" if s < 0 else (f"{s - L:.0f} m efter" if s > L else "på strækningen")
                maerke = "  <-- forslag: start" if i == start else ("  <-- forslag: slut" if i == slut else "")
                linjer.append(f"  {i + 1:3d}. {navn}   ({sted}){maerke}")
            if start is not None and slut is not None:
                forslag[r] = (raekke[start], raekke[slut])
        else:
            linjer += [f"  {i + 1:3d}. {navn}" for i, navn in enumerate(raekke)]
        linjer.append("")
    if med_punkter:
        if byt:
            linjer += ["OBS: retning 1 kører fra p2 mod p1. Byt p1 og p2 i config.yaml (koordinater og navne), og kør 1 igen.", ""]
        elif len(forslag) == 2:
            linjer += ["Forslag til config.yaml, punkt 4: ét stoppested før og ét efter strækningen, med et stop i margin.",
                       "Erstat de to stops-linjer i config.yaml med disse:",
                       "stops:"]
            linjer += [f'  direction_{r}: {{start: "{a}", end: "{b}"}}' for r, (a, b) in sorted(forslag.items())]
            linjer.append("")
    else:
        linjer += ["Udfyld p1 og p2 i config.yaml, og kør 1 igen: så foreslås start- og slutstop pr. retning.", ""]
    Path(ud).write_text("\n".join(linjer), encoding="utf-8")
    print(f"Skrev {ud}")


# ------------------------------------------------------------------ config med bump-vinduer

def beregnet_config(cfg_sti, ud):
    cfg = laes_config(cfg_sti)
    for k, v in (cfg.get("data") or {}).items():
        if isinstance(v, dict):
            for f in ("details_csv", "list_csv"):
                if v.get(f):
                    v[f] = str(sti_rel(cfg_sti, v[f]))
        elif k == "output":
            cfg["data"]["output"] = str(sti_rel(cfg_sti, v))
    kom = cfg.setdefault("komfort", {})
    pts = cfg.get("points") or {}
    fra, til = pts.get(kom.get("fra", "p1")), pts.get(kom.get("til", "p2"))
    if not kom.get("bump_vinduer") and fra and til:
        vinduer = {}
        for e in cfg.get("elementer") or []:
            if e.get("type") != "bump":
                continue
            r = float(e.get("radius_m") or STANDARD_RADIUS_M)
            s, _ = s_langs(fra, til, float(e["lat"]), float(e["lon"]))
            vinduer[str(e["navn"])] = [round(s - r), round(s + r)]
        kom["bump_vinduer"] = vinduer
        print("Bump-vinduer (meter fra " + str(fra.get("name", "p1")) + "): " +
              (", ".join(f"{k} {a}-{b}" for k, (a, b) in vinduer.items()) or "ingen bump"))
    Path(ud).parent.mkdir(parents=True, exist_ok=True)
    tekst = "# Lavet af forbered.py ud fra config.yaml. Ret i config.yaml, ikke her.\n"
    tekst += yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
    Path(ud).write_text(tekst, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("hvad", choices=["stopnavne", "config"])
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    (stopnavne if a.hvad == "stopnavne" else beregnet_config)(a.config, a.out)


if __name__ == "__main__":
    main()
