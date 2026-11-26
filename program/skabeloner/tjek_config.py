"""Tjekker en analyses config.yaml før kørsel og siger på dansk, hvad der er galt, hvor, og hvad man skal gøre.

Functionality: læser config.yaml (den nemme vej, men også gamle og fulde configs) og finder fejl, der ellers først
    viser sig midt i en lang kørsel: YAML-syntaks (med linjenummer), tabulatorer, dobbelte nøgler, ukendte nøgler
    og stavefejl (med forslag), pladsholder-koordinater, punkt- og distance-id'er der ikke findes, manglende eller
    tomme stop pr. retning, datoer i forkert format eller omvendt rækkefølge, manglende datafiler, elementer uden
    for strækningen, kryds-config med komfort-krav m.m. Fejl stopper kørslen (exit 1); advarsler gør ikke (exit 0).
    --trin stopnavne er mildere: pladsholder-punkter og -stop er kun advarsler, og kun data for periode A tjekkes.
Uses: kun standardbiblioteket og pyyaml. Kaldes af koer_analyse.bat før valg 1-4 og som valg 7.
Dependencies: ingen andre filer. stoppesteder_hafas.yaml i resultat\\ (fra forbered.py stopnavne) bruges, hvis den
    findes, til at tjekke stopnavnene mod data.
Debugging points: nøglesættet er samlet fra analyse_v2.2.py (DEFAULTS), komfort_v1.0.py (DEFAULTS), komfort_v1.1.py,
    zonetid.py, rapport\\lav_rapportdata_v1.2.py, byg_rapport.py og lav_kryds_rapport.py; tests\\test_tjek_config.py
    sammenligner det med programmernes DEFAULTS. Får et program en ny nøgle, så tilføj den her.
"""
import argparse
import datetime as dt
import difflib
import math
import re
import sys
from pathlib import Path

import yaml

EARTH_R = 6371000.0
PLADSHOLDER = (55.0, 8.0)
STANDARD_RADIUS_M = 30.0
STANDARD_KORRIDOR_M = 15.0
STOP_SIDEAFSTAND_M = 40.0          # som rapport\lav_rapportdata.py: et stop hører til strækningen inden for 40 m
CACHE = "resultat/stoppesteder_hafas.yaml"

# ------------------------------------------------------------------ nøglesættet
ANALYSE_PARAMS = {
    "buffer_rows", "speed_max_kmh", "speed_min_kmh", "stop_speed_kmh", "stand_still_dist_m", "max_match_distance_m",
    "speed_nearest_pings", "rising_count", "rising_min_dist_m", "min_rows_after_coarse_filter", "ping_prefix",
    "projection_value", "date_columns", "time_columns", "lat_range", "lon_range", "chunk_size",
    "max_trips_rows_per_trip", "summary_only_empty_log", "summary_exclude_flags", "quality_day_share", "percentiles",
    "export_segments"}
SEKTIONER = {"analysetype", "periods", "data", "points", "point_order", "distances", "stops", "komfort",
             "straekninger", "elementer", "udvalg", "zonetid", "rapport"}
TOP = SEKTIONER | ANALYSE_PARAMS
KOMFORT = {"fra", "til", "laengde_m", "korridor_margin_m", "korridor_sideafstand_m", "fuld_passage_margin_m", "max_hul_s",
           "gitter_s", "sg_vindue_s", "sg_orden", "kant", "taerskler_ms2", "haendelse_min_s", "stillestand_kmh", "std_ddof",
           "bump_vinduer"}
STRAEKNING = {"id", "navn", "fra", "til", "koretid_afstand", "elementer", "komfort", "retninger"}
ELEMENT = {"navn", "type", "lat", "lon", "radius_m"}
ELEMENT_TYPER = {"bump", "indsnævring", "indsnaevring", "andet"}
PUNKT = {"name", "lat", "lon"}
DISTANCE = {"name", "from", "to"}
STOP = {"start", "end"}
PERIODE = {"name", "start", "end"}
DATA_PERIODE = {"details_csv", "list_csv"}
UDVALG = {"dagtype", "helligdage"}
ZONETID = {"zonebredde_m", "foelsomhed_zonebredde_m"}
RAPPORT = {"titel", "undertitel", "emne", "straekning_tekst", "straekning_navn", "periode_navn", "afsender",
           "udtraekdato", "min_ture", "vej", "foer_navn", "efter_navn", "koretid_afstand", "retninger", "stoppesteder",
           "forbehold", "kilde", "kort", "maalenoter"}
VEJ = {"vejtype", "hastighed", "bumptype", "andre_foranstaltninger"}
STOPPESTED = {"navn", "retning", "lat", "lon", "straekning"}
RETNINGER = ("direction_1", "direction_2")
DATO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID = re.compile(r"^[A-Za-z0-9_-]+$")
STOP_PLADSHOLDER = re.compile(r"^Stop (før|efter) .*\(By\)$")


