#!/usr/bin/env python3
"""
lav_rapportdata.py (v1.1) - samler resultaterne til én rapportdata.json, som byg_rapport.py sætter ind i skabelonen.

Input:  output-mapperne for periode A (før) og, hvis der er en sammenligning, B (efter) fra analyse_v2.1.py og
        komfort_v1.1.py (--export-segments): <mappe>/result.csv, komfort.csv (eller komfort_<id>.csv ved flere
        strækninger), segmenter.csv, samt zonetid.json fra zonetid.py (valgfri).
Config: samme YAML som resten af værktøjet (points, strækninger eller komfort, elementer, udvalg, zonetid, rapport).
Output: rapportdata.json. Kun aggregerede tal (medianer, andele, antal) og tekster: ingen tur-id, ingen
        positioner pr. ping.

    python lav_rapportdata.py --config min_config.yaml --a ud_A --b ud_B --zonetid ud/zonetid.json --out ud/rapportdata.json
    python lav_rapportdata.py --config min_config.yaml --a ud_A --zonetid ud/zonetid.json --out ud/rapportdata.json   (kun én periode)

Udvalg (samme som zonetid.py): tom Log, ingen stoprække-match, komfort status ok, dagtype fra config (standard hverdage).
Alle tal i rapporten regnes på dette udvalg. Perioderne hedder 'A' (før) og 'B' (efter) i datafilen. Uden B er rapporten
en beskrivelse af niveauet i perioden A: ingen før/efter, ingen ekstra køretid.

Indhold i rapportdata.json (alle tabeller har feltet S = strækning-id):
  meta        titel, tekster, perioder, strækninger (navn, længde, retninger, elementer, stoppesteder, linje), forbehold
  omfang      dage og ture pr. periode
  nogletal    pr. retning (1, 2, B = begge) x gruppe (Alle ture / Uden stop / Med stop) x periode: medianer og andele
  fordeling   antal ture pr. komfortklasse (additivt, bruges til at filtrere i browseren)
  fartprofil  fart pr. 10 m (median, p25, p75), pr. retning x gruppe x periode
  maaned      median køretid pr. måned
  drift       ekstra køretid pr. hverdag (gennemsnit efter - før x ture pr. hverdag); uden B kun ture pr. dag
  zonetid     med B: interval for ekstra tid pr. element (fra zonetid.json); uden B: gennemsnitlig tid pr. zone (Niveau)
  foelsomhed  med B: ekstra tid ved bump for andre zonebredder

Afhængigheder: pandas, numpy, pyyaml, zonetid.py, komfort_v1.1.py og komfort_v1.0.py (mappen over denne). PYTHONUTF8=1 på Windows.
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
import zonetid as Z  # noqa: E402

K = Z.K
VERSION = "1.1"
GRUPPER = ("Alle ture", "Uden stop", "Med stop")
STANDARD_TITEL = "<Fundet i én sætning, fx: Køretiden steg X s samtidig med vejændringen>"   # pladsholder: byg_rapport.py advarer, hvis den står tilbage
STOP_SIDEAFSTAND_M = 40.0     # et stoppested uden eksplicit strækning hører til de strækninger, det ligger højst så langt fra


def r2(x, d=2):
    if x is None:
        return None
    x = float(x)
    return None if np.isnan(x) else round(x, d)


def pct(v, q):
    v = np.asarray(v, dtype=float)
    return float(np.percentile(v, q)) if len(v) else None


def koretid_kolonne(raw, s, df, antal):
    """Kolonnen med køretid for strækningen: strækningens koretid_afstand, ved én strækning rapport.koretid_afstand,
    ellers den distance der går fra strækningens fra-punkt til til-punkt (ellers den første)."""
    kom = s["komfort"]
    dist = raw.get("distances") or {}
    valgt = (s.get("raw") or {}).get("koretid_afstand")
    if valgt is None and antal == 1:
        valgt = (raw.get("rapport") or {}).get("koretid_afstand")
    if valgt is None:
        for did, d in dist.items():
            if d.get("from") == kom["fra"] and d.get("to") == kom["til"]:
                valgt = did
                break
    if valgt is None and dist:
        valgt = next(iter(dist))
    if valgt is None or valgt not in dist:
        raise SystemExit(f"Ingen distance at bruge til køretid for strækning '{s['id']}'. Sæt koretid_afstand (strækningen eller "
                         f"rapport:) til et id under distances: i config.")
    kol = f"{dist[valgt]['name']} - køretid (sek)"
    if kol not in df.columns:
        raise SystemExit(f"Kolonnen '{kol}' findes ikke i result.csv (strækning '{s['id']}', distance {valgt}). "
                         f"Tjek koretid_afstand og distances: i config.")
    return kol, valgt


def tur_profil(t, s, L, kom):
    """Som komfort_v1.0.beregn_tur: (position i m, fart i km/t, fremad) pr. gitterpunkt på strækningen, eller None."""
    ordn = np.argsort(t, kind="stable")
    t = np.asarray(t, dtype=float)[ordn]
    s = np.asarray(s, dtype=float)[ordn]
    keep = np.concatenate(([True], np.diff(t) > 0))
    t, s = t[keep], s[keep]
    if len(t) < 3:
        return None
    m = kom["fuld_passage_margin_m"]
    fremad = s[0] <= m and s[-1] >= L - m
    baglaens = s[0] >= L - m and s[-1] <= m
    if not (fremad or baglaens) or np.max(np.diff(t)) > kom["max_hul_s"]:
        return None
    dt = float(kom["gitter_s"])
    vindue = int(round(kom["sg_vindue_s"] / dt))
    vindue += 1 if vindue % 2 == 0 else 0
    grid = np.arange(t[0], t[-1] + 1e-9, dt)
    if len(grid) < vindue:
        return None
    sg = np.interp(grid, t, s)
    x = sg if fremad else L - sg
    v, a = K.sg_afledte(x, vindue, int(kom["sg_orden"]), dt, kom["kant"])
    ok = np.isfinite(v) & np.isfinite(a) & (x >= 0) & (x <= L)
    if ok.sum() < 3:
        return None
    return sg[ok], v[ok] * 3.6, bool(fremad)


def bygg_straekning(s, cfg, perioder, zj, out, log):
    """Beregner alle tabeller for én strækning (rækker får feltet S) og lægger dem i out. Returnér strækningens meta."""
    raw, pts, udv = cfg["raw"], cfg["points"], cfg["udvalg"]
    rap = raw.get("rapport") or {}
    sid, kom = s["id"], s["komfort"]
    PER = list(perioder)
    tosidet = len(PER) == 2
    lat0, lon0, enhed, L = K.linje_geometri(pts[kom["fra"]], pts[kom["til"]])
    if kom.get("laengde_m"):
        L = float(kom["laengde_m"])

    # ---- samlet tabel pr. tur ----
    dele = []
    for p, (r, k, _seg) in perioder.items():
        kd = Z.komfort_for(k, sid)
        kd = kd.drop(columns=[c for c in ("Periode", "Retning", "Køredag") if c in kd.columns])
        d = r.merge(kd, on="Turreference", how="left", validate="1:1")
        d["periode"] = p
        dele.append(d)
    df = pd.concat(dele, ignore_index=True)
    kt_kol, kt_id = koretid_kolonne(raw, s, df, len(cfg["straekninger"]))
    df["gyldig"] = Z.gyldig_maske(df)
    df["hverdag"] = Z.dagtype_maske(df, udv)
    h = df[df["gyldig"] & df["hverdag"]].copy()
    h["dato"] = pd.to_datetime(h["Køredag"])
    h["stop"] = np.where(h["stillestand"] == 0, "Uden stop", "Med stop")
    log(f"  strækning {sid}: ture i result {len(df)}, gyldige {int(df['gyldig'].sum())}, i udvalget (dagtype {udv['dagtype']}) {len(h)}")
    retninger = [r for r in (1, 2) if (h["Retning"] == r).any()]
    if not retninger or any(len(h[h["periode"] == p]) == 0 for p in PER):
        raise SystemExit(f"Strækning '{sid}': ingen ture i udvalget i mindst én periode (tjek udvalg.dagtype/helligdage, "
                         f"komfort status, strækningens fra/til og periode-mapperne)")

    suf = [K.kolonnesuffix(t) for t in kom["taerskler_ms2"]]
    t1, t2 = suf[0], suf[-1]
    h["klasse"] = np.where(h[f"opbr_haendelser_{t2}"] >= 1, "Kraftig", np.where(h[f"opbr_haendelser_{t1}"] >= 1, "Maerkbar", "Ingen"))
    h["klasse_acc"] = np.where(h[f"acc_haendelser_{t2}"] >= 1, "Kraftig", np.where(h[f"acc_haendelser_{t1}"] >= 1, "Maerkbar", "Ingen"))
    h["klasse_sam"] = np.where((h[f"opbr_haendelser_{t2}"] >= 1) | (h[f"acc_haendelser_{t2}"] >= 1), "Kraftig",
                               np.where((h[f"opbr_haendelser_{t1}"] >= 1) | (h[f"acc_haendelser_{t1}"] >= 1), "Maerkbar", "Ingen"))

    # ---- omfang ----
    for p in PER:
        out["omfang"].append({"S": sid, "Periode": p, "Dage": int(h[h.periode == p]["Køredag"].nunique()), "Ture": int((h.periode == p).sum())})

    # ---- fordeling (additive antal) ----
    f = h.groupby(["periode", "Retning", "stop", "klasse", "klasse_acc", "klasse_sam"]).size().reset_index(name="n")
    for r in f.itertuples():
        out["fordeling"].append({"S": sid, "Periode": r.periode, "Retning": str(r.Retning), "Stop": r.stop, "Klasse": r.klasse,
                                 "KlasseAcc": r.klasse_acc, "KlasseSam": r.klasse_sam, "n": int(r.n)})

    # ---- nøgletal ----
    vinduer = list(kom["bump_vinduer"])
    for d in retninger + ["B"]:
        for grp in GRUPPER:
            for p in PER:
                sub = h[h.periode == p]
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
                out["nogletal"].append(row)

    # ---- fartprofil ----
    bin_max = int(L // 10 * 10)
    recs, fremad_antal = [], {r: [0, 0] for r in retninger}
    meta = h.set_index("Turreference")[["periode", "Retning", "stillestand"]]
    for p, (_r, _k, seg) in perioder.items():
        seg = seg[(seg["er_stoprække"] == 0) & seg["Turreference"].isin(meta.index)].copy()
        sx, sd = K.projicer(seg["lat"].to_numpy(), seg["lon"].to_numpy(), lat0, lon0, enhed)
        seg["s"], seg["d"] = sx, sd
        mg = kom["korridor_margin_m"]
        seg = seg[(seg["s"] >= -mg) & (seg["s"] <= L + mg) & (seg["d"].abs() <= kom["korridor_sideafstand_m"])]
        seg["t"] = (pd.to_datetime(seg["datetime"], format="%Y-%m-%d %H:%M:%S") - pd.Timestamp("1970-01-01")).dt.total_seconds()
        antal = 0
        for ref, g in seg.groupby("Turreference", sort=False):
            res = tur_profil(g["t"].to_numpy(dtype=float), g["s"].to_numpy(), L, kom)
            if res is None:
                continue
            sg, vk, fremad = res
            ret = int(meta.at[ref, "Retning"])
            if ret in fremad_antal:
                fremad_antal[ret][0 if fremad else 1] += 1
            b = np.clip(np.floor(sg / 10).astype(int) * 10, 0, bin_max)
            dd = pd.DataFrame({"bin": b, "v": vk}).groupby("bin")["v"].mean().reset_index()
            dd["periode"] = p
            dd["Retning"] = str(ret)
            dd["Gruppe"] = "Uden stop" if int(meta.at[ref, "stillestand"]) == 0 else "Med stop"
            recs.append(dd)
            antal += 1
        log(f"  strækning {sid}: fartprofil periode {p}: {antal} ture")
    if recs:
        allv = pd.concat(recs, ignore_index=True)
        for grp in GRUPPER:
            gv = allv if grp == "Alle ture" else allv[allv["Gruppe"] == grp]
            for ret in [str(x) for x in retninger] + ["B"]:
                sub = gv if ret == "B" else gv[gv["Retning"] == ret]
                for p in PER:
                    for b, g in sub[sub["periode"] == p].groupby("bin"):
                        v = g["v"].to_numpy()
                        out["fartprofil"].append({"S": sid, "Retning": ret, "Gruppe": grp, "Periode": p, "Meter": int(b),
                                                  "Median": r2(np.percentile(v, 50), 1), "P25": r2(np.percentile(v, 25), 1),
                                                  "P75": r2(np.percentile(v, 75), 1), "Ture": int(len(v))})
    omvendt = {str(r): bool(fremad_antal[r][1] > fremad_antal[r][0]) for r in retninger}

    # ---- måned ----
    h["maaned"] = h["dato"].dt.strftime("%Y-%m")
    for ret in [str(x) for x in retninger] + ["B"]:
        sub = h if ret == "B" else h[h["Retning"] == int(ret)]
        for (p, m), g in sub.groupby(["periode", "maaned"]):
            dage = g["Køredag"].nunique()
            if dage < 5:
                continue
            out["maaned"].append({"S": sid, "Retning": ret, "Periode": p, "Maaned": m, "Median": r2(g[kt_kol].median(), 1),
                                  "Ture": int(len(g)), "Dage": int(dage)})

    # ---- drift ----
    dage_b = max(1, int(h[h.periode == PER[-1]]["Køredag"].nunique()))
    tot_min = 0.0
    for d in retninger:
        if not tosidet:
            a = h[(h.periode == "A") & (h.Retning == d)][kt_kol]
            out["drift"].append({"S": sid, "Retning": str(d), "Ture_dag": r2(len(a) / dage_b, 2)})
            continue
        a = h[(h.periode == "A") & (h.Retning == d)][kt_kol]
        b = h[(h.periode == "B") & (h.Retning == d)][kt_kol]
        if len(a) == 0 or len(b) == 0:
            continue
        pr_dag = len(b) / dage_b
        ekstra_s = (b.mean() - a.mean()) * pr_dag
        tot_min += ekstra_s / 60
        out["drift"].append({"S": sid, "Retning": str(d), "Ekstra_min_dag": r2(ekstra_s / 60, 3), "Ture_dag": r2(pr_dag, 2),
                             "Delta_s": r2(b.mean() - a.mean(), 3)})
    if tosidet:
        out["drift"].append({"S": sid, "Retning": "B", "Ekstra_min_dag": r2(tot_min, 3)})

    # ---- zonetid ----
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
            else:   # én periode: gennemsnitlig tid pr. zone
                A = v["A"]
                for e in navne:
                    out["zonetid"].append({"S": sid, "Retning": ret, "Element": e, "Type": typ[e], "Niveau": round(A[e], 2)})
                ov = sum(x for z, x in A.items() if z.startswith("øvrig"))
                out["zonetid"].append({"S": sid, "Retning": ret, "Element": "Øvrig strækning", "Type": "", "Niveau": round(ov, 2)})
                out["zonetid"].append({"S": sid, "Retning": ret, "Element": "Hele strækningen", "Type": "", "Niveau": round(A["total"], 2)})

    # ---- meta for strækningen ----
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
        hoerer = (str(eksplicit) == sid) if eksplicit is not None else (0.0 <= float(sx[0]) <= L and abs(float(sd[0])) <= STOP_SIDEAFSTAND_M)
        if hoerer:
            stopp.append({"navn": str(sp["navn"]), "retning": (str(sp["retning"]) if sp.get("retning") is not None else None),
                          "s_m": round(float(sx[0]), 1), "lat": float(sp["lat"]), "lon": float(sp["lon"])})
    return {"id": sid, "navn": s["navn"], "laengde_m": round(L, 1), "bin_max_m": bin_max,
            "start_navn": navn_fra, "slut_navn": navn_til,
            "retninger": [{"id": str(r), "navn": ret_navne[str(r)], "omvendt": omvendt[str(r)]} for r in retninger],
            "elementer": elementer, "stoppesteder": stopp, "vinduer": vinduer, "har_zonetid": har_zonetid,
            "linje": [[pts[kom["fra"]]["lat"], pts[kom["fra"]]["lon"]], [pts[kom["til"]]["lat"], pts[kom["til"]]["lon"]]],
            "koretid_afstand": kt_id}


def bygg(cfg, perioder, zonetid_json, log=print):
    """
    cfg = zonetid.laes_config(...). perioder = {'A': (result_df, komfort, segment_df)[, 'B': (...)]}; komfort er en tabel
    (én strækning) eller {strækning-id: tabel}. zonetid_json = indlæst zonetid.json (dict) eller None.
    Returnér rapportdata (dict).
    """
    raw, udv = cfg["raw"], cfg["udvalg"]
    rap = raw.get("rapport") or {}
    if "A" not in perioder or set(perioder) - {"A", "B"}:
        raise SystemExit("Perioderne skal være A, eller A og B")
    out = {k: [] for k in ("omfang", "nogletal", "fordeling", "fartprofil", "maaned", "drift", "zonetid", "foelsomhed")}
    strk = [bygg_straekning(s, cfg, perioder, zonetid_json, out, log) for s in cfg["straekninger"]]
    t_sk = cfg["straekninger"][0]["komfort"]
    graense = rap.get("vist_graense_ms2") or [1.0, 1.8]
    per_cfg = raw.get("periods") or {}
    datoer = {p: [str(per_cfg[p]["start"]), str(per_cfg[p]["end"])] for p in perioder if (per_cfg.get(p) or {}).get("start") and per_cfg[p].get("end")}
    meta_ut = {
        "titel": rap.get("titel") or STANDARD_TITEL,
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
    }
    return {"version": VERSION, "meta": meta_ut, **out}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Samler rapportdata.json til rapportskabelonen.")
    ap.add_argument("--config", required=True)
    ap.add_argument("--a", required=True, help="output-mappe periode A (før): result.csv, komfort*.csv, segmenter.csv")
    ap.add_argument("--b", default=None, help="output-mappe periode B (efter); udelades ved kun én periode")
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
    zj = json.loads(Path(a.zonetid).read_text(encoding="utf-8")) if a.zonetid else None
    doc = bygg(cfg, perioder, zj)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  Skrev {out} ({out.stat().st_size // 1024} kB): omfang {doc['omfang']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
