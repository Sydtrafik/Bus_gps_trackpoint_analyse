"""Hjælper til den nemme vej: stopnavne og stoppesteder pr. retning, kontrolkort, beregnet config og config-info.

Functionality:
    stopnavne: læser data\\A (Details.csv + List.csv) og skriver pr. kørselsretning stoppestederne i den rækkefølge,
        bussen kører dem (den hyppigste rækkefølge). For hver retning i point_order bruges retningens første og
        sidste punkt (de yderste), så det virker for to punkter, flere strækninger og kryds. Foreslår start- og
        slutstop pr. retning, klar til at kopiere, og siger, hvis en retning i data kører modsat point_order.
        Skriver også stoppestederne på strækningerne (navn, retning, lat, lon) som en blok til rapport.stoppesteder,
        og gemmer alle stop pr. retning i resultat\\stoppesteder_hafas.yaml (bruges af config, kort og tjek_config).
    kort: skriver kontrolkort.html: alle punkter, strækninger, elementer og stoppesteder på et vejkort (SVG med
        program\\vejkort.js, OpenStreetMap-data hentet én gang til resultat\\vejkort_kontrol.json) med en tabel med
        koordinater og Google Maps-links. Uden net (eller ved Overpass-fejl) vises kun punkterne.
    config: skriver resultat\\config_beregnet.yaml = config.yaml med absolutte datastier, bump-vinduer regnet ud fra
        hvert bumps koordinat og radius (radius_m, standard 30 m) pr. strækning, og rapport.stoppesteder fra
        stoppesteder_hafas.yaml, hvis feltet er tomt i config.yaml. Står bump_vinduer udfyldt i config.yaml, bruges de.
    info: skriver analysetype, perioder, strækninger og om der er elementer som NØGLE=værdi (læses af koer_analyse.bat).
Uses: pandas, pyyaml (som resten af værktøjet); tjek_config.py (geometri, analysetype); ..\\lav_vejkort.py (kort).
Dependencies: config.yaml i analysemappen. Kaldes af koer_analyse.bat.
Debugging points: stopnavne læser kun stop-rækker (Stop-nummer udfyldt). Varierer turene (fx kortere ture), bruges
    den hyppigste rækkefølge; antallet af ture med den står i filen. Stoppenes position er medianen af de planlagte
    koordinater pr. retning og stopnavn (samme navn kan ligge på hver side af vejen). Cachen genbruges, så længe
    Details.csv har samme størrelse og ændringstid.
"""
import argparse
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tjek_config as TJ  # noqa: E402

PROGRAM = Path(__file__).resolve().parent.parent
STANDARD_RADIUS_M = TJ.STANDARD_RADIUS_M
PLADSHOLDER = TJ.PLADSHOLDER
CACHE = TJ.CACHE
lokal_xy, afstand_m = TJ.lokal_xy, TJ.afstand_m


def s_langs(p_fra, p_til, lat, lon):
    """Meter langs den rette linje fra p_fra mod p_til (samme geometri som komfort_v1.0) og linjens længde."""
    s, _d, L = TJ.projicer(p_fra, p_til, lat, lon)
    return s, L


def laes_config(sti):
    return yaml.safe_load(Path(sti).read_text(encoding="utf-8-sig")) or {}


def udfyldt(pt):
    return isinstance(pt, dict) and TJ.er_tal(pt.get("lat")) and TJ.er_tal(pt.get("lon")) and not TJ.er_pladsholder(pt)


def sti_rel(cfg_sti, s):
    p = Path(s)
    return p if p.is_absolute() else (Path(cfg_sti).resolve().parent / p)


def kort_navn(navn):
    """'Kvaglundvej v Lærkevej (Esbjerg)' -> 'Kvaglundvej v Lærkevej' (som vejkortet)."""
    return re.sub(r"\s*\([^)]*\)$", "", str(navn)).strip()


def straekninger(cfg):
    """[(id, navn, fra, til, elementer, komfort-overskrivning)] i begge config-former."""
    if cfg.get("straekninger"):
        return [(str(s.get("id") or f"s{i}"), str(s.get("navn") or s.get("id") or f"s{i}"), s.get("fra"), s.get("til"),
                 s.get("elementer") or [], s.get("komfort") or {}) for i, s in enumerate(cfg["straekninger"], 1)]
    kom = cfg.get("komfort") or {}
    if TJ.analysetype(cfg) == "kryds" or not kom:
        return []
    return [("s1", str((cfg.get("rapport") or {}).get("straekning_navn") or "Strækningen"), kom.get("fra", "p1"),
             kom.get("til", "p5"), cfg.get("elementer") or [], {})]


