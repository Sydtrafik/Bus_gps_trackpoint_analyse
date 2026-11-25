"""Laver en udfyldt konklusionsfil (YAML) til de nationale analysekonklusioner ud fra en færdig analyse.

Functionality: læser tallene fra analysens resultater og skriver én YAML-fil, hvor tallene er udfyldt, og de felter,
du selv skal udfylde (vej, by, linjer, bustype, ændring, kontakt m.m.), står med UDFYLD. Felter, der er gættet ud fra
config'en (vejtype, hastighed, fartdæmpere, forbehold), har kommentaren "tjek". Når filen er udfyldt, tilføjes den med
    python program\\lav_konklusioner_html.py --tilfoej <konklusion.yaml>
som tjekker den, kopierer den til analyser\\<vej>_<by>_<år>.yaml og laver oversigten igen.

Tallene er præcis rapportens nøgletal (standardvalget): dagtypen fra udvalg i config (normalt hverdage), alle ruter,
alle timer, begge retninger, ture uden standsning ved stop, median.
  - Strækning (før/efter eller én periode):  --rapportdata resultat\\rapportdata.json   (lav_rapportdata_v1.2.py)
  - Kryds:                                    --overblik resultat\\overblik.csv --config config.yaml   (turtabel.py)

    python program\\lav_konklusion.py --rapportdata <resultat\\rapportdata.json> --out <resultat\\konklusion.yaml>
    python program\\lav_konklusion.py --overblik <resultat\\overblik.csv> --config <config.yaml> --out <konklusion.yaml>

Uses: pyyaml. Ingen ny beregning: kun tal, der allerede står i rapportdata.json / overblik.csv (laveste fart ved
fartdæmper = gennemsnit af medianerne pr. vindue, som rapportens nøgletal; mærkbar acceleration = andel ud fra
rapportdatas fordeling, samme udvalg). Overskriver ikke en eksisterende fil uden --overskriv.
"""
import argparse
import csv
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path

import yaml

PROGRAM = Path(__file__).resolve().parent
UDFYLD = "UDFYLD"


def _version():
    p = PROGRAM / "VERSION"
    return p.read_text(encoding="utf-8").strip() if p.exists() else "?"


def tal(v, n=1):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    v = round(float(v), n)
    return int(v) if n == 0 or v == int(v) else v


