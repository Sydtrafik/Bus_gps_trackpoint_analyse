"""Laver de nationale analysekonklusioner (HTML og Markdown) ud fra alle filer i analyser\\.

Functionality: hver afsluttet analyse er én YAML-fil i analyser\\ (lavet med lav_konklusion.py og udfyldt af
brugeren). Scriptet tjekker alle filerne (påkrævede felter, gyldig type, tal som tal, ingen "UDFYLD", ingen mail)
og skriver to filer i værktøjsmappens rod:
  - nationale_analysekonklusioner.html: graf over strækningens længde og ændringen i køretid, én sortérbar og
    filtrérbar tabel med mini-tegning af fartdæmperen, og et kort pr. analyse. Selvstændig fil (tegningerne er
    indlejret), kan åbnes direkte i en browser.
  - nationale_analysekonklusioner.md: samme tal som tabel, så GitHub viser en læsbar oversigt.
Begge filer laves; ret dem aldrig i hånden.
Uses: pyyaml (som resten af værktøjet). Ingen beregning ud over forskelle (efter minus før, pr. 100 m).
    python program\\lav_konklusioner_html.py                       # analyser\\ -> rodens .html og .md
    python program\\lav_konklusioner_html.py --tilfoej <konklusion.yaml>   # tjek, kopiér til analyser\\, lav begge
    python program\\lav_konklusioner_html.py --tjek                 # tjek kun filerne (bruges af testene)
Debugging points: fejl i en fil stopper kørslen med fil og felt i beskeden. Tegningen findes ud fra
fartdaempere[].type (fx "sinusbump", "cirkelbump"); typer uden tegning vises som tekst.
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
    "vejtype": ("tekst", False), "linjer": ("tekst", False), "bustype": ("tekst", False),
    "kort": ("url", False), "laengde_m": ("tal", False), "aendring": ("tekst", False),
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
            f("skal være en liste (- {type: sinusbump, antal: 2})")
            return
        for x in v:
            if not isinstance(x, dict) or not isinstance(x.get("type"), str) or not isinstance(x.get("antal"), int):
                f("skal have type (tekst) og antal (heltal) for hver fartdæmper")
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
def _per(d):
    return list(d["perioder"])


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
    L = d.get("laengde_m")
    fd = d.get("fartdaempere") or []
    return {
        "id": navn, "type": d["type"], "typeNavn": TYPER[d["type"]], "vej": str(d["vej"]), "by": str(d["by"]),
        "aar": d["aar"], "vejtype": str(d.get("vejtype") or ""), "laengde": L, "to": to,
        "hastighed": par("hastighed_kmt"), "koeretid": kt, "delta": delta,
        "delta100": round(delta / L * 100, 1) if delta is not None and L else None,
        "gnsfart": par("gnsfart_kmt"), "lavfart": par("laveste_fart_kmt"),
        "opbr": par("maerkbar_opbremsning_pct"), "acc": par("maerkbar_acceleration_pct"),
        "opbrPP": (round(par("maerkbar_opbremsning_pct")[1] - par("maerkbar_opbremsning_pct")[0], 1)
                   if to and None not in par("maerkbar_opbremsning_pct") else None),
        "ture": par("ture"), "bustype": str(d.get("bustype") or ""),
        "daempere": [{"type": str(x["type"]), "antal": x["antal"]} for x in fd],
    }


def _flertal(ord_, n):
    """indsnævring -> indsnævringer, chikane -> chikaner, hævet flade -> hævede flader; bump er det samme."""
    if n == 1:
        return ord_
    if ord_.endswith("ing"):
        return ord_ + "er"
    if ord_.endswith("e"):
        return ord_ + "r"
    return ord_


def daemper_tekst(fd):
    return ", ".join(f"{x['antal']} {_flertal(x['type'], x['antal'])}" for x in fd) or "ingen"


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
            return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")
    return None


def mini_tegning(navn, mappe):
    """Lille længdeprofil (kun profilen, ingen tekst) til tabellen; None hvis tegningen ikke har en profil."""
    p = Path(mappe) / f"{navn}.svg"
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


def byg_md(analyser, i_dag):
    r = [raekke(n, d) for n, d in analyser]
    ud = ["# Nationale analysekonklusioner", "",
          "Afsluttede trackpoint-analyser i hele landet, så vi kan lære af hinandens fund. "
          "Tallene er medianer på hverdage for ture **uden standsning ved stop**, begge retninger.", "",
          f"**Laves af** `program/lav_konklusioner_html.py` ud fra filerne i [analyser/](analyser/) (én fil pr. analyse). "
          "Ret aldrig denne fil i hånden. Se tabellen med graf, filtre og tegninger i `nationale_analysekonklusioner.html`. "
          "Sådan tilføjer du din analyse: [CONTRIBUTING.md](CONTRIBUTING.md).", "",
          f"**Senest opdateret:** {i_dag} · {len(r)} analyse(r)", "",
          "| Vej, by | Type | År | Længde | Fartdæmpere | Hastighed (km/t) | Køretid (s) | Ændring | Pr. 100 m | "
          "Laveste fart ved fartdæmper (km/t) | Mærkbar opbremsning (%) | Ture |",
          "|---|---|---|--:|---|---|---|--:|--:|---|---|---|"]
    for x, (n, d) in zip(r, analyser):
        delta = (("+" if x["delta"] > 0 else "") + _f(x["delta"]) + " s") if x["delta"] is not None else "–"
        ud.append(f"| [{x['vej']}, {x['by']}](analyser/{n}.yaml) | {x['typeNavn']} | {x['aar']} | "
                  f"{_f(x['laengde'])} m | {daemper_tekst(x['daempere'])} | {_fe(x['hastighed'])} | {_fe(x['koeretid'])} | "
                  f"{delta} | {_f(x['delta100'], 1) if x['delta100'] is not None else '–'} | {_fe(x['lavfart'])} | "
                  f"{_fe(x['opbr'])} | {_fe(x['ture'])} |")
    if not r:
        ud.append("| Ingen analyser endnu. | | | | | | | | | | | |")
    ud += ["", "Ændring = køretid efter minus før. Pr. 100 m = ændringen delt med strækningens længde, så strækninger "
           "af forskellig længde kan sammenlignes. Laveste fart ved fartdæmper = median af den laveste fart pr. tur "
           "ved fartdæmperne (bump o.l.); tom, hvis analysen ikke har målt den.", ""]
    for x, (n, d) in zip(r, analyser):
        ud += [f"## {x['vej']}, {x['by']} ({x['aar']})", ""]
        if d.get("aendring"):
            ud.append(f"- **Ændring:** {d['aendring']}")
        per = d["perioder"]
        ud.append("- **Perioder:** " + "; ".join(
            f"{PERIODE_NAVN[k]} {per[k].get('fra')} til {per[k].get('til')}"
            + (f" ({per[k]['dage']} {d.get('dage') or 'dage'})" if per[k].get("dage") else "") for k in per))
        for felt, tekst in (("vejtype", "Vejtype"), ("linjer", "Linje(r)"), ("bustype", "Bustype")):
            if d.get(felt):
                ud.append(f"- **{tekst}:** {d[felt]}")
        if d.get("maerkbar_acceleration_pct"):
            ud.append(f"- **Mærkbar acceleration (% af turene):** {_fe(x['acc'])}")
        if d.get("gnsfart_kmt"):
            ud.append(f"- **Gennemsnitsfart (km/t):** {_fe(x['gnsfart'])}")
        if d.get("ekstra_tid_pr_element_s"):
            ud.append("- **Ekstra tid pr. element (s, interval, kan ikke lægges sammen):** " + "; ".join(
                f"{e['element']} {_f(e['lav'], 1)}–{_f(e['hoej'], 1)}" if e["lav"] != e["hoej"] else f"{e['element']} {_f(e['lav'], 1)}"
                for e in d["ekstra_tid_pr_element_s"]))
        for s in d.get("kryds_stykker") or []:
            ud.append(f"- **Stykke {s['stykke']}" + (f" (retning {s['retning']})" if s.get("retning") else "") + ":** "
                      + _fe([s.get("foer"), s.get("efter")] if _to(d) else [s.get("periode")], 0, " s"))
        if d.get("sammenligning_vejregler"):
            ud.append(f"- **Vejregler:** {d['sammenligning_vejregler']}")
        for fb in d.get("forbehold") or []:
            ud.append(f"- **Forbehold:** {fb}")
        if d.get("kort"):
            ud.append(f"- [Strækningen i Google Maps]({d['kort']})")
        ud.append(f"- **Kontakt:** {d['kontakt']} · opdateret {d['opdateret']}")
        ud.append("")
    return "\n".join(ud)


# ---------------------------------------------------------------- HTML
def byg_html(analyser, mappe, i_dag):
    rows, kort = [], []
    tegn, mini = {}, {}
    for n, d in analyser:
        x = raekke(n, d)
        navn, filer = (None, [])
        for fd in x["daempere"]:
            navn, filer = bumptype(fd["type"])
            if navn:
                break
        x["bumpNavn"] = navn or ""
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
        x["daemperTekst"] = daemper_tekst(x["daempere"])
        x["daemperTyper"] = sorted({fd["type"].lower() for fd in x["daempere"]}) or ["ingen"]
        x["kort"] = d.get("kort") or ""
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
    data = {"rows": rows, "mini": {k: v for k, v in mini.items() if v}, "tegn": {k: v for k, v in tegn.items() if v},
            "typer": TYPER}
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
<p class="meta">Medianer på hverdage for ture uden standsning ved stop, begge retninger. Laves af <code>program/lav_konklusioner_html.py</code> ud fra filerne i <code>analyser/</code>; senest opdateret __DATO__. Ret ikke denne fil.</p>
</header>
<main>
<section aria-labelledby="graf-titel">
<h2 id="graf-titel">Ændring i køretid efter strækningens længde</h2>
<div class="forklaring" id="graf-forklaring"></div>
<div id="graf" class="graf"></div>
<p class="note" id="graf-note"></p>
</section>
<section aria-labelledby="tabel-titel">
<h2 id="tabel-titel">Alle analyser</h2>
<div class="filtre" id="filtre"></div>
<p class="meta" id="taeller" aria-live="polite"></p>
<div class="tabelboks"><table id="tabel"><thead></thead><tbody></tbody></table></div>
<p class="note">Klik på en overskrift for at sortere og på en analyse for at se den. Ændring = efter minus før; pr. 100 m gør strækninger af forskellig længde sammenlignelige. Laveste fart ved fartdæmper = median af den laveste fart pr. tur ved fartdæmperne (bump o.l.). Tegningerne er vejreglernes standardprofil for typen, ikke opmålte bump.</p>
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
h1 { font-size:1.6rem; margin:.2em 0; } h2 { font-size:1.15rem; margin:1.2em 0 .4em; } h3 { font-size:1rem; margin:.2em 0; }
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
.tip { position:fixed; pointer-events:none; background:var(--fg); color:var(--bg); padding:4px 8px; border-radius:4px; font-size:.85rem; display:none; z-index:5; }
.filtre { display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin:8px 0; }
.filtre label { display:flex; flex-direction:column; font-size:.85rem; color:var(--muted); gap:2px; flex:0 1 180px; }
.filtre select { font:inherit; padding:6px 8px; border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--fg); width:100%; }
.tabelboks { overflow-x:auto; border:1px solid var(--line); border-radius:8px; }
table { border-collapse:collapse; width:100%; }
#tabel th, #tabel td { padding:7px 9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:middle; }
#tabel th { background:var(--head); cursor:pointer; user-select:none; font-size:.85rem; white-space:nowrap; }
#tabel th.tal, #tabel td.tal { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
#tabel th[aria-sort=ascending]::after { content:" ▲"; } #tabel th[aria-sort=descending]::after { content:" ▼"; }
#tabel tbody tr { cursor:pointer; } #tabel tbody tr:hover { background:var(--hover); }
#tabel td.navn { font-weight:600; min-width:150px; }
#tabel td:last-child { min-width:200px; }
.soejler .linje { display:flex; align-items:center; gap:6px; margin:1px 0; }
.fa { color:var(--foer); } .ef { color:var(--fg); font-weight:600; }
.mini { display:inline-block; width:56px; height:16px; color:var(--efter); vertical-align:middle; }
.mini svg { width:100%; height:100%; display:block; }
.daemper { display:flex; align-items:center; gap:6px; white-space:nowrap; }
.mark { display:inline-block; width:9px; height:9px; border-radius:50%; background:var(--c); margin-right:5px; }
.kort { border:1px solid var(--line); border-radius:10px; padding:16px; margin:16px 0; scroll-margin-top:12px; }
.kort.valgt { border-color:var(--accent); box-shadow:0 0 0 2px var(--accent); }
.kort .under { color:var(--muted); margin:0 0 10px; }
.felter { display:grid; grid-template-columns:repeat(auto-fill, minmax(150px, 1fr)); gap:8px; margin:10px 0; }
.felt { background:var(--panel); border-radius:8px; padding:8px 10px; }
.felt .l { font-size:.78rem; color:var(--muted); } .felt .v { font-size:1.15rem; font-weight:600; font-variant-numeric:tabular-nums; }
.felt .s { font-size:.8rem; color:var(--muted); }
.to { display:flex; flex-wrap:wrap; gap:16px; align-items:flex-start; }
.to > div { flex:1 1 300px; min-width:0; }
figure { margin:0; border:1px solid var(--line); border-radius:8px; padding:8px; max-width:520px; }
figure img { width:100%; height:auto; display:block; background:#fff; }
figcaption { font-size:.82rem; color:var(--muted); margin-top:4px; }
.soejler .r { display:grid; grid-template-columns:minmax(70px, 30%) 1fr; gap:6px; align-items:center; font-size:.85rem; margin:3px 0; }
.soejler .b { height:10px; border-radius:2px; } .soejler .bf { background:var(--foer); } .soejler .be { background:var(--efter); }
.soejler .t { color:var(--muted); font-size:.78rem; }
ul.fb { margin:.3em 0; padding-left:1.2em; }
.galleri-boks { margin:24px 0; } .galleri-boks summary { cursor:pointer; font-weight:600; }
.galleri { display:flex; flex-wrap:wrap; gap:12px; margin-top:12px; } .galleri figure { flex:1 1 280px; }
.spaend .v { font-variant-numeric:tabular-nums; white-space:nowrap; font-size:.85rem; min-width:6.5em; }
#tabel td:nth-child(2) { white-space:nowrap; }
ul.fb { margin:.3em 0; padding-left:1.2em; }
.knap { display:inline-block; padding:5px 10px; border:1px solid var(--accent); border-radius:6px; text-decoration:none; font-size:.9rem; }
@media (max-width:640px) { .filtre label { flex:1 1 140px; } h1 { font-size:1.35rem; } }
"""

