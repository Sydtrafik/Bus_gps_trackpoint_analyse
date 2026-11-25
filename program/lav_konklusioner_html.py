"""Laver de nationale analysekonklusioner (HTML og Markdown) ud fra alle filer i analyser\\.

Functionality: hver afsluttet analyse er én YAML-fil i analyser\\ (lavet med lav_konklusion.py og udfyldt af
brugeren). Scriptet tjekker alle filerne (påkrævede felter, gyldig type, tal som tal, ingen "UDFYLD", ingen mail)
og skriver to filer i værktøjsmappens rod:
  - nationale_analysekonklusioner.html: graf over strækningens længde og ændringen i køretid, én sortérbar og
    filtrérbar tabel med mini-tegning af fartdæmperen, og et kort pr. analyse. Selvstændig fil (tegningerne er
    indlejret), kan åbnes direkte i en browser.
  - nationale_analysekonklusioner.md: samme tal som tabel, så GitHub viser en læsbar oversigt.
Begge filer laves; ret dem aldrig i hånden.
Uses: pyyaml (som resten af værktøjet). Ingen beregning ud over forskelle (efter minus før).
    python program\\lav_konklusioner_html.py                       # analyser\\ -> rodens .html og .md
    python program\\lav_konklusioner_html.py --tilfoej <konklusion.yaml>   # tjek, kopiér til analyser\\, lav begge
    python program\\lav_konklusioner_html.py --tjek                 # tjek kun filerne (bruges af testene)
Debugging points: fejl i en fil stopper kørslen med fil og felt i beskeden. Tegningen findes ud fra
fartdaempere[].type (fx "modificeret cirkelbump", "cirkelbump"); typer uden tegning vises som tekst.
"""
import argparse
import base64
import datetime as dt
import html
import json
import re
import shutil
import sys
from pathlib import Path

import yaml

PROGRAM = Path(__file__).resolve().parent
ROD = PROGRAM.parent
ANALYSER = ROD / "analyser"
BUMPMAPPE = ROD / "vejledning" / "kilder" / "bumptyper"
SKEMA = 1
UDFYLD = "UDFYLD"

TYPER = {"foer_efter": "Før/efter", "en_periode": "Én periode", "kryds": "Kryds"}
PERIODER = {"foer_efter": [("foer", "efter")], "en_periode": [("periode",)], "kryds": [("foer", "efter"), ("periode",)]}
PERIODE_NAVN = {"foer": "før", "efter": "efter", "periode": "perioden"}

# Felter: navn -> (art, påkrævet). Art: tekst, heltal, tal, url, dato, tekstliste, pr_periode, perioder,
# fartdaempere, elementtid, kryds_stykker.
FELTER = {
    "skema": ("heltal", True), "type": ("tekst", True),
    "vej": ("tekst", True), "by": ("tekst", True), "aar": ("heltal", True),
    "vejtype": ("tekst", False), "omraade": ("tekst", False), "buslommer": ("janej", False),
    "parkering_paa_vejen": ("janej", False), "linjer": ("tekst", False), "bustype": ("tekst", False),
    "kort": ("url", False), "punkter": ("punkter", False), "laengde_m": ("tal", False), "aendring": ("tekst", False),
    "fartdaempere": ("fartdaempere", False),
    "hastighed_kmt": ("pr_periode", False), "dage": ("tekst", False), "perioder": ("perioder", True),
    "ture": ("pr_periode", False), "koeretid_s": ("pr_periode", False), "gnsfart_kmt": ("pr_periode", False),
    "laveste_fart_kmt": ("pr_periode", False), "maerkbar_opbremsning_pct": ("pr_periode", False),
    "maerkbar_acceleration_pct": ("pr_periode", False),
    "ekstra_tid_pr_element_s": ("elementtid", False), "kryds_stykker": ("kryds_stykker", False),
    "forbehold": ("tekstliste", False), "sammenligning_vejregler": ("tekst", False),
    "vaerktoej": ("tekst", False), "opdateret": ("dato", True), "kontakt": ("tekst", True),
}

# (søgeord i fartdaempere[].type, visningsnavn, tegninger). Længste/mest specifikke først.
BUMPTYPER = [
    ("trapezbump med modificerede ramper", "Trapezbump med modificerede ramper", ["trapezbump_mod_ramper_40"]),
    ("modificeret cirkelbump", "Modificeret cirkelbump", ["modificeret_cirkelbump_40"]),
    ("modificeret sinusbump", "Modificeret sinusbump", ["modificeret_sinusbump_50"]),
    ("sinusbump", "Sinusbump", []),        # ingen tegning: vejreglerne har kun modificeret sinusbump (50 km/t)
    ("cirkelbump", "Cirkelbump", ["cirkelbump_40"]),
    ("trapezbump", "Trapezbump", ["trapezbump_40"]),
    ("hævet flade", "Hævet flade", ["haevet_flade_40"]),
    ("pudebump", "Pudebump", ["pudebump_40"]),
    ("kuppelafrundet", "Kuppelafrundet bump", ["kuppelafrundet_40"]),
    ("pukkelbump", "Pukkelbump (ældre type)", ["pukkelbump_50_tvaersnit", "pukkelbump_50_plan"]),
    ("præfabrikeret", "Præfabrikeret bump", []),
]
# Mini-tegningen (længdeprofil) for typer, hvis egen tegning ikke er en længdeprofil: bilaget angiver pudebumpets
# længdeprofil som cirkelbump 40 km/t (vejledning\kilder\README.md).
MINI_PROFIL = {"pudebump_40": "cirkelbump_40", "pukkelbump_50_plan": "pukkelbump_50_tvaersnit"}
JANEJ = ("ja", "nej", "ukendt")


class FilFejl(Exception):
    pass


# ---------------------------------------------------------------- indlæsning og tjek
def _er_tal(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _tjek_felt(navn, art, v, perioder, fejl):
    def f(tekst):
        fejl.append(f"'{navn}' {tekst}")
    if v is None or (isinstance(v, str) and UDFYLD in v):   # UDFYLD meldes for sig
        return
    if art == "tekst":
        if not isinstance(v, (str, int, float)) or isinstance(v, bool):
            f("skal være en tekst")
    elif art == "heltal":
        if not isinstance(v, int) or isinstance(v, bool):
            f(f"skal være et heltal (står: {v!r})")
    elif art == "tal":
        if not _er_tal(v):
            f(f"skal være et tal uden anførselstegn og enhed (står: {v!r})")
    elif art == "url":
        if not isinstance(v, str) or not re.match(r"^https?://", v):
            f("skal være et link, der starter med https://")
    elif art == "dato":
        if not (isinstance(v, dt.date) or (isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v))):
            f(f"skal være en dato som ÅÅÅÅ-MM-DD (står: {v!r})")
    elif art == "tekstliste":
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            f("skal være en liste af korte tekster (- tekst)")
    elif art == "pr_periode":
        if not isinstance(v, dict):
            f(f"skal have en værdi pr. periode ({', '.join(perioder)})")
            return
        for k, x in v.items():
            if k not in perioder:
                f(f"har perioden '{k}'; typen bruger {', '.join(perioder)}")
            elif x is not None and x != UDFYLD and not _er_tal(x):
                f(f"{k} skal være et tal uden anførselstegn og enhed (står: {x!r})")
    elif art == "perioder":
        if not isinstance(v, dict) or set(v) != set(perioder):
            f(f"skal have præcis perioderne {', '.join(perioder)}")
            return
        for k, x in v.items():
            if not isinstance(x, dict):
                f(f"{k} skal have fra, til og dage")
                continue
            for d in ("fra", "til"):
                _tjek_felt(f"perioder.{k}.{d}", "dato", x.get(d), perioder, fejl)
            if x.get("dage") is not None and not isinstance(x.get("dage"), int):
                f(f"{k}.dage skal være et heltal")
    elif art == "fartdaempere":
        if not isinstance(v, list):
            f("skal være en liste (- {type: modificeret cirkelbump, antal: 2})")
            return
        for x in v:
            if not isinstance(x, dict) or not isinstance(x.get("type"), str) or not isinstance(x.get("antal"), int):
                f("skal have type (tekst) og antal (heltal) for hver fartdæmper")
            elif set(x) - {"type", "antal", "antaget"}:
                f(f"ukendt nøgle {', '.join(sorted(set(x) - {'type', 'antal', 'antaget'}))} (kun type, antal og antaget)")
            elif not isinstance(x.get("antaget", False), bool):
                f("antaget skal være true eller false")
    elif art == "janej":
        if v not in JANEJ:
            f(f"skal være ja, nej eller ukendt (står: {v!r})")
    elif art == "punkter":
        if not isinstance(v, list):
            f("skal være en liste (- {navn: A, beskrivelse: ..., lat: 55.1, lon: 8.4})")
            return
        for x in v:
            if not isinstance(x, dict) or not isinstance(x.get("navn"), str) or not _er_tal(x.get("lat")) or not _er_tal(x.get("lon")):
                f("skal have navn (tekst), lat og lon (tal) for hvert punkt")
    elif art == "elementtid":
        if not isinstance(v, list):
            f("skal være en liste")
            return
        for x in v:
            if not isinstance(x, dict) or not isinstance(x.get("element"), str) or not _er_tal(x.get("lav")) or not _er_tal(x.get("hoej")):
                f("skal have element, lav og hoej (tal) for hver linje")
    elif art == "kryds_stykker":
        if not isinstance(v, list):
            f("skal være en liste")
            return
        for x in v:
            if not isinstance(x, dict) or not isinstance(x.get("stykke"), str):
                f("skal have stykke (tekst) for hver linje")
                continue
            for k in perioder:
                if x.get(k) is not None and not _er_tal(x.get(k)):
                    f(f"stykke {x.get('stykke')}: {k} skal være et tal")