# ------------------------------------------------------------------ geometri (som komfort_v1.0: lokal flad projektion)
def lokal_xy(lat, lon, lat0, lon0):
    k = math.pi / 180.0 * EARTH_R
    return (lon - lon0) * k * math.cos(math.radians(lat0)), (lat - lat0) * k


def projicer(p_fra, p_til, lat, lon):
    """(s, d, L): meter langs linjen fra p_fra mod p_til, sideafstand (uden fortegn) og linjens længde."""
    x1, y1 = lokal_xy(p_til["lat"], p_til["lon"], p_fra["lat"], p_fra["lon"])
    L = math.hypot(x1, y1)
    if L <= 0:
        return 0.0, 0.0, 0.0
    ex, ey = x1 / L, y1 / L
    x, y = lokal_xy(lat, lon, p_fra["lat"], p_fra["lon"])
    return x * ex + y * ey, abs(-x * ey + y * ex), L


def afstand_m(a, b):
    x, y = lokal_xy(b["lat"], b["lon"], a["lat"], a["lon"])
    return math.hypot(x, y)


def analysetype(cfg):
    """'straekning' eller 'kryds'. Uden nøglen (ældre configs): kryds, hvis der hverken er strækninger,
    komfort eller elementer (som kryds-configs i README), ellers strækning."""
    if "analysetype" in cfg:
        return cfg["analysetype"]
    if not any(cfg.get(k) for k in ("straekninger", "komfort", "elementer")):
        return "kryds"
    return "straekning"


