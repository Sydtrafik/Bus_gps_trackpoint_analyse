#!/usr/bin/env python3
"""
lav_rapportdata_v1.2.py - samler resultaterne til én rapportdata.json med synlige valg for dage, rute og time.
byg_rapport.py sætter filen ind i skabelon_v1.2.html.

Forskel fra lav_rapportdata.py (v1.1, beholdt uændret): tallene regnes også for andre dage, pr. rute og pr. time, så
rapporten kan vise datagrundlaget og lade læseren vælge. Med standardvalget (dagtypen fra udvalg: i config, alle ruter,
alle timer) er nøgletal, fordeling, fartprofil, drift og zonetid de samme som i v1.1. Genbruger v1.1's funktioner
(køretidskolonne, fart pr. tur) og zonetid.py's udvalg.

Input:  som v1.1 (output-mapperne for A og evt. B: result.csv, komfort*.csv, segmenter.csv; zonetid.json) plus
        turtabel.csv fra turtabel.py v1.1+ (dagtype, rute, planlagt turnummer og time pr. tur, fra HAFAS-eksporten).
Config: som v1.1, og valgfrit rapport.vej: vejtype, hastighed, bumptype, andre_foranstaltninger (tekst, som brugeren
        skriver; vises i "Om strækningen").
Output: rapportdata.json. Kun aggregerede tal (medianer, andele, antal) og tekster: ingen tur-id, ingen positioner pr.
        ping. Planlagte turnumre (samme afgang hver dag) står med antal kørsler og median, ikke enkelte kørsler.

    python lav_rapportdata_v1.2.py --config cfg.yaml --a ud\\A --b ud\\B --turtabel ud\\turtabel.csv --zonetid ud\\zonetid.json --out ud\\rapportdata.json

Ingen skjult filtrering (Anthon 2026-11-16/17):
 - Dage (hverdage / weekend og helligdage / alle dage), rute og time er synlige valg. Standard er udvalg.dagtype fra
   config (hverdage), alle ruter og alle timer; titlen og zonetiden gælder standardvalget.
 - Ture med dårlige data er fravalgt, men talt synligt (tabellen fravalg): stoprække-match (Flag), langt fra GPS (Log) og
   komfortberegning ikke ok (status). Samme udvalg som v1.1 og zonetid.py.
 - Intet udelades pga. få ture: grupper med få ture har tallene med (skabelonen markerer under OBS_N ture), og måneder
   med under 5 dage er med og markeret (feltet Faa) i stedet for at blive sprunget over som i v1.1.

Tabeller (felterne Dag, Rute, Time angiver valget; Time = -1 er alle timer):
  omfang, nogletal, fartprofil (kompakt: lister pr. 10 m), maaned, drift   pr. Dag x Rute x Time
  ture        pr. Dag x Rute: planlagte ture (turnummer, klokkeslæt = median over dagene) med antal og median køretid
  fordeling   additive antal pr. komfortklasse med Dagtype (hverdag/lørdag/søndag/helligdag), Rute og Time
  fravalg     additive antal ture i analysen og fravalgte pr. Periode x Retning x Dagtype x Rute x Time
  zonetid, foelsomhed   som v1.1 (standardvalget; zonetid.py regner kun det)

Afhængigheder: som v1.1 (pandas, numpy, pyyaml, zonetid.py, komfort_v1.1/v1.0, lav_rapportdata.py). PYTHONUTF8=1 på Windows.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import zonetid as Z  # noqa: E402
import lav_rapportdata as R11  # noqa: E402

K = Z.K
VERSION = "1.2"
GRUPPER = R11.GRUPPER
r2, pct = R11.r2, R11.pct
ALLE_RUTER = "Alle ruter"
UKENDT_RUTE = "ukendt"
ALLE_TIMER = -1
DAGTYPER = [("Hverdage", ["hverdag"]), ("Weekend og helligdage", ["lørdag", "søndag", "helligdag"]), ("Alle dage", None)]
OBS_N = 20                 # grupper med færre ture markeres i rapporten (usikker median); de vises stadig
OBS_N_TUR = 10             # planlagte ture med færre kørsler markeres (som kryds-rapporten); de vises stadig
OBS_DAGE_MAANED = 5        # måneder med færre dage markeres (v1.1 sprang dem over)
VEJ_FELTER = ("vejtype", "hastighed", "bumptype", "andre_foranstaltninger")
TT_KOL = ("Periode", "Turreference", "Dagtype", "Rute", "Turnummer", "Time")


def laes_turtabel(sti):
    """turtabel.csv -> DataFrame med periode, Turreference, _dagtype, _rute, _tur, _time, _min (minut på døgnet ved første punkt)."""
    sti = Path(sti)
    if not sti.exists():
        raise SystemExit(f"Filen findes ikke: {sti} (kør turtabel.py først; koer_analyse.bat valg 3 gør det)")
    tt = pd.read_csv(sti, sep=";", encoding="utf-8-sig", dtype=str)
    mangler = [k for k in TT_KOL if k not in tt.columns]
    if mangler:
        raise SystemExit(f"Kolonne(r) {mangler} mangler i {sti}: lav turtabellen igen med turtabel.py v1.1 eller nyere")
    tid = [c for c in tt.columns if c.startswith("Tid ")]
    t = pd.concat([pd.to_datetime(tt[c], errors="coerce") for c in tid], axis=1).min(axis=1) if tid else pd.Series(pd.NaT, index=tt.index)
    ud = pd.DataFrame({
        "periode": tt["Periode"], "Turreference": tt["Turreference"], "_dagtype": tt["Dagtype"].fillna(""),
        "_rute": tt["Rute"].fillna("").str.strip().replace("", UKENDT_RUTE),
        "_tur": tt["Turnummer"].fillna("").str.replace(r"\.0$", "", regex=True),
        "_time": pd.to_numeric(tt["Time"], errors="coerce"), "_min": t.dt.hour * 60 + t.dt.minute})
    if ud["_time"].isna().any():
        raise SystemExit(f"{int(ud['_time'].isna().sum())} ture i {sti} har ingen Time. Lav turtabellen igen.")
    ud["_time"] = ud["_time"].astype(int)
    return ud


def dagset(navn):
    return dict(DAGTYPER)[navn]


def stat4(v):
    v = pd.to_numeric(v, errors="coerce").dropna().to_numpy(float)
    if not len(v):
        return None
    p25, p50, p75 = np.percentile(v, [25, 50, 75])
    return [int(len(v)), r2(p50, 1), r2(p25, 1), r2(p75, 1)]


def profiler(perioder, g, kom, lat0, lon0, enhed, L, std_keys, retninger_std, log, sid):
    """Fart pr. 10 m pr. tur (som v1.1). Returnér (DataFrame k, bin, v, periode, Retning, Gruppe; fremad-tal i standardvalget)."""
    bin_max = int(L // 10 * 10)
    meta = g.set_index("_k")[["periode", "Retning", "stillestand"]]
    recs, fremad_antal = [], {r: [0, 0] for r in retninger_std}
    for p, (_r, _k, seg) in perioder.items():
        seg = seg.assign(_k=p + "|" + seg["Turreference"].astype(str))
        seg = seg[(seg["er_stoprække"] == 0) & seg["_k"].isin(meta.index)].copy()
        sx, sd = K.projicer(seg["lat"].to_numpy(), seg["lon"].to_numpy(), lat0, lon0, enhed)
        seg["s"], seg["d"] = sx, sd
        mg = kom["korridor_margin_m"]
        seg = seg[(seg["s"] >= -mg) & (seg["s"] <= L + mg) & (seg["d"].abs() <= kom["korridor_sideafstand_m"])]
        seg["t"] = (pd.to_datetime(seg["datetime"], format="%Y-%m-%d %H:%M:%S") - pd.Timestamp("1970-01-01")).dt.total_seconds()
        antal = 0
        for k, gg in seg.groupby("_k", sort=False):
            res = R11.tur_profil(gg["t"].to_numpy(dtype=float), gg["s"].to_numpy(), L, kom)
            if res is None:
                continue
            sg, vk, fremad = res
            ret = int(meta.at[k, "Retning"])
            if k in std_keys and ret in fremad_antal:
                fremad_antal[ret][0 if fremad else 1] += 1
            b = np.clip(np.floor(sg / 10).astype(int) * 10, 0, bin_max)
            dd = pd.DataFrame({"bin": b, "v": vk}).groupby("bin")["v"].mean().reset_index()
            dd["_k"] = k
            dd["periode"] = p
            dd["Retning"] = str(ret)
            dd["Gruppe"] = "Uden stop" if int(meta.at[k, "stillestand"]) == 0 else "Med stop"
            recs.append(dd)
            antal += 1
        log(f"  strækning {sid}: fart pr. tur periode {p}: {antal} ture")
    cols = ["bin", "v", "_k", "periode", "Retning", "Gruppe"]
    return (pd.concat(recs, ignore_index=True) if recs else pd.DataFrame(columns=cols)), fremad_antal, bin_max


def bygg_straekning(s, cfg, perioder, zj, tt, out, log):
    """Beregner alle tabeller for én strækning (rækker får feltet S) og lægger dem i out. Returnér strækningens meta."""
    raw, pts, udv = cfg["raw"], cfg["points"], cfg["udvalg"]
    rap = raw.get("rapport") or {}
    sid, kom = s["id"], s["komfort"]
    PER = list(perioder)
    tosidet = len(PER) == 2
    lat0, lon0, enhed, L = K.linje_geometri(pts[kom["fra"]], pts[kom["til"]])
    if kom.get("laengde_m"):
        L = float(kom["laengde_m"])

    # ---- samlet tabel pr. tur (som v1.1) + turtabellens dagtype, rute, planlagt tur og time ----
    dele = []
    for p, (r, k, _seg) in perioder.items():
        kd = Z.komfort_for(k, sid)
        kd = kd.drop(columns=[c for c in ("Periode", "Retning", "Køredag") if c in kd.columns])
        d = r.merge(kd, on="Turreference", how="left", validate="1:1")
        d["periode"] = p
        dele.append(d)
    df = pd.concat(dele, ignore_index=True)
    kt_kol, kt_id = R11.koretid_kolonne(raw, s, df, len(cfg["straekninger"]))
    df["Turreference"] = df["Turreference"].astype(str)
    df = df.merge(tt, on=["periode", "Turreference"], how="left", validate="1:1")
    if df["_time"].isna().any():
        n = int(df["_time"].isna().sum())
        raise SystemExit(f"{n} ture i result.csv findes ikke i turtabel.csv. Lav turtabellen igen med samme analyse (turtabel.py).")
    df["_time"] = df["_time"].astype(int)
    df["_k"] = df["periode"] + "|" + df["Turreference"]
    df["gyldig"] = Z.gyldig_maske(df)
    std_dag = "Alle dage" if udv["dagtype"] == "alle" else "Hverdage"
    std_maske = Z.dagtype_maske(df, udv)
    ds = dagset(std_dag)
    tjek = pd.Series(True, index=df.index) if ds is None else df["_dagtype"].isin(ds)
    if (std_maske != tjek).any():
        raise SystemExit(f"Dagtypen i turtabel.csv passer ikke med udvalg i config ({int((std_maske != tjek).sum())} ture). "
                         f"Lav turtabellen igen med samme config (udvalg.helligdage).")
    df["hverdag"] = std_maske

    # ---- fravalg: additive antal (synligt i rapporten) ----
    df["_stop"] = df["Flag"].fillna("").str.contains("stoprække_", regex=False)
    df["_afst"] = df["Log"].fillna("") != ""
    df["_komf"] = df["status"] != "ok"
    df["_fra"] = ~df["gyldig"]
    fv = df.groupby(["periode", "Retning", "_dagtype", "_rute", "_time"]).agg(
        n=("_fra", "size"), fra=("_fra", "sum"), stop=("_stop", "sum"), afst=("_afst", "sum"), komf=("_komf", "sum")).reset_index()
    fv = fv.rename(columns={"_dagtype": "dagtype", "_rute": "rute", "_time": "time"})
    for r in fv.itertuples():
        out["fravalg"].append({"S": sid, "Periode": r.periode, "Retning": str(r.Retning), "Dagtype": r.dagtype, "Rute": r.rute,
                               "Time": int(r.time), "n": int(r.n), "fra": int(r.fra), "stop": int(r.stop), "afst": int(r.afst),
                               "komf": int(r.komf)})

    g = df[df["gyldig"]].copy()
    g["dato"] = pd.to_datetime(g["Køredag"])
    g["stop"] = np.where(g["stillestand"] == 0, "Uden stop", "Med stop")
    h = g[g["hverdag"]]
    log(f"  strækning {sid}: ture i result {len(df)}, gyldige {len(g)}, i standardvalget (dagtype {udv['dagtype']}) {len(h)}")
    retninger = [r for r in (1, 2) if (h["Retning"] == r).any()]
    if not retninger or any(len(h[h["periode"] == p]) == 0 for p in PER):
        raise SystemExit(f"Strækning '{sid}': ingen ture i udvalget i mindst én periode (tjek udvalg.dagtype/helligdage, "
                         f"komfort status, strækningens fra/til og periode-mapperne)")

    suf = [K.kolonnesuffix(t) for t in kom["taerskler_ms2"]]
    t1, t2 = suf[0], suf[-1]
    g["klasse"] = np.where(g[f"opbr_haendelser_{t2}"] >= 1, "Kraftig", np.where(g[f"opbr_haendelser_{t1}"] >= 1, "Maerkbar", "Ingen"))
    g["klasse_acc"] = np.where(g[f"acc_haendelser_{t2}"] >= 1, "Kraftig", np.where(g[f"acc_haendelser_{t1}"] >= 1, "Maerkbar", "Ingen"))
    g["klasse_sam"] = np.where((g[f"opbr_haendelser_{t2}"] >= 1) | (g[f"acc_haendelser_{t2}"] >= 1), "Kraftig",
                               np.where((g[f"opbr_haendelser_{t1}"] >= 1) | (g[f"acc_haendelser_{t1}"] >= 1), "Maerkbar", "Ingen"))
    g["maaned"] = g["dato"].dt.strftime("%Y-%m")

    # ---- fordeling: additive antal med Dagtype, Rute og Time (browseren lægger sammen efter valget) ----
    f = g.groupby(["periode", "Retning", "stop", "klasse", "klasse_acc", "klasse_sam", "_dagtype", "_rute", "_time"]).size().reset_index(name="n")
    f = f.rename(columns={"_dagtype": "dagtype", "_rute": "rute", "_time": "time"})
    for r in f.itertuples():
        out["fordeling"].append({"S": sid, "Periode": r.periode, "Retning": str(r.Retning), "Stop": r.stop, "Klasse": r.klasse,
                                 "KlasseAcc": r.klasse_acc, "KlasseSam": r.klasse_sam, "Dagtype": r.dagtype, "Rute": r.rute,
                                 "Time": int(r.time), "n": int(r.n)})

    # ---- fart pr. tur (én gang), derefter pr. valg ----
    prof, fremad_antal, bin_max = profiler(perioder, g, kom, lat0, lon0, enhed, L, set(h["_k"]), retninger, log, sid)
    omvendt = {str(r): bool(fremad_antal[r][1] > fremad_antal[r][0]) for r in retninger}

    vinduer = list(kom["bump_vinduer"])
    ruter = [ALLE_RUTER] + sorted(set(g["_rute"]))
    timer = sorted(int(x) for x in g["_time"].unique())
    for dnavn, dset in DAGTYPER:
        gd = g if dset is None else g[g["_dagtype"].isin(dset)]
        for ru in ruter:
            gr = gd if ru == ALLE_RUTER else gd[gd["_rute"] == ru]
            if gr.empty:
                continue
            dage_valg = {p: int(gr[gr.periode == p]["Køredag"].nunique()) for p in PER}   # dage i dag x rute (alle timer): nævner for "pr. dag"
            pr_gr = prof[prof["_k"].isin(set(gr["_k"]))]
            for t in [ALLE_TIMER] + timer:
                sub0 = gr if t == ALLE_TIMER else gr[gr["_time"] == t]
                if sub0.empty:
                    continue
                key = {"Dag": dnavn, "Rute": ru, "Time": t}
                # omfang
                for p in PER:
                    out["omfang"].append({"S": sid, **key, "Periode": p, "Dage": int(sub0[sub0.periode == p]["Køredag"].nunique()),
                                          "Ture": int((sub0.periode == p).sum())})
                # nøgletal (som v1.1)
                for d in retninger + ["B"]:
                    for grp in GRUPPER:
                        for p in PER:
                            sub = sub0[sub0.periode == p]
                            if d != "B":
                                sub = sub[sub.Retning == d]
                            if grp != "Alle ture":
                                sub = sub[sub.stop == grp]
                            row = {"S": sid, "Retning": str(d), "Gruppe": grp, "Periode": p, "Ture": int(len(sub))}
                            row["koretid"] = r2(pct(sub[kt_kol].dropna(), 50))
                            row["gnsfart"] = r2(pct(pd.to_numeric(sub["gns_fart_kmh"], errors="coerce").dropna(), 50))
                            row["minfart_straek"] = r2(pct(pd.to_numeric(sub["min_fart_kmh"], errors="coerce").dropna(), 50))
                            row["minfart"] = {v: r2(pct(pd.to_numeric(sub[f"{v}_min_fart_kmh"], errors="coerce").dropna(), 50)) for v in vinduer}
                            row["andel_opbr"] = r2((sub[f"opbr_haendelser_{t1}"] >= 1).mean(), 4) if len(sub) else None
                            row["andel_stop"] = r2((sub["stillestand"] == 1).mean(), 4) if len(sub) else None
                            out["nogletal"].append({**row, **key})
                # fartprofil (som v1.1, kompakt: én række pr. retning x gruppe x periode med lister pr. 10 m)
                allv = pr_gr if t == ALLE_TIMER else pr_gr[pr_gr["_k"].isin(set(sub0["_k"]))]
                for grp in GRUPPER:
                    gv = allv if grp == "Alle ture" else allv[allv["Gruppe"] == grp]
                    for ret in [str(x) for x in retninger] + ["B"]:
                        sv = gv if ret == "B" else gv[gv["Retning"] == ret]
                        for p in PER:
                            rk = {"S": sid, **key, "Retning": ret, "Gruppe": grp, "Periode": p, "Meter": [], "Median": [], "P25": [], "P75": [], "Ture": []}
                            for b, gb in sv[sv["periode"] == p].groupby("bin"):
                                v = gb["v"].to_numpy()
                                rk["Meter"].append(int(b))
                                rk["Median"].append(r2(np.percentile(v, 50), 1))
                                rk["P25"].append(r2(np.percentile(v, 25), 1))
                                rk["P75"].append(r2(np.percentile(v, 75), 1))
                                rk["Ture"].append(int(len(v)))
                            if rk["Meter"]:
                                out["fartprofil"].append(rk)
                # måned (som v1.1, men måneder med få dage er med og markeret)
                for ret in [str(x) for x in retninger] + ["B"]:
                    sub = sub0 if ret == "B" else sub0[sub0["Retning"] == int(ret)]
                    for (p, m), gm in sub.groupby(["periode", "maaned"]):
                        dage = gm["Køredag"].nunique()
                        rk = {"S": sid, "Retning": ret, "Periode": p, "Maaned": m, "Median": r2(gm[kt_kol].median(), 1),
                              "Ture": int(len(gm)), "Dage": int(dage)}
                        if dage < OBS_DAGE_MAANED:
                            rk["Faa"] = True
                        out["maaned"].append({**rk, **key})
                # drift (som v1.1; ture pr. dag = ture i valget / dage med ture i dag x rute)
                dage_b = max(1, dage_valg[PER[-1]])
                tot_min = 0.0
                for d in retninger:
                    a = sub0[(sub0.periode == "A") & (sub0.Retning == d)][kt_kol]
                    if not tosidet:
                        out["drift"].append({"S": sid, "Retning": str(d), "Ture_dag": r2(len(a) / dage_b, 2), **key})
                        continue
                    b = sub0[(sub0.periode == "B") & (sub0.Retning == d)][kt_kol]
                    if len(a) == 0 or len(b) == 0:
                        continue
                    pr_dag = len(b) / dage_b
                    ekstra_s = (b.mean() - a.mean()) * pr_dag
                    tot_min += ekstra_s / 60
                    out["drift"].append({"S": sid, "Retning": str(d), "Ekstra_min_dag": r2(ekstra_s / 60, 3), "Ture_dag": r2(pr_dag, 2),
                                         "Delta_s": r2(b.mean() - a.mean(), 3), **key})
                if tosidet:
                    out["drift"].append({"S": sid, "Retning": "B", "Ekstra_min_dag": r2(tot_min, 3), **key})
            # planlagte ture (dag x rute, alle timer; browseren filtrerer på klokkeslæt)
            for (ret, tn), gt in gr[gr["_tur"] != ""].groupby(["Retning", "_tur"]):
                rk = {"S": sid, "Dag": dnavn, "Rute": ru, "Retning": str(ret), "Tur": str(tn),
                      "Linje": ", ".join(sorted(set(gt["_rute"]))),
                      "Kl": int(np.nanmedian(gt["_min"])) if gt["_min"].notna().any() else None, "G": {}}
                for grp in GRUPPER:
                    sg = gt if grp == "Alle ture" else gt[gt["stop"] == grp]
                    rk["G"][grp] = {p: stat4(sg.loc[sg["periode"] == p, kt_kol]) for p in PER}
                out["ture"].append(rk)

    # ---- zonetid (som v1.1: standardvalget, fra zonetid.json) ----
    typ = {e["navn"]: e["type"] for e in s["elementer"]}
    zs = (zj or {}).get("straekninger", {}).get(sid) if zj else None
    har_zonetid = bool(zs) and not zs.get("ingen_elementer")
    if har_zonetid:
        pos = zs["positioner_m"]
        navne = sorted(zs["elementer"], key=lambda n: pos[n])
        w0 = zs["hoved_zonebredde_m"]
        for ret, key in [(str(x), str(x)) for x in retninger] + [("B", "begge")]:
            v = zs.get(f"w{w0:g}|uden stop|{key}")
            if v is None:
                continue
            if tosidet:
                for e in navne:
                    lo, hi = v["interval"][e]
                    out["zonetid"].append({"S": sid, "Retning": ret, "Element": e, "Type": typ[e], "Lav": round(lo, 2), "Hoej": round(hi, 2)})
                lo, hi = v["interval"][Z.OVRIG]
                out["zonetid"].append({"S": sid, "Retning": ret, "Element": "Øvrig strækning", "Type": "", "Lav": round(lo, 2), "Hoej": round(hi, 2)})
                out["zonetid"].append({"S": sid, "Retning": ret, "Element": "Hele strækningen", "Type": "", "Lav": round(v["total"], 2),
                                       "Hoej": round(v["total"], 2)})
                bumps = [e for e in navne if typ[e] == "bump"]
                for k2, v2 in zs.items():
                    if not k2.startswith("w") or not k2.endswith(f"|uden stop|{key}") or k2 == f"w{w0:g}|uden stop|{key}" or not bumps:
                        continue
                    bredde = float(k2[1:].split("|")[0])
                    iv = v2["interval"]
                    out["foelsomhed"].append({"S": sid, "Retning": ret, "Bredde": bredde, "Lav": round(min(iv[e][0] for e in bumps), 2),
                                              "Hoej": round(max(iv[e][1] for e in bumps), 2)})
            else:
                A = v["A"]
                for e in navne:
                    out["zonetid"].append({"S": sid, "Retning": ret, "Element": e, "Type": typ[e], "Niveau": round(A[e], 2)})
                ov = sum(x for z, x in A.items() if z.startswith("øvrig"))
                out["zonetid"].append({"S": sid, "Retning": ret, "Element": "Øvrig strækning", "Type": "", "Niveau": round(ov, 2)})
                out["zonetid"].append({"S": sid, "Retning": ret, "Element": "Hele strækningen", "Type": "", "Niveau": round(A["total"], 2)})

    # ---- meta for strækningen (som v1.1 + ruter og timer) ----
    navn_fra, navn_til = pts[kom["fra"]].get("name", kom["fra"]), pts[kom["til"]].get("name", kom["til"])
    ret_over = {**(s.get("retninger") or {}), **(rap.get("retninger") or {})} if len(cfg["straekninger"]) == 1 else dict(s.get("retninger") or {})
    ret_navne = {}
    for r in retninger:
        txt = ret_over.get(str(r)) or ret_over.get(r)
        ret_navne[str(r)] = txt or f"Retning {r} (mod {navn_fra if omvendt[str(r)] else navn_til})"
    elementer = []
    for e in sorted(s["elementer"], key=lambda x: K.projicer([x["lat"]], [x["lon"]], lat0, lon0, enhed)[0][0]):
        sx, _sd = K.projicer([e["lat"]], [e["lon"]], lat0, lon0, enhed)
        elementer.append({"navn": e["navn"], "type": e["type"], "s_m": round(float(sx[0]), 1), "lat": e["lat"], "lon": e["lon"]})
    stopp = []
    for sp in rap.get("stoppesteder") or []:
        sx, sd = K.projicer([float(sp["lat"])], [float(sp["lon"])], lat0, lon0, enhed)
        eksplicit = sp.get("straekning")
        hoerer = (str(eksplicit) == sid) if eksplicit is not None else (0.0 <= float(sx[0]) <= L and abs(float(sd[0])) <= R11.STOP_SIDEAFSTAND_M)
        if hoerer:
            stopp.append({"navn": str(sp["navn"]), "retning": (str(sp["retning"]) if sp.get("retning") is not None else None),
                          "s_m": round(float(sx[0]), 1), "lat": float(sp["lat"]), "lon": float(sp["lon"])})
    return {"id": sid, "navn": s["navn"], "laengde_m": round(L, 1), "bin_max_m": bin_max,
            "start_navn": navn_fra, "slut_navn": navn_til,
            "retninger": [{"id": str(r), "navn": ret_navne[str(r)], "omvendt": omvendt[str(r)]} for r in retninger],
            "elementer": elementer, "stoppesteder": stopp, "vinduer": vinduer, "har_zonetid": har_zonetid,
            "linje": [[pts[kom["fra"]]["lat"], pts[kom["fra"]]["lon"]], [pts[kom["til"]]["lat"], pts[kom["til"]]["lon"]]],
            "koretid_afstand": kt_id, "ruter": ruter, "timer": timer}


def bygg(cfg, perioder, zonetid_json, turtabel, log=print):
    """
    Som lav_rapportdata.bygg (v1.1) plus turtabel = laes_turtabel(...) (DataFrame). Returnér rapportdata (dict).
    """
    raw, udv = cfg["raw"], cfg["udvalg"]
    rap = raw.get("rapport") or {}
    if "A" not in perioder or set(perioder) - {"A", "B"}:
        raise SystemExit("Perioderne skal være A, eller A og B")
    out = {k: [] for k in ("omfang", "nogletal", "fordeling", "fartprofil", "maaned", "drift", "zonetid", "foelsomhed", "fravalg", "ture")}
    strk = [bygg_straekning(s, cfg, perioder, zonetid_json, turtabel, out, log) for s in cfg["straekninger"]]
    t_sk = cfg["straekninger"][0]["komfort"]
    graense = rap.get("vist_graense_ms2") or [1.0, 1.8]
    per_cfg = raw.get("periods") or {}
    datoer = {p: [str(per_cfg[p]["start"]), str(per_cfg[p]["end"])] for p in perioder if (per_cfg.get(p) or {}).get("start") and per_cfg[p].get("end")}
    vej = rap.get("vej") or {}
    meta_ut = {
        "titel": rap.get("titel") or R11.STANDARD_TITEL,
        "undertitel": rap.get("undertitel") or "",
        "afsender": rap.get("afsender") or "",
        "udtraekdato": str(rap.get("udtraekdato") or ""),
        "bygget": date.today().isoformat(),
        "perioder_datoer": datoer,
        "min_ture": int(rap.get("min_ture", 5)),
        "straekning_tekst": rap.get("straekning_tekst") or "",
        "perioder": list(perioder),
        "foer_navn": rap.get("foer_navn") or "Før",
        "efter_navn": rap.get("efter_navn") or "Efter",
        "periode_navn": rap.get("periode_navn") or "Perioden",
        "kilde": rap.get("kilde") or "Kilde: realtidsdata (GPS-positioner).",
        "forbehold": [str(x) for x in (rap.get("forbehold") or [])],
        "maalenoter": [str(x) for x in (rap.get("maalenoter") or [])],
        "straekninger": strk,
        "zonebredde_m": cfg["zonetid"]["zonebredde_m"],
        "dagtype": udv["dagtype"],
        "taerskler_ms2": t_sk["taerskler_ms2"], "vist_graense_ms2": graense,
        "sg_vindue_s": t_sk["sg_vindue_s"], "stillestand_kmh": t_sk["stillestand_kmh"], "haendelse_min_s": t_sk["haendelse_min_s"],
        "kort": {"aktiv": bool(rap.get("kort", False))},
        # v1.2
        "dagtyper": [{"navn": n, "dagtyper": d} for n, d in DAGTYPER],
        "standard_dag": "Alle dage" if udv["dagtype"] == "alle" else "Hverdage",
        "alle_ruter": ALLE_RUTER, "alle_timer": ALLE_TIMER, "obs_n": OBS_N, "obs_n_tur": OBS_N_TUR, "obs_dage_maaned": OBS_DAGE_MAANED,
        "vej": {k: str(vej[k]) for k in VEJ_FELTER if vej.get(k) not in (None, "")},
    }
    return {"version": VERSION, "meta": meta_ut, **out}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Samler rapportdata.json (v1.2: valg for dage, rute og time) til skabelon_v1.2.html.")
    ap.add_argument("--config", required=True)
    ap.add_argument("--a", required=True, help="output-mappe periode A (før): result.csv, komfort*.csv, segmenter.csv")
    ap.add_argument("--b", default=None, help="output-mappe periode B (efter); udelades ved kun én periode")
    ap.add_argument("--turtabel", required=True, help="turtabel.csv fra turtabel.py v1.1+ (dagtype, rute, planlagt tur, time)")
    ap.add_argument("--zonetid", default=None, help="zonetid.json fra zonetid.py (valgfri; uden den vises ingen zonetabel)")
    ap.add_argument("--out", required=True, help="rapportdata.json")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cfg = Z.laes_config(a.config)
    print(f"lav_rapportdata v{VERSION}: {len(cfg['straekninger'])} strækning(er), {'før og efter' if a.b else 'én periode'}")
    perioder = {}
    for p, mappe in (("A", a.a), ("B", a.b)):
        if mappe is None:
            continue
        r, ks = Z.laes_periode(mappe, cfg["straekninger"])
        seg = pd.read_csv(Path(mappe) / "segmenter.csv", sep=";", encoding="utf-8", dtype={"Turreference": str},
                          usecols=["Turreference", "datetime", "lat", "lon", "er_stoprække"])
        perioder[p] = (r, ks, seg)
    tt = laes_turtabel(a.turtabel)
    zj = json.loads(Path(a.zonetid).read_text(encoding="utf-8")) if a.zonetid else None
    doc = bygg(cfg, perioder, zj, tt)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    std = [r for r in doc["omfang"] if r["Dag"] == doc["meta"]["standard_dag"] and r["Rute"] == ALLE_RUTER and r["Time"] == ALLE_TIMER]
    fra = sum(r["fra"] for r in doc["fravalg"])
    alle = sum(r["n"] for r in doc["fravalg"])
    print(f"  Skrev {out} ({out.stat().st_size // 1024} kB). Standardvalg: "
          + ", ".join(f"{r['Periode']} {r['Dage']} dage {r['Ture']} ture" for r in std)
          + f". Fravalgt pga. dårlige data: {fra} af {alle} ture (vises i rapporten).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