def _find_udfyld(v, sti, ud):
    if isinstance(v, str) and UDFYLD in v:
        ud.append(sti)
    elif isinstance(v, dict):
        for k, x in v.items():
            _find_udfyld(x, f"{sti}.{k}", ud)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            _find_udfyld(x, f"{sti}[{i}]", ud)


def tjek_analyse(d):
    """Returnér en liste af fejl (tom = filen er i orden)."""
    if not isinstance(d, dict):
        return ["filen er ikke en YAML-ordbog (felt: værdi)"]
    fejl = []
    for k in d:
        if k not in FELTER:
            fejl.append(f"ukendt felt '{k}' (stavefejl? gyldige felter står i analyser\\README.md)")
    for k, (_art, paakraevet) in FELTER.items():
        if paakraevet and d.get(k) in (None, ""):
            fejl.append(f"'{k}' mangler")
    if d.get("skema") not in (None, SKEMA):
        fejl.append(f"'skema' skal være {SKEMA}")
    typ = d.get("type")
    if typ is not None and typ not in TYPER:
        fejl.append(f"'type' skal være foer_efter, en_periode eller kryds (står: {typ!r})")
        return fejl
    mulige = PERIODER.get(typ, [("foer", "efter")])
    pkeys = list(mulige[0])
    if isinstance(d.get("perioder"), dict):
        for m in mulige:
            if set(d["perioder"]) == set(m):
                pkeys = list(m)
    for k, (art, _p) in FELTER.items():
        if k in d:
            _tjek_felt(k, art, d[k], pkeys, fejl)
    udf = []
    _find_udfyld(d, "", udf)
    for s in udf:
        fejl.append(f"'{s.lstrip('.')}' er ikke udfyldt ({UDFYLD})")
    if "@" in str(d.get("kontakt", "")):
        fejl.append("'kontakt' må ikke have en mailadresse; skriv dit GitHub-brugernavn (filen er offentlig)")
    return fejl


def laes_fil(sti):
    try:
        d = yaml.safe_load(Path(sti).read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise FilFejl(f"{Path(sti).name}: kan ikke læses som YAML: {e}")
    fejl = tjek_analyse(d)
    if fejl:
        raise FilFejl(f"{Path(sti).name}:\n  - " + "\n  - ".join(fejl))
    return d


def laes_analyser(mappe=ANALYSER):
    """Alle *.yaml i mappen (sorteret). Stopper med alle fejl samlet, hvis én eller flere filer er forkerte."""
    filer = sorted(Path(mappe).glob("*.yaml"))
    ud, fejl = [], []
    for p in filer:
        try:
            ud.append((p.stem, laes_fil(p)))
        except FilFejl as e:
            fejl.append(str(e))
    if fejl:
        raise SystemExit("Fejl i analyser:\n" + "\n".join(fejl))
    return ud


def filnavn(d):
    def slug(s):
        s = str(s).lower().replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
        return re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return f"{slug(d['vej'])}_{slug(d['by'])}_{d['aar']}.yaml"


# ---------------------------------------------------------------- udledte tal
def _to(d):
    return set(d["perioder"]) == {"foer", "efter"}


def raekke(navn, d):
    """Én tabelrække med udledte tal (bruges af både HTML og Markdown)."""
    to = _to(d)

    def par(felt):
        v = d.get(felt) or {}
        return [v.get("foer"), v.get("efter")] if to else [v.get("periode")]
    kt = par("koeretid_s")
    delta = (kt[1] - kt[0]) if to and None not in kt else None
    fd = d.get("fartdaempere") or []
    return {
        "id": navn, "type": d["type"], "typeNavn": TYPER[d["type"]], "vej": str(d["vej"]), "by": str(d["by"]),
        "aar": d["aar"], "laengde": d.get("laengde_m"), "to": to,
        "hastighed": par("hastighed_kmt"), "koeretid": kt, "delta": delta,
        "gnsfart": par("gnsfart_kmt"), "lavfart": par("laveste_fart_kmt"),
        "opbr": par("maerkbar_opbremsning_pct"), "acc": par("maerkbar_acceleration_pct"),
        "ture": par("ture"), "bustype": str(d.get("bustype") or ""),
        "vejtype": str(d.get("vejtype") or ""), "omraade": str(d.get("omraade") or ""),
        "buslommer": str(d.get("buslommer") or ""), "parkering": str(d.get("parkering_paa_vejen") or ""),
        "daempere": [{"type": str(x["type"]), "antal": x["antal"], "antaget": x.get("antaget", False)} for x in fd],
    }


def _flertal(ord_, n):
    """indsnævring -> indsnævringer, chikane -> chikaner; bump er det samme."""
    if n == 1:
        return ord_
    if ord_.endswith("ing"):
        return ord_ + "er"
    if ord_.endswith("e"):
        return ord_ + "r"
    return ord_


def daemper_tekst(fd):
    return ", ".join(f"{x['antal']} {_flertal(x['type'], x['antal'])}" + (" (antaget)" if x.get("antaget") else "")
                     for x in fd) or "ingen"


def bumptype(tekst):
    t = tekst.lower()
    for ord_, navn, filer in BUMPTYPER:
        if ord_ in t:
            return navn, filer
    return None, []


# ---------------------------------------------------------------- tegninger
def tegning(navn, mappe):
    """SVG (foretrækkes) eller PNG som data-URI; None hvis filen mangler."""
    for ext, mime in (("svg", "image/svg+xml"), ("png", "image/png")):
        p = Path(mappe) / f"{navn}.{ext}"
        if p.exists():
            b = p.read_bytes().replace(b"\r\n", b"\n") if ext == "svg" else p.read_bytes()   # samme bytes ved CRLF- og LF-checkout
            return f"data:{mime};base64," + base64.b64encode(b).decode("ascii")
    return None


def mini_tegning(navn, mappe):
    """Lille længdeprofil (kun profilen, ingen tekst) til tabellen; None hvis der ikke findes en profil."""
    p = Path(mappe) / f"{MINI_PROFIL.get(navn, navn)}.svg"
    if not p.exists():
        return None
    s = p.read_text(encoding="utf-8")
    rect = re.search(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" fill="#e9e9e9"', s)
    poly = re.search(r'<polygon points="([^"]+)"', s)
    if not rect or not poly:
        return None
    x, y, w, h = (float(v) for v in rect.groups())
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:g} {y + h * 0.35:g} {w:g} {h * 0.65:g}" '
            f'preserveAspectRatio="none" aria-hidden="true"><polygon points="{poly.group(1)}" fill="currentColor"/></svg>')


# Lille plantegning til fartdæmpere uden længdeprofil (vejen set ovenfra)
MINI_INDSNAEVRING = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 56 16" aria-hidden="true">'
                     '<path d="M0 2 H18 L24 6 H32 L38 2 H56 M0 14 H18 L24 10 H32 L38 14 H56" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>')


# ---------------------------------------------------------------- Markdown
def _f(v, n=0):
    if v is None:
        return "–"
    s = f"{v:,.{n}f}".replace(",", "_").replace(".", ",").replace("_", ".")   # dansk: 4.095 og 1,9
    return s.replace("-", "−")


def _fe(par, n=0, enhed=""):
    if len(par) == 2:
        return f"{_f(par[0], n)} → {_f(par[1], n)}{enhed}" if any(v is not None for v in par) else "–"
    return f"{_f(par[0], n)}{enhed}" if par[0] is not None else "–"


def _punkt_tekst(p):
    return f"{p['navn']}" + (f" ({p['beskrivelse']})" if p.get("beskrivelse") else "")