# ---------------------------------------------------------------- strækning (rapportdata.json)
def fra_rapportdata(doc, sid=None):
    """Returnér (felter, kommentarer) ud fra rapportdata.json v1.2."""
    if str(doc.get("version")) != "1.2":
        raise SystemExit(f"rapportdata.json har version {doc.get('version')}; lav den med lav_rapportdata_v1.2.py (koer_analyse.bat valg 4)")
    m = doc["meta"]
    strk = m["straekninger"]
    if sid is None:
        if len(strk) > 1:
            raise SystemExit("Analysen har flere strækninger. Vælg én med --straekning: " + ", ".join(f"{s['id']} ({s['navn']})" for s in strk))
        s = strk[0]
    else:
        s = next((x for x in strk if x["id"] == sid), None)
        if s is None:
            raise SystemExit(f"Strækningen '{sid}' findes ikke. Vælg en af: " + ", ".join(x["id"] for x in strk))
    sid = s["id"]
    PER = m["perioder"]
    to = len(PER) == 2
    nav = {"A": "foer", "B": "efter"} if to else {"A": "periode"}
    std, AR, AT = m["standard_dag"], m["alle_ruter"], m["alle_timer"]
    dagset = next((x["dagtyper"] for x in m["dagtyper"] if x["navn"] == std), None)

    def nr(p):
        r = [x for x in doc["nogletal"] if x["S"] == sid and x["Retning"] == "B" and x["Gruppe"] == "Uden stop"
             and x["Periode"] == p and x["Dag"] == std and x["Rute"] == AR and x["Time"] == AT]
        if len(r) != 1:
            raise SystemExit(f"Fandt {len(r)} nøgletal for periode {p} i standardvalget (forventede 1)")
        return r[0]

    def andel(p, kol):
        rk = [x for x in doc["fordeling"] if x["S"] == sid and x["Periode"] == p and x["Stop"] == "Uden stop"
              and (dagset is None or x["Dagtype"] in dagset)]
        n = sum(x["n"] for x in rk)
        return 100 * sum(x["n"] for x in rk if x[kol] in ("Maerkbar", "Kraftig")) / n if n else None

    ud, kom = {}, {}
    vind = s.get("vinduer") or []
    for felt in ("ture", "koeretid_s", "gnsfart_kmt", "laveste_fart_kmt", "maerkbar_opbremsning_pct", "maerkbar_acceleration_pct"):
        ud[felt] = {}
    for p in PER:
        r, k = nr(p), nav[p]
        ud["ture"][k] = r["Ture"]
        ud["koeretid_s"][k] = tal(r["koretid"], 0)
        ud["gnsfart_kmt"][k] = tal(r["gnsfart"])
        mf = r.get("minfart") or {}
        ud["laveste_fart_kmt"][k] = tal(sum(mf[v] for v in vind) / len(vind)) if vind and all(mf.get(v) is not None for v in vind) else None
        ud["maerkbar_opbremsning_pct"][k] = tal(100 * r["andel_opbr"], 2) if r.get("andel_opbr") is not None else None
        ud["maerkbar_acceleration_pct"][k] = tal(andel(p, "KlasseAcc"), 2)
        # kontrol: andelen med mærkbar opbremsning fra fordelingen = nøgletallet (samme udvalg)
        a2 = andel(p, "Klasse")
        if r.get("andel_opbr") is not None and a2 is not None and abs(a2 - 100 * r["andel_opbr"]) > 0.05:
            raise SystemExit(f"Fordeling og nøgletal passer ikke sammen i periode {p} ({a2:.2f} mod {100 * r['andel_opbr']:.2f} %)")
    if not vind:
        ud["laveste_fart_kmt"] = None
        kom["laveste_fart_kmt"] = "ingen fartdæmpere med vindue i analysen (komfort.bump_vinduer)"
    ud["dage"] = "hverdage" if std == "Hverdage" else std.lower()
    pd_ = m.get("perioder_datoer") or {}
    ud["perioder"] = {}
    for p in PER:
        omf = [x for x in doc["omfang"] if x["S"] == sid and x["Periode"] == p and x["Dag"] == std and x["Rute"] == AR and x["Time"] == AT]
        fra, til = (pd_.get(p) or [UDFYLD, UDFYLD])
        ud["perioder"][nav[p]] = {"fra": fra, "til": til, "dage": omf[0]["Dage"] if omf else None}
    (la, lo), (lb, lob) = s["linje"]
    ud["laengde_m"] = tal(s["laengde_m"], 0)
    ud["kort"] = f"https://www.google.com/maps/dir/?api=1&origin={la:.5f},{lo:.5f}&destination={lb:.5f},{lob:.5f}&travelmode=driving"
    # elementer -> fartdæmpere (gættet ud fra config; tjekkes af personen)
    vej = m.get("vej") or {}
    antal = {}
    for e in s.get("elementer") or []:
        t = str(e["type"]).lower()
        if t == "bump":
            t = str(vej.get("bumptype") or "bump").lower()
        elif t.startswith("indsn"):
            t = "indsnævring"
        antal[t] = antal.get(t, 0) + 1
    ud["fartdaempere"] = sorted(({"type": t, "antal": n} for t, n in antal.items()), key=lambda x: x["type"] == "indsnævring")
    kom["fartdaempere"] = "tjek: fra elementer i config og rapport.vej.bumptype; brug bumptypens navn fra vejreglerne"
    ud["vejtype"] = vej.get("vejtype") or UDFYLD
    if vej.get("vejtype"):
        kom["vejtype"] = "tjek: fra rapport.vej i config"
    hast = [int(x) for x in re.findall(r"\d+", str(vej.get("hastighed") or ""))]
    if to and len(hast) >= 2:
        ud["hastighed_kmt"] = {"foer": hast[0], "efter": hast[1]}
        kom["hastighed_kmt"] = "tjek: fra rapport.vej.hastighed i config"
    elif not to and len(hast) == 1:
        ud["hastighed_kmt"] = {"periode": hast[0]}
        kom["hastighed_kmt"] = "tjek: fra rapport.vej.hastighed i config"
    else:
        ud["hastighed_kmt"] = {k: UDFYLD for k in nav.values()}
    zt = [x for x in doc.get("zonetid") or [] if x["S"] == sid and x["Retning"] == "B" and "Lav" in x]
    ud["ekstra_tid_pr_element_s"] = [{"element": x["Element"], "lav": tal(x["Lav"], 2), "hoej": tal(x["Hoej"], 2)} for x in zt] or None
    ud["forbehold"] = list(m.get("forbehold") or []) or [UDFYLD]
    if m.get("forbehold"):
        kom["forbehold"] = "tjek: fra rapport.forbehold i config; kom flere ændringer samtidig, så skriv, at tallene ikke kan skille dem ad"
    ud["type"] = "foer_efter" if to else "en_periode"
    sidste = (pd_.get(PER[-1]) or [""])[0]
    ud["aar"] = int(sidste[:4]) if re.match(r"\d{4}", str(sidste)) else UDFYLD
    ud["vaerktoej"] = f"trackpoint-værktøj {_version()}, rapportdata {doc['version']}"
    return ud, kom