# ------------------------------------------------------------------ stoppesteder fra HAFAS (cache)

def rens(df):
    df.columns = [c.strip().strip('"').strip() for c in df.columns]
    return df


def laes_stop(cfg_sti, cfg, brug_cache=True):
    """Alle stop pr. HAFAS-retning fra periode A: {'1': {ture, med_raekkefoelgen, stop: [{navn, lat, lon}]}, ...}.
    Gemmes i resultat\\stoppesteder_hafas.yaml og genbruges, så længe Details.csv er den samme."""
    import pandas as pd
    d = cfg["data"]["Periode_A"]
    det, lst = sti_rel(cfg_sti, d["details_csv"]), sti_rel(cfg_sti, d["list_csv"])
    for f in (det, lst):
        if not f.exists():
            sys.exit(f"Filen findes ikke: {f}\nLæg HAFAS-eksporten i data\\A (se config.yaml, data).")
    kilde = {"details_csv": str(det), "stoerrelse": det.stat().st_size, "aendret": int(det.stat().st_mtime)}
    cache_fil = Path(cfg_sti).resolve().parent / CACHE
    if brug_cache and cache_fil.exists():
        try:
            c = yaml.safe_load(cache_fil.read_text(encoding="utf-8")) or {}
            if c.get("kilde") == kilde and c.get("retninger"):
                return c["retninger"]
        except yaml.YAMLError:
            pass
    liste = rens(pd.read_csv(lst, sep=";", encoding="utf-8", dtype=str))
    retning = dict(zip(liste["Turnummer"].str.strip(), liste["Retningsflag"].str.strip().str.split(".").str[0]))
    kol = ["Turreference", "Stop-navn", "Stop-nummer", "Breddegrad (PLANLAGT)", "Længdegrad (PLANLAGT)"]
    hoved = list(pd.read_csv(det, sep=";", encoding="utf-8", nrows=0).columns)
    brug = [c for c in hoved if c.strip().strip('"').strip() in kol]
    if len(brug) < len(kol):
        sys.exit(f"Details.csv mangler kolonner: {sorted(set(kol) - {c.strip().strip(chr(34)).strip() for c in hoved})}")
    stykker = []
    for ch in pd.read_csv(det, sep=";", encoding="utf-8", usecols=brug, dtype=str, chunksize=500_000):
        ch = rens(ch)
        stykker.append(ch[ch["Stop-nummer"].notna() & (ch["Stop-nummer"].str.strip() != "")])
    df = pd.concat(stykker, ignore_index=True)
    df["Stop-navn"] = df["Stop-navn"].str.strip()
    for c in ("Breddegrad (PLANLAGT)", "Længdegrad (PLANLAGT)"):
        df[c] = pd.to_numeric(df[c].str.replace(",", "."), errors="coerce")
    df["retning"] = df["Turreference"].str.strip().map(retning)
    ud = {}
    for r in sorted(x for x in df["retning"].dropna().unique() if x in ("1", "2")):
        dr = df[df["retning"] == r]
        sek = Counter(tuple(g["Stop-navn"]) for _, g in dr.groupby("Turreference", sort=False))
        (raekke, n), ture = sek.most_common(1)[0], sum(sek.values())
        pos = dr.groupby("Stop-navn")[["Breddegrad (PLANLAGT)", "Længdegrad (PLANLAGT)"]].median()
        stop, set_ = [], set()
        for navn in raekke:
            if navn in set_ or navn not in pos.index:
                continue
            set_.add(navn)
            la, lo = pos.loc[navn]
            if la == la and lo == lo:                      # ikke NaN
                stop.append({"navn": navn, "lat": round(float(la), 6), "lon": round(float(lo), 6)})
        ud[r] = {"ture": int(ture), "med_raekkefoelgen": int(n), "stop": stop}
    cache_fil.parent.mkdir(parents=True, exist_ok=True)
    cache_fil.write_text("# Lavet af forbered.py stopnavne: stoppesteder pr. retning fra HAFAS-eksporten (periode A). Ret ikke.\n"
                         + yaml.safe_dump({"kilde": kilde, "retninger": ud}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return ud


def laes_cache(cfg_sti, cfg=None):
    """Stoppestederne fra resultat\\stoppesteder_hafas.yaml, eller None hvis filen mangler eller er fra en anden
    Details.csv (anden sti, størrelse eller ændringstid) end config'ens periode A."""
    return TJ.laes_stop_cache(cfg_sti, cfg if cfg is not None else laes_config(cfg_sti))


def stop_paa_straekninger(cfg, ret_stop):
    """Stoppesteder (navn, retning, lat, lon), der ligger på en af strækningerne: 0-L langs linjen og højst 40 m fra den."""
    pts = cfg.get("points") or {}
    ud, set_ = [], set()
    for _sid, _navn, fra, til, _els, _k in straekninger(cfg):
        p_fra, p_til = pts.get(fra), pts.get(til)
        if not (udfyldt(p_fra) and udfyldt(p_til)):
            continue
        p_fra, p_til = {k: float(p_fra[k]) for k in ("lat", "lon")}, {k: float(p_til[k]) for k in ("lat", "lon")}
        for r, v in sorted((ret_stop or {}).items()):
            for s in v.get("stop", []):
                sx, sd, L = TJ.projicer(p_fra, p_til, s["lat"], s["lon"])
                noegle = (r, s["navn"])
                if 0.0 <= sx <= L and sd <= TJ.STOP_SIDEAFSTAND_M and noegle not in set_:
                    set_.add(noegle)
                    ud.append({"navn": kort_navn(s["navn"]), "retning": int(r), "lat": s["lat"], "lon": s["lon"]})
    return ud


# ------------------------------------------------------------------ stopnavne

def retning_ender(cfg):
    """{'direction_1': (første punkt-id, sidste punkt-id), ...} ud fra point_order; uden point_order: første og sidste
    punkt under points (retning 1) og omvendt (retning 2). Kun retninger, hvor begge punkter er udfyldt."""
    pts = cfg.get("points") or {}
    po = cfg.get("point_order") if isinstance(cfg.get("point_order"), dict) else None
    if not po:
        ids = list(pts)
        po = {"direction_1": ids, "direction_2": ids[::-1]} if len(ids) >= 2 else {}
    ud = {}
    for d, liste in po.items():
        if d in TJ.RETNINGER and isinstance(liste, list) and len(liste) >= 2 and udfyldt(pts.get(liste[0])) and udfyldt(pts.get(liste[-1])):
            ud[d] = (liste[0], liste[-1])
    return ud


def foreslaa(stop, p_foerst, p_sidst):
    """Indeks for start- og slutstop: første stop uden for de yderste punkter i hver ende plus ét stop som margin."""
    i1 = min(range(len(stop)), key=lambda i: afstand_m(stop[i], p_foerst))
    i2 = min(range(len(stop)), key=lambda i: afstand_m(stop[i], p_sidst))
    s_vals = [s_langs(p_foerst, p_sidst, x["lat"], x["lon"])[0] for x in stop]
    L = s_langs(p_foerst, p_sidst, p_sidst["lat"], p_sidst["lon"])[1]
    ia, ib = min(i1, i2), max(i1, i2)
    start = next((i for i in range(ia, -1, -1) if s_vals[i] < 0), None)
    slut = next((i for i in range(ib, len(stop)) if s_vals[i] > L), None)
    start = None if start is None else max(start - 1, 0)
    slut = None if slut is None else min(slut + 1, len(stop) - 1)
    return i1, i2, s_vals, L, start, slut


def koerer_frem(stop, p_foerst, p_sidst):
    """True, hvis bussen (stoppene i køreorden) kører fra p_foerst mod p_sidst. Bruger stoppene nær punkterne: kommer
    de senere stop længere fremme langs linjen p_foerst -> p_sidst, kører den frem."""
    s_vals = [s_langs(p_foerst, p_sidst, x["lat"], x["lon"]) for x in stop]
    L = s_vals[0][1] if s_vals else 0.0
    midt = {"lat": (p_foerst["lat"] + p_sidst["lat"]) / 2, "lon": (p_foerst["lon"] + p_sidst["lon"]) / 2}
    naer = [s for (s, _L), x in zip(s_vals, stop) if afstand_m(x, midt) <= L / 2 + 400]
    if len(naer) >= 2 and naer[-1] != naer[0]:
        return naer[-1] > naer[0]
    i1 = min(range(len(stop)), key=lambda i: afstand_m(stop[i], p_foerst))
    i2 = min(range(len(stop)), key=lambda i: afstand_m(stop[i], p_sidst))
    return i1 < i2


def stopnavne(cfg_sti, ud):
    cfg = laes_config(cfg_sti)
    ret_stop = laes_stop(cfg_sti, cfg)
    pts = cfg.get("points") or {}
    P = {pid: {"lat": float(p["lat"]), "lon": float(p["lon"])} for pid, p in pts.items() if udfyldt(p)}
    ender = retning_ender(cfg)
    linjer = ["Stoppesteder pr. kørselsretning, i den rækkefølge bussen kører dem (periode A).",
              "Navnene kan være forskellige i de to retninger, og stoppene kan ligge forskelligt (fx et stop på hver",
              "side af vejen). Vælg derfor start og slut for hver retning for sig, og kopiér navnene præcist.",
              "Meter før/efter er målt i ret linje mellem retningens første og sidste punkt; svinger ruten, er tallet kun vejledende.",
              "Alle punkter og stoppesteder kan ses på kontrolkort.html.", ""]
    forslag, obs, kører = {}, [], {}
    for r, v in sorted(ret_stop.items()):
        stop = v["stop"]
        d = f"direction_{r}"
        e = ender.get(d) or (next(iter(ender.values())) if len(ender) == 1 else None)
        linjer.append(f"=== Retning {r}: {len(stop)} stoppesteder (rækkefølgen for {v['med_raekkefoelgen']} af {v['ture']} ture) ===")
        if not e or not stop:
            linjer += [f"  {i + 1:3d}. {s['navn']}" for i, s in enumerate(stop)] + [""]
            continue
        f_id, l_id = e
        frem = koerer_frem(stop, P[f_id], P[l_id])
        kører[r] = frem
        foerst, sidst = (f_id, l_id) if frem else (l_id, f_id)
        i1, i2, s_vals, L, start, slut = foreslaa(stop, P[foerst], P[sidst])
        linjer.append(f"  (kører fra {foerst} mod {sidst})")
        for i, s in enumerate(stop):
            x = s_vals[i]
            side = TJ.projicer(P[foerst], P[sidst], s["lat"], s["lon"])[1]
            sted = f"{-x:.0f} m før {foerst}" if x < 0 else (f"{x - L:.0f} m efter {sidst}" if x > L else
                                                             "mellem punkterne" if side <= 40 else f"ved siden af, {side:.0f} m fra linjen")
            maerke = "  <-- forslag: start" if i == start else ("  <-- forslag: slut" if i == slut else "")
            linjer.append(f"  {i + 1:3d}. {s['navn']}   ({sted}){maerke}")
        if start is not None and slut is not None:
            forslag[r] = (stop[start]["navn"], stop[slut]["navn"])
        linjer.append("")
    # retninger i config mod retninger i data
    brug = {}
    for d, (f_id, l_id) in ender.items():
        r = d[-1]
        if r in kører and kører[r]:
            brug[d] = r
        elif r in kører:
            anden = next((x for x in kører if x != r and kører[x]), None)
            if len(ender) == 1 and anden:
                obs.append(f"OBS: din point_order ({d}: {f_id} -> {l_id}) køres i data som retning {anden}. "
                           f"Skriv direction_{anden} i stedet for {d} under point_order og stops.")
                brug[f"direction_{anden}"] = anden
            else:
                obs.append(f"OBS: retning {r} kører fra {l_id} mod {f_id}. Byt rækkefølgen af punkterne under point_order "
                           f"for {d} (to punkter: byt p1 og p2 i config.yaml, koordinater og navne), og kør 1 igen.")
    if not ender:
        linjer += ["Udfyld punkterne (points) i config.yaml, og kør 1 igen: så foreslås start- og slutstop pr. retning.", ""]
    elif obs:
        linjer += obs + [""]
    if ender and (not obs or len(ender) == 1) and brug and all(r in forslag for r in brug.values()):
        linjer += ["Forslag til config.yaml, stops: ét stoppested før og ét efter de yderste punkter, med et stop i margin.",
                   "Erstat stops-linjerne i config.yaml med disse:", "stops:"]
        linjer += [f'  direction_{r}: {{start: "{forslag[r][0]}", end: "{forslag[r][1]}"}}' for r in sorted(set(brug.values()))]
        linjer.append("")
    sp = stop_paa_straekninger(cfg, ret_stop)
    if sp:
        linjer += [f"Stoppesteder på strækningerne ({len(sp)}), fundet i HAFAS-eksporten. De bruges automatisk i rapporten,",
                   "så længe rapport.stoppesteder er tom ([]) i config.yaml. Vil du rette dem, så erstat linjen",
                   "  stoppesteder: []  under rapport: med denne blok (og ret i den):",
                   "  stoppesteder:"]
        linjer += [f'    - {{navn: "{s["navn"]}", retning: {s["retning"]}, lat: {s["lat"]}, lon: {s["lon"]}}}' for s in sp]
        linjer.append("")
    elif straekninger(cfg):
        linjer += ["Ingen stoppesteder fundet på strækningerne (højst 40 m fra linjen mellem fra og til).", ""]
    Path(ud).write_text("\n".join(linjer), encoding="utf-8")
    print(f"Skrev {ud}")


# ------------------------------------------------------------------ config med bump-vinduer og stoppesteder

def bump_vinduer(els, p_fra, p_til):
    vinduer = {}
    for e in els or []:
        if str(e.get("type") or "").strip().lower() != "bump":       # som zonetid og tjek_config
            continue
        r = float(e.get("radius_m") or STANDARD_RADIUS_M)
        s, _ = s_langs(p_fra, p_til, float(e["lat"]), float(e["lon"]))
        vinduer[str(e["navn"])] = [round(s - r), round(s + r)]
    return vinduer


def beregnet_config(cfg_sti, ud, laes_data=False):
    cfg = laes_config(cfg_sti)
    for k, v in (cfg.get("data") or {}).items():
        if isinstance(v, dict):
            for f in ("details_csv", "list_csv"):
                if v.get(f):
                    v[f] = str(sti_rel(cfg_sti, v[f]))
        elif k == "output":
            cfg["data"]["output"] = str(sti_rel(cfg_sti, v))
    pts = cfg.get("points") or {}
    if TJ.analysetype(cfg) != "kryds":
        if not isinstance(cfg.get("komfort"), dict):
            cfg["komfort"] = {}
        if cfg.get("straekninger"):
            faelles = cfg["komfort"].get("bump_vinduer")       # udfyldt i config.yaml: gælder alle strækninger uden egne
            if not faelles:
                cfg["komfort"]["bump_vinduer"] = {}          # komfort_v1.0's standardvinduer må ikke følge med
            for s in cfg["straekninger"]:
                if not isinstance(s.get("komfort"), dict):
                    s["komfort"] = {}
                k = s["komfort"]
                fra, til = pts.get(s.get("fra")), pts.get(s.get("til"))
                if not k.get("bump_vinduer") and not faelles and fra and til:
                    k["bump_vinduer"] = bump_vinduer(s.get("elementer"), fra, til)
                    print(f"Bump-vinduer, strækning {s.get('id')} (meter fra {fra.get('name', s.get('fra'))}): " +
                          (", ".join(f"{n} {a}-{b}" for n, (a, b) in k["bump_vinduer"].items()) or "ingen bump"))
        else:
            kom = cfg["komfort"]
            fra, til = pts.get(kom.get("fra", "p1")), pts.get(kom.get("til", "p2"))
            if not kom.get("bump_vinduer") and fra and til:
                kom["bump_vinduer"] = bump_vinduer(cfg.get("elementer"), fra, til)
                print("Bump-vinduer (meter fra " + str(fra.get("name", "p1")) + "): " +
                      (", ".join(f"{n} {a}-{b}" for n, (a, b) in kom["bump_vinduer"].items()) or "ingen bump"))
        if cfg.get("rapport") is None:
            cfg["rapport"] = {}
        rap = cfg["rapport"]
        if isinstance(rap, dict):
            if not rap.get("stoppesteder"):
                ret_stop = laes_cache(cfg_sti, cfg)
                if ret_stop is None and laes_data:
                    print("Finder stoppestederne i data\\A (ca. 1 min pr. GB) ...")
                    ret_stop = laes_stop(cfg_sti, laes_config(cfg_sti))
                sp = stop_paa_straekninger(cfg, ret_stop) if ret_stop else []
                rap["stoppesteder"] = sp
                print(f"Stoppesteder i rapporten: {len(sp)} fundet i HAFAS-eksporten" if ret_stop else
                      "Stoppesteder i rapporten: ingen (vælg 1 for at finde dem i data)")
    Path(ud).parent.mkdir(parents=True, exist_ok=True)
    tekst = "# Lavet af forbered.py ud fra config.yaml. Ret i config.yaml, ikke her.\n"
    tekst += yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
    Path(ud).write_text(tekst, encoding="utf-8")


# ------------------------------------------------------------------ info til koer_analyse.bat

def info(cfg_sti, ud=None):
    cfg = laes_config(cfg_sti)
    sk = straekninger(cfg)
    linjer = [f"CFG_TYPE={TJ.analysetype(cfg)}",
              f"CFG_PERIODER={' '.join(TJ.koer_perioder(cfg))}",
              f"CFG_STRAEKNINGER={' '.join(s[0] for s in sk)}",
              f"CFG_ANTAL={len(sk)}",
              f"CFG_ELEMENTER={1 if any(s[4] for s in sk) else 0}"]
    tekst = "\n".join(linjer)
    if ud:
        Path(ud).write_text(tekst + "\n", encoding="utf-8")
    print(tekst)


# ------------------------------------------------------------------ kontrolkort

FARVE = {"punkt": None, "element": "#c2410c", "1": "#7c3aed", "2": "#0e7490", "stop_andet": "#9aa5b1"}


def gmaps(lat, lon):
    return f"https://www.google.com/maps?q={lat:.6f},{lon:.6f}"


def osm_stop(grund):
    if not grund:
        return []
    s, w = grund["omraade"][0], grund["omraade"][1]
    en = grund["enhed"]
    return [{"navn": t, "lat": s + dy * en, "lon": w + dx * en} for art, t, dy, dx in grund.get("detaljer", []) if art == "stop"]


def kort(cfg_sti, ud, hent=True):
    cfg = laes_config(cfg_sti)
    mappe = Path(cfg_sti).resolve().parent
    pts = cfg.get("points") or {}
    rap = cfg.get("rapport") if isinstance(cfg.get("rapport"), dict) else {}
    ret_stop = laes_cache(cfg_sti) or {}
    P = {pid: {"lat": float(p["lat"]), "lon": float(p["lon"]), "name": str(p.get("name", pid))} for pid, p in pts.items() if udfyldt(p)}
    raekker, punkter, linjer = [], [], []
    for pid, p in P.items():
        punkter.append({"lat": p["lat"], "lon": p["lon"], "navn": f"{pid} {p['name']}", "ende": True, "navn_altid": True})
        raekker.append(("Punkt", f"{pid}: {p['name']}", "", p["lat"], p["lon"], ""))
    sk = straekninger(cfg)
    for sid, navn, fra, til, els, _k in sk:
        if fra in P and til in P:
            linjer.append({"pkt": [[P[fra]["lat"], P[fra]["lon"]], [P[til]["lat"], P[til]["lon"]]], "valgt": True,
                           "titel": f"Strækning {sid}: {navn} ({fra} -> {til})"})
        for e in els:
            if not udfyldt(e):
                continue
            lat, lon = float(e["lat"]), float(e["lon"])
            note = ""
            if fra in P and til in P:
                sx, sd, L = TJ.projicer(P[fra], P[til], lat, lon)
                note = f"{sx:.0f} m fra {fra} (strækningen er {L:.0f} m), {sd:.0f} m fra linjen"
            punkter.append({"lat": lat, "lon": lon, "navn": str(e.get("navn", "")), "farve": FARVE["element"]})
            raekker.append(("Element", f"{e.get('navn', '')} ({e.get('type', 'andet')}, strækning {sid})", "", lat, lon, note))
    if not sk:                                   # kryds: punkterne i køreorden pr. retning
        for d, liste in (cfg.get("point_order") or {}).items():
            pk = [[P[x]["lat"], P[x]["lon"]] for x in (liste or []) if x in P]
            if len(pk) > 1:
                linjer.append({"pkt": pk, "valgt": True, "titel": f"{d}: {' -> '.join(map(str, liste))}"})
    # stoppesteder: config'ens, ellers de fundne på strækningerne; øvrige fundne stop i området nedtonet
    fra_config = bool(rap.get("stoppesteder"))
    brugte = rap.get("stoppesteder") if fra_config else stop_paa_straekninger(cfg, ret_stop)
    omr_pk = [[p["lat"], p["lon"]] for p in P.values()]
    if omr_pk:
        la0, la1 = min(p[0] for p in omr_pk) - 0.0013, max(p[0] for p in omr_pk) + 0.0013
        lo0, lo1 = min(p[1] for p in omr_pk) - 0.0022, max(p[1] for p in omr_pk) + 0.0022
    alle_stop = []
    for r, v in sorted(ret_stop.items()):
        for s in v.get("stop", []):
            if omr_pk and la0 <= s["lat"] <= la1 and lo0 <= s["lon"] <= lo1:
                alle_stop.append({**s, "retning": r})
    grund, besked = None, ""
    if omr_pk:
        fil = mappe / "resultat" / "vejkort_kontrol.json"
        omraade = [{"lat": p[0], "lon": p[1]} for p in omr_pk] + [{"lat": s["lat"], "lon": s["lon"]} for s in alle_stop]
        try:
            sys.path.insert(0, str(PROGRAM))
            import lav_vejkort
            if hent:
                lav_vejkort.hent_til(omraade, fil)
            if fil.exists():
                g = json.loads(fil.read_text(encoding="utf-8"))
                grund = g if lav_vejkort.daekker(g, omraade) else None
            if grund is None:
                besked = "Vejkortet er ikke hentet; kortet viser kun punkterne."
        except Exception as ex:                  # Overpass 502/429, intet net m.m.: kun punkterne
            besked = f"Vejkortet kunne ikke hentes ({ex}); kortet viser kun punkterne. Vælg 7 for at prøve igen."
    osm = osm_stop(grund)

    def osm_note(lat, lon):
        if not osm:
            return "OSM: ikke hentet" if grund is None else "OSM: intet stop i området"
        n = min(osm, key=lambda o: afstand_m({"lat": lat, "lon": lon}, o))
        return f"nærmeste OSM-stop: {n['navn'] or '(uden navn)'}, {afstand_m({'lat': lat, 'lon': lon}, n):.0f} m"

    brugt_noegle = set()
    for s in brugte or []:
        if not (TJ.er_tal(s.get("lat")) and TJ.er_tal(s.get("lon"))):
            continue
        r = str(s.get("retning", ""))
        brugt_noegle.add((r, kort_navn(s.get("navn", ""))))
        punkter.append({"lat": float(s["lat"]), "lon": float(s["lon"]), "navn": f"Stop {r}: {s.get('navn', '')}",
                        "farve": FARVE.get(r, FARVE["1"])})
        raekker.append(("Stoppested i rapporten" + (" (config)" if fra_config else " (fundet)"), str(s.get("navn", "")), r,
                        float(s["lat"]), float(s["lon"]), osm_note(float(s["lat"]), float(s["lon"]))))
    for s in alle_stop:
        if (s["retning"], kort_navn(s["navn"])) in brugt_noegle:
            continue
        punkter.append({"lat": s["lat"], "lon": s["lon"], "navn": "", "farve": FARVE["stop_andet"],
                        "titel": f"Stop {s['retning']}: {s['navn']} (HAFAS, ikke på en strækning)"})
        raekker.append(("Stop i data (ikke i rapporten)" if sk else "Stop i data", s["navn"], s["retning"], s["lat"], s["lon"], osm_note(s["lat"], s["lon"])))
    titel = f"Kontrolkort: {mappe.name}"
    tabel = "".join(
        f"<tr><td>{html.escape(t)}</td><td>{html.escape(str(n))}</td><td>{html.escape(str(r))}</td>"
        f"<td class='tal'>{la:.6f}</td><td class='tal'>{lo:.6f}</td>"
        f"<td><a href='{gmaps(la, lo)}' target='_blank' rel='noopener'>Google Maps</a></td><td>{html.escape(note)}</td></tr>"
        for t, n, r, la, lo, note in raekker)
    mangler = [pid for pid, p in pts.items() if not udfyldt(p)]
    noter = []
    if mangler:
        noter.append(f"Punkter uden koordinat (pladsholder) vises ikke: {', '.join(map(str, mangler))}.")
    if not ret_stop:
        noter.append("Stoppesteder fra data er ikke fundet endnu: vælg 1 i koer_analyse.bat.")
    if besked:
        noter.append(besked)
    data = {"grund": grund, "linjer": linjer, "punkter": punkter, "omraade": omr_pk or [[56.0, 10.0]]}
    vk_js = (PROGRAM / "vejkort.js").read_text(encoding="utf-8").replace("</", "<\\/")
    vk_css = (PROGRAM / "vejkort.css").read_text(encoding="utf-8")
    # Outside the f-string: a backslash in an f-string expression needs Python 3.12+.
    data_js = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    side = f"""<!doctype html>
<html lang="da"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titel)}</title>
<style>
:root {{ --bg:#ffffff; --tekst:#1d1d1f; --daempet:#5f6368; --ramme:#d9dce1; }}
body {{ background:var(--bg); color:var(--tekst); font-family:system-ui, Segoe UI, Arial, sans-serif; margin:0 auto; max-width:1100px; padding:16px; }}
h1 {{ font-size:1.4rem; margin:0 0 4px; }} p {{ margin:4px 0 10px; }} .daempet {{ color:var(--daempet); font-size:.9rem; }}
.forklaring span {{ display:inline-block; margin-right:14px; }} .forklaring i {{ display:inline-block; width:11px; height:11px; border-radius:50%; margin-right:4px; vertical-align:-1px; }}
table {{ border-collapse:collapse; width:100%; font-size:.88rem; margin-top:12px; }} th, td {{ border-bottom:1px solid var(--ramme); padding:4px 6px; text-align:left; vertical-align:top; }}
td.tal {{ font-variant-numeric:tabular-nums; white-space:nowrap; }} .tabel {{ overflow-x:auto; }}
.note {{ background:#fff7e6; border:1px solid #f0c36d; border-radius:6px; padding:6px 10px; }}
{vk_css}
</style></head><body>
<h1>{html.escape(titel)}</h1>
<p>Alle punkter fra config.yaml og de stoppesteder, der er fundet i HAFAS-eksporten. Tjek, at de ligger rigtigt, og ret dem i
config.yaml før kørsel (koordinaterne står i tabellen; Google Maps-linket viser hvert punkt). Kortet er kun til visning.</p>
{''.join(f'<p class="note">{html.escape(n)}</p>' for n in noter)}
<p class="forklaring daempet"><span><i style="background:#1f5fa8"></i>punkt fra config</span><span><i style="background:{FARVE['element']}"></i>element</span>
<span><i style="background:{FARVE['1']}"></i>stoppested retning 1</span><span><i style="background:{FARVE['2']}"></i>stoppested retning 2</span>
<span><i style="background:{FARVE['stop_andet']}"></i>andet stop i data</span><span>busikon = stoppested i OpenStreetMap (ved zoom)</span></p>
<div id="kort"></div>
<div class="tabel"><table><thead><tr><th>Type</th><th>Navn</th><th>Retning</th><th>lat</th><th>lon</th><th>Kort</th><th>Bemærkning</th></tr></thead>
<tbody>{tabel}</tbody></table></div>
<p class="daempet">Lavet af forbered.py kort ud fra {html.escape(Path(cfg_sti).name)}. Stoppesteder: HAFAS' planlagte koordinater (median pr. retning og stopnavn).</p>
<script>{vk_js}</script>
<script>
const D = {data_js};
const k = Vejkort.lav(document.getElementById('kort'), D.grund, D.omraade);
k.tegn(D.linjer, D.punkter);
k.tilpas(D.punkter.map((p) => [p.lat, p.lon]));
</script>
</body></html>
"""
    Path(ud).write_text(side, encoding="utf-8")
    print(f"Skrev {ud}" + (f" ({besked})" if besked else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("hvad", choices=["stopnavne", "config", "info", "kort"])
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--laes-data", action="store_true", help="config: find stoppesteder i data\\A, hvis valg 1 ikke er kørt")
    ap.add_argument("--uden-net", action="store_true", help="kort: hent ikke vejkortet (bruger det gemte, hvis det findes)")
    a = ap.parse_args()
    if a.hvad == "info":
        return info(a.config, a.out)
    if not a.out:
        ap.error("--out mangler")
    if a.hvad == "stopnavne":
        stopnavne(a.config, a.out)
    elif a.hvad == "kort":
        kort(a.config, a.out, hent=not a.uden_net)
    else:
        beregnet_config(a.config, a.out, laes_data=a.laes_data)


if __name__ == "__main__":
    main()