def byg_md(analyser, i_dag):
    r = [raekke(n, d) for n, d in analyser]
    ud = ["# Nationale analysekonklusioner", "",
          "Afsluttede trackpoint-analyser i hele landet, så vi kan lære af hinandens fund.", "",
          "- **Tallene** er medianer. Strækninger: hverdage, ture uden standsning ved stop, begge retninger. Kryds: retningen med flest ture.",
          "- **Ændring** er køretid efter minus før.",
          "- **Laveste fart ved fartdæmper** er medianen af den laveste fart pr. tur ved hver fartdæmper (bump o.l.), gennemsnit over fartdæmperne.",
          "- **Graf, filtre og tegninger** står i `nationale_analysekonklusioner.html` (åbn den i en browser).",
          "- **Filen laves** af `program/lav_konklusioner_html.py` ud fra [analyser/](analyser/) (én fil pr. analyse); "
          "ret den ikke i hånden. Sådan tilføjer du din analyse: [CONTRIBUTING.md](CONTRIBUTING.md).", "",
          f"**Senest opdateret:** {i_dag} · {len(r)} analyse(r)", "",
          "| Vej, by | Type | År | Målt strækning | Fartdæmpere | Hastighedsgrænse (km/t) | Køretid (s) | Ændring | "
          "Laveste fart ved fartdæmper (km/t) | Mærkbar opbremsning (%) | Mærkbar acceleration (%) | Ture målt |",
          "|---|---|---|--:|---|---|---|--:|---|---|---|---|"]
    for x, (n, d) in zip(r, analyser):
        delta = (("+" if x["delta"] > 0 else "") + _f(x["delta"]) + " s") if x["delta"] is not None else "–"
        ud.append(f"| [{x['vej']}, {x['by']}](analyser/{n}.yaml) | {x['typeNavn']} | {x['aar']} | "
                  f"{_f(x['laengde'])} m | {daemper_tekst(x['daempere'])} | {_fe(x['hastighed'])} | {_fe(x['koeretid'])} | "
                  f"{delta} | {_fe(x['lavfart'])} | {_fe(x['opbr'])} | {_fe(x['acc'])} | {_fe(x['ture'])} |")
    if not r:
        ud.append("| Ingen analyser endnu. | | | | | | | | | | | |")
    ud.append("")
    for x, (n, d) in zip(r, analyser):
        ud += [f"## {x['vej']}, {x['by']} ({x['aar']})", ""]
        if d.get("aendring"):
            ud.append(f"- **Ændring:** {d['aendring']}")
        vej = ", ".join(v for v in (x["vejtype"], x["omraade"]) if v)
        if vej:
            ud.append(f"- **Vej og område:** {vej}")
        if x["buslommer"] or x["parkering"]:
            ud.append(f"- **Buslommer:** {x['buslommer'] or 'ikke oplyst'} · **Parkering på vejen:** {x['parkering'] or 'ikke oplyst'}")
        for felt, tekst in (("linjer", "Linje(r)"), ("bustype", "Bustype")):
            if d.get(felt):
                ud.append(f"- **{tekst}:** {d[felt]}")
        per = d["perioder"]
        ud.append("- **Perioder:** " + "; ".join(
            f"{PERIODE_NAVN[k]} {per[k].get('fra')} til {per[k].get('til')}"
            + (f" ({per[k]['dage']} {d.get('dage') or 'dage'})" if per[k].get("dage") else "") for k in per))
        if d.get("gnsfart_kmt"):
            ud.append(f"- **Gennemsnitsfart (km/t):** {_fe(x['gnsfart'])}")
        if d.get("ekstra_tid_pr_element_s"):
            ud.append("- **Ekstra køretid pr. element (s pr. tur, mindst–højst; tallene overlapper og kan ikke lægges sammen):** " + "; ".join(
                f"{e['element']} {_f(e['lav'], 1)}–{_f(e['hoej'], 1)}" if e["lav"] != e["hoej"] else f"{e['element']} {_f(e['lav'], 1)}"
                for e in d["ekstra_tid_pr_element_s"]))
        if d.get("punkter"):
            ud.append("- **Punkter:** " + "; ".join(_punkt_tekst(p) for p in d["punkter"]))
        for s in d.get("kryds_stykker") or []:
            ud.append(f"- **Stykke {s['stykke']}" + (f" (retning {s['retning']})" if s.get("retning") else "") + ":** "
                      + _fe([s.get("foer"), s.get("efter")] if _to(d) else [s.get("periode")], 0, " s"))
        if d.get("sammenligning_vejregler"):
            ud.append(f"- **Vejregler:** {d['sammenligning_vejregler']}")
        for fb in d.get("forbehold") or []:
            ud.append(f"- **Forbehold:** {fb}")
        if d.get("kort"):
            ud.append(f"- **Kort:** [strækningen i Google Maps]({d['kort']})")
        ud.append(f"- **Kontakt:** {d['kontakt']} · opdateret {d['opdateret']}")
        ud.append("")
    return "\n".join(ud)


# ---------------------------------------------------------------- HTML
def laes_vejkort(kortmappe, navn):
    """Vejkortet fra lav_vejkort.py (analyser\\kort\\<navn>.json), eller None. En ødelagt fil stopper kørslen."""
    p = Path(kortmappe) / f"{navn}.json" if kortmappe else None
    if not p or not p.exists():
        return None
    try:
        k = json.loads(p.read_text(encoding="utf-8"))
        assert k.get("skema") == 1 and len(k["omraade"]) == 4 and all(isinstance(k[x], list) for x in ("veje", "bygninger", "detaljer"))
    except (ValueError, KeyError, TypeError, AssertionError):
        raise SystemExit(f"{p.name} er ikke et gyldigt vejkort. Slet den, og lav den igen: python program\\lav_vejkort.py analyser\\{navn}.yaml")
    return {x: k[x] for x in ("omraade", "enhed", "hentet", "veje", "bygninger", "detaljer")}


def byg_html(analyser, mappe, i_dag, kortmappe=None):
    rows = []
    tegn, mini = {}, {}
    for n, d in analyser:
        x = raekke(n, d)
        navn, filer = (None, [])
        for fd in x["daempere"]:
            navn, filer = bumptype(fd["type"])
            if navn:
                break
        x["bumpNavn"] = navn or ""
        x["bumpAntaget"] = bool(navn) and next((fd["antaget"] for fd in x["daempere"] if bumptype(fd["type"])[0] == navn), False)
        x["mini"] = None
        x["tegning"] = None
        for f in filer:
            if f not in mini:
                mini[f] = mini_tegning(f, mappe)
                tegn[f] = tegning(f, mappe)
            if mini[f] and not x["mini"]:
                x["mini"] = f
            if tegn[f] and not x["tegning"]:
                x["tegning"] = f
        if not x["mini"] and any(fd["type"].lower().startswith("indsnævring") for fd in x["daempere"]):
            x["mini"] = "indsnaevring"
        x["daemperTekst"] = daemper_tekst(x["daempere"])
        x["daemperTyper"] = sorted({fd["type"].lower() for fd in x["daempere"]}) or ["ingen"]
        x["kort"] = d.get("kort") or ""
        x["punkter"] = [{"navn": str(p["navn"]), "beskrivelse": str(p.get("beskrivelse") or ""), "lat": p["lat"], "lon": p["lon"]}
                        for p in (d.get("punkter") or [])]
        x["vejkort"] = laes_vejkort(kortmappe, n) if x["punkter"] else None
        x["aendring"] = str(d.get("aendring") or "")
        x["linjer"] = str(d.get("linjer") or "")
        x["perioder"] = {k: {kk: str(vv) for kk, vv in v.items()} for k, v in d["perioder"].items()}
        x["dageNavn"] = str(d.get("dage") or "dage")
        x["forbehold"] = list(d.get("forbehold") or [])
        x["vejregler"] = str(d.get("sammenligning_vejregler") or "")
        x["elementer"] = d.get("ekstra_tid_pr_element_s") or []
        x["stykker"] = [{"stykke": s["stykke"], "retning": str(s.get("retning") or ""),
                         "v": [s.get("foer"), s.get("efter")] if x["to"] else [s.get("periode")]}
                        for s in (d.get("kryds_stykker") or [])]
        x["kontakt"] = str(d["kontakt"])
        x["opdateret"] = str(d["opdateret"])
        x["vaerktoej"] = str(d.get("vaerktoej") or "")
        rows.append(x)
    mini_ud = {k: v for k, v in mini.items() if v}
    mini_ud["indsnaevring"] = MINI_INDSNAEVRING
    data = {"rows": rows, "mini": mini_ud, "tegn": {k: v for k, v in tegn.items() if v}, "typer": TYPER}
    js_data = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    alle = [("oversigt_laengdeprofiler", "Oversigt: længdeprofiler")] + [(f, n) for _o, n, fl in BUMPTYPER for f in fl]
    galleri = "".join(f'<figure><img src="{src}" alt="{html.escape(n)}" loading="lazy"><figcaption>{html.escape(n)}</figcaption></figure>'
                      for f, n in alle for src in [tegn.get(f) or tegning(f, mappe)] if src)
    return SKABELON.replace("__ANTAL__", str(len(rows))).replace("__DATO__", html.escape(i_dag)) \
        .replace("__GALLERI__", galleri).replace("__CSS__", CSS).replace("__JS__", JS).replace("__DATA__", js_data)


