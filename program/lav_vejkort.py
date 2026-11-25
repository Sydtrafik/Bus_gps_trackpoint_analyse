#!/usr/bin/env python3
"""lav_vejkort.py - henter vejkortet til en analyse fra OpenStreetMap én gang og gemmer det i analyser\\kort\\.

    python program\\lav_vejkort.py analyser\\<analyse>.yaml               # hent, hvis kortet mangler
    python program\\lav_vejkort.py analyser\\<analyse>.yaml --overskriv   # hent igen (fx nye punkter)
    python program\\lav_vejkort.py --alle                                 # alle analyser uden kort

Kortet er veje, bygninger, fodgængerfelter, stoppesteder (med navn) og fartdæmpere, som OSM har dem, i et
område på ca. 140 m omkring analysens punkter. Det hentes med én forespørgsel til Overpass API og gemmes som
analyser\\kort\\<analysens filnavn>.json. lav_konklusioner_html.py tegner det som et SVG-kort uden kortfliser,
så oversigten virker uden internet. Der hentes ingen kortfliser (OSM's regler forbyder at gemme dem).
Licens: kortfilerne er OpenStreetMap-data under ODbL 1.0 (© OpenStreetMap-bidragydere), ikke MIT; se
THIRD_PARTY_NOTICES.md.
Uses: kun standardbiblioteket og pyyaml.
Debugging points: svarer Overpass 429 eller 5xx, prøves igen op til 3 gange med pause; derefter stopper scriptet
med en besked (oversigten virker stadig, bare uden vejkort for den analyse).
"""
import argparse
import datetime as dt
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

PROGRAM = Path(__file__).resolve().parent
ANALYSER = PROGRAM.parent / "analyser"
OVERPASS = "https://overpass-api.de/api/interpreter"
UA = "trackpoint_vaerktoej (+https://github.com/Sydtrafik/Bus_gps_trackpoint_analyse)"
MARGIN_M = 140
DECIMALER = 5          # ca. 1 m
KLASSE = {"motorway": 1, "trunk": 1, "primary": 1, "secondary": 1, "tertiary": 2, "residential": 3, "unclassified": 3,
          "living_street": 3, "service": 4, "track": 4, "footway": 5, "cycleway": 5, "path": 5, "pedestrian": 5, "steps": 5}


class VejkortFejl(Exception):
    pass


def _meter(lat0):
    return 111320 * math.cos(math.radians(lat0)), 110540


def omraade(punkter, margin_m=MARGIN_M):
    """(syd, vest, nord, øst) om punkterne + margin, mindst 16:10 i bredden."""
    lats, lons = [float(p["lat"]) for p in punkter], [float(p["lon"]) for p in punkter]
    kx, ky = _meter(sum(lats) / len(lats))
    s, n = min(lats) - margin_m / ky, max(lats) + margin_m / ky
    w, e = min(lons) - margin_m / kx, max(lons) + margin_m / kx
    bredde, hoejde = (e - w) * kx, (n - s) * ky
    if bredde < hoejde * 1.6:
        ekstra = (hoejde * 1.6 - bredde) / 2 / kx
        w, e = w - ekstra, e + ekstra
    return tuple(round(v, 6) for v in (s, w, n, e))


