#!/usr/bin/env python3
"""
lav_rapportdata_v1.3.py - rapportdata.json til skabelon_v1.3.html: som v1.2 plus to definitioner af standsning,
bredere fartbånd, total-række for planlagte ture og drift pr. 4 uger og pr. år.

Forskel fra lav_rapportdata_v1.2.py (beholdt uændret, ligesom v1.1):
 - To definitioner af standsning (standsning_v1.0.py):
     "i alt"   = farten kommer under komfort.stillestand_kmh et sted på strækningen (= komfort-kolonnen stillestand;
                 det, v1.2 kaldte "Uden stop"/"Med stop").
     "ved stop" = farten kommer under grænsen højst standsning_v1.0.VED_STOP_M (40 m) fra et stoppested for turens
                 retning (rapport.stoppesteder). Standsning i kø eller kryds tæller ikke.
   Grupper: "Alle ture", "Uden ved stop", "Med ved stop", "Uden i alt", "Med i alt". Uden stoppesteder på strækningen
   findes kun "Alle ture", "Uden i alt" og "Med i alt" (meta.standsning.ved_stop = false), og rapporten siger det.
   Standard i rapporten: "Uden ved stop" (meta.standsning.standard), ellers "Uden i alt".
 - fartprofil har også P10 og P90 (bånd 10-90 % og 25-75 %) og er kompakt: M0 = første 10 m-bin, listerne går i
   skridt af 10 m (null uden værdi) i stedet for listen Meter.
 - Er der kun én rute i data, regnes tallene kun for "Alle ruter" (de er de samme; rutevælgeren vises ikke).
 - ture har pr. gruppe og periode fordelingen af køretid (H: [[sekunder, antal], ...]), så skabelonen kan regne en
   total-række (antal og median) for de viste planlagte ture.
 - drift har også Ture_dag_hel (ture pr. dag rundet ned) og Ekstra_min_dag_hel (regnet med de nedrundede ture), og
   meta.drift_dage giver dage pr. 4 uger og pr. år for hver dagtype (hverdage: 20 og 250).
 - fordeling har felterne Alt og Ved ("Uden"/"Med") i stedet for Stop.
Med standardvalget og gruppen "i alt" er nøgletal, fartprofil (median, 25 % og 75 %), omfang, måned, fravalg og zonetid
de samme som i v1.2 (v1.2's "Uden stop"/"Med stop" = v1.3's "Uden i alt"/"Med i alt").

Input og config som v1.2; valgfrit rapport.stoppesteder (navn, retning, lat, lon; ét pr. side af vejen).

    python lav_rapportdata_v1.3.py --config cfg.yaml --a ud\\A --b ud\\B --turtabel ud\\turtabel.csv --zonetid ud\\zonetid.json --out ud\\rapportdata.json

Afhængigheder: som v1.2 + standsning_v1.0.py. PYTHONUTF8=1 på Windows.
"""
import argparse
import importlib.util
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


def _load(navn, sti):
    spec = importlib.util.spec_from_file_location(navn, sti)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R12 = _load("lav_rapportdata_v1_2", HERE / "lav_rapportdata_v1.2.py")
ST = _load("standsning_v1_0", HERE.parent / "standsning_v1.0.py")

K = Z.K
VERSION = "1.3"
r2, pct = R11.r2, R11.pct
ALLE_RUTER, ALLE_TIMER, DAGTYPER = R12.ALLE_RUTER, R12.ALLE_TIMER, R12.DAGTYPER
OBS_N, OBS_N_TUR, OBS_DAGE_MAANED, VEJ_FELTER = R12.OBS_N, R12.OBS_N_TUR, R12.OBS_DAGE_MAANED, R12.VEJ_FELTER
ALLE = "Alle ture"
GRUPPER_VED = ("Uden ved stop", "Med ved stop")
GRUPPER_ALT = ("Uden i alt", "Med i alt")
DRIFT_DAGE = {"Hverdage": {"uger4": 20, "aar": 250}, "Weekend og helligdage": {"uger4": 8, "aar": 115},
              "Alle dage": {"uger4": 28, "aar": 365}}   # 4 uger og 1 år; 250 + 115 = 365


def grupper(har_ved):
    return (ALLE,) + (GRUPPER_VED if har_ved else ()) + GRUPPER_ALT