SKABELON = """<!doctype html>
<html lang="da"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nationale analysekonklusioner</title>
<style>__CSS__</style></head>
<body>
<header>
<h1>Nationale analysekonklusioner</h1>
<p class="lead">Hvad skete der med bussernes køretid, fart og komfort, da vejen blev ændret? Afsluttede trackpoint-analyser i hele landet: __ANTAL__ analyse(r).</p>
<p class="meta">Laves af <code>program/lav_konklusioner_html.py</code> ud fra filerne i <code>analyser/</code>; senest opdateret __DATO__. Ret ikke denne fil.</p>
</header>
<main>
<section aria-labelledby="graf-titel">
<h2 id="graf-titel">Ændring i køretid efter målt strækning</h2>
<div class="forklaring" id="graf-forklaring"></div>
<div id="graf" class="graf"></div>
<p class="note" id="graf-note"></p>
</section>
<section aria-labelledby="tabel-titel">
<h2 id="tabel-titel">Alle analyser</h2>
<div class="filtre" id="filtre"></div>
<p class="meta" id="taeller" aria-live="polite"></p>
<div class="tabelboks"><table id="tabel"><thead></thead><tbody></tbody></table></div>
<ul class="noter">
<li><strong>Tallene</strong> er medianer. Strækninger: hverdage, ture uden standsning ved stop, begge retninger. Kryds: retningen med flest ture.</li>
<li><strong>Ændring</strong> er køretid efter minus før.</li>
<li><strong>Laveste fart ved fartdæmper</strong> er medianen af den laveste fart pr. tur ved hver fartdæmper (bump o.l.), gennemsnit over fartdæmperne.</li>
<li><strong>Tegningerne</strong> er vejreglernes standardprofil for typen, ikke opmålte bump.</li>
<li><strong>Sådan bruges tabellen:</strong> klik på en overskrift for at sortere og på en analyse for at se den.</li>
</ul>
</section>
<section id="kort" aria-label="Analyserne"></section>
<details class="galleri-boks"><summary>Alle bumptyper: vejreglernes standardprofiler</summary>
<p class="note">Tegnet efter Vejdirektoratets håndbogsbilag (vejledning/kilder/README.md). Tallet efter navnet er hastigheden i km/t, profilen er tegnet til.</p>
<div class="galleri">__GALLERI__</div></details>
</main>
<script>const D = __DATA__;</script>
<script>__JS__</script>
</body></html>
"""

CSS = """
:root { --bg:#ffffff; --fg:#1d1d1f; --muted:#5f6368; --line:#d9dce1; --head:#f3f4f6; --panel:#f8f9fa;
  --foer:#8a8f98; --efter:#1f5fa8; --t-foer_efter:#1f5fa8; --t-en_periode:#6b5ca5; --t-kryds:#b45309; --hover:#eef4fb; --accent:#1f5fa8; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#16181c; --fg:#e8eaed; --muted:#a6abb3; --line:#363a42;
  --head:#20242a; --panel:#1c1f24; --foer:#9aa0a8; --efter:#7fb2ee; --t-foer_efter:#7fb2ee; --t-en_periode:#b3a6e6; --t-kryds:#f0a35e;
  --hover:#1f2a38; --accent:#7fb2ee; } }
:root[data-theme="dark"] { --bg:#16181c; --fg:#e8eaed; --muted:#a6abb3; --line:#363a42; --head:#20242a; --panel:#1c1f24;
  --foer:#9aa0a8; --efter:#7fb2ee; --t-foer_efter:#7fb2ee; --t-en_periode:#b3a6e6; --t-kryds:#f0a35e; --hover:#1f2a38; --accent:#7fb2ee; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }
header, main { max-width:1400px; margin:0 auto; padding:16px; }
main { padding-top:0; }
h1 { font-size:1.6rem; margin:.2em 0; } h2 { font-size:1.15rem; margin:1.2em 0 .4em; } h3 { font-size:1rem; margin:1em 0 .3em; }
.lead { font-size:1.05rem; margin:.3em 0; max-width:60em; }
.meta, .note { color:var(--muted); font-size:.88rem; max-width:70em; }
code { font-size:.9em; }
a { color:var(--accent); }
.graf { width:100%; max-width:900px; }
.graf svg { width:100%; height:auto; display:block; overflow:visible; }
.graf .akse { stroke:var(--line); } .graf text { fill:var(--muted); font-size:12px; }
.graf .nul { stroke:var(--muted); stroke-dasharray:3 3; }
.graf circle { stroke:var(--bg); stroke-width:2; cursor:pointer; }
.graf circle:hover, .graf circle:focus { stroke:var(--fg); outline:none; }
.forklaring { display:flex; flex-wrap:wrap; gap:14px; font-size:.88rem; color:var(--muted); margin-bottom:4px; }
.forklaring span::before { content:""; display:inline-block; width:10px; height:10px; border-radius:50%; background:var(--c); margin-right:5px; }
.tip { position:fixed; pointer-events:none; background:var(--fg); color:var(--bg); padding:4px 8px; border-radius:4px; font-size:.85rem; display:none; z-index:1000; }
.filtre { display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin:8px 0; }
.filtre label { display:flex; flex-direction:column; font-size:.85rem; color:var(--muted); gap:2px; flex:0 1 170px; }
.filtre select { font:inherit; padding:6px 8px; border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--fg); width:100%; }
.tabelboks { overflow-x:auto; border:1px solid var(--line); border-radius:8px; }
table { border-collapse:collapse; width:100%; }
#tabel th, #tabel td { padding:7px 9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:middle; }
#tabel th { background:var(--head); cursor:pointer; user-select:none; font-size:.85rem; }
#tabel th.tal, #tabel td.tal { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
#tabel th[aria-sort=ascending]::after { content:" ▲"; } #tabel th[aria-sort=descending]::after { content:" ▼"; }
#tabel tbody tr { cursor:pointer; } #tabel tbody tr:hover { background:var(--hover); }
#tabel td.navn { font-weight:600; min-width:150px; }
#tabel td:nth-child(2) { white-space:nowrap; }
#tabel td:last-child { min-width:180px; }
.noter { color:var(--muted); font-size:.88rem; margin:10px 0 0; padding-left:1.2em; max-width:70em; }
.noter li { margin:2px 0; } .noter strong { color:var(--fg); }
.fa { color:var(--foer); } .ef { color:var(--fg); font-weight:600; }
.mini { display:inline-block; width:56px; height:16px; color:var(--efter); vertical-align:middle; flex:none; }
.mini svg { width:100%; height:100%; display:block; }
.daemper { display:flex; align-items:center; gap:6px; min-width:250px; }
.mark { display:inline-block; width:9px; height:9px; border-radius:50%; background:var(--c); margin-right:5px; }
.kort { border:1px solid var(--line); border-radius:10px; padding:16px; margin:16px 0; scroll-margin-top:12px; }
.kort.valgt { border-color:var(--accent); box-shadow:0 0 0 2px var(--accent); }
.kort h2 { margin-top:0; }
.kort .under { color:var(--muted); margin:0 0 6px; }
.to { display:flex; flex-wrap:wrap; gap:24px; align-items:flex-start; }
.to > div { flex:1 1 320px; min-width:0; }
ul.fakta { margin:.3em 0; padding-left:1.2em; } ul.fakta li { margin:3px 0; } ul.fakta.note { margin-top:16px; }
figure { margin:0; border:1px solid var(--line); border-radius:8px; padding:8px; max-width:520px; }
figure img { width:100%; height:auto; display:block; background:#fff; }
figcaption { font-size:.82rem; color:var(--muted); margin-top:4px; }
.vk { --land:#f4f3ef; --bygn:#e2dfd8; --vej:#ffffff; --vkant:#c9c6bf; --sti:#b5b2aa; --bump:#c2410c; --stop:#0f766e; margin-bottom:8px; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .vk { --land:#1f2227; --bygn:#2b2f36; --vej:#3a3f47; --vkant:#2a2d33; --sti:#555b64; --bump:#f0a35e; --stop:#5eead4; } }
:root[data-theme="dark"] .vk { --land:#1f2227; --bygn:#2b2f36; --vej:#3a3f47; --vkant:#2a2d33; --sti:#555b64; --bump:#f0a35e; --stop:#5eead4; }
.vk-svg { width:100%; height:auto; display:block; border:1px solid var(--line); border-radius:8px; touch-action:none; cursor:grab;
  user-select:none; -webkit-user-select:none; --k:1; --ky:1; }
.vk-bg { fill:var(--land); } .vk-bygn { fill:var(--bygn); }
.vk-vej { fill:none; stroke-linecap:round; stroke-linejoin:round; stroke:var(--vej); }
.vk-k1 { stroke-width:9; filter:drop-shadow(0 0 1px var(--vkant)); } .vk-k2 { stroke-width:7; filter:drop-shadow(0 0 1px var(--vkant)); }
.vk-k3 { stroke-width:5.5; filter:drop-shadow(0 0 1px var(--vkant)); } .vk-k4 { stroke-width:3; }
.vk-k5 { stroke:var(--sti); stroke-width:1.2; stroke-dasharray:3 3; }
.vk-maalt { fill:none; stroke:var(--efter); stroke-width:3; stroke-linecap:round; stroke-linejoin:round; opacity:.6; vector-effect:non-scaling-stroke; }
.vk-vejnavn { font-size:calc(11px * var(--k)); fill:var(--muted); paint-order:stroke; stroke:var(--land); stroke-width:calc(3px * var(--k)); }
.vk-ende { fill:var(--efter); stroke:var(--bg); stroke-width:2; } .vk-elem { fill:var(--bg); stroke:var(--efter); stroke-width:2.5; }
.vk-lbg { fill:var(--bg); opacity:.85; } .vk-lbl { font-size:12px; fill:var(--fg); } .vk-lbl.fed { font-weight:600; }
.vk-svg.lille .vk-pkt:not(.vk-altid) .vk-lbg, .vk-svg.lille .vk-pkt:not(.vk-altid) .vk-lbl { display:none; }
.vk-detalje { display:none; } .vk-svg.zoomet .vk-detalje { display:inline; }
.vk-s-bump { fill:var(--bump); stroke:var(--bg); stroke-width:1; } .vk-s-kryds { fill:var(--bg); stroke:var(--fg); stroke-width:1.2; }
.vk-s-stop rect { fill:var(--stop); } .vk-s-stop path { fill:none; stroke:var(--bg); stroke-width:1.2; }
.vk-stopnavn { font-size:11px; fill:var(--stop); paint-order:stroke; stroke:var(--land); stroke-width:3px; }
.vk-skala path { fill:none; stroke:var(--fg); stroke-width:calc(1.5px * var(--ky)); }
.vk-skala text { font-size:calc(10px * var(--ky)); fill:var(--muted); paint-order:stroke; stroke:var(--land); stroke-width:calc(3px * var(--ky)); }
.vk-knapper { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-top:6px; }
.vk-knapper button { font:inherit; font-size:.9rem; min-width:34px; padding:3px 10px; border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--fg); cursor:pointer; }
.vk-tegn { display:flex; flex-wrap:wrap; gap:2px 12px; color:var(--muted); font-size:.82rem; margin-left:6px; }
.vk-tegn svg { width:13px; height:13px; vertical-align:-2px; margin-right:3px; }
.vk-kilde { color:var(--muted); font-size:.8rem; margin:4px 0 0; }
.tid { display:grid; grid-template-columns:minmax(110px, max-content) 7.5em 1fr; gap:4px 12px; align-items:center; font-size:.9rem; }
.tid .v { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.tid .spor { position:relative; height:10px; background:var(--head); border-radius:2px; }
.tid .spor span { position:absolute; top:0; bottom:0; background:var(--efter); }
.tid .spor .hoejst { opacity:.35; } .tid .spor .mindst { border-radius:2px 0 0 2px; }
.tid .hoved { font-size:.8rem; color:var(--muted); }
.tid .akse { display:flex; justify-content:space-between; font-size:.8rem; color:var(--muted); border-bottom:1px solid var(--line); }
.tidtotal { margin:.2rem 0 .5rem; }
.stykker { display:grid; grid-template-columns:minmax(90px, max-content) 1fr; gap:6px 12px; align-items:center; font-size:.9rem; }
.stykker .linje { display:flex; align-items:center; gap:6px; margin:1px 0; }
.stykker .b { height:10px; border-radius:2px; } .stykker .bf { background:var(--foer); } .stykker .be { background:var(--efter); }
.stykker .t { color:var(--muted); font-size:.8rem; white-space:nowrap; }
.knap { display:inline-block; padding:5px 10px; border:1px solid var(--accent); border-radius:6px; text-decoration:none; font-size:.9rem; }
.galleri-boks { margin:24px 0; } .galleri-boks summary { cursor:pointer; font-weight:600; }
.galleri { display:flex; flex-wrap:wrap; gap:12px; margin-top:12px; } .galleri figure { flex:1 1 280px; }
@media (max-width:640px) { .filtre label { flex:1 1 140px; } h1 { font-size:1.35rem; } .tid { grid-template-columns:1fr 7em; } .tid .spor, .tid .akse { grid-column:1 / -1; } .tid .hoved { display:none; } }
"""