# ---------------------------------------------------------------- kryds (overblik.csv + config)
def _afstand(a, b):
    R = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def fra_overblik(rk, cfg):
    """Returnér (felter, kommentarer) for en kryds-analyse ud fra overblik.csv (rækker) og config (dict)."""
    pts = cfg.get("points") or {}
    orden = (cfg.get("point_order") or {}).get("direction_1") or list(pts)
    if len(orden) < 2 or any(p not in pts for p in orden):
        raise SystemExit("config.yaml mangler points eller point_order.direction_1")
    per = sorted({r["Periode"] for r in rk})
    if per not in (["A"], ["A", "B"]):
        raise SystemExit(f"overblik.csv har perioderne {per}; forventede A eller A og B")
    to = per == ["A", "B"]
    nav = {"A": "foer", "B": "efter"} if to else {"A": "periode"}
    alle = [r for r in rk if r["Time"] == "alle"]
    ud, kom = {"type": "kryds"}, {}
    stykker = []
    for (stk, ret) in dict.fromkeys((r["Stykke"], r["Retning"]) for r in alle):   # rækkefølge som i overblik.csv
        s = {"stykke": stk, "retning": int(ret) if ret.isdigit() else ret}
        for p in per:
            r = [x for x in alle if x["Stykke"] == stk and x["Retning"] == ret and x["Periode"] == p]
            s[nav[p]] = tal(float(r[0]["median"]), 0) if r and r[0]["median"] not in ("", None) else None
        stykker.append(s)
    ud["kryds_stykker"] = stykker
    # hele krydset = stykket fra første til sidste punkt (distances i config), i retningen med flest ture
    navne = {d.get("name"): (d.get("from"), d.get("to")) for d in (cfg.get("distances") or {}).values()}
    hel = [n for n, (f, t) in navne.items() if {f, t} == {orden[0], orden[-1]}]
    ud["koeretid_s"], ud["ture"] = None, None
    if hel:
        kand = [x for x in alle if x["Stykke"] == hel[0]]
        if kand:
            rets = sorted({x["Retning"] for x in kand}, key=lambda r: -sum(int(x["n"]) for x in kand if x["Retning"] == r))
            ret = rets[0]
            ud["koeretid_s"] = {nav[p]: next((tal(float(x["median"]), 0) for x in kand if x["Retning"] == ret and x["Periode"] == p), None) for p in per}
            ud["ture"] = {nav[p]: next((int(x["n"]) for x in kand if x["Retning"] == ret and x["Periode"] == p), None) for p in per}
            kom["koeretid_s"] = f"hele krydset ({hel[0]}), retning {ret}, median"
    if ud["koeretid_s"] is None:
        kom["koeretid_s"] = "ingen distance fra første til sidste punkt i config; se kryds_stykker"
    ud["laengde_m"] = tal(sum(_afstand(pts[a], pts[b]) for a, b in zip(orden, orden[1:])), 0)
    kom["laengde_m"] = "ca.: lige linjer mellem punkterne i point_order.direction_1"
    a, b = pts[orden[0]], pts[orden[-1]]
    ud["kort"] = f"https://www.google.com/maps/dir/?api=1&origin={a['lat']:.5f},{a['lon']:.5f}&destination={b['lat']:.5f},{b['lon']:.5f}&travelmode=driving"
    pc = cfg.get("periods") or {}
    ud["perioder"] = {nav[p]: {"fra": str((pc.get(p) or {}).get("start") or UDFYLD), "til": str((pc.get(p) or {}).get("end") or UDFYLD), "dage": None} for p in per}
    dt_ = ((cfg.get("udvalg") or {}).get("dagtype") or "hverdage")
    ud["dage"] = "hverdage" if dt_ == "hverdage" else str(dt_)
    ud["fartdaempere"] = []
    ud["hastighed_kmt"] = {k: UDFYLD for k in nav.values()}
    ud["vejtype"] = UDFYLD
    ud["forbehold"] = [UDFYLD]
    sidste = str((pc.get(per[-1]) or {}).get("start") or "")
    ud["aar"] = int(sidste[:4]) if re.match(r"\d{4}", sidste) else UDFYLD
    ud["vaerktoej"] = f"trackpoint-værktøj {_version()}, overblik.csv"
    return ud, kom


