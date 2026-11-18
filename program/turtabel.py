#!/usr/bin/env python3
"""
turtabel.py (v1.1) - én flad tabel pr. tur og et kort overblik over køretid pr. stykke, pr. time og periode.

Ingen beregning ændres: tabellen samler det, analysen allerede har regnet. Eneste kilde er HAFAS-eksporten
(via analysens output og List.csv). v1.1: kolonnen Turnummer (planlagt turnummer fra List.csv).

Input:  output-mapperne fra analyse_v2.2.py (kørt med --export-segments) for periode A og evt. B:
        <mappe>/result.csv (køretid pr. stykke, Flag, Log) og <mappe>/segmenter.csv (tidspunkt for det matchede ping
        pr. punkt, kolonnen match_punkt). Rute læses fra List.csv (config: data.Periode_A/B.list_csv); mangler den,
        er Rute tom.
Config: samme YAML som analysen (periods, points, distances, data, evt. udvalg).
Output: turtabel.csv  én række pr. beholdt tur: periode, dato, ugedag, dagtype, time, retning, rute, planlagt turnummer, køretid pr. stykke,
                      tidspunkt ved hvert punkt, Flag, Log, Turreference. Til egen udforskning: indeholder tur-id og
                      deles ikke (pakkens regel 3). UTF-8 med BOM og ';', så Excel viser æ, ø og å.
        overblik.csv  køretid pr. stykke: n, p25, median, p75 pr. retning, periode og time (og 'alle' timer).
        overblik.md   samme overblik til at læse. Kun aggregerede tal.

    python turtabel.py --config config.yaml --a ud_A --b ud_B --out ud     (før og efter)
    python turtabel.py --config config.yaml --a ud_A --out ud              (kun én periode)

Definitioner:
  Dato     = Køredag fra List (en tur over midnat hører til køredagen).
  Time     = timen (0-23), da bussen passerede strækningens første punkt (det tidligst matchede punkt på turen).
  Tid <p>  = tidspunkt for det ping, analysen valgte som punktets position (samme ping, som køretiden regnes fra).
  Overblik = ture med tom Log, uden stoprække-match i Flag og med dagtype fra config (udvalg.dagtype, standard
             hverdage uden udvalg.helligdage), samme udvalg som zonetid og rapporten. Percentiler som opsummering.csv.

Exit-kode 0 = færdig; mangler en fil eller en kolonne, stopper kørslen med en dansk fejlbesked (exit 1).
Afhængigheder: pandas, numpy, pyyaml. Sæt PYTHONUTF8=1 på Windows.
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

VERSION = "1.1"
UGEDAGE = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
MIN_N = 20                       # timer med færre ture markeres med * i overblik.md
CHUNK = 500_000


# ------------------------------------------------------------------ config

def laes_config(sti):
    with open(sti, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    for k in ("points", "distances"):
        if not raw.get(k):
            raise SystemExit(f"Sektionen '{k}:' mangler i {sti}")
    udv = {"dagtype": "hverdage", "helligdage": []}
    udv.update({k: v for k, v in (raw.get("udvalg") or {}).items() if v is not None})
    if udv["dagtype"] not in ("hverdage", "alle"):
        raise SystemExit("udvalg.dagtype skal være 'hverdage' eller 'alle'")
    udv["helligdage"] = {str(x) for x in (udv.get("helligdage") or [])}
    return {
        "points": {pid: str(p.get("name", pid)) for pid, p in raw["points"].items()},
        "distances": {did: {"navn": str(d.get("name", did)), "from": d["from"], "to": d["to"]}
                      for did, d in raw["distances"].items()},
        "periods": raw.get("periods") or {},
        "data": raw.get("data") or {},
        "udvalg": udv,
    }


# ------------------------------------------------------------------ indlæsning

def _rens(s):
    return s.astype(str).str.strip().str.strip('"').str.strip()


def laes_result(mappe):
    sti = Path(mappe) / "result.csv"
    if not sti.exists():
        raise SystemExit(f"Filen findes ikke: {sti} (kør analyse_v2.2.py først)")
    return pd.read_csv(sti, sep=";", encoding="utf-8", dtype={"Turreference": str, "Log": str, "Flag": str})


def laes_punkttider(mappe, refs=None):
    """Tidspunkt for det matchede ping pr. (tur, punkt) fra segmenter.csv. Returnér DataFrame: Turreference x punkt-id."""
    sti = Path(mappe) / "segmenter.csv"
    if not sti.exists():
        raise SystemExit(f"Filen findes ikke: {sti} (kør analyse_v2.2.py med --export-segments)")
    dele = []
    for ch in pd.read_csv(sti, sep=";", encoding="utf-8", usecols=["Turreference", "datetime", "match_punkt"],
                          dtype=str, chunksize=CHUNK):
        ch = ch[ch["match_punkt"].fillna("").str.strip() != ""]
        if len(ch):
            dele.append(ch)
    if not dele:
        return pd.DataFrame()
    m = pd.concat(dele, ignore_index=True)
    m["punkt"] = m["match_punkt"].str.split(";")
    m = m.explode("punkt")
    m["punkt"] = m["punkt"].str.strip()
    if refs is not None:
        m = m[m["Turreference"].isin(refs)]
    dubl = int(m.duplicated(["Turreference", "punkt"]).sum())
    if dubl:
        print(f"  ADVARSEL: {dubl} punkter er matchet mere end én gang i samme tur; det første tidspunkt bruges")
    m = m.drop_duplicates(["Turreference", "punkt"], keep="first")
    return m.pivot(index="Turreference", columns="punkt", values="datetime")


def laes_rute(list_csv):
    """
    Rute og planlagt turnummer pr. tur fra List.csv (HAFAS). Returnér DataFrame med indeks Turreference og kolonnerne
    'Rute' ('Rute nr.', ellers 'Rute') og 'Turnummer' (den anden kolonne, der hedder Turnummer: det planlagte turnummer,
    som er den samme afgang hver dag; tom, hvis den mangler). None, hvis filen eller tur-kolonnen mangler.
    """
    if not list_csv or not Path(list_csv).exists():
        return None
    hoved = pd.read_csv(list_csv, sep=";", encoding="utf-8", nrows=0)
    rene = [c.strip().strip('"').strip() for c in hoved.columns]
    tur = [c for c, r in zip(hoved.columns, rene) if re.fullmatch(r"Turnummer(\.\d+)?", r)]
    rute_kol = next((c for k in ("Rute nr.", "Rute") for c, r in zip(hoved.columns, rene) if r == k), None)
    if not tur:
        return None
    brug = [tur[0]] + tur[1:2] + ([rute_kol] if rute_kol else [])
    lst = pd.read_csv(list_csv, sep=";", encoding="utf-8", usecols=brug, dtype=str)
    ud = pd.DataFrame({"Turreference": _rens(lst[tur[0]])})
    ud["Rute"] = _rens(lst[rute_kol]).replace({"nan": ""}) if rute_kol else ""
    ud["Turnummer"] = _rens(lst[tur[1]]).replace({"nan": ""}) if len(tur) > 1 else ""
    return ud.drop_duplicates("Turreference", keep="first").set_index("Turreference")


# ------------------------------------------------------------------ turtabel

def dagtype(dato, helligdage):
    d = pd.to_datetime(dato)
    t = np.where(d.dt.dayofweek == 5, "lørdag", np.where(d.dt.dayofweek == 6, "søndag", "hverdag"))
    return pd.Series(np.where(dato.astype(str).isin(helligdage), "helligdag", t), index=dato.index)


def lav_turtabel(cfg, perioder):
    """
    perioder = {'A': (result_df, punkttider_df, rute_serie_eller_None), ['B': ...]}.
    Returnér (turtabel, kontrol) hvor kontrol = {'ture', 'uden_tid', 'koretid_ok', 'koretid_tjekket'}.
    """
    pts, dists, udv = cfg["points"], cfg["distances"], cfg["udvalg"]
    dele = []
    kontrol = {"ture": 0, "uden_tid": 0, "koretid_ok": 0, "koretid_tjekket": 0}
    for p, (r, tider, rute) in perioder.items():
        if r.empty:
            continue
        t = pd.DataFrame(index=r.index)
        t["Periode"] = p
        t["Periodenavn"] = r["Periode"].astype(str)
        t["Dato"] = r["Køredag"].astype(str)
        d = pd.to_datetime(t["Dato"], errors="coerce")
        t["Ugedag_nr"] = (d.dt.dayofweek + 1).astype("Int64")
        t["Ugedag"] = d.dt.dayofweek.map(lambda i: UGEDAGE[int(i)] if pd.notna(i) else "")
        t["Dagtype"] = dagtype(t["Dato"], udv["helligdage"])
        t["Retning"] = r["Retning"]
        t["Rute"] = r["Turreference"].map(rute["Rute"]).fillna("") if rute is not None else ""
        t["Turnummer"] = r["Turreference"].map(rute["Turnummer"]).fillna("") if rute is not None else ""
        # tidspunkt pr. punkt (matchet ping)
        tid = {}
        for pid in pts:
            if not tider.empty and pid in tider.columns:
                tid[pid] = pd.to_datetime(r["Turreference"].map(tider[pid]), errors="coerce")
            else:
                tid[pid] = pd.Series(pd.NaT, index=r.index)
        tid_df = pd.DataFrame(tid)
        foerste = tid_df.min(axis=1)
        t["Time"] = foerste.dt.hour.astype("Int64")
        for did, ds in dists.items():
            kol = f"{ds['navn']} - køretid (sek)"
            if kol not in r.columns:
                raise SystemExit(f"Kolonnen '{kol}' findes ikke i result.csv for periode {p}. Er det samme config?")
            t[f"Køretid {ds['navn']} (s)"] = pd.to_numeric(r[kol], errors="coerce").astype("Int64")
            # kontrol: køretid = |tid ved til-punkt - tid ved fra-punkt|
            diff = (tid_df[ds["to"]] - tid_df[ds["from"]]).dt.total_seconds().abs().round()
            ok = diff.notna() & t[f"Køretid {ds['navn']} (s)"].notna()
            kontrol["koretid_tjekket"] += int(ok.sum())
            kontrol["koretid_ok"] += int((diff[ok] == t.loc[ok, f"Køretid {ds['navn']} (s)"].astype(float)).sum())
        for pid, navn in pts.items():
            t[f"Tid {navn}"] = tid_df[pid].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")
        t["Flag"] = r["Flag"].fillna("")
        t["Log"] = r["Log"].fillna("")
        t["I_overblik"] = overblik_maske(t, udv).astype(int)
        t["Turreference"] = r["Turreference"]
        kontrol["ture"] += len(t)
        kontrol["uden_tid"] += int(foerste.isna().sum())
        dele.append(t)
    tt = pd.concat(dele, ignore_index=True) if dele else pd.DataFrame()
    return tt, kontrol


def overblik_maske(t, udv, uden_stopraekke=True):
    m = t["Log"].fillna("") == ""
    if uden_stopraekke:
        m &= ~t["Flag"].fillna("").str.contains("stoprække_", regex=False)
    if udv["dagtype"] == "hverdage":
        m &= t["Dagtype"] == "hverdag"
    return m


# ------------------------------------------------------------------ overblik

def _stat(v):
    v = v.dropna().astype(float).to_numpy()
    if not len(v):
        return {"n": 0, "p25": None, "median": None, "p75": None}
    p25, p50, p75 = np.percentile(v, [25, 50, 75])
    return {"n": int(len(v)), "p25": round(float(p25), 1), "median": round(float(p50), 1), "p75": round(float(p75), 1)}


def lav_overblik(tt, cfg, maske=None):
    """Lang tabel: Stykke, Retning, Periode, Time ('alle' eller 0-23), n, p25, median, p75."""
    if maske is None:
        maske = tt["I_overblik"] == 1 if len(tt) else pd.Series(dtype=bool)
    sub = tt[maske]
    rows = []
    for ds in cfg["distances"].values():
        kol = f"Køretid {ds['navn']} (s)"
        for (ret, p), g in sub.groupby(["Retning", "Periode"], sort=True):
            rows.append({"Stykke": ds["navn"], "Retning": ret, "Periode": p, "Time": "alle", **_stat(g[kol])})
            for h, gh in g.groupby("Time", sort=True):
                rows.append({"Stykke": ds["navn"], "Retning": ret, "Periode": p, "Time": int(h), **_stat(gh[kol])})
    return pd.DataFrame(rows, columns=["Stykke", "Retning", "Periode", "Time", "n", "p25", "median", "p75"])


def _celle(r):
    if r is None or r["n"] == 0:
        return "", ""
    mark = "*" if r["n"] < MIN_N else ""
    return f"{r['n']}{mark}", f"{r['median']:g} ({r['p25']:g}–{r['p75']:g})"


def overblik_md(ov, cfg, perioder):
    udv = cfg["udvalg"]
    navne = {p: str((cfg["periods"].get(p) or {}).get("name", p)) for p in perioder}
    to = "B" in perioder
    md = ["# Overblik: køretid pr. stykke, pr. time og periode", "",
          f"Lavet af turtabel.py v{VERSION}. Køretid i sekunder: median (p25–p75), n = antal ture. "
          f"Time = timen, da bussen passerede strækningens første punkt.",
          f"Udvalg: tom Log, ingen stoprække-match, dagtype {udv['dagtype']}"
          + (" (uden helligdage fra config)" if udv["dagtype"] == "hverdage" else "") + ". "
          f"* = under {MIN_N} ture: usikker median.",
          "Perioder: " + ", ".join(f"{p} = {navne[p]}" for p in perioder) + ". "
          "Alle ture pr. tur står i turtabel.csv (til egen udforskning, deles ikke).", ""]
    if ov.empty:
        return md + ["(ingen ture i udvalget)", ""]
    for stykke in ov["Stykke"].unique():
        for ret in sorted(ov.loc[ov["Stykke"] == stykke, "Retning"].unique()):
            s = ov[(ov["Stykke"] == stykke) & (ov["Retning"] == ret)]
            md += [f"## {stykke} · retning {ret}", ""]
            hoved = "| Time | " + " | ".join(f"n {p} | {navne[p]}" for p in perioder)
            hoved += " | Ændring median (s) |" if to else " |"
            md += [hoved, "|---|" + "---:|---|" * len(perioder) + ("---:|" if to else "")]
            timer = ["alle"] + sorted(int(h) for h in s["Time"] if h != "alle")
            for h in dict.fromkeys(timer):
                celler, med = [], {}
                for p in perioder:
                    r = s[(s["Periode"] == p) & (s["Time"] == h)]
                    rr = r.iloc[0].to_dict() if len(r) else None
                    n, c = _celle(rr)
                    celler += [n, c]
                    med[p] = rr["median"] if rr and rr["n"] else None
                lab = "**alle**" if h == "alle" else f"{h:02d}"
                linje = f"| {lab} | " + " | ".join(celler)
                if to:
                    d = (med["B"] - med["A"]) if med.get("A") is not None and med.get("B") is not None else None
                    linje += f" | {d:+g} |" if d is not None else " | |"
                else:
                    linje += " |"
                md.append(linje)
            md.append("")
    return md


# ------------------------------------------------------------------ main

def main(argv=None):
    ap = argparse.ArgumentParser(description="Flad tabel pr. tur og overblik over køretid pr. stykke, time og periode.")
    ap.add_argument("--config", required=True, help="samme YAML som analysen (points, distances, periods, data, udvalg)")
    ap.add_argument("--a", required=True, help="output-mappe for periode A: result.csv og segmenter.csv")
    ap.add_argument("--b", default=None, help="output-mappe for periode B; udelades ved kun én periode")
    ap.add_argument("--out", required=True, help="mappe til turtabel.csv, overblik.csv og overblik.md")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cfg = laes_config(a.config)
    print(f"turtabel v{VERSION}: {len(cfg['distances'])} stykke(r), {len(cfg['points'])} punkter, "
          f"{'før og efter' if a.b else 'én periode'}")
    perioder = {}
    for p, mappe in (("A", a.a), ("B", a.b)):
        if mappe is None:
            continue
        r = laes_result(mappe)
        tider = laes_punkttider(mappe, set(r["Turreference"]))
        rute = laes_rute((cfg["data"].get(f"Periode_{p}") or {}).get("list_csv"))
        if rute is None:
            print(f"  Periode {p}: List.csv eller kolonnen 'Rute nr.'/'Rute' findes ikke - Rute er tom")
        perioder[p] = (r, tider, rute)
        print(f"  Periode {p}: {len(r)} ture i result.csv, {len(tider)} med tidspunkter i segmenter.csv")
    tt, k = lav_turtabel(cfg, perioder)
    ov = lav_overblik(tt, cfg)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tt.to_csv(out / "turtabel.csv", sep=";", index=False, encoding="utf-8-sig")
    ov.to_csv(out / "overblik.csv", sep=";", index=False, encoding="utf-8")
    (out / "overblik.md").write_text("\n".join(overblik_md(ov, cfg, list(perioder))) + "\n", encoding="utf-8")
    print(f"  {k['ture']} ture i turtabellen, {int(tt['I_overblik'].sum()) if len(tt) else 0} i overblikket; "
          f"{k['uden_tid']} uden tidspunkt")
    print(f"  Kontrol: køretid = tid ved til-punkt minus tid ved fra-punkt i {k['koretid_ok']} af "
          f"{k['koretid_tjekket']} tilfælde")
    if k["koretid_ok"] != k["koretid_tjekket"]:
        print("  ADVARSEL: tidspunkterne passer ikke med køretiden for alle ture. Er result.csv og segmenter.csv "
              "fra samme kørsel?")
    print(f"  Skrev {out / 'turtabel.csv'}, {out / 'overblik.csv'} og {out / 'overblik.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