JS = r"""
const R = D.rows, TYPENAVN = D.typer;
const fmt = (v, n = 0) => v == null ? '–' : (v === 0 ? 0 : v).toLocaleString('da-DK', {minimumFractionDigits: n, maximumFractionDigits: n}).replace('-', '−');
const sgn = (v, n = 0) => v == null ? '–' : (v > 0 ? '+' : '') + fmt(v, n);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const farve = (t) => `var(--t-${t})`;
const par = (p, n = 0, enh = '') => p.length === 2 ? (p[0] == null && p[1] == null ? '–' : `<span class="fa">${fmt(p[0], n)}</span> → <span class="ef">${fmt(p[1], n)}</span>${enh}`) : (p[0] == null ? '–' : `<span class="ef">${fmt(p[0], n)}</span>${enh}`);
const mini = (r) => r.mini ? `<span class="mini" title="${esc(r.bumpNavn)}">${D.mini[r.mini]}</span>` : '';

// ---------- kolonner: (overskrift, sorteringsværdi, celle, tal?)
const KOL = [
  ['Vej, by', (r) => r.vej + ' ' + r.by, (r) => `<td class="navn">${esc(r.vej)}, ${esc(r.by)}</td>`],
  ['Type', (r) => r.typeNavn, (r) => `<td><span class="mark" style="--c:${farve(r.type)}"></span>${esc(r.typeNavn)}</td>`],
  ['Fartdæmpere', (r) => r.daemperTekst, (r) => `<td><span class="daemper">${mini(r)}${esc(r.daemperTekst)}</span></td>`],
  ['År', (r) => r.aar, (r) => `<td class="tal">${r.aar}</td>`, 1],
  ['Længde (m)', (r) => r.laengde, (r) => `<td class="tal">${fmt(r.laengde)}</td>`, 1],
  ['Hastighed (km/t)', (r) => r.hastighed[r.hastighed.length - 1], (r) => `<td class="tal">${par(r.hastighed)}</td>`, 1],
  ['Køretid (s)', (r) => r.koeretid[r.koeretid.length - 1], (r) => `<td class="tal">${par(r.koeretid)}</td>`, 1],
  ['Ændring (s)', (r) => r.delta, (r) => `<td class="tal">${sgn(r.delta)}</td>`, 1],
  ['Pr. 100 m (s)', (r) => r.delta100, (r) => `<td class="tal">${sgn(r.delta100, 1)}</td>`, 1],
  ['Gns. fart (km/t)', (r) => r.gnsfart[r.gnsfart.length - 1], (r) => `<td class="tal">${par(r.gnsfart)}</td>`, 1],
  ['Laveste fart ved fartdæmper (km/t)', (r) => r.lavfart[r.lavfart.length - 1], (r) => `<td class="tal">${par(r.lavfart)}</td>`, 1],
  ['Mærkbar opbremsning (%)', (r) => r.opbr[r.opbr.length - 1], (r) => `<td class="tal">${par(r.opbr)}</td>`, 1],
  ['Ture', (r) => r.ture.reduce((a, b) => a + (b || 0), 0), (r) => `<td class="tal">${par(r.ture)}</td>`, 1],
  ['Bustype', (r) => r.bustype, (r) => `<td>${esc(r.bustype)}</td>`],
];
const FILTRE = [
  ['Type', (r) => [r.typeNavn]], ['By', (r) => [r.by]], ['Vejtype', (r) => [r.vejtype || 'ikke oplyst']],
  ['Fartdæmper', (r) => r.daemperTyper],
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

// ---------- graf: længde (x) mod ændring i køretid (y)
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
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Ændring i køretid mod strækningens længde, ét punkt pr. analyse">`;
  for (let v = 0; v <= xmax; v += tx) s += `<line class="akse" x1="${X(v)}" x2="${X(v)}" y1="${m.t}" y2="${H - m.b}" opacity=".5"/><text x="${X(v)}" y="${H - m.b + 16}" text-anchor="middle">${fmt(v)}</text>`;
  for (let v = Math.ceil(y0 / ty) * ty; v <= y1; v = Math.round((v + ty) * 1e6) / 1e6 || 0) s += `<line class="akse" x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}" opacity=".5"/><text x="${m.l - 6}" y="${Y(v) + 4}" text-anchor="end">${sgn(v)}</text>`;
  s += `<line class="nul" x1="${m.l}" x2="${W - m.r}" y1="${Y(0)}" y2="${Y(0)}"/>`;
  s += `<text x="${(m.l + W - m.r) / 2}" y="${H - 4}" text-anchor="middle">Strækningens længde (m)</text>`;
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

// ---------- kort pr. analyse
const felt = (l, v, s = '') => `<div class="felt"><div class="l">${l}</div><div class="v">${v}</div>${s ? `<div class="s">${s}</div>` : ''}</div>`;
function kortHtml(r) {
  const pn = {foer: 'før', efter: 'efter', periode: 'perioden'};
  const per = Object.entries(r.perioder).map(([k, p]) => `${pn[k]} ${esc(p.fra)} til ${esc(p.til)}${p.dage ? ` (${esc(p.dage)} ${esc(r.dageNavn)})` : ''}`).join('; ');
  let f = '';
  if (r.koeretid.some((v) => v != null)) f += felt('Køretid (s)', par(r.koeretid), r.delta != null ? `${sgn(r.delta)} s · ${sgn(r.delta100, 1)} s pr. 100 m` : '');
  if (r.lavfart.some((v) => v != null)) f += felt('Laveste fart ved fartdæmper (km/t)', par(r.lavfart));
  if (r.gnsfart.some((v) => v != null)) f += felt('Gennemsnitsfart (km/t)', par(r.gnsfart));
  if (r.opbr.some((v) => v != null)) f += felt('Mærkbar opbremsning (% af turene)', par(r.opbr), r.opbrPP != null ? `${sgn(r.opbrPP)} procentpoint` : '');
  if (r.acc.some((v) => v != null)) f += felt('Mærkbar acceleration (% af turene)', par(r.acc));
  if (r.hastighed.some((v) => v != null)) f += felt('Hastighedsgrænse (km/t)', par(r.hastighed));
  if (r.ture.some((v) => v != null)) f += felt('Ture', par(r.ture));
  let el = '';
  if (r.elementer.length) {
    const dele = r.elementer.filter((e) => e.lav !== e.hoej), hel = r.elementer.filter((e) => e.lav === e.hoej);
    const mx = Math.max(0.1, ...dele.map((e) => e.hoej)), mn = Math.min(0, ...dele.map((e) => e.lav));
    const P = (v) => (v - mn) / (mx - mn) * 100;
    el = `<h3>Ekstra tid pr. element (s)</h3><div class="soejler">${dele.map((e) => `<div class="r"><span>${esc(e.element)}</span><span class="spaend"><span class="spor"><span class="b be" style="margin-left:${P(e.lav)}%;width:${Math.max(1, P(e.hoej) - P(e.lav))}%"></span></span><span class="v">${fmt(e.lav, 1)} til ${fmt(e.hoej, 1)}</span></span></div>`).join('')}</div>`
      + `<p class="note">Interval pr. element (gennemsnit pr. tur); intervallerne kan ikke lægges sammen.${hel.map((e) => ` ${esc(e.element)}: ${sgn(e.lav, 1)} s.`).join('')}</p>`;
  }
  if (r.stykker.length) {
    const mx = Math.max(1, ...r.stykker.flatMap((s) => s.v.filter((v) => v != null)));
    el = `<h3>Køretid pr. stykke (s)${r.to ? ': <span class="fa">før</span> og <span class="ef">efter</span>' : ''}</h3><div class="soejler">` + r.stykker.map((s) => `<div class="r"><span>${esc(s.stykke)}${s.retning ? ` <span class="t">retn. ${esc(s.retning)}</span>` : ''}</span><span>` + s.v.map((v, i) => v == null ? '' : `<span class="linje"><span class="b ${s.v.length === 2 && i === 0 ? 'bf' : 'be'}" style="width:${v / mx * 80}%"></span><span class="t">${fmt(v)} s</span></span>`).join('') + '</span></div>').join('') + '</div>';
  }
  const tegn = r.tegning ? `<figure><img src="${D.tegn[r.tegning]}" alt="Standardprofil: ${esc(r.bumpNavn)}"><figcaption>${esc(r.bumpNavn)}: vejreglernes standardprofil, ikke opmålt</figcaption></figure>`
    : (r.bumpNavn ? `<p class="note">Ingen tegning af ${esc(r.bumpNavn.toLowerCase())}: typen findes ikke i vejreglernes bilag (vejledning/kilder/bumptyper).</p>` : '');
  return `<article class="kort" id="k-${esc(r.id)}"><h2><span class="mark" style="--c:${farve(r.type)}"></span>${esc(r.vej)}, ${esc(r.by)} (${r.aar})</h2>
<p class="under">${esc(r.typeNavn)} · ${esc(r.aendring || r.daemperTekst)}${r.laengde != null ? ` · ${fmt(r.laengde)} m` : ''}${r.linjer ? ` · linje ${esc(r.linjer)}` : ''}${r.vejtype ? ` · ${esc(r.vejtype)}` : ''}</p>
<div class="felter">${f}</div>
<div class="to"><div>${el}${r.vejregler ? `<h3>Vejregler</h3><p>${esc(r.vejregler)}</p>` : ''}${r.forbehold.length ? `<h3>Forbehold</h3><ul class="fb">${r.forbehold.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
<p class="note">Perioder: ${per}.${r.bustype ? ` Bustype: ${esc(r.bustype)}.` : ''}${r.vaerktoej ? ` Værktøj: ${esc(r.vaerktoej)}.` : ''}<br>Kontakt: ${esc(r.kontakt)} (GitHub) · opdateret ${esc(r.opdateret)}</p>
${/^https?:\/\//.test(r.kort) ? `<a class="knap" href="${esc(r.kort)}" target="_blank" rel="noopener">Strækningen i Google Maps</a>` : ''}</div>
<div>${tegn}</div></div></article>`;
}
function visKort(id) {
  document.querySelectorAll('.kort').forEach((k) => k.classList.toggle('valgt', k.id === 'k-' + id));
  const k = document.getElementById('k-' + id); if (k) k.scrollIntoView({behavior: 'smooth'});
}
function tegn() { tabel(); graf(); document.querySelectorAll('.kort').forEach((k) => { k.hidden = !synlig(R.find((r) => 'k-' + r.id === k.id)); }); }
document.getElementById('kort').innerHTML = R.map(kortHtml).join('');
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
    analyser = laes_analyser(a.analyser)
    if a.tjek:
        print(f"{len(analyser)} analyse(r) i {a.analyser}: alle i orden")
        return 0
    # nyeste "opdateret" (ikke dagens dato), så filerne kun ændrer sig, når en analyse gør
    i_dag = a.dato or max((str(d["opdateret"]) for _n, d in analyser), default="ingen analyser")
    ud = Path(a.out)
    ud.write_text(byg_html(analyser, a.bumptyper, i_dag), encoding="utf-8")
    ud.with_suffix(".md").write_text(byg_md(analyser, i_dag), encoding="utf-8")
    print(f"{ud} og {ud.with_suffix('.md').name} ({len(analyser)} analyse(r))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
