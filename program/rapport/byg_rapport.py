#!/usr/bin/env python3
"""
byg_rapport.py - bygger én selvstændig HTML-fil af skabelon.html + rapportdata.json.

    python byg_rapport.py --data ud/rapportdata.json --out ud/rapport.html

Filen indeholder alt (data, ECharts fra vendor/ og, hvis kort er slået til i config, vejkortet). Den kan sendes pr. mail
og åbnes i en browser uden internet. Kortet (rapport.kort: true) tegnes som SVG med program/vejkort.js ud fra
OpenStreetMap-data, som hentes én gang (Overpass) til vejkort.json ved siden af rapportdata.json; der hentes ingen
kortfliser. --uden-kort springer hentningen over.

Farver og skrift ligger øverst i skabelonen som CSS-variabler (:root). Ret dem dér, og kør byg_rapport.py igen.
Skabelonen vælges efter datafilens version: rapportdata fra lav_rapportdata_v1.2.py (version 1.2) bruger
skabelon_v1.2.html (valg for dage, rute og time); ældre rapportdata (lav_rapportdata.py, v1.1) bruger skabelon.html.
Valgfrit: --skabelon <fil> hvis du har en tilpasset kopi af skabelonen.
"""
import argparse
import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROGRAM = HERE.parent
VERSION = "1.2"
VEJ_FELTER = {"vejtype": "vejtype", "hastighed": "hastighedsgrænse", "bumptype": "bumptype", "andre_foranstaltninger": "andre hastighedsforanstaltninger"}


def standard_skabelon(data):
    """skabelon_v1.2.html til rapportdata v1.2 og nyere, ellers skabelon.html (v1.1)."""
    try:
        ny = tuple(int(x) for x in str(data.get("version", "1.1")).split(".")[:2]) >= (1, 2)
    except ValueError:
        ny = False
    return HERE / ("skabelon_v1.2.html" if ny else "skabelon.html")


def laes(sti):
    return Path(sti).read_text(encoding="utf-8")


def script_sikker(js):
    """Gør en JS-fil sikker at lægge inde i <script>...</script>."""
    return js.replace("</script", "<\\/script").replace("<!--", "<\\!--")


def kort_punkter(data):
    """Alle punkter, kortet skal dække: strækningernes ender, elementer og stoppesteder."""
    ud = []
    for s in data["meta"].get("straekninger") or []:
        ud += [{"lat": la, "lon": lo} for la, lo in s.get("linje") or []]
        ud += [{"lat": x["lat"], "lon": x["lon"]} for x in (s.get("elementer") or []) + (s.get("stoppesteder") or []) if x.get("lat") is not None]
    return ud


def byg(data, skabelon_tekst, vendor=None, vejkort=None):
    """Returnér HTML som tekst. data = rapportdata (dict); vejkort = kortdata fra lav_vejkort.py (dict) eller None."""
    vendor = Path(vendor) if vendor else HERE / "vendor"
    t = skabelon_tekst
    gammel = "/*__LEAFLET_JS__*/" in t and "/*__VEJKORT_JS__*/" not in t
    if gammel:   # egen kopi af en skabelon fra før 1.10.0: Leaflet-kortet virker ikke længere (OSM blokerer fliser til lokale filer)
        print("ADVARSEL: skabelonen er fra før 1.10.0 og har Leaflet-kortet; kortet vises ikke. Kopiér skabelon_v1.2.html igen "
              "for at få vejkortet.", file=sys.stderr)
        t = t.replace("/*__LEAFLET_JS__*/", "/*__VEJKORT_JS__*/").replace("/*__LEAFLET_CSS__*/", "/*__VEJKORT_CSS__*/")
    for mark in ("{{TITEL}}", "__RAPPORTDATA__", "/*__ECHARTS__*/", "/*__VEJKORT_JS__*/", "/*__VEJKORT_CSS__*/"):
        if t.count(mark) != 1:
            raise SystemExit(f"Skabelonen skal indeholde præcis én '{mark}' (fandt {t.count(mark)})")
    titel = data["meta"].get("titel") or "Rapport"
    kort = bool(data["meta"].get("kort", {}).get("aktiv")) and not gammel
    if kort and vejkort:
        data = {**data, "meta": {**data["meta"], "kort": {**data["meta"]["kort"],
                "grund": {k: vejkort[k] for k in ("omraade", "enhed", "hentet", "veje", "bygninger", "detaljer")}}}}
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("<!--", "<\\!--")
    echarts = script_sikker(laes(vendor / "echarts.min.js"))
    vk_js = script_sikker(laes(PROGRAM / "vejkort.js")) if kort else ""
    vk_css = laes(PROGRAM / "vejkort.css") if kort else ""
    # Rækkefølge: data først (kan indeholde mærkerne som tekst, må ikke erstattes bagefter)
    t = t.replace("{{TITEL}}", html.escape(titel))
    t = t.replace("/*__VEJKORT_CSS__*/", vk_css)
    t = t.replace("/*__ECHARTS__*/", echarts)
    t = t.replace("/*__VEJKORT_JS__*/", vk_js)
    t = t.replace("__RAPPORTDATA__", js)
    return t