JS = r"""
const R = D.rows, TYPENAVN = D.typer;
const fmt = (v, n = 0) => v == null ? '–' : (v === 0 ? 0 : v).toLocaleString('da-DK', {minimumFractionDigits: n, maximumFractionDigits: n}).replace('-', '−');
const sgn = (v, n = 0) => v == null ? '–' : (v > 0 ? '+' : '') + fmt(v, n);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const farve = (t) => `var(--t-${t})`;
const par = (p, n = 0, enh = '') => p.length === 2 ? (p[0] == null && p[1] == null ? '–' : `<span class="fa">${fmt(p[0], n)}</span> → <span class="ef">${fmt(p[1], n)}</span>${enh}`) : (p[0] == null ? '–' : `<span class="ef">${fmt(p[0], n)}</span>${enh}`);
const mini = (r) => r.mini ? `<span class="mini" title="${esc(r.bumpNavn || r.daemperTekst)}">${D.mini[r.mini]}</span>` : '<span class="mini"></span>';
const sidst = (p) => p[p.length - 1];

// ---------- kolonner: (overskrift, sorteringsværdi, celle, tal?)
const KOL = [
  ['Vej, by', (r) => r.vej + ' ' + r.by, (r) => `<td class="navn">${esc(r.vej)}, ${esc(r.by)}</td>`],
  ['Type', (r) => r.typeNavn, (r) => `<td><span class="mark" style="--c:${farve(r.type)}"></span>${esc(r.typeNavn)}</td>`],
  ['Fartdæmpere', (r) => r.daemperTekst, (r) => `<td><span class="daemper">${mini(r)}<span>${esc(r.daemperTekst)}</span></span></td>`],
  ['År', (r) => r.aar, (r) => `<td class="tal">${r.aar}</td>`, 1],
  ['Målt strækning (m)', (r) => r.laengde, (r) => `<td class="tal">${fmt(r.laengde)}</td>`, 1],
  ['Hastighedsgrænse (km/t)', (r) => sidst(r.hastighed), (r) => `<td class="tal">${par(r.hastighed)}</td>`, 1],
  ['Køretid (s)', (r) => sidst(r.koeretid), (r) => `<td class="tal">${par(r.koeretid)}</td>`, 1],
  ['Ændring (s)', (r) => r.delta, (r) => `<td class="tal">${sgn(r.delta)}</td>`, 1],
  ['Gns. fart (km/t)', (r) => sidst(r.gnsfart), (r) => `<td class="tal">${par(r.gnsfart)}</td>`, 1],
  ['Laveste fart ved fartdæmper (km/t)', (r) => sidst(r.lavfart), (r) => `<td class="tal">${par(r.lavfart)}</td>`, 1],
  ['Mærkbar opbremsning (%)', (r) => sidst(r.opbr), (r) => `<td class="tal">${par(r.opbr)}</td>`, 1],
  ['Mærkbar acceleration (%)', (r) => sidst(r.acc), (r) => `<td class="tal">${par(r.acc)}</td>`, 1],
  ['Ture målt', (r) => r.ture.reduce((a, b) => a + (b || 0), 0), (r) => `<td class="tal">${par(r.ture)}</td>`, 1],
  ['Bustype', (r) => r.bustype, (r) => `<td>${esc(r.bustype)}</td>`],
];
const ikke = (v) => v || 'ikke oplyst';
const FILTRE = [
  ['Type', (r) => [r.typeNavn]], ['By', (r) => [r.by]], ['Område', (r) => [ikke(r.omraade)]],
  ['Fartdæmper', (r) => r.daemperTyper], ['Buslommer', (r) => [ikke(r.buslommer)]], ['Parkering på vejen', (r) => [ikke(r.parkering)]],
];
const ST = {sort: 7, op: false, f: {}};

function byggFiltre() {
  const box = document.getElementById('filtre');
  box.innerHTML = FILTRE.map(([navn, fn], i) => {
    const v = [...new Set(R.flatMap(fn))].sort((a, b) => a.localeCompare(b, 'da'));
    return `<label>${navn}<select data-i="${i}"><option value="">Alle</option>${v.map((x) => `<option>${esc(x)}</option>`).join('')}</select></label>`;
  }).join('');
  box.querySelectorAll('select').forEach((s) => s.addEventListener('change', () => { ST.f[s.dataset.i] = s.value; tegn(); }));
}
const synlig = (r) => FILTRE.every(([, fn], i) => !ST.f[i] || fn(r).includes(ST.f[i]));

function tabel() {
  const th = KOL.map(([n, , , tal], i) => `<th scope="col" class="${tal ? 'tal' : ''}" data-i="${i}" tabindex="0"${ST.sort === i ? ` aria-sort="${ST.op ? 'ascending' : 'descending'}"` : ''}>${n}</th>`).join('');
  document.querySelector('#tabel thead').innerHTML = `<tr>${th}</tr>`;
  const [, key] = KOL[ST.sort];
  const rk = R.filter(synlig).sort((a, b) => {
    const x = key(a), y = key(b);
    if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;   // tomme altid sidst
    const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'da');
    return ST.op ? c : -c;
  });
  document.querySelector('#tabel tbody').innerHTML = rk.map((r) => `<tr data-id="${esc(r.id)}">${KOL.map(([, , celle]) => celle(r)).join('')}</tr>`).join('')
    || `<tr><td colspan="${KOL.length}">Ingen analyser passer til filtrene.</td></tr>`;
  document.getElementById('taeller').textContent = `${rk.length} af ${R.length} analyser`;
  document.querySelectorAll('#tabel th').forEach((h) => {
    const klik = () => { const i = +h.dataset.i; ST.op = ST.sort === i ? !ST.op : !KOL[i][3]; ST.sort = i; tabel(); };
    h.addEventListener('click', klik); h.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); klik(); } });
  });
  document.querySelectorAll('#tabel tbody tr[data-id]').forEach((tr) => tr.addEventListener('click', () => visKort(tr.dataset.id)));
}

// ---------- graf: målt strækning (x) mod ændring i køretid (y)
function graf() {
  const pk = R.filter((r) => synlig(r) && r.delta != null && r.laengde != null);
  const uden = R.filter((r) => synlig(r) && !(r.delta != null && r.laengde != null)).length;
  const typer = [...new Set(R.map((r) => r.type))];
  document.getElementById('graf-forklaring').innerHTML = typer.map((t) => `<span style="--c:${farve(t)}">${esc(TYPENAVN[t])}</span>`).join('');
  document.getElementById('graf-note').textContent = (pk.length ? 'Hold musen over et punkt for navnet, klik for at se analysen. ' : 'Ingen analyser med før og efter i udvalget. ')
    + (uden ? `${uden} analyse(r) har ingen før/efter-ændring (fx én periode) og vises kun i tabellen.` : '');
  const W = 640, H = 300, m = {l: 52, r: 16, t: 12, b: 40};
  const xs = pk.map((r) => r.laengde), ys = pk.map((r) => r.delta);
  const xmax = Math.max(100, ...xs) * 1.1, ymin = Math.min(0, ...ys), ymax = Math.max(1, ...ys);
  const yspan = (ymax - ymin) || 1, y0 = ymin - yspan * 0.1, y1 = ymax + yspan * 0.15;
  const X = (v) => m.l + v / xmax * (W - m.l - m.r), Y = (v) => H - m.b - (v - y0) / (y1 - y0) * (H - m.t - m.b);
  const trin = (span) => { const r = span / 5, p = 10 ** Math.floor(Math.log10(r)); return [1, 2, 5, 10].map((k) => k * p).find((k) => k >= r); };
  const tx = trin(xmax), ty = trin(y1 - y0);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Ændring i køretid mod målt strækning, ét punkt pr. analyse">`;
  for (let v = 0; v <= xmax; v += tx) s += `<line class="akse" x1="${X(v)}" x2="${X(v)}" y1="${m.t}" y2="${H - m.b}" opacity=".5"/><text x="${X(v)}" y="${H - m.b + 16}" text-anchor="middle">${fmt(v)}</text>`;
  for (let v = Math.ceil(y0 / ty) * ty; v <= y1; v = Math.round((v + ty) * 1e6) / 1e6 || 0) s += `<line class="akse" x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}" opacity=".5"/><text x="${m.l - 6}" y="${Y(v) + 4}" text-anchor="end">${sgn(v)}</text>`;
  s += `<line class="nul" x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}"/>`;
  s += `<text x="${(m.l + W - m.r) / 2}" y="${H - 4}" text-anchor="middle">Målt strækning (m)</text>`;
  s += `<text x="12" y="${(m.t + H - m.b) / 2}" text-anchor="middle" transform="rotate(-90 12 ${(m.t + H - m.b) / 2})">Ændring i køretid (s)</text>`;
  pk.forEach((r) => { s += `<circle cx="${X(r.laengde)}" cy="${Y(r.delta)}" r="7" fill="${farve(r.type)}" tabindex="0" data-id="${esc(r.id)}" data-tip="${esc(`${r.vej}, ${r.by} (${r.aar}): ${sgn(r.delta)} s på ${fmt(r.laengde)} m`)}"><title>${esc(`${r.vej}, ${r.by}`)}</title></circle>`; });
  s += '</svg>';
  const g = document.getElementById('graf'); g.innerHTML = s;
  let tip = document.querySelector('.tip'); if (!tip) { tip = document.createElement('div'); tip.className = 'tip'; document.body.appendChild(tip); }
  g.querySelectorAll('circle').forEach((c) => {
    c.addEventListener('mousemove', (e) => { tip.textContent = c.dataset.tip; tip.style.display = 'block'; tip.style.left = Math.min(e.clientX + 12, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (e.clientY + 12) + 'px'; });
    c.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
    c.addEventListener('click', () => visKort(c.dataset.id));
    c.addEventListener('keydown', (e) => { if (e.key === 'Enter') visKort(c.dataset.id); });
  });
}

// ---------- kort pr. analyse: det, tabellen ikke viser
const li = (l, v) => v ? `<li><strong>${l}:</strong> ${v}</li>` : '';
function tidHtml(r) {
  const dele = r.elementer.filter((e) => e.lav !== e.hoej), hel = r.elementer.find((e) => e.lav === e.hoej);
  const mx = Math.max(0.1, ...dele.map((e) => e.hoej)), mn = Math.min(0, ...dele.map((e) => e.lav));
  const P = (v) => (v - mn) / (mx - mn) * 100;
  // mørk = mindst (0 til lav), lys = måske (lav til høj)
  const bjaelke = (e) => (e.lav > 0 ? `<span class="mindst" style="left:${P(0)}%;width:${P(e.lav) - P(0)}%"></span>` : '')
    + `<span class="hoejst" style="left:${P(e.lav)}%;width:${Math.max(1, P(e.hoej) - P(e.lav))}%"></span>`;
  return `<h3>Hvor kom den ekstra køretid fra?</h3>`
    + (hel ? `<p class="tidtotal">${esc(hel.element)}: <strong>${sgn(hel.lav, 1)} s</strong> pr. tur. Sådan fordeler det sig:</p>` : '')
    + `<div class="tid"><span class="hoved"></span><span class="v hoved">mindst – højst</span><span class="akse"><span>${fmt(mn, 0)} s</span><span>${fmt(mx, 1)} s</span></span>`
    + dele.map((e) => `<span>${esc(e.element)}</span><span class="v">${fmt(e.lav, 1)} – ${fmt(e.hoej, 1)} s</span><span class="spor">${bjaelke(e)}</span>`).join('')
    + `</div><ul class="noter"><li><strong>Mørk del (mindst):</strong> ekstra tid ved elementet ud over, at bussen også kørte langsommere på resten af strækningen.</li>`
    + `<li><strong>Lys del (højst):</strong> al ekstra tid i zonen om elementet. Den sande værdi ligger et sted imellem.</li>`
    + `<li><strong>Tallene overlapper</strong> og kan derfor ikke lægges sammen til hele strækningens tal. Gennemsnit pr. tur uden standsning ved stop.</li></ul>`;
}
function stykkerHtml(r) {
  const navn = Object.fromEntries(r.punkter.map((p) => [p.navn, p.beskrivelse]));
  const mx = Math.max(1, ...r.stykker.flatMap((s) => s.v.filter((v) => v != null)));
  const pkt = r.punkter.length ? `<ul class="fakta">${r.punkter.map((p) => `<li><strong>${esc(p.navn)}:</strong> ${esc(p.beskrivelse || 'ikke beskrevet')}</li>`).join('')}</ul>` : '';
  return `<h3>Punkterne</h3>${pkt}<h3>Køretid pr. stykke (s)${r.to ? ': <span class="fa">før</span> og <span class="ef">efter</span>' : ''}</h3><div class="stykker">`
    + r.stykker.map((s) => `<span><strong>${esc(s.stykke)}</strong>${s.retning ? ` <span class="t">retning ${esc(s.retning)}</span>` : ''}</span><span>`
      + s.v.map((v, i) => v == null ? '' : `<span class="linje"><span class="b ${s.v.length === 2 && i === 0 ? 'bf' : 'be'}" style="width:${v / mx * 80}%"></span><span class="t">${fmt(v)} s</span></span>`).join('') + '</span>').join('')
    + '</div>' + (Object.keys(navn).length ? '' : '<p class="note">Punkternes navne står ikke i analysens fil.</p>');
}
function kortHtml(r, ri) {
  const pn = {foer: 'før', efter: 'efter', periode: 'perioden'};
  const per = Object.entries(r.perioder).map(([k, p]) => `${pn[k]} ${esc(p.fra)} til ${esc(p.til)}${p.dage ? ` (${esc(p.dage)} ${esc(r.dageNavn)})` : ''}`).join('; ');
  const vej = [r.vejtype, r.omraade].filter(Boolean).map(esc).join(', ');
  const fakta = `<ul class="fakta">${li('Vej og område', vej)}${li('Buslommer', esc(r.buslommer))}${li('Parkering på vejen', esc(r.parkering))}`
    + `${li('Fartdæmpere', esc(r.daemperTekst))}${li('Linje', esc(r.linjer))}${li('Perioder', per)}</ul>`;
  const tegn = r.tegning ? `<figure><img src="${D.tegn[r.tegning]}" alt="Standardprofil: ${esc(r.bumpNavn)}"><figcaption><strong>${esc(r.bumpNavn)}</strong>: vejreglernes standardprofil, ikke opmålt${r.bumpAntaget ? '. Typen er antaget' : ''}.</figcaption></figure>`
    : (r.bumpNavn ? `<p class="note">Ingen tegning af ${esc(r.bumpNavn.toLowerCase())}: typen findes ikke i vejreglernes bilag.</p>` : '');
  const kort = r.punkter.length ? vejkortHtml(r, ri) : '';
  const link = /^https?:\/\//.test(r.kort) ? `<a class="knap" href="${esc(r.kort)}" target="_blank" rel="noopener">Åbn i Google Maps</a>` : '';
  return `<article class="kort" id="k-${esc(r.id)}"><h2><span class="mark" style="--c:${farve(r.type)}"></span>${esc(r.vej)}, ${esc(r.by)} (${r.aar})</h2>
<p class="under">${esc(r.typeNavn)}${r.aendring ? ' · ' + esc(r.aendring) : ''}</p>
<div class="to"><div>${fakta}${r.elementer.length ? tidHtml(r) : ''}${r.stykker.length ? stykkerHtml(r) : ''}
${r.vejregler ? `<h3>Vejregler</h3><p>${esc(r.vejregler)}</p>` : ''}${r.forbehold.length ? `<h3>Forbehold</h3><ul class="fakta">${r.forbehold.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
<ul class="fakta note">${li('Bustype', esc(r.bustype))}${li('Værktøj', esc(r.vaerktoej))}${li('Kontakt', `${esc(r.kontakt)} · opdateret ${esc(r.opdateret)}`)}</ul></div>
<div>${kort}${link}${tegn ? `<div style="margin-top:12px">${tegn}</div>` : ''}</div></div></article>`;
}
// ---------- vejkort: SVG ud fra OSM-data i analyser/kort/ (ingen kortfliser, virker uden internet)
const VK_W = 640, VK_MARGIN = 140;
function vkOmraade(pk) {
  const la = pk.map((p) => p.lat), lo = pk.map((p) => p.lon), lat0 = la.reduce((a, b) => a + b, 0) / la.length;
  const kx = 111320 * Math.cos(lat0 * Math.PI / 180), ky = 110540;
  let s = Math.min(...la) - VK_MARGIN / ky, n = Math.max(...la) + VK_MARGIN / ky, w = Math.min(...lo) - VK_MARGIN / kx, e = Math.max(...lo) + VK_MARGIN / kx;
  const b = (e - w) * kx, h = (n - s) * ky;
  if (b < h * 1.6) { const x = (h * 1.6 - b) / 2 / kx; w -= x; e += x; }
  return [s, w, n, e];
}
function vejkortHtml(r, ri) {
  const vk = r.vejkort, [s, w, n, e] = vk ? vk.omraade : vkOmraade(r.punkter), en = vk ? vk.enhed : 1e-5;
  const kx = 111320 * Math.cos((s + n) / 2 * Math.PI / 180), ky = 110540, sk = VK_W / ((e - w) * kx), H = Math.round((n - s) * ky * sk);
  const X = (lon) => +((lon - w) * kx * sk).toFixed(1), Y = (lat) => +((n - lat) * ky * sk).toFixed(1);
  const U = (dy, dx) => [X(w + dx * en), Y(s + dy * en)];
  const linje = (f) => { const p = []; let y = 0, x = 0; for (let i = 0; i < f.length; i += 2) { y += f[i]; x += f[i + 1]; p.push(U(y, x)); } return p; };
  const d = (p) => 'M' + p.map(([x, y]) => `${x},${y}`).join(' L');
  let ind = `<rect class="vk-bg" width="${VK_W}" height="${H}"/>`;
  const navne = {}, kl = {1: [], 2: [], 3: [], 4: [], 5: []}, legende = new Set();
  if (vk) {
    ind += vk.bygninger.map((b) => `<path class="vk-bygn" d="${d(linje(b))}Z"/>`).join('');
    vk.veje.forEach(([k, navn, f]) => {
      const p = linje(f); kl[k].push(d(p));
      if (navn && k <= 3) {
        const l = p.slice(1).reduce((a, q, i) => a + Math.hypot(q[0] - p[i][0], q[1] - p[i][1]), 0);
        if (!navne[navn] || l > navne[navn][0]) navne[navn] = [l, p[p.length - 1][0] < p[0][0] ? p.slice().reverse() : p];
      }
    });
    [5, 4, 3, 2, 1].forEach((k) => { if (kl[k].length) ind += `<path class="vk-vej vk-k${k}" d="${kl[k].join(' ')}"/>`; });
  }
  const ps = r.punkter.map((p) => [X(p.lon), Y(p.lat)]);
  if (ps.length > 1) ind += `<path class="vk-maalt" d="${d(ps)}"/>`;
  Object.entries(navne).sort().forEach(([navn, [l, p]], i) => {
    if (l < navn.length * 6.5 + 20) return;
    ind += `<path id="vk${ri}-${i}" d="${d(p)}" fill="none"/><text class="vk-vejnavn" dy="-0.35em"><textPath href="#vk${ri}-${i}" startOffset="50%" text-anchor="middle">${esc(navn)}</textPath></text>`;
  });
  // fast skærmstørrelse: gruppen skaleres med 1/zoom i aktiverVejkort
  const fast = (x, y, indhold, kl2 = '', attr = '') => `<g class="vk-fast ${kl2}" data-x="${x}" data-y="${y}"${attr} transform="translate(${x} ${y})">${indhold}</g>`;
  const BUS = '<rect x="-6" y="-6" width="12" height="12" rx="2.5"/><path d="M-3.5,-3.5 h7 v6 h-7 Z M-3.5,0 h7 M-2,2.5 v2 M2,2.5 v2"/>';
  if (vk) {
    const stop = vk.detaljer.filter((x) => x[0] === 'stop').map(([, t, dy, dx]) => [t, ...U(dy, dx)]);
    vk.detaljer.forEach(([art, t, dy, dx]) => {
      const [x, y] = U(dy, dx); legende.add(art);
      if (art === 'bump') ind += fast(x, y, `<path class="vk-s-bump" d="M-5,3 L0,-5 L5,3 Z"><title>Fartdæmper i OSM: ${esc(t)}</title></path>`, 'vk-detalje');
      else if (art === 'kryds') ind += fast(x, y, '<rect class="vk-s-kryds" x="-4" y="-4" width="8" height="8" rx="1"><title>Fodgængerfelt (OSM)</title></rect>', 'vk-detalje');
      else {
        // navnet står på den side, der vender væk fra nærmeste andet stoppested (typisk det i modsat retning)
        const andre = stop.filter(([, x2, y2]) => x2 !== x || y2 !== y).map(([, x2, y2]) => [Math.hypot(x2 - x, y2 - y), x2]).sort((a, b) => a[0] - b[0]);
        const side = !andre.length || andre[0][1] <= x ? 1 : -1;
        ind += fast(x, y, `<g class="vk-s-stop">${BUS}<title>Stoppested: ${esc(t)} (OSM)</title></g>`
          + (t ? `<text class="vk-stopnavn" x="${9 * side}" y="3.5" text-anchor="${side === 1 ? 'start' : 'end'}">${esc(t)}</text>` : ''), 'vk-detalje');
      }
    });
  }
  // analysens punkter: navn til højre, ellers til venstre ved overlap
  const bokse = [];
  r.punkter.forEach((p, i) => {
    const [x, y] = ps[i], ende = r.type !== 'kryds' && (i === 0 || i === r.punkter.length - 1), tb = p.navn.length * 6.6 + 10;
    let b;
    for (const side of [1, -1]) {
      const lx = side === 1 ? x + 10 : x - 10 - tb; b = [lx, y - 9, lx + tb, y + 9];
      if (!bokse.some((q) => !(b[2] < q[0] || b[0] > q[2] || b[3] < q[1] || b[1] > q[3]))) break;
    }
    bokse.push(b);
    const rx = +(b[0] - x).toFixed(1);
    ind += fast(x, y,
      `<circle class="${ende || r.type === 'kryds' ? 'vk-ende' : 'vk-elem'}" r="${ende ? 6 : 4.5}"><title>${esc(p.beskrivelse || p.navn)}</title></circle>`
      + `<rect class="vk-lbg" x="${rx}" y="-9" width="${tb.toFixed(0)}" height="18" rx="3"/><text class="vk-lbl${ende ? ' fed' : ''}" x="${rx + 5}" y="4">${esc(p.navn)}</text>`,
      'vk-pkt' + (ende || r.type === 'kryds' ? ' vk-altid' : ''), ` data-rx="${rx}" data-tb="${tb.toFixed(0)}"`);
  });
  const LEG = {bump: ['<path class="vk-s-bump" d="M-5,3 L0,-5 L5,3 Z"/>', 'fartdæmper i OSM'], kryds: ['<rect class="vk-s-kryds" x="-4" y="-4" width="8" height="8" rx="1"/>', 'fodgængerfelt'],
    stop: [`<g class="vk-s-stop">${BUS}</g>`, 'stoppested']};
  const leg = ['bump', 'kryds', 'stop'].filter((a) => legende.has(a)).map((a) => `<span><svg viewBox="-7 -7 14 14" aria-hidden="true">${LEG[a][0]}</svg>${LEG[a][1]}</span>`).join('');
  return `<div class="vk" data-w="${VK_W}" data-h="${H}" data-sk="${sk}">`
    + `<svg class="vk-svg" viewBox="0 0 ${VK_W} ${H}" role="img" aria-label="Vejkort over analysens punkter"><svg class="vk-indre" x="0" y="0" width="${VK_W}" height="${H}" viewBox="0 0 ${VK_W} ${H}">${ind}</svg>`
    + `<g class="vk-skala"><path d=""/><text x="12" y="${H - 20}" text-anchor="middle"></text></g></svg>`
    + `<div class="vk-knapper"><button type="button" data-z="ind" aria-label="Zoom ind">+</button><button type="button" data-z="ud" aria-label="Zoom ud">−</button><button type="button" data-z="nul">Hele kortet</button>`
    + `<span class="vk-tegn">${leg}${leg ? '<span>(ved zoom)</span>' : ''}</span></div>`
    + `<p class="vk-kilde">${vk ? 'Kortdata © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>-bidragydere, hentet ' + esc(vk.hentet) + '. ' : 'Intet vejkort for denne analyse; kun punkterne. '}`
    + 'Træk for at flytte; zoom med knapperne, eller klik i kortet og brug musehjulet.</p></div>';
}
function aktiverVejkort(el) {
  const ydre = el.querySelector('.vk-svg'), indre = el.querySelector('.vk-indre'), W = +el.dataset.w, H = +el.dataset.h, SK = +el.dataset.sk;
  const faste = [...indre.querySelectorAll('.vk-fast')], pkter = [...indre.querySelectorAll('.vk-pkt')], skala = el.querySelector('.vk-skala path'), skt = el.querySelector('.vk-skala text');
  let v = {x: 0, y: 0, w: W, h: H};
  const saet = () => {
    v.w = Math.min(W, Math.max(W / 16, v.w)); v.h = v.w * H / W;
    v.x = Math.min(W - v.w, Math.max(0, v.x)); v.y = Math.min(H - v.h, Math.max(0, v.y));
    indre.setAttribute('viewBox', `${v.x} ${v.y} ${v.w} ${v.h}`);
    const bredde = ydre.getBoundingClientRect().width || W, k = v.w / bredde, ky = W / bredde;   // k: brugerenheder pr. skærm-pixel
    ydre.style.setProperty('--k', k); ydre.style.setProperty('--ky', ky);
    ydre.classList.toggle('zoomet', v.w / W < 0.5);
    ydre.classList.toggle('lille', k > 1.5);   // lille kort (mobil, hele kortet): kun navne ved enderne
    faste.forEach((g) => g.setAttribute('transform', `translate(${g.dataset.x} ${g.dataset.y}) scale(${k})`));
    // et navn, der ville stikke ud over kortets kant, flyttes til den anden side af punktet
    pkter.forEach((g) => {
      const x = +g.dataset.x, rx = +g.dataset.rx, tb = +g.dataset.tb, alt = rx >= 0 ? -10 - tb : 10;
      const ude = (r0) => x + r0 * k < v.x || x + (r0 + tb) * k > v.x + v.w;
      const brug = ude(rx) && !ude(alt) ? alt : rx;
      g.querySelector('.vk-lbg').setAttribute('x', brug); g.querySelector('.vk-lbl').setAttribute('x', brug + 5);
    });
    const pxPrM = SK * W / v.w / ky, m = [10, 20, 25, 50, 100, 200, 500, 1000].find((x) => x * pxPrM >= 50) || 1000, L = m * pxPrM * ky;
    skala.setAttribute('d', `M12,${H - 14} v-5 M12,${H - 14} h${L.toFixed(1)} v-5`);
    skt.setAttribute('x', (12 + L / 2).toFixed(1)); skt.textContent = `${m} m`;
  };
  const pkt = (cx, cy) => { const b = ydre.getBoundingClientRect(); return [v.x + (cx - b.left) / b.width * v.w, v.y + (cy - b.top) / b.height * v.h]; };
  const zoom = (f, px, py) => { const nw = Math.min(W, Math.max(W / 16, v.w * f)), q = nw / v.w; v.x = px - (px - v.x) * q; v.y = py - (py - v.y) * q; v.w = nw; saet(); };
  // musehjulet zoomer først, når man har klikket i kortet (ellers scroller siden som normalt)
  ydre.addEventListener('wheel', (e) => { if (!ydre.classList.contains('aktiv') && !e.ctrlKey) return; e.preventDefault(); const [px, py] = pkt(e.clientX, e.clientY); zoom(e.deltaY < 0 ? 0.8 : 1.25, px, py); }, {passive: false});
  ydre.addEventListener('mouseleave', () => ydre.classList.remove('aktiv'));
  const tryk = new Map();
  ydre.addEventListener('pointerdown', (e) => { e.preventDefault(); ydre.classList.add('aktiv'); ydre.setPointerCapture(e.pointerId); tryk.set(e.pointerId, [e.clientX, e.clientY]); });
  ydre.addEventListener('pointermove', (e) => {
    if (!tryk.has(e.pointerId)) return;
    const b = ydre.getBoundingClientRect(), gl = tryk.get(e.pointerId);
    if (tryk.size === 2) {
      const [a, c] = [...tryk.values()], d0 = Math.hypot(a[0] - c[0], a[1] - c[1]);
      tryk.set(e.pointerId, [e.clientX, e.clientY]);
      const [p, q] = [...tryk.values()], d1 = Math.hypot(p[0] - q[0], p[1] - q[1]);
      const [px, py] = pkt((p[0] + q[0]) / 2, (p[1] + q[1]) / 2); if (d1 > 0) zoom(d0 / d1, px, py); return;
    }
    v.x -= (e.clientX - gl[0]) / b.width * v.w; v.y -= (e.clientY - gl[1]) / b.height * v.h; saet();
    tryk.set(e.pointerId, [e.clientX, e.clientY]);
  });
  const slip = (e) => tryk.delete(e.pointerId);
  ydre.addEventListener('pointerup', slip); ydre.addEventListener('pointercancel', slip);
  el.querySelectorAll('.vk-knapper button').forEach((b) => b.addEventListener('click', () => {
    if (b.dataset.z === 'nul') { v = {x: 0, y: 0, w: W, h: H}; saet(); return; }
    zoom(b.dataset.z === 'ind' ? 0.7 : 1 / 0.7, v.x + v.w / 2, v.y + v.h / 2);
  }));
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(saet).observe(ydre);
  saet();
}
function visKort(id) {
  document.querySelectorAll('.kort').forEach((k) => k.classList.toggle('valgt', k.id === 'k-' + id));
  const k = document.getElementById('k-' + id); if (k) k.scrollIntoView({behavior: 'smooth'});
}
function tegn() {
  tabel(); graf();
  document.querySelectorAll('.kort').forEach((k) => { k.hidden = !synlig(R.find((r) => 'k-' + r.id === k.id)); });
}
document.getElementById('kort').innerHTML = R.map(kortHtml).join('');
document.querySelectorAll('.vk').forEach(aktiverVejkort);
byggFiltre(); tegn();
"""