# ---------------------------------------------------------------- skriv YAML med vejledning
def _v(x):
    """YAML-værdi på én linje (JSON er gyldig YAML)."""
    if isinstance(x, dict):
        return "{" + ", ".join(f"{k}: {_v(v)}" for k, v in x.items()) + "}"
    if x is None:
        return "null"
    return json.dumps(x, ensure_ascii=False)


def skriv_yaml(ud, kom):
    i_dag = dt.date.today().isoformat()

    def linje(felt, vaerdi, hjaelp=""):
        k = kom.get(felt) or hjaelp
        return f"{felt}: {_v(vaerdi)}" + (f"   # {k}" if k else "")

    L = ["# Konklusion til de nationale analysekonklusioner (én fil pr. analyse; vejledning: analyser/README.md).",
         f"# Lavet af lav_konklusion.py {i_dag}. Udfyld alle UDFYLD, tjek linjer med 'tjek', og tilføj filen med",
         "#   python program\\lav_konklusioner_html.py --tilfoej <denne fil>",
         "# Filen bliver offentlig på GitHub: kun aggregerede tal, ingen mail, telefon, tur-id eller rådata.",
         "",
         f"skema: 1",
         linje("type", ud["type"], "foer_efter, en_periode eller kryds"),
         linje("vej", UDFYLD, "vejnavn, fx Kvaglundvej"),
         linje("by", UDFYLD),
         linje("aar", ud["aar"], "året for ændringen (eller perioden)"),
         linje("vejtype", ud["vejtype"], "fx gennemkørselsvej i boligkvarter, boligvej, trafikvej, landevej"),
         linje("linjer", UDFYLD, "fx 3A, begge retninger"),
         linje("bustype", UDFYLD, "drivmiddel og længde, fx elbusser (alle); 'ikke oplyst' hvis ukendt"),
         linje("aendring", UDFYLD if ud["type"] != "en_periode" else "ingen (én periode)",
               "kort, fx 2 sinusbump + 2 indsnævringer, 50 → 40 km/t"),
         "# Fartdæmpere: bumptype med navnet fra vejreglerne (sinusbump, cirkelbump, modificeret cirkelbump, pudebump,",
         "# trapezbump, hævet flade ...), indsnævring, chikane, rundkørsel o.l. Tom liste [] = ingen. Første bumptype giver tegningen.",
         ("fartdaempere:" + (f"   # {kom['fartdaempere']}" if kom.get("fartdaempere") else "")
          if ud["fartdaempere"] else "fartdaempere: []   # ingen fartdæmpere i config; tilføj dem, hvis der er nogen"),
    ]
    for x in ud["fartdaempere"]:
        L.append(f"  - {_v(x)}")
    L += [linje("hastighed_kmt", ud["hastighed_kmt"], "hastighedsgrænsen i km/t, tal uden enhed"),
          "",
          "# ---- herunder er tallene udfyldt fra analysen; ret dem ikke ----",
          linje("laengde_m", ud["laengde_m"]),
          linje("kort", ud["kort"]),
          linje("dage", ud["dage"]),
          "perioder:"]
    for k, v in ud["perioder"].items():
        L.append(f"  {k}: {_v(v)}")
    for felt in ("ture", "koeretid_s", "gnsfart_kmt", "laveste_fart_kmt", "maerkbar_opbremsning_pct", "maerkbar_acceleration_pct"):
        if felt in ud:
            L.append(linje(felt, ud[felt]))
    if ud.get("ekstra_tid_pr_element_s"):
        L.append("ekstra_tid_pr_element_s:   # uden standsning ved stop, gennemsnit pr. tur, interval (lav-hoej)")
        L += [f"  - {_v(x)}" for x in ud["ekstra_tid_pr_element_s"]]
    if ud.get("kryds_stykker"):
        L.append("kryds_stykker:   # median køretid pr. stykke (s), alle timer")
        L += [f"  - {_v(x)}" for x in ud["kryds_stykker"]]
    L += ["",
          "# ---- kort tekst ----",
          "forbehold:" + (f"   # {kom['forbehold']}" if kom.get("forbehold") else "   # fx ingen sammenligningsstrækning; flere ændringer på samme tid")]
    L += [f"  - {_v(x)}" for x in ud["forbehold"]]
    L += [linje("sammenligning_vejregler", UDFYLD, "målt fart ved fartdæmperen mod vejreglernes passagehastighed; skriv 'ikke sammenlignet', hvis I ikke har gjort det"),
          linje("vaerktoej", ud["vaerktoej"]),
          linje("opdateret", i_dag),
          linje("kontakt", UDFYLD, "dit GitHub-brugernavn (evt. 'Organisation (GitHub: brugernavn)'); ingen mail eller telefon"),
          ""]
    tekst = "\n".join(L)
    yaml.safe_load(tekst)   # skal kunne læses igen
    return tekst


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rapportdata", help="rapportdata.json fra lav_rapportdata_v1.2.py (strækning)")
    ap.add_argument("--straekning", help="strækningens id, hvis analysen har flere")
    ap.add_argument("--overblik", help="overblik.csv fra turtabel.py (kryds); kræver --config")
    ap.add_argument("--config", help="analysens config.yaml (kun ved --overblik)")
    ap.add_argument("--out", required=True, help="konklusionsfilen, der skal udfyldes (fx resultat\\konklusion.yaml)")
    ap.add_argument("--overskriv", action="store_true", help="overskriv en eksisterende fil")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if bool(a.rapportdata) == bool(a.overblik):
        raise SystemExit("Angiv enten --rapportdata (strækning) eller --overblik med --config (kryds)")
    if a.rapportdata:
        doc = json.loads(Path(a.rapportdata).read_text(encoding="utf-8"))
        ud, kom = fra_rapportdata(doc, a.straekning)
    else:
        if not a.config:
            raise SystemExit("--overblik kræver --config (punkter, perioder og distances)")
        with open(a.overblik, encoding="utf-8-sig", newline="") as f:
            rk = list(csv.DictReader(f, delimiter=";"))
        cfg = yaml.safe_load(Path(a.config).read_text(encoding="utf-8"))
        ud, kom = fra_overblik(rk, cfg)
    out = Path(a.out)
    if out.exists() and not a.overskriv:
        raise SystemExit(f"{out} findes allerede (måske med dine udfyldte felter). Slet eller omdøb den for at lave den igen (eller brug --overskriv).")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(skriv_yaml(ud, kom), encoding="utf-8")
    print(f"Skrev {out}. Udfyld felterne med UDFYLD, og tilføj filen med lav_konklusioner_html.py --tilfoej.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
