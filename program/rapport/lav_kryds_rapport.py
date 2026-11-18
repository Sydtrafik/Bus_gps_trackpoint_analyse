#!/usr/bin/env python3
"""
lav_kryds_rapport.py (v1.0) - rapport over køretid gennem et kryds: køretid pr. stykke over døgnet, pr. rute og pr.
planlagt tur, for én periode eller før/efter. Én selvstændig HTML-fil.

Eneste kilde er HAFAS-eksporten: tallene kommer fra turtabel.csv (turtabel.py v1.1+), som er lavet af analysens
output og List.csv. Rapporten indeholder kun aggregerede tal (median, p25, p75, antal ture) pr. time, rute og planlagt
turnummer; ingen tur-id og ingen enkelte kørsler.

    python lav_kryds_rapport.py --config config.yaml --turtabel ud\\turtabel.csv --out ud\\kryds_rapport.html

Config: samme YAML som analysen (points, point_order, distances, periods) og evt. rapport: emne (hvad og hvor, fx
"Krydset Søndre Tobølvej / Sædding Strandvej, Esbjerg"; uden emne bruges de to stop fra stops:), titel, undertitel,
afsender, kilde. Stykkerne vises med punkternes navne fra config (fra → til), så giv punkterne sigende navne. Uden titel beregnes en ud fra tallene (største forskel mellem to timer på et stykke, timer med mindst
OBS_N_TIME ture, alle dage og ruter).

Ingen skjult filtrering (Anthon 2026-11-16/17):
 - Dagtype og rute er synlige valg. Standard er hverdage (det typiske døgn med mest trafik), og titlen siger det.
 - Ture med dårlige data er fravalgt, men synligt: rapporten viser antal og andel. Det er ture, hvor et punkt er
   matchet til en stop-række (planlagt position, Flag 'stoprække_') eller ligger over analysens afstandsgrænse fra GPS
   (Log udfyldt).
 - Intet vises ikke pga. få ture: timer med under OBS_N_TIME ture og planlagte ture med under OBS_N_TUR kørsler er med
   og markeret, og afsnittet "Datagrundlag" viser antal ture pr. time, så skævheder ses.
Exit-kode 0 = færdig; mangler en fil eller en kolonne, stopper kørslen med en dansk fejlbesked.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

VERSION = "1.0"
HER = Path(__file__).resolve().parent
OBS_N_TIME = 20          # timer med færre ture får OBS (usikker median); de vises stadig
OBS_N_TUR = 10           # planlagte ture med færre kørsler får OBS; de vises stadig
ALLE = "Alle ruter"
DAGTYPER = [("Hverdage", {"hverdag"}), ("Weekend og helligdage", {"lørdag", "søndag", "helligdag"}), ("Alle dage", None)]
STANDARD_DAG = "Hverdage"


def stat(v):
    v = pd.to_numeric(v, errors="coerce").dropna().to_numpy(float)
    if not len(v):
        return None
    p25, p50, p75 = np.percentile(v, [25, 50, 75])
    return {"n": int(len(v)), "p25": round(float(p25), 1), "m": round(float(p50), 1), "p75": round(float(p75), 1)}


def laes(cfg_sti, tt_sti):
    cfg = yaml.safe_load(Path(cfg_sti).read_text(encoding="utf-8")) or {}
    if not Path(tt_sti).exists():
        raise SystemExit(f"Filen findes ikke: {tt_sti} (kør turtabel.py først)")
    tt = pd.read_csv(tt_sti, sep=";", encoding="utf-8-sig", dtype={"Turnummer": str, "Rute": str, "Flag": str, "Log": str})
    for k in ("Periode", "Retning", "Time", "Dagtype"):
        if k not in tt.columns:
            raise SystemExit(f"Kolonnen '{k}' findes ikke i {tt_sti}. Er den lavet af turtabel.py?")
    if "Turnummer" not in tt.columns:
        raise SystemExit(f"Kolonnen 'Turnummer' mangler i {tt_sti}: lav turtabellen igen med turtabel.py v1.1 eller nyere")
    for k in ("Rute", "Flag", "Log"):
        tt[k] = tt[k].fillna("").astype(str) if k in tt.columns else ""
    tt["Turnummer"] = tt["Turnummer"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    return cfg, tt


def foerste_tid_min(tt, pts):
    """Minut på døgnet for passage af turens første punkt (tidligste 'Tid <punkt>')."""
    kol = [f"Tid {p}" for p in pts if f"Tid {p}" in tt.columns]
    t = pd.concat([pd.to_datetime(tt[k], errors="coerce") for k in kol], axis=1).min(axis=1)
    return t.dt.hour * 60 + t.dt.minute


def byg_data(cfg, tt):
    pts = {pid: str(p.get("name", pid)) for pid, p in (cfg.get("points") or {}).items()}
    dists = (cfg.get("distances") or {}).items()
    stykker = [str(d.get("name", did)) for did, d in dists]
    fra_til = {str(d.get("name", did)): (pts.get(d.get("from"), d.get("from")), pts.get(d.get("to"), d.get("to")))
               for did, d in dists}
    for s in stykker:
        if f"Køretid {s} (s)" not in tt.columns:
            raise SystemExit(f"Kolonnen 'Køretid {s} (s)' findes ikke i turtabellen. Er det samme config?")
    perioder = sorted(tt["Periode"].dropna().unique())
    pnavn = {p: str(((cfg.get("periods") or {}).get(p) or {}).get("name", p)) for p in perioder}
    po = cfg.get("point_order") or {}
    tt = tt.copy()
    tt["_min"] = foerste_tid_min(tt, pts.values())
    tt["_stop"] = tt["Flag"].str.contains("stoprække_", regex=False)
    tt["_afst"] = tt["Log"] != ""
    tt["_fra"] = tt["_stop"] | tt["_afst"]          # fravalgt pga. dårlige data (vises som antal og andel)
    retninger = []
    for ret in sorted(tt["Retning"].dropna().unique()):
        rt = tt[tt["Retning"] == ret]
        orden = po.get(f"direction_{int(ret)}") or []
        rnavn = " → ".join(pts.get(p, p) for p in orden) or f"Retning {int(ret)}"
        ruter = [ALLE] + sorted(r for r in rt["Rute"].unique() if r)
        R = {"retning": int(ret), "navn": rnavn, "ruter": ruter, "obs": {},
             "stykker": [{"navn": s, "fra": fra_til[s][0], "til": fra_til[s][1], "pr": {}} for s in stykker]}
        for dnavn, dset in DAGTYPER:
            dt = rt if dset is None else rt[rt["Dagtype"].isin(dset)]
            R["obs"][dnavn] = {}
            for S in R["stykker"]:
                S["pr"][dnavn] = {}
            for ru in ruter:
                alt = dt if ru == ALLE else dt[dt["Rute"] == ru]
                R["obs"][dnavn][ru] = {p: {"n": int((alt["Periode"] == p).sum()),
                                           "fravalgt": int((alt["_fra"] & (alt["Periode"] == p)).sum()),
                                           "stop": int((alt["_stop"] & (alt["Periode"] == p)).sum()),
                                           "afstand": int((alt["_afst"] & (alt["Periode"] == p)).sum())} for p in perioder}
                sub = alt[~alt["_fra"]]
                for S in R["stykker"]:
                    kol = f"Køretid {S['navn']} (s)"
                    alle = {p: stat(sub.loc[sub["Periode"] == p, kol]) for p in perioder}
                    timer = {p: [dict(t=int(h), **st) for h, g in sub[sub["Periode"] == p].groupby("Time")
                                 if (st := stat(g[kol])) is not None] for p in perioder}
                    ture = []
                    for tn, g in sub[sub["Turnummer"] != ""].groupby("Turnummer"):
                        rk = {"tur": tn, "rute": ", ".join(sorted(set(g["Rute"]) - {""})),
                              "kl": int(np.nanmedian(g["_min"])) if g["_min"].notna().any() else None}
                        for p in perioder:
                            rk[p] = stat(g.loc[g["Periode"] == p, kol])
                        ture.append(rk)
                    ture.sort(key=lambda x: (x["kl"] is None, x["kl"] or 0, x["tur"]))
                    S["pr"][dnavn][ru] = {"alle": alle, "timer": timer, "ture": ture}
        retninger.append(R)
    return {"perioder": perioder, "periodenavne": pnavn, "retninger": retninger, "dagtyper": [d for d, _ in DAGTYPER],
            "standard_dag": STANDARD_DAG, "obs_n_time": OBS_N_TIME, "obs_n_tur": OBS_N_TUR, "version": VERSION}


def emne_fra_stop(cfg):
    """Hvad er undersøgt, når rapport.emne mangler: krydset mellem de to stop i config (første retning)."""
    st = next(iter((cfg.get("stops") or {}).values()), None) or {}
    a, b = st.get("start"), st.get("end")
    return f"Kryds mellem stoppene {a} og {b}" if a and b else "Kryds"


def beregn_titel(data):
    """Største forskel mellem to timer med mindst OBS_N_TIME ture på et stykke (hverdage, alle ruter, sidste periode).
    Kun timer med nok ture vælges til titlen, så den ikke bygger på en usikker median; alle timer vises i grafen."""
    p = data["perioder"][-1]
    bedst = None
    for R in data["retninger"]:
        for S in R["stykker"]:
            t = [x for x in S["pr"][STANDARD_DAG][ALLE]["timer"][p] if x["n"] >= OBS_N_TIME]
            if len(t) < 2:
                continue
            hi, lo = max(t, key=lambda x: x["m"]), min(t, key=lambda x: x["m"])
            if bedst is None or hi["m"] - lo["m"] > bedst[0]:
                bedst = (hi["m"] - lo["m"], S["navn"], hi, lo)
    if bedst is None:
        return f"Køretid gennem krydset pr. stykke, {STANDARD_DAG.lower()}"
    _, s, hi, lo = bedst
    return f"På {STANDARD_DAG.lower()} tager stykket {s} {hi['m']:g} s kl. {hi['t']:02d} mod {lo['m']:g} s kl. {lo['t']:02d}"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kryds-rapport: køretid pr. stykke over døgnet, pr. rute og planlagt tur.")
    ap.add_argument("--config", required=True, help="samme YAML som analysen")
    ap.add_argument("--turtabel", required=True, help="turtabel.csv fra turtabel.py (v1.1 eller nyere)")
    ap.add_argument("--out", required=True, help="HTML-fil, der skrives")
    ap.add_argument("--skabelon", default=str(HER / "kryds_skabelon.html"))
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cfg, tt = laes(a.config, a.turtabel)
    data = byg_data(cfg, tt)
    rap = cfg.get("rapport") or {}
    titel = str(rap.get("titel") or beregn_titel(data))
    data["tekst"] = {"emne": str(rap.get("emne") or emne_fra_stop(cfg)),
                     "undertitel": str(rap.get("undertitel") or "Køretid pr. stykke · bussernes GPS"),
                     "afsender": str(rap.get("afsender") or ""),
                     "kilde": str(rap.get("kilde") or "Kilde: realtidsdata (GPS-positioner) fra HAFAS.")}
    html = Path(a.skabelon).read_text(encoding="utf-8")
    vendor = (HER / "vendor" / "echarts.min.js").read_text(encoding="utf-8")
    html = (html.replace("{{TITEL}}", titel.replace("<", "&lt;"))
                .replace("__RAPPORTDATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
                .replace("/*__ECHARTS__*/", vendor))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    n_ture = len(data["retninger"][0]["stykker"][0]["pr"]["Alle dage"][ALLE]["ture"]) if data["retninger"] else 0
    n_fra = sum(o["fravalgt"] for R in data["retninger"] for o in R["obs"]["Alle dage"][ALLE].values())
    print(f"lav_kryds_rapport v{VERSION}: {len(data['retninger'])} retning(er), {len(data['perioder'])} periode(r), "
          f"{len(tt)} ture, heraf {n_fra} fravalgt pga. dårlige data (vises i rapporten), {n_ture} planlagte ture. "
          f"Titel: {titel}")
    print(f"  Skrev {out} ({out.stat().st_size // 1024} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