def hent_vejkort(data, datafil, hent=True):
    """rapport.kort: true -> vejkortet fra vejkort.json ved rapportdata.json; hentes én gang fra OpenStreetMap (Overpass).
    Returnerer kortdata eller None (kortet viser så kun punkterne)."""
    if not data["meta"].get("kort", {}).get("aktiv"):
        return None
    punkter = kort_punkter(data)
    if not punkter:
        return None
    sys.path.insert(0, str(PROGRAM))
    import lav_vejkort
    fil = Path(datafil).parent / "vejkort.json"
    try:
        if hent:
            lav_vejkort.hent_til(punkter, fil)
        return json.loads(fil.read_text(encoding="utf-8")) if fil.exists() else None
    except lav_vejkort.VejkortFejl as e:
        print(f"ADVARSEL: {e}\nRapporten laves med kortet uden veje (kun punkterne).", file=sys.stderr)
        return json.loads(fil.read_text(encoding="utf-8")) if fil.exists() else None


def advarsler(data):
    """Liste af advarsler om indhold, der bør ændres, før rapporten deles."""
    m = data.get("meta", {})
    ud = []
    titel = (m.get("titel") or "").strip()
    if not titel or titel.startswith("<Fundet i én sætning") or ("<" in titel and ">" in titel):
        ud.append("Titlen er stadig en pladsholder. Skriv i config (rapport.titel), hvad og hvor der er målt, fx 'Køretid og fart "
                  "på Kvaglundvej før og efter bump'. Et fund står først i titlen, når det er verificeret (formidling_og_grafik.md, afsnit 2).")
    if not m.get("forbehold"):
        ud.append("Ingen forbehold er skrevet (rapport.forbehold). Skriv fx om manglende dage eller om, at der ikke er en kontrolstrækning.")
    if "vej" in m:                      # rapportdata v1.2: "Om strækningen" viser vejens oplysninger fra config
        mangler = [t for k, t in VEJ_FELTER.items() if not (m.get("vej") or {}).get(k)]
        if mangler:
            ud.append(f"'Om strækningen' mangler: {', '.join(mangler)} (rapport.vej i config). Rapporten skriver 'ikke oplyst i config'.")
    return ud


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bygger rapporten (én HTML-fil) af skabelon + rapportdata.json.")
    ap.add_argument("--data", required=True, help="rapportdata.json fra lav_rapportdata.py")
    ap.add_argument("--out", required=True, help="HTML-fil der skrives")
    ap.add_argument("--skabelon", default=None, help="standard: efter datafilens version (skabelon_v1.2.html eller skabelon.html)")
    ap.add_argument("--vendor", default=str(HERE / "vendor"))
    ap.add_argument("--uden-kort", action="store_true", help="hent ikke vejkortet fra OpenStreetMap (bruger vejkort.json, hvis den findes)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    data = json.loads(laes(a.data))
    ut = byg(data, laes(a.skabelon or standard_skabelon(data)), a.vendor, hent_vejkort(data, a.data, hent=not a.uden_kort))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ut, encoding="utf-8")
    print(f"byg_rapport v{VERSION}: skrev {out} ({out.stat().st_size // 1024} kB)")
    for tekst in advarsler(data):
        print("ADVARSEL: " + tekst, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