def hent(bbox, url=OVERPASS, forsoeg=3, aabn=urllib.request.urlopen, vent=time.sleep):
    """Én Overpass-forespørgsel; nye forsøg ved 429/5xx/netfejl. Returnerer OSM-JSON som dict."""
    bb = "({},{},{},{})".format(*bbox)
    q = (f"[out:json][timeout:25];(way[highway]{bb};way[building]{bb};node[traffic_calming]{bb};"
         f"node[highway=bus_stop]{bb};node[highway=crossing]{bb};);out geom;")
    sidste = None
    for i in range(forsoeg):
        req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode("utf-8"),
                                     headers={"User-Agent": UA})
        try:
            with aabn(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            sidste = f"HTTP {e.code}"
            if e.code not in (429, 502, 503, 504):
                break
            pause = 30 if e.code == 429 else 5 * (i + 1)
        except (urllib.error.URLError, TimeoutError) as e:
            sidste = f"ingen forbindelse ({getattr(e, 'reason', e)})"
            pause = 5 * (i + 1)
        if i < forsoeg - 1:
            vent(pause)
    raise VejkortFejl(f"Kunne ikke hente vejkortet fra Overpass ({sidste}). Prøv igen senere: "
                      f"python program\\lav_vejkort.py <analyse>.yaml")


def kompakt(osm, bbox, hentet=None):
    """Kun det, kortet tegner. Koordinater er heltal i 1/100000 grad (ca. 1 m): et punkt er [lat, lon] målt fra
    områdets sydvestlige hjørne; en linje er første punkt efterfulgt af forskellen til det forrige punkt
    (fladt: [lat0, lon0, dlat1, dlon1, ...]). veje: [klasse, navn, linje]; bygninger: [linje]; detaljer: [art, tekst, lat, lon]."""
    s0, w0 = bbox[0], bbox[1]
    f = 10 ** DECIMALER

    def pkt(lat, lon):
        return round((float(lat) - s0) * f), round((float(lon) - w0) * f)

    def linje(g):
        ud, fx, fy = [], 0, 0
        for p in g:
            y, x = pkt(p["lat"], p["lon"])
            ud += [y - fy, x - fx]
            fy, fx = y, x
        return ud

    veje, bygn, det = [], [], []
    for el in osm.get("elements", []):
        t = el.get("tags") or {}
        if el.get("type") == "node":
            if "traffic_calming" in t:
                det.append(["bump", str(t["traffic_calming"]), *pkt(el["lat"], el["lon"])])
            elif t.get("highway") == "bus_stop":
                navn = re.sub(r"\s*\([^)]*\)$", "", str(t.get("name") or ""))   # "Kvaglundvej v Lærkevej (Esbjerg)" -> uden by
                det.append(["stop", navn, *pkt(el["lat"], el["lon"])])
            elif t.get("highway") == "crossing":
                det.append(["kryds", "", *pkt(el["lat"], el["lon"])])
            continue
        g = el.get("geometry") or []
        if el.get("type") != "way" or len(g) < 2:
            continue
        flad = linje(g)
        if "building" in t:
            bygn.append(flad)
        elif "highway" in t:
            veje.append([KLASSE.get(t["highway"], 4), str(t.get("name") or ""), flad])
    return {"skema": 1, "omraade": list(bbox), "enhed": 1 / f, "hentet": hentet or dt.date.today().isoformat(),
            "kilde": "OpenStreetMap via Overpass API", "licens": "© OpenStreetMap-bidragydere, ODbL 1.0 (https://www.openstreetmap.org/copyright)",
            "veje": veje, "bygninger": bygn, "detaljer": det}


def kortfil(analyse):
    p = Path(analyse)
    return p.parent / "kort" / f"{p.stem}.json"


def daekker(kort, punkter):
    """True, hvis kortets område dækker alle punkter."""
    s, w, n, e = kort["omraade"]
    return all(s <= float(p["lat"]) <= n and w <= float(p["lon"]) <= e for p in punkter)


def lav(analyse, overskriv=False, hent_fn=hent):
    """Hent og gem kortet til én analyse. Returnerer stien, eller None hvis analysen ingen punkter har."""
    d = yaml.safe_load(Path(analyse).read_text(encoding="utf-8")) or {}
    punkter = [p for p in (d.get("punkter") or []) if isinstance(p, dict) and p.get("lat") is not None]
    if not punkter:
        return None
    return hent_til(punkter, kortfil(analyse), overskriv, hent_fn)


def hent_til(punkter, ud, overskriv=False, hent_fn=hent):
    """Hent kortet om punkterne ({lat, lon}) til filen ud, medmindre den findes og dækker punkterne. Returnerer ud.
    Bruges også af rapport/byg_rapport.py (rapport.kort: true -> vejkort.json ved rapportdata.json)."""
    ud = Path(ud)
    if ud.exists() and not overskriv:
        try:
            if daekker(json.loads(ud.read_text(encoding="utf-8")), punkter):
                return ud
        except (ValueError, KeyError, TypeError):
            pass                                   # ødelagt fil: hent igen
    bbox = omraade(punkter)
    k = kompakt(hent_fn(bbox), bbox)
    ud.parent.mkdir(parents=True, exist_ok=True)
    ud.write_text(json.dumps(k, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return ud


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("analyse", nargs="?", help="analysens YAML-fil i analyser\\")
    ap.add_argument("--alle", action="store_true", help="alle analyser i analyser\\, der mangler et kort")
    ap.add_argument("--overskriv", action="store_true", help="hent igen, selvom kortet findes")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    filer = sorted(ANALYSER.glob("*.yaml")) if a.alle else [Path(a.analyse)] if a.analyse else []
    if not filer:
        ap.error("angiv en analyse eller --alle")
    for f in filer:
        try:
            p = lav(f, overskriv=a.overskriv)
        except VejkortFejl as e:
            raise SystemExit(str(e))
        print(f"{f.name}: " + (f"vejkort i {p}" if p else "ingen punkter, intet vejkort"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
