#!/usr/bin/env python3
"""
byg_rapport.py - bygger én selvstændig HTML-fil af skabelon.html + rapportdata.json.

    python byg_rapport.py --data ud/rapportdata.json --out ud/rapport.html

Filen indeholder alt (data, ECharts fra vendor/, og Leaflet hvis kort er slået til i config). Den kan sendes pr. mail
og åbnes i en browser uden internet (undtagen kortet, hvis det er slået til: kortfliser hentes fra OpenStreetMap).

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


def byg(data, skabelon_tekst, vendor=None):
    """Returnér HTML som tekst. data = rapportdata (dict)."""
    vendor = Path(vendor) if vendor else HERE / "vendor"
    t = skabelon_tekst
    for mark in ("{{TITEL}}", "__RAPPORTDATA__", "/*__ECHARTS__*/", "/*__LEAFLET_JS__*/", "/*__LEAFLET_CSS__*/"):
        if t.count(mark) != 1:
            raise SystemExit(f"Skabelonen skal indeholde præcis én '{mark}' (fandt {t.count(mark)})")
    titel = data["meta"].get("titel") or "Rapport"
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("<!--", "<\\!--")
    echarts = script_sikker(laes(vendor / "echarts.min.js"))
    kort = bool(data["meta"].get("kort", {}).get("aktiv"))
    leaflet_js = script_sikker(laes(vendor / "leaflet.min.js")) if kort else ""
    leaflet_css = laes(vendor / "leaflet.min.css") if kort else ""
    # Rækkefølge: data først (kan indeholde mærkerne som tekst, må ikke erstattes bagefter)
    t = t.replace("{{TITEL}}", html.escape(titel))
    t = t.replace("/*__LEAFLET_CSS__*/", leaflet_css)
    t = t.replace("/*__ECHARTS__*/", echarts)
    t = t.replace("/*__LEAFLET_JS__*/", leaflet_js)
    t = t.replace("__RAPPORTDATA__", js)
    return t


def advarsler(data):
    """Liste af advarsler om indhold, der bør ændres, før rapporten deles."""
    m = data.get("meta", {})
    ud = []
    titel = (m.get("titel") or "").strip()
    if not titel or titel.startswith("<Fundet i én sætning"):
        ud.append("Titlen er stadig standardtitlen (pladsholderen). Skriv fundet i én sætning i config (rapport.titel), "
                  "fx 'Køretiden steg X s samtidig med vejændringen'. Se formidling_og_grafik.md, afsnit 2.")
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
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    data = json.loads(laes(a.data))
    ut = byg(data, laes(a.skabelon or standard_skabelon(data)), a.vendor)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ut, encoding="utf-8")
    print(f"byg_rapport v{VERSION}: skrev {out} ({out.stat().st_size // 1024} kB)")
    for tekst in advarsler(data):
        print("ADVARSEL: " + tekst, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