def vaelg(sub, grp):
    """Turene i gruppen: kolonnerne ved og alt er 0/1 (1 = standsning)."""
    if grp == ALLE:
        return sub
    kol = "ved" if grp in GRUPPER_VED else "alt"
    return sub[sub[kol] == (0 if grp.startswith("Uden") else 1)]


def fordeling_h(v):
    """Køretider (s) -> [[sekunder, antal], ...] sorteret, til total-rækken i skabelonen."""
    v = pd.to_numeric(v, errors="coerce").dropna().round().astype(int)
    return [[int(k), int(n)] for k, n in v.value_counts().sort_index().items()]


def profiler(perioder, g, kom, lat0, lon0, enhed, L, std_keys, retninger_std, stops, log, sid):
    """Som v1.2.profiler plus standsning ved stop pr. tur. Returnér (prof, fremad_antal, bin_max, ved: {_k: 0/1})."""
    bin_max = int(L // 10 * 10)
    meta = g.set_index("_k")[["periode", "Retning", "stillestand"]]
    recs, fremad_antal, ved, afvig = [], {r: [0, 0] for r in retninger_std}, {}, 0
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
            ved[k] = ST.ved_stop(sg, vk, ret, stops, kom["stillestand_kmh"])
            if ST.i_alt(vk, kom["stillestand_kmh"]) != int(meta.at[k, "stillestand"]):
                afvig += 1
            if k in std_keys and ret in fremad_antal:
                fremad_antal[ret][0 if fremad else 1] += 1
            b = np.clip(np.floor(sg / 10).astype(int) * 10, 0, bin_max)
            dd = pd.DataFrame({"bin": b, "v": vk}).groupby("bin")["v"].mean().reset_index()
            dd["_k"] = k
            dd["periode"] = p
            dd["Retning"] = str(ret)
            recs.append(dd)
            antal += 1
        log(f"  strækning {sid}: fart pr. tur periode {p}: {antal} ture")
    if afvig:
        raise SystemExit(f"Strækning '{sid}': standsning i alt fra GPS-farten passer ikke med komfort.csv i {afvig} ture "
                         f"(komfort.csv og segmenter.csv er ikke fra samme kørsel?)")
    cols = ["bin", "v", "_k", "periode", "Retning"]
    return (pd.concat(recs, ignore_index=True) if recs else pd.DataFrame(columns=cols)), fremad_antal, bin_max, ved


def bygg_straekning(s, cfg, perioder, zj, tt, out, log):
    """Som v1.2.bygg_straekning med to definitioner af standsning. Returnér strækningens meta."""
    raw, pts, udv = cfg["raw"], cfg["points"], cfg["udvalg"]
    rap = raw.get("rapport") or {}
    sid, kom = s["id"], s["komfort"]
    PER = list(perioder)
    tosidet = len(PER) == 2
    lat0, lon0, enhed, L = K.linje_geometri(pts[kom["fra"]], pts[kom["til"]])
    if kom.get("laengde_m"):
        L = float(kom["laengde_m"])
    stops = ST.stoppesteder_for(s, rap, pts, L)
    har_ved = len(stops) > 0
    GR = grupper(har_ved)

    # ---- samlet tabel pr. tur (som v1.2) ----
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
    ds = R12.dagset(std_dag)
    tjek = pd.Series(True, index=df.index) if ds is None else df["_dagtype"].isin(ds)
    if (std_maske != tjek).any():
        raise SystemExit(f"Dagtypen i turtabel.csv passer ikke med udvalg i config ({int((std_maske != tjek).sum())} ture). "
                         f"Lav turtabellen igen med samme config (udvalg.helligdage).")
    df["hverdag"] = std_maske

    # ---- fravalg (som v1.2) ----
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
    g["alt"] = (g["stillestand"] == 1).astype(int)
    h = g[g["hverdag"]]
    log(f"  strækning {sid}: ture i result {len(df)}, gyldige {len(g)}, i standardvalget (dagtype {udv['dagtype']}) {len(h)}")
    retninger = [r for r in (1, 2) if (h["Retning"] == r).any()]
    if not retninger or any(len(h[h["periode"] == p]) == 0 for p in PER):
        raise SystemExit(f"Strækning '{sid}': ingen ture i udvalget i mindst én periode (tjek udvalg.dagtype/helligdage, "
                         f"komfort status, strækningens fra/til og periode-mapperne)")

    # ---- fart pr. tur og standsning ved stop (én gang) ----
    prof, fremad_antal, bin_max, ved = profiler(perioder, g, kom, lat0, lon0, enhed, L, set(h["_k"]), retninger, stops, log, sid)
    mangler = int((~g["_k"].isin(ved)).sum())
    if mangler:
        raise SystemExit(f"Strækning '{sid}': fart kunne ikke regnes for {mangler} gyldige ture (komfort status ok); tjek kørslen")
    g["ved"] = g["_k"].map(ved).astype(int)
    log(f"  strækning {sid}: standsning i alt {int(g['alt'].sum())}, ved stop {int(g['ved'].sum())} af {len(g)} ture "
        f"({len(stops)} stoppesteder)")
    pk = g.set_index("_k")
    prof["alt"] = prof["_k"].map(pk["alt"])
    prof["ved"] = prof["_k"].map(pk["ved"])
    omvendt = {str(r): bool(fremad_antal[r][1] > fremad_antal[r][0]) for r in retninger}

    suf = [K.kolonnesuffix(t) for t in kom["taerskler_ms2"]]
    t1, t2 = suf[0], suf[-1]
    g["klasse"] = np.where(g[f"opbr_haendelser_{t2}"] >= 1, "Kraftig", np.where(g[f"opbr_haendelser_{t1}"] >= 1, "Maerkbar", "Ingen"))
    g["klasse_acc"] = np.where(g[f"acc_haendelser_{t2}"] >= 1, "Kraftig", np.where(g[f"acc_haendelser_{t1}"] >= 1, "Maerkbar", "Ingen"))
    g["klasse_sam"] = np.where((g[f"opbr_haendelser_{t2}"] >= 1) | (g[f"acc_haendelser_{t2}"] >= 1), "Kraftig",
                               np.where((g[f"opbr_haendelser_{t1}"] >= 1) | (g[f"acc_haendelser_{t1}"] >= 1), "Maerkbar", "Ingen"))
    g["maaned"] = g["dato"].dt.strftime("%Y-%m")

    # ---- fordeling: additive antal med begge standsningsdefinitioner ----
    f = g.groupby(["periode", "Retning", "alt", "ved", "klasse", "klasse_acc", "klasse_sam", "_dagtype", "_rute", "_time"]).size().reset_index(name="n")
    f = f.rename(columns={"_dagtype": "dagtype", "_rute": "rute", "_time": "time"})
    for r in f.itertuples():
        out["fordeling"].append({"S": sid, "Periode": r.periode, "Retning": str(r.Retning), "Alt": "Med" if r.alt else "Uden",
                                 "Ved": "Med" if r.ved else "Uden", "Klasse": r.klasse, "KlasseAcc": r.klasse_acc,
                                 "KlasseSam": r.klasse_sam, "Dagtype": r.dagtype, "Rute": r.rute, "Time": int(r.time), "n": int(r.n)})

    vinduer = list(kom["bump_vinduer"])
    ruter = [ALLE_RUTER] + sorted(set(g["_rute"]))
    timer = sorted(int(x) for x in g["_time"].unique())
    # kun én rute i data: tallene for ruten er de samme som for "Alle ruter" (og rapporten viser ingen rutevælger),
    # så de regnes ikke to gange (halverer filen)
    ruter_beregn = [ALLE_RUTER] if len(ruter) == 2 else ruter
    for dnavn, dset in DAGTYPER:
        gd = g if dset is None else g[g["_dagtype"].isin(dset)]
        for ru in ruter_beregn:
            gr = gd if ru == ALLE_RUTER else gd[gd["_rute"] == ru]
            if gr.empty:
                continue
            dage_valg = {p: int(gr[gr.periode == p]["Køredag"].nunique()) for p in PER}
            pr_gr = prof[prof["_k"].isin(set(gr["_k"]))]
            for t in [ALLE_TIMER] + timer:
                sub0 = gr if t == ALLE_TIMER else gr[gr["_time"] == t]
                if sub0.empty:
                    continue
                key = {"Dag": dnavn, "Rute": ru, "Time": t}
                for p in PER:
                    out["omfang"].append({"S": sid, **key, "Periode": p, "Dage": int(sub0[sub0.periode == p]["Køredag"].nunique()),
                                          "Ture": int((sub0.periode == p).sum())})
                # nøgletal (som v1.2; grupperne efter begge definitioner)
                for d in retninger + ["B"]:
                    for grp in GR:
                        for p in PER:
                            sub = sub0[sub0.periode == p]
                            if d != "B":
                                sub = sub[sub.Retning == d]
                            sub = vaelg(sub, grp)
                            row = {"S": sid, "Retning": str(d), "Gruppe": grp, "Periode": p, "Ture": int(len(sub))}
                            row["koretid"] = r2(pct(sub[kt_kol].dropna(), 50))
                            row["gnsfart"] = r2(pct(pd.to_numeric(sub["gns_fart_kmh"], errors="coerce").dropna(), 50))
                            row["minfart_straek"] = r2(pct(pd.to_numeric(sub["min_fart_kmh"], errors="coerce").dropna(), 50))
                            row["minfart"] = {v: r2(pct(pd.to_numeric(sub[f"{v}_min_fart_kmh"], errors="coerce").dropna(), 50)) for v in vinduer}
                            row["andel_opbr"] = r2((sub[f"opbr_haendelser_{t1}"] >= 1).mean(), 4) if len(sub) else None
                            row["andel_stop"] = r2((sub["alt"] == 1).mean(), 4) if len(sub) else None
                            row["andel_stop_ved"] = r2((sub["ved"] == 1).mean(), 4) if len(sub) and har_ved else None
                            out["nogletal"].append({**row, **key})
                # fartprofil: median, 10, 25, 75 og 90 % pr. 10 m
                allv = pr_gr if t == ALLE_TIMER else pr_gr[pr_gr["_k"].isin(set(sub0["_k"]))]
                for grp in GR:
                    gv = vaelg(allv, grp)
                    for ret in [str(x) for x in retninger] + ["B"]:
                        sv = gv if ret == "B" else gv[gv["Retning"] == ret]
                        for p in PER:
                            sp = sv[sv["periode"] == p]
                            if sp.empty:
                                continue
                            # kompakt: M0 = første 10 m-bin; listerne går i skridt af 10 m (null, hvor ingen tur har en værdi)
                            q = sp.groupby("bin")["v"].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).unstack()
                            n = sp.groupby("bin")["v"].size()
                            m0, m1 = int(q.index.min()), int(q.index.max())
                            q = q.reindex(range(m0, m1 + 10, 10))
                            n = n.reindex(q.index)
                            rk = {"S": sid, **key, "Retning": ret, "Gruppe": grp, "Periode": p, "M0": m0}
                            for felt, kol in (("Median", 0.5), ("P10", 0.1), ("P25", 0.25), ("P75", 0.75), ("P90", 0.9)):
                                rk[felt] = [r2(x, 1) for x in q[kol]]
                            rk["Ture"] = [None if pd.isna(x) else int(x) for x in n]
                            out["fartprofil"].append(rk)
                # måned (som v1.2)
                for ret in [str(x) for x in retninger] + ["B"]:
                    sub = sub0 if ret == "B" else sub0[sub0["Retning"] == int(ret)]
                    for (p, m), gm in sub.groupby(["periode", "maaned"]):
                        dage = gm["Køredag"].nunique()
                        rk = {"S": sid, "Retning": ret, "Periode": p, "Maaned": m, "Median": r2(gm[kt_kol].median(), 1),
                              "Ture": int(len(gm)), "Dage": int(dage)}
                        if dage < OBS_DAGE_MAANED:
                            rk["Faa"] = True
                        out["maaned"].append({**rk, **key})
                # drift (som v1.2 + ture pr. dag rundet ned og ekstra køretid regnet med dem)
                dage_b = max(1, dage_valg[PER[-1]])
                tot_min, tot_hel = 0.0, 0.0
                for d in retninger:
                    a = sub0[(sub0.periode == "A") & (sub0.Retning == d)][kt_kol]
                    if not tosidet:
                        out["drift"].append({"S": sid, "Retning": str(d), "Ture_dag": r2(len(a) / dage_b, 2),
                                             "Ture_dag_hel": int(len(a) // dage_b), **key})
                        continue
                    b = sub0[(sub0.periode == "B") & (sub0.Retning == d)][kt_kol]
                    if len(a) == 0 or len(b) == 0:
                        continue
                    pr_dag = len(b) / dage_b
                    hel = len(b) // dage_b
                    delta = b.mean() - a.mean()
                    tot_min += delta * pr_dag / 60
                    tot_hel += delta * hel / 60
                    out["drift"].append({"S": sid, "Retning": str(d), "Ekstra_min_dag": r2(delta * pr_dag / 60, 3), "Ture_dag": r2(pr_dag, 2),
                                         "Delta_s": r2(delta, 3), "Ture_dag_hel": int(hel), "Ekstra_min_dag_hel": r2(delta * hel / 60, 3), **key})
                if tosidet:
                    out["drift"].append({"S": sid, "Retning": "B", "Ekstra_min_dag": r2(tot_min, 3), "Ekstra_min_dag_hel": r2(tot_hel, 3), **key})
            # planlagte ture (dag x rute, alle timer; skabelonen filtrerer på klokkeslæt og regner total-rækken af H)
            for (ret, tn), gt in gr[gr["_tur"] != ""].groupby(["Retning", "_tur"]):
                rk = {"S": sid, "Dag": dnavn, "Rute": ru, "Retning": str(ret), "Tur": str(tn),
                      "Linje": ", ".join(sorted(set(gt["_rute"]))),
                      "Kl": int(np.nanmedian(gt["_min"])) if gt["_min"].notna().any() else None, "G": {}, "H": {}}
                for grp in GR:
                    sg = vaelg(gt, grp)
                    rk["G"][grp] = {p: R12.stat4(sg.loc[sg["periode"] == p, kt_kol]) for p in PER}
                    rk["H"][grp] = {p: fordeling_h(sg.loc[sg["periode"] == p, kt_kol]) for p in PER}
                out["ture"].append(rk)

    # ---- zonetid (som v1.2: standardvalget, ture uden standsning i alt, fra zonetid.json) ----
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

    # ---- meta for strækningen (som v1.2 + standsning) ----
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
            "koretid_afstand": kt_id, "ruter": ruter, "timer": timer, "ved_stop": har_ved, "grupper": list(GR)}


def bygg(cfg, perioder, zonetid_json, turtabel, log=print):
    """Som v1.2.bygg; rapportdata version 1.3."""
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
    har_ved = all(s["ved_stop"] for s in strk)
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
        "dagtyper": [{"navn": n, "dagtyper": d} for n, d in DAGTYPER],
        "standard_dag": "Alle dage" if udv["dagtype"] == "alle" else "Hverdage",
        "alle_ruter": ALLE_RUTER, "alle_timer": ALLE_TIMER, "obs_n": OBS_N, "obs_n_tur": OBS_N_TUR, "obs_dage_maaned": OBS_DAGE_MAANED,
        "vej": {k: str(vej[k]) for k in VEJ_FELTER if vej.get(k) not in (None, "")},
        # v1.3
        "standsning": {"ved_stop": har_ved, "ved_stop_m": ST.VED_STOP_M, "standard": "ved stop" if har_ved else "i alt",
                       "zonetid": "i alt"},
        "drift_dage": DRIFT_DAGE,
    }
    return {"version": VERSION, "meta": meta_ut, **out}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Samler rapportdata.json (v1.3: to definitioner af standsning) til skabelon_v1.3.html.")
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
    tt = R12.laes_turtabel(a.turtabel)
    zj = json.loads(Path(a.zonetid).read_text(encoding="utf-8")) if a.zonetid else None
    doc = bygg(cfg, perioder, zj, tt)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    std = [r for r in doc["omfang"] if r["Dag"] == doc["meta"]["standard_dag"] and r["Rute"] == ALLE_RUTER and r["Time"] == ALLE_TIMER]
    fra = sum(r["fra"] for r in doc["fravalg"])
    alle = sum(r["n"] for r in doc["fravalg"])
    sd = doc["meta"]["standsning"]
    print(f"  Skrev {out} ({out.stat().st_size // 1024} kB). Standardvalg: "
          + ", ".join(f"{r['Periode']} {r['Dage']} dage {r['Ture']} ture" for r in std)
          + f". Fravalgt pga. dårlige data: {fra} af {alle} ture (vises i rapporten). Standsning: "
          + ("ved stop (stoppesteder i config) og i alt" if sd["ved_stop"] else "kun i alt (ingen stoppesteder på strækningen i config)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