# ---------------------------------------------------------------- kørsel
def tilfoej(kilde, mappe):
    """Tjek en udfyldt konklusion og kopiér den til analyser\\<vej>_<by>_<år>.yaml. Returnér stien."""
    d = laes_fil(kilde)
    maal = Path(mappe) / filnavn(d)
    if maal.exists() and maal.resolve() != Path(kilde).resolve():
        gammel = yaml.safe_load(maal.read_text(encoding="utf-8")) or {}
        if str(gammel.get("kontakt")) != str(d["kontakt"]):
            raise SystemExit(f"{maal.name} findes allerede med en anden kontakt ({gammel.get('kontakt')}). "
                             "Ret ikke andres analyser; giv din analyse et andet vejnavn, by eller år.")
    Path(mappe).mkdir(parents=True, exist_ok=True)
    if maal.resolve() != Path(kilde).resolve():
        shutil.copyfile(kilde, maal)
    return maal


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--analyser", default=str(ANALYSER), help="mappe med én YAML-fil pr. analyse")
    ap.add_argument("--out", default=str(ROD / "nationale_analysekonklusioner.html"), help="HTML-fil (.md skrives ved siden af)")
    ap.add_argument("--bumptyper", default=str(BUMPMAPPE), help="mappe med tegninger af bumptyper")
    ap.add_argument("--tilfoej", default=None, help="udfyldt konklusion (fra lav_konklusion.py), der kopieres til analyser\\")
    ap.add_argument("--tjek", action="store_true", help="tjek kun filerne i analyser\\, skriv intet")
    ap.add_argument("--uden-kort", action="store_true", help="hent ikke vejkort fra OpenStreetMap ved --tilfoej")
    ap.add_argument("--dato", default=None, help=argparse.SUPPRESS)   # fast dato i testene
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.tilfoej:
        try:
            maal = tilfoej(a.tilfoej, a.analyser)
        except FilFejl as e:
            raise SystemExit(f"Konklusionen kan ikke tilføjes. Ret filen, og kør igen:\n{e}")
        print(f"Tilføjet: {maal}")
        if not a.uden_kort:
            sys.path.insert(0, str(PROGRAM))
            import lav_vejkort
            try:
                k = lav_vejkort.lav(maal)
                print(f"Vejkort: {k}" if k else "Ingen punkter i filen, så intet vejkort.")
            except lav_vejkort.VejkortFejl as e:
                print(f"Advarsel: {e}\nOversigten laves uden vejkort for denne analyse.")
    analyser = laes_analyser(a.analyser)
    if a.tjek:
        print(f"{len(analyser)} analyse(r) i {a.analyser}: alle i orden")
        return 0
    # nyeste "opdateret" (ikke dagens dato), så filerne kun ændrer sig, når en analyse gør
    i_dag = a.dato or max((str(d["opdateret"]) for _n, d in analyser), default="ingen analyser")
    ud = Path(a.out)
    ud.write_text(byg_html(analyser, a.bumptyper, i_dag, Path(a.analyser) / "kort"), encoding="utf-8")
    ud.with_suffix(".md").write_text(byg_md(analyser, i_dag), encoding="utf-8")
    print(f"{ud} og {ud.with_suffix('.md').name} ({len(analyser)} analyse(r))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