def laes_stop_cache(cfg_sti, cfg):
    """retninger fra resultat\\stoppesteder_hafas.yaml (forbered.py stopnavne), eller None, hvis filen mangler, ikke
    kan læses eller er lavet ud fra en anden Details.csv (sti, størrelse, ændringstid) end periode A i cfg."""
    fil = Path(cfg_sti).resolve().parent / CACHE
    if not fil.exists():
        return None
    try:
        c = yaml.safe_load(fil.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None
    kilde = c.get("kilde")
    d = ((cfg.get("data") or {}) if isinstance(cfg.get("data"), dict) else {}).get("Periode_A")
    if isinstance(kilde, dict) and isinstance(d, dict) and isinstance(d.get("details_csv"), str):
        det = Path(d["details_csv"])
        det = det if det.is_absolute() else Path(cfg_sti).resolve().parent / det
        if not det.exists() or kilde != {"details_csv": str(det), "stoerrelse": det.stat().st_size,
                                          "aendret": int(det.stat().st_mtime)}:
            return None
    return c.get("retninger") or None


def koer_perioder(cfg):
    """Perioderne, der køres, når PERIODER=auto: dem under periods, der også har data (A før B)."""
    per = cfg.get("periods") if isinstance(cfg.get("periods"), dict) else {}
    data = cfg.get("data") if isinstance(cfg.get("data"), dict) else {}
    return sorted(p for p in per if isinstance(per[p], dict) and isinstance(data.get(f"Periode_{p}"), dict))


def er_tal(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def er_pladsholder(p):
    try:
        return (round(float(p["lat"]), 4), round(float(p["lon"]), 4)) == PLADSHOLDER
    except (TypeError, ValueError, KeyError):
        return False


# ------------------------------------------------------------------ YAML med linjenumre og dobbelte nøgler
class _Loader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    set_af, dobbelte = {}, []
    for k_node, _v in node.value:
        k = loader.construct_object(k_node, deep=deep)
        try:
            if k in set_af:
                dobbelte.append((k, set_af[k], k_node.start_mark.line + 1))
            else:
                set_af[k] = k_node.start_mark.line + 1
        except TypeError:
            pass
    loader.dobbelte.extend(dobbelte)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def laes_yaml(tekst):
    """Returnér (data, dobbelte nøgler [(nøgle, linje1, linje2)]). Rejser yaml.YAMLError ved syntaksfejl."""
    loader = _Loader(tekst)
    loader.dobbelte = []
    try:
        data = loader.get_single_data()
    finally:
        loader.dispose()
    return data, loader.dobbelte


# ------------------------------------------------------------------ selve tjekket
class Tjek:
    def __init__(self, cfg_sti, trin="fuld", perioder=None):
        self.sti = Path(cfg_sti)
        self.trin = trin
        self.perioder_valgt = perioder
        self.fejl, self.advarsler = [], []

    # beskeder
    def F(self, hvor, hvad, goer):
        self.fejl.append(f"FEJL      [{hvor}] {hvad}\n          Gør: {goer}")

    def A(self, hvor, hvad, goer=""):
        self.advarsler.append(f"ADVARSEL  [{hvor}] {hvad}" + (f"\n          Gør: {goer}" if goer else ""))

    def FA(self, mild, hvor, hvad, goer):
        """Fejl, men kun advarsel når mild er sand (fx ved trin stopnavne)."""
        (self.A if mild else self.F)(hvor, hvad, goer)

    @property
    def mild(self):
        return self.trin == "stopnavne"

    def ukendte(self, d, kendte, hvor):
        if not isinstance(d, dict):
            return
        for k in d:
            if k in kendte:
                continue
            forslag = difflib.get_close_matches(str(k), sorted(kendte), n=1, cutoff=0.6)
            hint = f'Mente du "{forslag[0]}"? Ret stavningen.' if forslag else \
                f"Slet linjen, eller ret den til en af: {', '.join(sorted(kendte))}."
            self.F(f"{hvor} > {k}" if hvor else str(k), f'Nøglen "{k}" kendes ikke.', hint)

    # hele config'en
    def koer(self):
        if not self.sti.exists():
            self.F("config.yaml", f"Filen findes ikke: {self.sti}", "Kør koer_analyse.bat fra analysemappen (der hvor config.yaml ligger).")
            return self
        tekst = self.sti.read_text(encoding="utf-8-sig")
        for nr, linje in enumerate(tekst.splitlines(), 1):
            if "\t" in linje and not linje.lstrip().startswith("#"):
                self.F(f"linje {nr}", "Linjen har en tabulator.", "Erstat tabulatoren med mellemrum (YAML tillader kun mellemrum).")
        try:
            cfg, dobbelte = laes_yaml(tekst)
        except yaml.YAMLError as e:
            mark = getattr(e, "problem_mark", None) or getattr(e, "context_mark", None)
            linje = f"linje {mark.line + 1}" if mark else "ukendt linje"
            problem = getattr(e, "problem", None) or str(e).splitlines()[0]
            self.F(linje, f"Filen kan ikke læses (YAML-fejl: {problem}).",
                   f"Se {linje} og linjen før: tjek indrykning (samme antal mellemrum som linjerne omkring), kolon efter "
                   "nøglen, og at anførselstegn og {{ }} / [ ] er lukket.")
            return self
        for k, l1, l2 in dobbelte:
            self.F(f"linje {l2}", f'Nøglen "{k}" står to gange (linje {l1} og {l2}); den sidste overskriver den første.',
                   "Giv den ene et andet navn (fx p3 i stedet for p2), eller slet den.")
        if not isinstance(cfg, dict):
            self.F("config.yaml", "Filen er tom eller ikke en config.", "Start forfra med skabelonen (ny_analyse.bat).")
            return self
        self.cfg = cfg
        self.ukendte(cfg, TOP, "")
        self.analysetype()
        self.periods_og_data()
        self.points()
        self.point_order_distances()
        self.stops()
        if self.type == "kryds":
            self.kryds()
        else:
            self.straekninger()
        self.udvalg_zonetid()
        self.rapport()
        return self

    def analysetype(self):
        t = analysetype(self.cfg)
        if t not in ("straekning", "kryds"):
            self.F("analysetype", f'"{t}" kendes ikke.', 'Skriv  analysetype: straekning  eller  analysetype: kryds')
            t = "straekning"
        self.type = t

    # perioder, datoer og data
    def periods_og_data(self):
        per = self.cfg.get("periods")
        if not isinstance(per, dict) or not per:
            self.F("periods", "Sektionen mangler eller er tom.", "Skriv periode A (og evt. B) med name, start og end, som i skabelonen.")
            per = {}
        datoer = {}
        for p, v in per.items():
            hvor = f"periods > {p}"
            if not isinstance(v, dict):
                self.F(hvor, "Perioden skal have name, start og end.", 'Fx  A: {name: "Før", start: "2025-01-01", end: "2025-03-31"}')
                continue
            self.ukendte(v, PERIODE, hvor)
            d = {}
            for f in ("start", "end"):
                d[f] = self.dato(v.get(f), f"{hvor} > {f}")
            if d["start"] and d["end"]:
                if d["start"] > d["end"]:
                    self.F(hvor, f"start ({d['start']}) ligger efter end ({d['end']}).", "Byt de to datoer.")
                datoer[p] = d
        self.perioder = [p for p in per if isinstance(per.get(p), dict)]
        data = self.cfg.get("data")
        if not isinstance(data, dict):
            self.F("data", "Sektionen mangler.", "Kopiér data-sektionen fra skabelonen (den skal ikke rettes).")
            return
        if self.perioder_valgt:
            for p in self.perioder_valgt:
                if p not in per:
                    self.F("periods", f"Periode {p} køres (PERIODER i koer_analyse.bat), men står ikke under periods.",
                           f"Tilføj periode {p}, eller ret PERIODER i koer_analyse.bat.")
            koeres = list(self.perioder_valgt)
        else:
            koeres = koer_perioder(self.cfg)
            for p in self.perioder:
                if p not in koeres:
                    self.A(f"periods > {p}", f"Periode {p} har ingen data under data: og køres ikke.",
                           f"Skal den med, så tilføj Periode_{p} under data. Ellers slet periode {p} under periods.")
        if not koeres:
            self.F("data", "Ingen periode har data.", "Skriv Periode_A under data, som i skabelonen.")
        if "A" in datoer and "B" in datoer and "B" in koeres and \
                datoer["A"]["end"] >= datoer["B"]["start"] and datoer["B"]["end"] >= datoer["A"]["start"]:
            self.A("periods", "Periode A og B overlapper.", "Tjek datoerne: før og efter bør ikke dække de samme dage.")
        self.koeres = koeres
        if self.mild or self.trin == "proeve":       # valg 1 og 2 læser kun periode A
            koeres = koeres[:1] if "A" not in koeres else ["A"]
        elif self.trin == "rapport":
            koeres = []                            # valg 4 læser resultat\, ikke rådata
        kendte = {f"Periode_{p}" for p in per} | {"output"}
        self.ukendte(data, kendte | {"Periode_A", "Periode_B"}, "data")
        for p in koeres:
            d = data.get(f"Periode_{p}")
            hvor = f"data > Periode_{p}"
            if not isinstance(d, dict):
                self.F(hvor, f"Periode {p} står under periods, men har ingen data.",
                       f"Tilføj Periode_{p} under data, eller slet periode {p} under periods (kun én periode).")
                continue
            self.ukendte(d, DATA_PERIODE, hvor)
            for f in ("details_csv", "list_csv"):
                s = d.get(f)
                if not s or not isinstance(s, str):
                    self.F(f"{hvor} > {f}", "Stien mangler." if not s else f"Stien skal være tekst (er {s}).",
                           f'Skriv stien i anførselstegn, fx "data/{p}/{"Details" if f == "details_csv" else "List"}.csv".')
                    continue
                fil = Path(s) if Path(s).is_absolute() else self.sti.resolve().parent / s
                if not fil.exists():
                    self.F(f"{hvor} > {f}", f"Filen findes ikke: {fil}",
                           f"Læg HAFAS-eksporten ({fil.name}) i {fil.parent}, eller ret stien.")

    def dato(self, v, hvor):
        if isinstance(v, dt.datetime):
            self.F(hvor, f'"{v}" har et klokkeslæt.', 'Skriv kun datoen i anførselstegn som ÅÅÅÅ-MM-DD, fx "2025-05-01".')
            return None
        if isinstance(v, dt.date):
            return v
        if not isinstance(v, str) or not DATO.match(v.strip()):
            self.F(hvor, f'"{v}" er ikke en dato som ÅÅÅÅ-MM-DD.', 'Skriv datoen i anførselstegn som ÅÅÅÅ-MM-DD, fx "2025-05-01".')
            return None
        try:
            return dt.date.fromisoformat(v.strip())
        except ValueError:
            self.F(hvor, f'"{v}" er ikke en gyldig dato.', "Ret måned eller dag (fx findes 2025-02-30 ikke).")
            return None

    # punkter
    def points(self):
        pts = self.cfg.get("points")
        self.pts = {}
        if not isinstance(pts, dict) or not pts:
            self.F("points", "Sektionen mangler eller er tom.", "Skriv mindst to punkter (p1, p2) med name, lat og lon.")
            return
        navne = {}
        for pid, p in pts.items():
            hvor = f"points > {pid}"
            if not isinstance(p, dict):
                self.F(hvor, "Punktet skal have name, lat og lon.", f'Fx  {pid}: {{name: "Vejkryds", lat: 55.4804, lon: 8.4674}}')
                continue
            self.ukendte(p, PUNKT, hvor)
            lat, lon = p.get("lat"), p.get("lon")
            if not er_tal(lat) or not er_tal(lon):
                self.F(hvor, f"lat og lon skal være tal (er: {lat}, {lon}).",
                       "Skriv koordinaten med punktum som decimaltegn, fx lat: 55.4804, lon: 8.4674.")
                continue
            if er_pladsholder(p):
                self.FA(self.mild, hvor, "Koordinaten er skabelonens pladsholder (55.0000, 8.0000).",
                        "Find punktet i Google Maps (højreklik på vejen), og sæt koordinaten ind som lat, lon.")
            elif 7 <= lat <= 14 and 53 <= lon <= 58:
                self.F(hvor, f"lat og lon ser ud til at være byttet om ({lat}, {lon}).", "Byt de to tal: lat er ca. 54-58 i Danmark, lon ca. 8-15.")
            elif not (53 <= lat <= 58 and 7 <= lon <= 16):
                self.A(hvor, f"Koordinaten ({lat}, {lon}) ligger uden for Danmark.", "Tjek for tastefejl.")
            navn = str(p.get("name", pid))
            if navn in navne:
                self.F(hvor, f'Navnet "{navn}" bruges også af {navne[navn]}.', "Giv punkterne forskellige navne (de bliver kolonnenavne i resultatet).")
            navne[navn] = pid
            self.pts[pid] = {"lat": float(lat), "lon": float(lon), "name": navn, "pladsholder": er_pladsholder(p)}

    def punkt_findes(self, pid, hvor):
        if isinstance(pid, (list, dict)):
            self.F(hvor, f"Skal være ét punkt-id (er {pid}).", "Skriv punkt-id'et uden [ ], fx p1.")
            return False
        if pid not in (self.cfg.get("points") or {}):
            kendte = sorted(map(str, (self.cfg.get("points") or {})))
            forslag = difflib.get_close_matches(str(pid), kendte, n=1, cutoff=0.5)
            self.F(hvor, f'Punktet "{pid}" findes ikke under points.',
                   (f'Mente du "{forslag[0]}"? ' if forslag else "") + f"Brug et af punkterne: {', '.join(kendte) or '(ingen)'}.")
            return False
        return True

    def point_order_distances(self):
        po = self.cfg.get("point_order")
        self.retninger = []
        if not isinstance(po, dict) or not po:
            self.F("point_order", "Sektionen mangler eller er tom.", "Skriv punkterne i køreorden pr. retning, fx  direction_1: [p1, p2]")
            po = {}
        self.ukendte(po, set(RETNINGER), "point_order")
        for r, liste in po.items():
            if r not in RETNINGER:
                continue
            hvor = f"point_order > {r}"
            if not isinstance(liste, list) or not liste:
                self.F(hvor, "Skal være en liste af punkt-id'er.", "Fx  direction_1: [p1, p2]")
                continue
            for pid in liste:
                self.punkt_findes(pid, hvor)
            if len(set(map(str, liste))) != len(liste):
                self.F(hvor, "Et punkt står to gange.", "Hvert punkt må kun stå én gang pr. retning.")
            self.retninger.append(r)
        dist = self.cfg.get("distances")
        self.dist = dist if isinstance(dist, dict) else {}
        navne = {}
        for did, d in self.dist.items():
            hvor = f"distances > {did}"
            if not isinstance(d, dict):
                self.F(hvor, "Skal have name, from og to.", f'Fx  {did}: {{name: "Strækningen", from: p1, to: p2}}')
                continue
            self.ukendte(d, DISTANCE, hvor)
            if not d.get("name"):
                self.F(f"{hvor} > name", "Distancen har intet navn (rapporten skal bruge det).", f'Skriv fx  name: "Strækningen"')
            elif str(d["name"]) in navne:
                self.F(f"{hvor} > name", f'Navnet "{d["name"]}" bruges også af {navne[str(d["name"])]}.',
                       "Giv distancerne forskellige navne (de bliver kolonnenavne i resultatet).")
            else:
                navne[str(d["name"])] = did
            for f in ("from", "to"):
                if d.get(f) is None:
                    self.F(f"{hvor} > {f}", "Mangler.", "Skriv punkt-id'et (fx p1).")
                else:
                    self.punkt_findes(d[f], f"{hvor} > {f}")
        if not self.dist and any(len(po.get(r) or []) > 1 for r in self.retninger):
            self.A("distances", "Ingen distancer: der regnes ingen køretid.", "Tilføj fx  d1: {name: \"Strækningen\", from: p1, to: p2}")

    def stops(self):
        st = self.cfg.get("stops")
        if not isinstance(st, dict):
            st = {}
            if self.retninger:
                self.FA(self.mild, "stops", "Sektionen mangler.", "Vælg 1 i koer_analyse.bat, og kopiér forslaget fra stopnavne.txt.")
        self.ukendte(st, set(RETNINGER), "stops")
        cache = self.laes_cache()
        for r in self.retninger:
            hvor = f"stops > {r}"
            s = st.get(r)
            if not isinstance(s, dict):
                if "stops" in self.cfg:
                    self.FA(self.mild, hvor, f"Retningen står under point_order, men har ingen stop.",
                            f"Tilføj  {r}: {{start: \"...\", end: \"...\"}}  med navne fra stopnavne.txt (valg 1).")
                continue
            self.ukendte(s, STOP, hvor)
            for f in ("start", "end"):
                v = s.get(f)
                if not v or not str(v).strip():
                    self.FA(self.mild, f"{hvor} > {f}", "Stopnavnet er tomt.", "Kopiér navnet fra stopnavne.txt (valg 1).")
                elif STOP_PLADSHOLDER.match(str(v).strip()):
                    self.FA(self.mild, f"{hvor} > {f}", f'"{v}" er skabelonens pladsholder.',
                            "Vælg 1 i koer_analyse.bat, og kopiér start og slut for retningen fra stopnavne.txt.")
                elif cache:
                    self.stop_i_data(cache, r, str(v).strip(), f"{hvor} > {f}")
        for r in st:
            if r in RETNINGER and r not in self.retninger and self.retninger:
                self.A(f"stops > {r}", "Retningen har stop, men står ikke under point_order (den kasseres).",
                       "Det er rigtigt ved kryds (én retning). Ellers: tilføj retningen under point_order.")

    def laes_cache(self):
        return laes_stop_cache(self.sti, self.cfg)

    def stop_i_data(self, ret, r, navn, hvor):
        her = [s["navn"] for s in (ret.get(r[-1]) or {}).get("stop", [])]
        alle = {s["navn"] for v in ret.values() for s in (v or {}).get("stop", [])}
        if not her or navn in her:
            return
        if navn in alle:
            self.A(hvor, f'"{navn}" findes i data, men kun i den anden retning.', "Tjek, at du har kopieret fra den rigtige retning i stopnavne.txt.")
            return
        forslag = difflib.get_close_matches(navn, sorted(alle), n=1, cutoff=0.6)
        self.F(hvor, f'Stoppet "{navn}" findes ikke i data (periode A).',
               (f'Mente du "{forslag[0]}"? ' if forslag else "") + "Kopiér navnet præcist fra stopnavne.txt.")

    # strækninger, elementer, komfort
    def straekninger(self):
        sk = self.cfg.get("straekninger")
        kom = self.cfg.get("komfort")
        if kom is not None and not isinstance(kom, dict):
            self.F("komfort", "Skal være en sektion (eller slettes).", "Skriv  komfort:  og  bump_vinduer: {}  under, som i skabelonen.")
            kom = {}
        kom = kom or {}
        self.ukendte(kom, KOMFORT, "komfort")
        liste = []
        if sk is not None:
            if not isinstance(sk, list) or not sk:
                self.F("straekninger", "Skal være en liste med mindst én strækning.", "Se skabelonen: hver strækning starter med  - id:")
                return
            ids = set()
            for i, s in enumerate(sk, 1):
                hvor = f"straekninger > {i}. strækning"
                if not isinstance(s, dict):
                    self.F(hvor, "Skal have id, navn, fra, til og elementer.", "Se skabelonen.")
                    continue
                sid = str(s.get("id") or f"s{i}")
                hvor = f"straekninger > {sid}"
                self.ukendte(s, STRAEKNING, hvor)
                sk_kom = s.get("komfort") or {}
                if not isinstance(sk_kom, dict):
                    self.F(f"{hvor} > komfort", "Skal være en sektion (eller slettes).", "Slet linjen, eller skriv nøglerne under den.")
                    sk_kom = {}
                self.ukendte(sk_kom, KOMFORT - {"fra", "til"}, f"{hvor} > komfort")
                if sid in ids:
                    self.F(f"{hvor} > id", f'id "{sid}" bruges to gange.', "Giv hver strækning sit eget id.")
                if not ID.match(sid):
                    self.F(f"{hvor} > id", f'id "{sid}" må kun have bogstaver a-z, tal, - og _ (det bliver en del af filnavne).',
                           "Brug et kort id uden mellemrum og tegn, fx vest, oest eller s1.")
                ids.add(sid)
                for f in ("fra", "til"):
                    if s.get(f) is None:
                        self.F(f"{hvor} > {f}", "Mangler.", "Skriv punkt-id'et for strækningens ende (fx p1).")
                liste.append((sid, hvor, s.get("fra"), s.get("til"), s.get("elementer"), s.get("koretid_afstand"), {**kom, **sk_kom}))
            self.straekning_ids = ids
            if self.cfg.get("elementer"):
                self.A("elementer", "Elementerne øverst bruges ikke, når der er straekninger.",
                       "Flyt dem under den strækning, de ligger på (elementer: under strækningen).")
        elif "fra" in kom or "til" in kom:
            liste.append(("s1", "komfort", kom.get("fra", "p1"), kom.get("til", "p5"), self.cfg.get("elementer"),
                          (self.cfg.get("rapport") or {}).get("koretid_afstand") if isinstance(self.cfg.get("rapport"), dict) else None, kom))
        else:
            self.F("straekninger", "Der er ingen strækning.",
                   "Skriv strækningen under straekninger (id, navn, fra, til, elementer), som i skabelonen. Er det et kryds: analysetype: kryds")
            return
        self.har_elementer = False
        for sid, hvor, fra, til, els, kt, k in liste:
            ok = fra is not None and til is not None and self.punkt_findes(fra, f"{hvor} > fra") & self.punkt_findes(til, f"{hvor} > til")
            if ok and fra == til:
                self.F(hvor, "fra og til er det samme punkt.", "Vælg to forskellige punkter.")
                ok = False
            if kt is not None and kt not in self.dist:
                self.F(f"{hvor} > koretid_afstand", f'Distancen "{kt}" findes ikke under distances.',
                       f"Brug en af: {', '.join(map(str, self.dist)) or '(ingen)'}, eller slet linjen.")
            elif kt is None and ok and self.dist and not any(
                    isinstance(d, dict) and d.get("from") == fra and d.get("to") == til for d in self.dist.values()):
                besked = (f"Ingen distance går fra {fra} til {til}; rapporten tager så køretiden fra den første distance.",
                          f"Tilføj under distances fx  d{len(self.dist) + 1}: {{name: \"...\", from: {fra}, to: {til}}}")
                (self.F if len(liste) > 1 else self.A)(hvor, *besked)
            if ok:
                if not any(fra in (self.cfg["point_order"].get(r) or []) and til in (self.cfg["point_order"].get(r) or [])
                           for r in self.retninger):
                    self.A(hvor, f"{fra} og {til} står ikke begge under point_order.", "Tilføj dem i køreorden under point_order.")
            self.elementer(els, f"{hvor} > elementer", self.pts.get(fra) if ok else None, self.pts.get(til) if ok else None, k)

    def elementer(self, els, hvor, p_fra, p_til, kom):
        if els is None:
            return
        if not isinstance(els, list):
            self.F(hvor, "Skal være en liste (eller  elementer: []  uden elementer).", "Se skabelonen.")
            return
        navne = set()
        korridor = float(kom.get("korridor_sideafstand_m") or STANDARD_KORRIDOR_M)
        for i, e in enumerate(els, 1):
            h = f"{hvor} > {e.get('navn', i) if isinstance(e, dict) else i}"
            if not isinstance(e, dict):
                self.F(h, "Elementet skal have navn, type, lat og lon.", '{navn: "Bump 1", type: bump, lat: 55.48, lon: 8.46, radius_m: 30}')
                continue
            self.ukendte(e, ELEMENT, h)
            for f in ("navn", "lat", "lon"):
                if e.get(f) is None:
                    self.F(h, f"{f} mangler.", "Elementet skal have navn, type, lat og lon.")
            if str(e.get("navn")) in navne:
                self.F(h, f'Navnet "{e.get("navn")}" bruges to gange på strækningen.', "Giv elementerne forskellige navne (fx Bump 1, Bump 2).")
            navne.add(str(e.get("navn")))
            t = str(e.get("type", "andet")).strip().lower()
            if t not in ELEMENT_TYPER:
                forslag = difflib.get_close_matches(t, sorted(ELEMENT_TYPER), n=1, cutoff=0.5)
                self.F(f"{h} > type", f'Typen "{e.get("type")}" kendes ikke.',
                       (f'Mente du "{forslag[0]}"? ' if forslag else "") + "Brug bump, indsnævring eller andet.")
            if "radius_m" in e and (not er_tal(e["radius_m"]) or e["radius_m"] <= 0):
                self.F(f"{h} > radius_m", f"radius_m skal være et tal over 0 (er {e['radius_m']}).", "Skriv fx radius_m: 30.")
            if not er_tal(e.get("lat")) or not er_tal(e.get("lon")):
                if e.get("lat") is not None and e.get("lon") is not None:
                    self.F(h, "lat og lon skal være tal.", "Skriv koordinaten med punktum som decimaltegn.")
                continue
            if er_pladsholder(e):
                self.FA(self.mild, h, "Koordinaten er skabelonens pladsholder (55.0000, 8.0000).",
                        "Sæt elementets koordinat ind fra Google Maps, eller slet linjen.")
                continue
            if p_fra and p_til and not p_fra["pladsholder"] and not p_til["pladsholder"]:
                s, d, L = projicer(p_fra, p_til, float(e["lat"]), float(e["lon"]))
                if kom.get("laengde_m"):
                    L = float(kom["laengde_m"])
                if not (0.0 <= s <= L):
                    self.F(h, f"Elementet ligger uden for strækningen ({s:.0f} m fra fra-punktet; strækningen er 0-{L:.0f} m).",
                           "Tjek elementets lat/lon og strækningens fra og til (er de byttet om?).")
                elif d > korridor:
                    self.A(h, f"Elementet ligger {d:.0f} m fra linjen mellem fra og til (korridoren er {korridor:.0f} m).",
                           "Tjek koordinaten: den skal ligge på vejen.")
            self.har_elementer = True

    def kryds(self):
        for k in ("straekninger", "komfort", "zonetid"):
            if self.cfg.get(k):
                self.F(k, f"Et kryds bruger ikke {k} (komfort, zonetid og strækningsrapporten antager en ret strækning).",
                       f"Slet sektionen {k}, eller skriv  analysetype: straekning, hvis det ikke er et kryds.")
        if self.cfg.get("elementer"):
            self.F("elementer", "Et kryds bruger ikke elementer.", "Slet sektionen elementer.")
        if not any(len((self.cfg.get("point_order") or {}).get(r) or []) >= 2 for r in self.retninger):
            self.F("point_order", "Et kryds skal have mindst to punkter i én retning.", "Skriv punkterne i køreorden, fx  direction_2: [pA, pS, pB]")

    def udvalg_zonetid(self):
        u = self.cfg.get("udvalg")
        if isinstance(u, dict):
            self.ukendte(u, UDVALG, "udvalg")
            if u.get("dagtype", "hverdage") not in ("hverdage", "alle"):
                self.F("udvalg > dagtype", f'"{u.get("dagtype")}" kendes ikke.', "Skriv hverdage eller alle.")
            hd = u.get("helligdage") or []
            if not isinstance(hd, list):
                self.F("udvalg > helligdage", "Skal være en liste.", 'Fx  helligdage: ["2025-04-17", "2025-04-18"]')
            else:
                for x in hd:
                    self.dato(x, "udvalg > helligdage")
        z = self.cfg.get("zonetid")
        if isinstance(z, dict):
            self.ukendte(z, ZONETID, "zonetid")

    def rapport(self):
        r = self.cfg.get("rapport")
        if r is None:
            return
        if not isinstance(r, dict):
            self.F("rapport", "Skal være en sektion.", "Se skabelonen.")
            return
        self.ukendte(r, RAPPORT, "rapport")
        if isinstance(r.get("vej"), dict):
            self.ukendte(r["vej"], VEJ, "rapport > vej")
        if "<" in str(r.get("titel") or ""):
            self.A("rapport > titel", "Titlen har stadig en pladsholder (<...>).", "Skriv, hvad og hvor der er målt (rapporten kan bygges igen med valg 4).")
        sp = r.get("stoppesteder")
        if sp is None:
            return
        if not isinstance(sp, list):
            self.F("rapport > stoppesteder", "Skal være en liste (eller  stoppesteder: []).", "Kopiér blokken fra stopnavne.txt.")
            return
        for i, s in enumerate(sp, 1):
            h = f"rapport > stoppesteder > {s.get('navn', i) if isinstance(s, dict) else i}"
            if not isinstance(s, dict):
                self.F(h, "Skal have navn, retning, lat og lon.", '{navn: "Stopnavn", retning: 1, lat: 55.48, lon: 8.46}')
                continue
            self.ukendte(s, STOPPESTED, h)
            if not er_tal(s.get("lat")) or not er_tal(s.get("lon")):
                self.F(h, "lat og lon skal være tal.", "Kopiér blokken fra stopnavne.txt, eller ret koordinaten.")
            elif er_pladsholder(s):
                self.F(h, "Koordinaten er en pladsholder.", "Kopiér blokken fra stopnavne.txt, eller slet linjen.")
            if s.get("retning") is not None and str(s.get("retning")) not in ("1", "2"):
                self.F(f"{h} > retning", f'Retningen "{s.get("retning")}" kendes ikke.', "Skriv retning: 1 eller retning: 2.")
            ids = getattr(self, "straekning_ids", None)
            if s.get("straekning") is not None and ids is not None and str(s["straekning"]) not in ids:
                self.F(f"{h} > straekning", f'Strækningen "{s["straekning"]}" findes ikke under straekninger.',
                       f"Brug et af id'erne: {', '.join(sorted(ids))}, eller slet straekning: (så findes den ud fra positionen).")

    # udskrift
    def tekst(self):
        navn = self.sti.name
        linjer = [f"Tjek af {navn} ({'kryds' if getattr(self, 'type', '') == 'kryds' else 'strækning'}): "
                  f"{len(self.fejl)} fejl, {len(self.advarsler)} advarsler."]
        if self.fejl:
            linjer += ["", *self.fejl]
        if self.advarsler:
            linjer += ["", *self.advarsler]
        if self.fejl:
            linjer += ["", f"Ret fejlene i {navn}, gem filen, og kør igen. Hjælp: kommentarerne i {navn} og program\\README.md (Den nemme vej)."]
        elif not self.advarsler:
            linjer += ["Alt ser rigtigt ud."]
        return "\n".join(linjer)


def tjek(cfg_sti, trin="fuld", perioder=None):
    """Kør tjekket. Returnér Tjek-objektet (fejl, advarsler, tekst())."""
    return Tjek(cfg_sti, trin, perioder).koer()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--trin", default="fuld", choices=["stopnavne", "proeve", "fuld", "rapport"],
                    help="stopnavne er mildere (pladsholdere er advarsler, kun data A); standard fuld")
    ap.add_argument("--perioder", default=None, help='perioderne, der køres, fx "A B" (standard: alle i config)')
    a = ap.parse_args(argv)
    perioder = a.perioder.split() if a.perioder and a.perioder.strip().lower() != "auto" else None
    t = tjek(a.config, a.trin, perioder)
    print(t.tekst())
    return 1 if t.fejl else 0


if __name__ == "__main__":
    sys.exit(main())
