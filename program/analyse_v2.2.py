#!/usr/bin/env python3
"""
analyse_v2.2.py - GPS Busdata Tids-analyse (v2.2)

Maaler koeretid og hastighed paa en straekning ud fra realtids-GPS (HAFAS-eksport).
Sammenligner to perioder (A og B), fx foer/efter en vejaendring, eller koerer én periode.

v2.0 er en omskrivning af analyse_v1.0.py med SAMME beregning som standard
(koeretid, punkt-match, hastighed pr. ping, hastighed ved punkt, Log, kasseringsregler).
Nyt: alle graenser i config, datakvalitetsoversigt hver koersel, 1/2/mange punkter,
kolonnetjek ved start, percentil-opsummering og valgfri eksport af segment-pings.
v2.1 (review 2026-11-09): kasserede ture pr. dag i kvalitetsoversigten og valgfri
udelukkelse af flag-ture fra opsummeringen. result.csv er uaendret ift. v2.0.
v2.2 (2026-11-13): store filer. Stop-filteret (grovfilteret i fase 1) er flyttet ind i
indlaesningen: Details.csv laeses i to gennemloeb i bidder, og kun hver turs raekker
mellem de to stop (+ buffer_rows) holdes i hukommelsen. Beregningen er uaendret, saa
result.csv er den samme som med v2.1. --list-stops laeses ogsaa i bidder.
Se CHANGELOG.md.

Brug:
    python analyse_v2.2.py --config config_3A.yaml --list-stops
    python analyse_v2.2.py --config config_3A.yaml --max-trips 300 --debug
    python analyse_v2.2.py --config config_3A.yaml --period A
    python analyse_v2.2.py --config config_3A.yaml --period B --export-segments
"""

import argparse
import logging
import sys
import time
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# Pandas advarer om blandede typer i en kolonne, naar Details.csv laeses i bidder (ogsaa i v2.1).
# Advarslen aendrer ingen tal (v2.2 = v2.1 byte for byte) og er kun stoej i konsollen.
warnings.filterwarnings('ignore', category=pd.errors.DtypeWarning)

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

VERSION = "2.2"
logger = logging.getLogger('analyse')


class KonfigFejl(Exception):
    """Fejl i config eller inputfiler - vises paa dansk uden traceback."""


# -- Kolonnenavne (eet sted, saa en senere kolonnemapping let kan tilfoejes) ------------
# Navnene er de STRIPPEDE navne (eksporten har foranstillet tab-tegn og anfoerselstegn).
COLUMNS = {
    'details': {
        'trip': 'Turreference',
        'stop_name': 'Stop-navn',
        'stop_nr': 'Stop-nummer',
        'lat': 'Breddegrad (PLANLAGT)',
        'lon': 'Længdegrad (PLANLAGT)',
        'projection': 'Projektion',          # valgfri
    },
    'list': {
        'trip': 'Turnummer',
        'day': 'Køredag',                    # valgfri
        'direction': 'Retningsflag',
    },
}
DETAILS_REQUIRED = ['trip', 'stop_name', 'stop_nr', 'lat', 'lon']
DETAILS_OPTIONAL = ['projection']
LIST_REQUIRED = ['trip', 'direction']
LIST_OPTIONAL = ['day']

# -- Standardvaerdier = v1's faktiske vaerdier (se config_eksempel.yaml for forklaring) ---
DEFAULTS = {
    'buffer_rows': 50,                 # v1-kode: 30, men 3A-config og README: 50
    'speed_max_kmh': 80.0,
    'speed_min_kmh': 0.0,
    'stop_speed_kmh': 4.0,             # v1: STOP_SPEED_KMH
    'stand_still_dist_m': 0.1,         # v1: dist < 0.1 -> Stop
    'max_match_distance_m': 200.0,     # v1: afstand > 200 -> flag i Log
    'speed_nearest_pings': 5,          # v1: de 5 naermeste pings
    'rising_count': 5,                 # v1: RISING_THRESHOLD (bruges ogsaa som raekke-offset)
    'rising_min_dist_m': 15.0,         # v1: RISING_MIN_DIST_M
    'min_rows_after_coarse_filter': 3,  # v1: len(filtered) < 3
    'ping_prefix': 'Pegeredskab',
    'projection_value': 'X',
    'date_columns': ['Ankomst-dato (REALTID)', 'Afgangs-dato (REALTID)', 'Ankomst-dato (PLANLAGT)'],
    'time_columns': ['Tid (REALTID) (+sekunder)', 'Ankomst-tid (REALTID)',
                     'Afgangs-tid (REALTID) (+sekunder)', 'Tid (PLANLAGT)'],
    'lat_range': [53, 58],
    'lon_range': [7, 14],
    'chunk_size': 300_000,
    'max_trips_rows_per_trip': 2000,   # v1: --max-trips N laeser kun foerste N*2000 raekker
    'summary_only_empty_log': True,    # opsummering.csv: kun ture med tom Log (v1-praksis)
    'summary_exclude_flags': [],       # v2.1: udelad ture med disse Flag-typer fra opsummering (fx ['stoprække'])
    'quality_day_share': 0.5,          # v2.1: dage med kasseret-andel >= denne vises i kvalitet.md
    'percentiles': [5, 25, 50, 75, 95],
    'export_segments': False,
}


# -- Hjaelpefunktioner -----------------------------------------------------------------

def haversine_distance(lat1, lon1, lat2, lon2):
    """Afstand i meter mellem GPS-koordinater (skalar eller numpy-arrays). Samme formel som v1."""
    R = 6371000  # meter
    lat1, lon1, lat2, lon2 = map(np.radians, [np.asarray(lat1, dtype=float), np.asarray(lon1, dtype=float),
                                              np.asarray(lat2, dtype=float), np.asarray(lon2, dtype=float)])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def setup_logging(debug=False, log_file=None):
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, '_analyse_handler', False):
            root.removeHandler(h)
    fmt = logging.Formatter('%(message)s')
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh._analyse_handler = True
    root.addHandler(sh)
    if log_file:
        fh = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        fh.setFormatter(fmt)
        fh._analyse_handler = True
        root.addHandler(fh)
    root.setLevel(level)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    return logger


def _to_int(x):
    """Retningsflag -> int ('1', 1, 1.0 -> 1). None hvis ikke tolkbar."""
    if x is None or (not isinstance(x, str) and pd.isna(x)):
        return None
    try:
        return int(float(str(x).strip()))
    except (ValueError, TypeError):
        return None


def _argsort_dt(dt):
    """Sortering paa datetime - IDENTISK kald som v1 (DataFrame.sort_values, quicksort, NaT sidst),
    saa raekkefoelgen ved lige tidsstempler bliver den samme som i v1."""
    return pd.DataFrame({'datetime': dt}).sort_values('datetime').index.to_numpy()


# -- Config ----------------------------------------------------------------------------

def _num(v, key, minimum=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise KonfigFejl(f"'{key}' skal være et tal, men er: {v!r}")
    if minimum is not None and f < minimum:
        raise KonfigFejl(f"'{key}' skal være mindst {minimum}, men er: {v!r}")
    return f


def _int(v, key, minimum=None):
    f = _num(v, key, minimum)
    if f != int(f):
        raise KonfigFejl(f"'{key}' skal være et heltal, men er: {v!r}")
    return int(f)


def _str_list(v, key):
    if not isinstance(v, (list, tuple)) or not v or not all(isinstance(x, str) for x in v):
        raise KonfigFejl(f"'{key}' skal være en liste af tekster (kolonnenavne), men er: {v!r}")
    return [str(x).strip() for x in v]


FLAG_TYPES = ('afstand', 'projektion', 'stoprække')


def _flag_list(v, key):
    if v is None:
        return []
    if not isinstance(v, (list, tuple)) or not all(str(x).strip() in FLAG_TYPES for x in v):
        raise KonfigFejl(f"'{key}' skal være en liste med nogle af {list(FLAG_TYPES)}, men er: {v!r}")
    return [str(x).strip() for x in v]


def _range(v, key):
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        raise KonfigFejl(f"'{key}' skal være [min, max], fx [53, 58], men er: {v!r}")
    lo, hi = _num(v[0], key), _num(v[1], key)
    if lo >= hi:
        raise KonfigFejl(f"'{key}': min ({lo}) skal være mindre end max ({hi})")
    return [lo, hi]


def _percentiles(v, key):
    if not isinstance(v, (list, tuple)) or not v:
        raise KonfigFejl(f"'{key}' skal være en liste af tal mellem 0 og 100, fx [5, 50, 95]")
    out = [_num(x, key) for x in v]
    if any(x < 0 or x > 100 for x in out):
        raise KonfigFejl(f"'{key}' skal være tal mellem 0 og 100, men er: {v!r}")
    return out


def _bool(v, key):
    if isinstance(v, bool):
        return v
    raise KonfigFejl(f"'{key}' skal være true eller false, men er: {v!r}")


PARAM_CHECKS = {
    'buffer_rows': lambda v, k: _int(v, k, 0),
    'speed_max_kmh': lambda v, k: _num(v, k, 0),
    'speed_min_kmh': lambda v, k: _num(v, k),
    'stop_speed_kmh': lambda v, k: _num(v, k, 0),
    'stand_still_dist_m': lambda v, k: _num(v, k, 0),
    'max_match_distance_m': lambda v, k: _num(v, k, 0),
    'speed_nearest_pings': lambda v, k: _int(v, k, 1),
    'rising_count': lambda v, k: _int(v, k, 1),
    'rising_min_dist_m': lambda v, k: _num(v, k, 0),
    'min_rows_after_coarse_filter': lambda v, k: _int(v, k, 1),
    'ping_prefix': lambda v, k: str(v),
    'projection_value': lambda v, k: str(v),
    'date_columns': _str_list,
    'time_columns': _str_list,
    'lat_range': _range,
    'lon_range': _range,
    'chunk_size': lambda v, k: _int(v, k, 1000),
    'max_trips_rows_per_trip': lambda v, k: _int(v, k, 1),
    'summary_only_empty_log': _bool,
    'summary_exclude_flags': _flag_list,
    'quality_day_share': lambda v, k: _num(v, k, 0),
    'percentiles': _percentiles,
    'export_segments': _bool,
}


def load_config(config_path):
    """Indlaeser og validerer config.yaml. Stier gøres absolutte relativt til config-mappen.
    Manglende parametre faar standardvaerdi (v1's vaerdi) og logges.
    Returnerer cfg med nøglerne '_params' (alle parametre) og '_defaults_used'."""
    config_path = Path(config_path).resolve()
    if not config_path.exists():
        raise KonfigFejl(f"Config-fil ikke fundet: {config_path}")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise KonfigFejl(f"Config-filen er ikke gyldig YAML ({config_path.name}): {e}")
    if not isinstance(cfg, dict):
        raise KonfigFejl(f"Config-filen er tom eller har forkert format: {config_path.name}")

    base_dir = config_path.parent

    # Punkter
    points = cfg.get('points')
    if not isinstance(points, dict) or not points:
        raise KonfigFejl("Ingen punkter defineret: sektionen 'points' mangler eller er tom. "
                         "Mindst ét punkt kræves (id med lat, lon og evt. name).")
    names_seen = {}
    for pid, pt in points.items():
        if not isinstance(pt, dict) or pt.get('lat') is None or pt.get('lon') is None:
            raise KonfigFejl(f"Punkt '{pid}' mangler lat eller lon")
        pt['lat'] = _num(pt['lat'], f"points/{pid}/lat")
        pt['lon'] = _num(pt['lon'], f"points/{pid}/lon")
        name = str(pt.get('name', pid))
        if name in names_seen:
            raise KonfigFejl(f"Punkt '{pid}' og '{names_seen[name]}' har samme navn '{name}' - "
                             f"navne bruges som kolonnenavne i output og skal være unikke")
        names_seen[name] = pid

    # Parametre (standard + validering)
    params, defaults_used = {}, []
    for key, default in DEFAULTS.items():
        if key in cfg and cfg[key] is not None:
            params[key] = PARAM_CHECKS[key](cfg[key], key)
        else:
            params[key] = PARAM_CHECKS[key](default, key)
            defaults_used.append(key)
    unknown = [k for k in cfg if k not in DEFAULTS and k not in
               ('periods', 'data', 'points', 'point_order', 'distances', 'stops',
                'komfort')]  # komfort: laeses af komfort_v1.0.py
    if unknown:
        logger.warning(f"  ADVARSEL: ukendte nøgler i config ignoreres (stavefejl?): {', '.join(map(str, unknown))}")

    lat_lo, lat_hi = params['lat_range']
    lon_lo, lon_hi = params['lon_range']
    for pid, pt in points.items():
        if not (lat_lo <= pt['lat'] <= lat_hi):
            logger.warning(f"  ADVARSEL: Punkt {pid} lat={pt['lat']} er udenfor interval ({lat_lo:g}-{lat_hi:g}) - mulig typo?")
        if not (lon_lo <= pt['lon'] <= lon_hi):
            logger.warning(f"  ADVARSEL: Punkt {pid} lon={pt['lon']} er udenfor interval ({lon_lo:g}-{lon_hi:g}) - mulig typo?")

    # point_order
    point_order = cfg.get('point_order')
    if not isinstance(point_order, dict) or not point_order:
        raise KonfigFejl("Sektionen 'point_order' mangler. Angiv rækkefølgen af punkter pr. retning, fx "
                         "direction_1: [p1, p2] og direction_2: [p2, p1].")
    for direction, order in point_order.items():
        if not str(direction).startswith('direction_'):
            raise KonfigFejl(f"point_order/{direction}: nøglen skal hedde direction_1 eller direction_2")
        if not isinstance(order, list) or not order:
            raise KonfigFejl(f"point_order/{direction} skal være en ikke-tom liste af punkt-id'er")
        for pid in order:
            if pid not in points:
                raise KonfigFejl(f"point_order/{direction} refererer til '{pid}', som ikke er defineret i points")

    # distances (valgfri)
    distances = cfg.get('distances') or {}
    if not isinstance(distances, dict):
        raise KonfigFejl("'distances' skal være en liste af navngivne strækninger (d1, d2, ...) eller udelades")
    dist_names = {}
    for did, dist in distances.items():
        if not isinstance(dist, dict):
            raise KonfigFejl(f"Distance '{did}' skal have from og to")
        for k in ('from', 'to'):
            if dist.get(k) not in points:
                raise KonfigFejl(f"Distance '{did}': '{k}: {dist.get(k)}' er ikke defineret i points")
        nm = str(dist.get('name', did))
        if nm in dist_names:
            raise KonfigFejl(f"Distance '{did}' og '{dist_names[nm]}' har samme navn '{nm}' - navne skal være unikke")
        dist_names[nm] = did
    cfg['distances'] = distances

    # stops (kraeves for hver retning der har en point_order)
    stops = cfg.get('stops')
    if not isinstance(stops, dict):
        raise KonfigFejl("Sektionen 'stops' mangler. Den bruges til grovfilteret: angiv start- og slut-stop "
                         "(præcist stop-navn, se --list-stops) pr. retning.")
    for direction in point_order:
        s = stops.get(direction)
        if not isinstance(s, dict) or not s.get('start') or not s.get('end'):
            raise KonfigFejl(f"stops/{direction} mangler 'start' og/eller 'end' (præcist stop-navn fra data; "
                             f"find navne med --list-stops)")

    # data-stier
    data = cfg.get('data')
    if not isinstance(data, dict):
        raise KonfigFejl("Sektionen 'data' mangler (Periode_A/Periode_B med details_csv og list_csv).")
    for period_key in ['Periode_A', 'Periode_B']:
        if period_key in data:
            for file_key in ['details_csv', 'list_csv']:
                if file_key not in data[period_key]:
                    raise KonfigFejl(f"data/{period_key}/{file_key} mangler")
                data[period_key][file_key] = str(base_dir / str(data[period_key][file_key]))
    data['output'] = str(base_dir / str(data.get('output', 'output/result.csv')))

    # perioder
    periods = cfg.get('periods')
    if not isinstance(periods, dict) or not periods:
        raise KonfigFejl("Sektionen 'periods' mangler (A og/eller B med name, start og end).")
    for period_id, period_cfg in periods.items():
        try:
            s, e = pd.to_datetime(period_cfg['start']), pd.to_datetime(period_cfg['end'])
        except Exception:
            raise KonfigFejl(f"Periode {period_id} har ugyldig start/end (forventet ÅÅÅÅ-MM-DD): {period_cfg}")
        if s > e:
            raise KonfigFejl(f"Periode {period_id}: start ({period_cfg['start']}) ligger efter end ({period_cfg['end']})")
        period_cfg.setdefault('name', str(period_id))

    cfg['_params'] = params
    cfg['_defaults_used'] = defaults_used
    return cfg


# -- Kolonnetjek (kun header) ----------------------------------------------------------

def _read_header(path):
    try:
        return [str(c).strip() for c in pd.read_csv(path, sep=';', encoding='utf-8', nrows=0).columns]
    except Exception as e:
        raise KonfigFejl(f"Kan ikke læse headeren i {path}: {e}")


def check_columns(details_path, list_path, P):
    """Returnerer liste af fejltekster (tom = OK). Laeser kun headeren."""
    problems, warns = [], []
    dcols = set(_read_header(details_path))
    lcols = set(_read_header(list_path))

    miss = [COLUMNS['details'][k] for k in DETAILS_REQUIRED if COLUMNS['details'][k] not in dcols]
    if miss:
        problems.append(f"Details ({Path(details_path).name}): PÅKRÆVEDE kolonner mangler: " + ", ".join(miss))
    if not any(c in dcols for c in P['date_columns']):
        problems.append(f"Details ({Path(details_path).name}): ingen af datokolonnerne findes "
                        f"(mindst én påkrævet): " + ", ".join(P['date_columns']))
    if not any(c in dcols for c in P['time_columns']):
        problems.append(f"Details ({Path(details_path).name}): ingen af tidskolonnerne findes "
                        f"(mindst én påkrævet): " + ", ".join(P['time_columns']))
    for k in DETAILS_OPTIONAL:
        if COLUMNS['details'][k] not in dcols:
            warns.append(f"Details: valgfri kolonne mangler: {COLUMNS['details'][k]} (projektions-flag udelades)")
    for c in P['date_columns'] + P['time_columns']:
        if c not in dcols:
            warns.append(f"Details: kolonne fra prioritetskæden findes ikke og springes over: {c}")

    miss = [COLUMNS['list'][k] for k in LIST_REQUIRED if COLUMNS['list'][k] not in lcols]
    if miss:
        problems.append(f"List ({Path(list_path).name}): PÅKRÆVEDE kolonner mangler: " + ", ".join(miss))
    for k in LIST_OPTIONAL:
        if COLUMNS['list'][k] not in lcols:
            warns.append(f"List: valgfri kolonne mangler: {COLUMNS['list'][k]} (Køredag udelades)")
    return problems, warns


# -- Indlaesning -----------------------------------------------------------------------

def _read_csv_robust(path, wanted_cols, chunk_size, nrows=None):
    """Laeser kun oenskede kolonner (matchet paa strippet navn). Samme logik som v1."""
    wanted = {c.strip() for c in wanted_cols}
    header_df = pd.read_csv(path, sep=';', encoding='utf-8', nrows=0)
    actual_cols = [c for c in header_df.columns if c.strip() in wanted]
    if not actual_cols:
        raise KonfigFejl(f"Ingen af de ønskede kolonner fundet i {path}. "
                         f"Første 5 kolonner: {list(header_df.columns[:5])}")
    if nrows:
        df = pd.read_csv(path, sep=';', encoding='utf-8', usecols=actual_cols, nrows=nrows)
    else:
        chunks = []
        for chunk in pd.read_csv(path, sep=';', encoding='utf-8', usecols=actual_cols, chunksize=chunk_size):
            chunks.append(chunk)
        df = pd.concat(chunks, ignore_index=True)
        del chunks
    df.columns = df.columns.str.strip()
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].str.strip()
    return df


def _clean_frame(df):
    """Samme rensning som _read_csv_robust: strippede kolonnenavne og strippede tekstvaerdier."""
    df.columns = df.columns.str.strip()
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].str.strip()
    return df


def _valid_mask(chunk, P, p_start, p_end):
    """Raekker, som load_data beholder efter koordinat- og datofilteret (samme regler som v2.1),
    og som har en Turreference. Kun disse raekker taeller med i turens raekkenumre."""
    C = COLUMNS['details']
    ok = chunk[C['trip']].notna().to_numpy()
    for col in [C['lat'], C['lon']]:
        v = pd.to_numeric(chunk[col].astype(str).str.replace(',', '.', regex=False), errors='coerce')
        ok &= v.notna().to_numpy()
    avail = [c for c in P['date_columns'] if c in chunk.columns]
    dato = chunk[avail[0]].copy()
    for c in avail[1:]:
        dato = dato.combine_first(chunk[c])
    ok &= pd.to_datetime(dato, errors='coerce').between(p_start, p_end).to_numpy()
    return ok


class _TripCounter:
    """Giver hver gyldig raekke dens tur (loebenummer i foerste-forekomst-raekkefoelge) og dens
    raekkenummer i turen (0, 1, 2, ... i filens raekkefoelge), paa tvaers af bidder.
    Raekkenummeret er det samme som positionen i turen i v2.1's grovfilter."""

    def __init__(self, known=None):
        self.known = known            # gennemloeb 2: turene fra gennemloeb 1 (ingen nye tilladt)
        self.gid = dict(known) if known is not None else {}
        self.order = []
        self.counts = np.zeros(max(1024, len(self.gid)), dtype=np.int64)

    def ordinals(self, trips):
        codes, uniq = pd.factorize(trips)
        g = np.empty(len(uniq), dtype=np.int64)
        for i, u in enumerate(uniq):
            k = self.gid.get(u)
            if k is None:
                if self.known is not None:
                    raise RuntimeError(f"Intern fejl: tur {u!r} fandtes ikke i første gennemløb")
                k = len(self.order)
                self.gid[u] = k
                self.order.append(u)
            g[i] = k
        need = len(self.gid)
        if need > len(self.counts):
            self.counts = np.concatenate([self.counts, np.zeros(max(need, len(self.counts)), dtype=np.int64)])
        cum = pd.Series(codes).groupby(codes, sort=False).cumcount().to_numpy()
        rows_g = g[codes]
        ordn = self.counts[rows_g] + cum
        self.counts[g] += np.bincount(codes, minlength=len(uniq))
        return rows_g, ordn


def _trip_windows(details_path, list_lookup_dir, cfg, P, period_cfg, nrows):
    """Gennemloeb 1: find for hver tur det raekkevindue, v2.1's grovfilter ville bruge:
    [foerste forekomst af et af turens to stop - buffer_rows, sidste forekomst + buffer_rows],
    talt i turens gyldige raekker. Ture uden vindue (ingen retning, retning uden config,
    et stop mangler) faar vinduet [0, 0], saa kun deres foerste raekke beholdes, og de
    kasseres med samme aarsag som i v2.1. Returnerer (counter, lo, hi)."""
    C = COLUMNS['details']
    p_start, p_end = pd.to_datetime(period_cfg['start']), pd.to_datetime(period_cfg['end'])
    wanted = {C['trip'], C['stop_name'], C['lat'], C['lon']} | set(P['date_columns'])
    header = pd.read_csv(details_path, sep=';', encoding='utf-8', nrows=0).columns
    usecols = [c for c in header if c.strip() in wanted]

    stop_names = []
    for dk, sc in cfg['stops'].items():
        for k in ('start', 'end'):
            if sc[k] not in stop_names:
                stop_names.append(sc[k])
    name_idx = {n: i for i, n in enumerate(stop_names)}

    counter = _TripCounter()
    rec_g, rec_o, rec_n = [], [], []
    n_read = n_valid = 0
    for chunk in pd.read_csv(details_path, sep=';', encoding='utf-8', usecols=usecols,
                             chunksize=P['chunk_size'], nrows=nrows):
        chunk = _clean_frame(chunk)
        n_read += len(chunk)
        ok = _valid_mask(chunk, P, p_start, p_end)
        sub = chunk[ok]
        n_valid += len(sub)
        if not len(sub):
            continue
        rows_g, ordn = counter.ordinals(sub[C['trip']].to_numpy())
        names = sub[C['stop_name']]
        m = names.isin(stop_names).to_numpy()
        if m.any():
            rec_g.append(rows_g[m])
            rec_o.append(ordn[m])
            rec_n.append(np.array([name_idx[x] for x in names[m]], dtype=np.int64))

    n_trips = len(counter.order)
    counts = counter.counts[:n_trips]
    lo = np.zeros(n_trips, dtype=np.int64)
    hi = np.zeros(n_trips, dtype=np.int64)
    if n_trips == 0:
        return counter, lo, hi, n_read, n_valid, 0

    # Turens retning som i process_trip (Retningsflag fra List -> heltal -> direction_<n>)
    dir_keys = []
    for dk, sc in cfg['stops'].items():
        if cfg['point_order'].get(dk):
            dir_keys.append(dk)
    dk_idx = {dk: i for i, dk in enumerate(dir_keys)}
    trip_dir = np.full(n_trips, -1, dtype=np.int64)
    for t, raw in enumerate(pd.Series(counter.order, dtype=object).map(list_lookup_dir).tolist()):
        if raw is None or (not isinstance(raw, str) and pd.isna(raw)):
            continue
        d = _to_int(raw)
        if d is None:
            continue
        trip_dir[t] = dk_idx.get(f'direction_{d}', -1)

    has_s = np.zeros(n_trips, dtype=bool)
    has_e = np.zeros(n_trips, dtype=bool)
    rmin = np.full(n_trips, np.iinfo(np.int64).max, dtype=np.int64)
    rmax = np.full(n_trips, -1, dtype=np.int64)
    if rec_g:
        g = np.concatenate(rec_g)
        o = np.concatenate(rec_o)
        n = np.concatenate(rec_n)
        td = trip_dir[g]
        for dk, i in dk_idx.items():
            ns, ne = name_idx[cfg['stops'][dk]['start']], name_idx[cfg['stops'][dk]['end']]
            is_s = (td == i) & (n == ns)
            is_e = (td == i) & (n == ne)
            has_s[g[is_s]] = True
            has_e[g[is_e]] = True
            use = is_s | is_e
            np.minimum.at(rmin, g[use], o[use])
            np.maximum.at(rmax, g[use], o[use])
    win = has_s & has_e
    b = P['buffer_rows']
    lo[win] = np.maximum(0, rmin[win] - b)
    hi[win] = np.minimum(counts[win] - 1, rmax[win] + b)
    return counter, lo, hi, n_read, n_valid, int(win.sum())


def _normalize_times(tid):
    """HH / HH:MM / HH:MM:SS -> HH:MM:SS (samme regler som v1's _parse_time_str, men paa unikke vaerdier)."""
    uniq = tid.dropna().unique()
    mapping = {}
    for t in uniq:
        s = str(t).strip()
        parts = s.split(':')
        if len(parts) == 1:
            mapping[t] = s.zfill(2) + ':00:00'
        elif len(parts) == 2:
            mapping[t] = s + ':00'
        else:
            mapping[t] = s
    return tid.map(mapping)


class PeriodData:
    """Numpy-arrays for én periode (efter datofilter). Turenes raekker er i filens raekkefoelge."""


def load_data(details_path, list_path, period_cfg, P, cfg, max_trips=None):
    C = COLUMNS['details']
    size_mb = Path(details_path).stat().st_size / 1024 / 1024
    nrows = max_trips * P['max_trips_rows_per_trip'] if max_trips else None
    if nrows:
        logger.info(f"  (--max-trips {max_trips}: læser kun første ~{nrows:,} rækker)")

    logger.info(f"  Indlæser {Path(list_path).name}...")
    L = COLUMNS['list']
    lst = _read_csv_robust(list_path, [L[k] for k in LIST_REQUIRED + LIST_OPTIONAL], P['chunk_size'])
    logger.info(f"  List.csv: {len(lst):,} ture")
    lst_first = lst.drop_duplicates(L['trip'], keep='first').set_index(L['trip'])

    # v2.2: to gennemloeb i bidder. 1) find hver turs raekkevindue mellem de to stop.
    # 2) laes alle kolonner, men behold kun vinduernes raekker (stop-filteret i indlaesningen).
    logger.info(f"  Indlæser {Path(details_path).name} ({size_mb:.0f} MB), gennemløb 1 af 2 (stop pr. tur)...")
    t0 = time.time()
    counter, lo, hi, n_read, n_valid, n_win = _trip_windows(
        details_path, lst_first[L['direction']], cfg, P, period_cfg, nrows)
    logger.info(f"  Gennemløb 1: {n_read:,} rækker, {n_valid:,} med koordinat og dato i perioden, "
                f"{len(counter.order):,} ture, {n_win:,} med begge stop ({time.time() - t0:.1f}s)")

    t1 = time.time()
    logger.info("  Gennemløb 2 af 2 (kun rækker mellem de to stop + buffer_rows)...")
    p_start_, p_end_ = pd.to_datetime(period_cfg['start']), pd.to_datetime(period_cfg['end'])
    wanted = {c.strip() for c in [C[k] for k in DETAILS_REQUIRED + DETAILS_OPTIONAL] + P['date_columns'] + P['time_columns']}
    header = pd.read_csv(details_path, sep=';', encoding='utf-8', nrows=0).columns
    usecols = [c for c in header if c.strip() in wanted]
    counter2 = _TripCounter(known=counter.gid)
    kept = []
    for chunk in pd.read_csv(details_path, sep=';', encoding='utf-8', usecols=usecols,
                             chunksize=P['chunk_size'], nrows=nrows):
        chunk = _clean_frame(chunk)
        ok = _valid_mask(chunk, P, p_start_, p_end_)
        sub = chunk[ok]
        if not len(sub):
            continue
        rows_g, ordn = counter2.ordinals(sub[C['trip']].to_numpy())
        keep = (ordn >= lo[rows_g]) & (ordn <= hi[rows_g])
        if keep.any():
            kept.append(sub[keep])
    if not np.array_equal(counter2.counts[:len(counter.order)], counter.counts[:len(counter.order)]):
        raise RuntimeError("Intern fejl: de to gennemløb fandt forskellige rækker pr. tur")
    if kept:
        df = pd.concat(kept, ignore_index=True)
    else:
        df = pd.read_csv(details_path, sep=';', encoding='utf-8', usecols=usecols, nrows=0)
    del kept
    df = _clean_frame(df)
    logger.info(f"  Gennemløb 2: {len(df):,} rækker beholdt ({time.time() - t1:.1f}s)")

    # Ture i List i perioden pr. retning (til kvalitetsoversigten)
    p_start, p_end = pd.to_datetime(period_cfg['start']), pd.to_datetime(period_cfg['end'])
    sub = lst
    if L['day'] in lst.columns:
        kd = pd.to_datetime(lst[L['day']], errors='coerce')
        sub = lst[kd.between(p_start, p_end)]
    list_counts = defaultdict(int)
    for v in sub[L['direction']]:
        d = _to_int(v)
        list_counts[str(d) if d is not None else 'ukendt'] += 1

    # Tilknyt List-metadata via opslag (som v1)
    if lst[L['trip']].duplicated().any():
        logger.warning(f"  ADVARSEL: {int(lst[L['trip']].duplicated().sum())} dublet-Turnummer i List - første forekomst bruges")
        lst = lst.drop_duplicates(L['trip'], keep='first')
    lookup = lst.set_index(L['trip'])
    df['Retningsflag'] = df[C['trip']].map(lookup[L['direction']])
    df['Køredag'] = df[C['trip']].map(lookup[L['day']]) if L['day'] in lookup.columns else None

    # Koordinater (decimalkomma)
    for col in [C['lat'], C['lon']]:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.', regex=False), errors='coerce')
    df = df.dropna(subset=[C['lat'], C['lon']])

    # Dato/tid: foerste udfyldte i prioritetskaeden (som v1)
    avail_dates = [c for c in P['date_columns'] if c in df.columns]
    df['_Dato'] = df[avail_dates[0]].copy()
    for c in avail_dates[1:]:
        df['_Dato'] = df['_Dato'].combine_first(df[c])
    avail_times = [c for c in P['time_columns'] if c in df.columns]
    df['_Tid'] = df[avail_times[0]].copy()
    for c in avail_times[1:]:
        df['_Tid'] = df['_Tid'].combine_first(df[c])
    df['_Tid'] = _normalize_times(df['_Tid'])
    df['datetime'] = pd.to_datetime(df['_Dato'].astype(str) + ' ' + df['_Tid'].astype(str),
                                    format='%Y-%m-%d %H:%M:%S', errors='coerce')

    # Datofilter paa perioden
    mask = pd.to_datetime(df['_Dato'], errors='coerce').between(p_start, p_end)
    df = df[mask]
    logger.info(f"  Efter datofilter ({period_cfg['start']} til {period_cfg['end']}): {len(df):,} raekker")

    # Til numpy-arrays (sparer hukommelse og tid)
    D = PeriodData()
    D.lat = df[C['lat']].to_numpy(dtype=float)
    D.lon = df[C['lon']].to_numpy(dtype=float)
    D.dt = df['datetime'].to_numpy()
    codes, uniq = pd.factorize(df[C['stop_name']])
    D.name_codes = codes.astype(np.int32)
    D.name_uniques = list(uniq)
    D.name_to_code = {n: i for i, n in enumerate(D.name_uniques)}
    ping_by_code = np.array([isinstance(s, str) and s.startswith(P['ping_prefix']) for s in D.name_uniques] + [False])
    D.is_ping = ping_by_code[codes]  # kode -1 -> sidste element (False)

    sn = df[C['stop_nr']]
    D.stopnum_notna = sn.notna().to_numpy()
    if pd.api.types.is_numeric_dtype(sn):
        D.is_stop = D.stopnum_notna.copy()
    else:
        D.is_stop = np.zeros(len(df), dtype=bool)
        s = sn[D.stopnum_notna].astype(str).str.strip().str.lower()
        D.is_stop[D.stopnum_notna] = ~s.isin(['', 'nan']).to_numpy()

    D.proj = np.zeros(len(df), dtype=bool)
    if C['projection'] in df.columns:
        pj = df[C['projection']]
        nn = pj.notna().to_numpy()
        if nn.any():
            D.proj[nn] = (pj[nn].astype(str).str.strip() == P['projection_value']).to_numpy()

    D.day = df['Køredag'].to_numpy() if 'Køredag' in df.columns and df['Køredag'] is not None else np.full(len(df), None)
    D.dirflag = df['Retningsflag'].to_numpy()

    # v2.2: turenes raekkefoelge = foerste gyldige raekke i hele filen (fra gennemloeb 1), som i v2.1,
    # selv om turens foerste raekker ligger foer vinduet og ikke er indlaest.
    tcodes = pd.Categorical(df[C['trip']], categories=pd.Index(counter.order, dtype=object)).codes.astype(np.int64)
    tuniq = counter.order
    if len(df) and (tcodes < 0).any():
        raise RuntimeError("Intern fejl: række med tur, der ikke fandtes i første gennemløb")
    D.trip_ids = list(tuniq)                 # raekkefoelge = foerste forekomst (som groupby sort=False)
    order = np.argsort(tcodes, kind='stable')
    n_neg = int((tcodes < 0).sum())
    D.order = order[n_neg:]
    D.counts = np.bincount(tcodes[tcodes >= 0], minlength=len(D.trip_ids))
    D.starts = np.concatenate([[0], np.cumsum(D.counts)[:-1]])
    D.list_counts = dict(list_counts)
    del df
    return D


# -- Pipeline pr. tur ------------------------------------------------------------------

ST_FIRST, ST_STOPPESTED, ST_SKIP, ST_NOCOORD, ST_NOTIME, ST_STOP, ST_TIDSFEJL, ST_OVER, ST_UNDER, ST_OK = range(10)


def status_names(P):
    return ['Ingen tidligere række', 'Stoppested', 'SkipEfterstop', 'Manglende_koordinat', 'Manglende_tid',
            'Stop', 'Tidsfejl', f"Hastighed over {P['speed_max_kmh']}", f"Hastighed under {P['speed_min_kmh']}", 'OK']


def find_nearest_row(dists, start_idx, P):
    """Raekken med mindst afstand fra start_idx. Afbryder tidligt naar afstanden er steget
    `rising_count` gange (kumulativt, som v1) efter et minimum < rising_min_dist_m."""
    rc, rmd = P['rising_count'], P['rising_min_dist_m']
    min_dist = float('inf')
    min_pos = start_idx
    prev_dist = float('inf')
    rising = 0
    for k, dist in enumerate(dists[start_idx:].tolist()):
        i = start_idx + k
        if dist != dist:  # NaN
            continue
        if dist < min_dist:
            min_dist = dist
            min_pos = i
            rising = 0
        elif dist > prev_dist:
            rising += 1
            if rising >= rc and i > min_pos + rc and min_dist < rmd:
                break
        prev_dist = dist
    return min_pos, min_dist


def calculate_speeds(lat, lon, dt, is_stop, P):
    """Vektoriseret version af v1's calculate_speeds. Input skal vaere sorteret paa datetime.
    Returnerer (status[int8], distance_m, tdiff_h, speed_kmh_OK, raw_dist, raw_dt_s)."""
    n = len(lat)
    status = np.full(n, ST_FIRST, dtype=np.int8)
    dist_out = np.full(n, np.nan)
    tdiff_out = np.full(n, np.nan)
    speed_ok = np.full(n, np.nan)
    raw_dist = np.full(n, np.nan)
    raw_dt = np.full(n, np.nan)
    if n < 2:
        return status, dist_out, tdiff_out, speed_ok, raw_dist, raw_dt

    cur_stop, prev_stop = is_stop[1:], is_stop[:-1]
    la1, lo1, la2, lo2 = lat[:-1], lon[:-1], lat[1:], lon[1:]
    nocoord = np.isnan(la1) | np.isnan(lo1) | np.isnan(la2) | np.isnan(lo2)
    nat = np.isnat(dt[1:]) | np.isnat(dt[:-1])
    with np.errstate(invalid='ignore', divide='ignore'):
        dist = haversine_distance(la1, lo1, la2, lo2)
        diff_s = (dt[1:].astype('int64') - dt[:-1].astype('int64')) / 1e9
        diff_h = diff_s / 3600.0
        speed = (dist / 1000.0) / diff_h

    st = np.full(n - 1, ST_OK, dtype=np.int8)       # laveste prioritet foerst, overskrives opad
    st[speed < P['stop_speed_kmh']] = ST_STOP
    st[speed < P['speed_min_kmh']] = ST_UNDER
    st[speed > P['speed_max_kmh']] = ST_OVER
    st[diff_h == 0] = ST_STOP
    st[diff_h < 0] = ST_TIDSFEJL
    st[dist < P['stand_still_dist_m']] = ST_STOP
    st[nat] = ST_NOTIME
    st[nocoord] = ST_NOCOORD
    st[prev_stop & ~cur_stop] = ST_SKIP
    st[cur_stop] = ST_STOPPESTED
    status[1:] = st

    none_mask = np.isin(st, [ST_STOPPESTED, ST_SKIP, ST_NOCOORD, ST_NOTIME, ST_TIDSFEJL])
    d = np.where(dist < P['stand_still_dist_m'], 0.0, dist)
    # stillestaaende: v1 saetter distance=0.0 (men beholder tidsdiff); t_diff == 0: tidsdiff=0.0 (=diff_h)
    dist_out[1:] = np.where(none_mask, np.nan, d)
    tdiff_out[1:] = np.where(none_mask, np.nan, diff_h)
    ok = st == ST_OK
    with np.errstate(invalid='ignore', divide='ignore'):
        sp = (dist_out[1:] / 1000.0) / tdiff_out[1:]
    speed_ok[1:] = np.where(ok, sp, np.nan)
    raw_dist[1:] = dist
    raw_dt[1:] = np.where(nat, np.nan, diff_s)
    return status, dist_out, tdiff_out, speed_ok, raw_dist, raw_dt


def get_speed_at_point(lat, lon, status, speed_ok, tlat, tlon, k):
    """Laveste OK-hastighed blandt de k pings geografisk naermest punktet (som v1)."""
    d = haversine_distance(lat, lon, tlat, tlon)
    d = np.where(np.isnan(lat) | np.isnan(lon), np.inf, d)
    idx = np.argsort(d)[:k]
    vals = speed_ok[idx][status[idx] == ST_OK]
    vals = vals[~np.isnan(vals)]
    return float(vals.min()) if len(vals) else np.nan


def process_trip(D, ti, cfg, P, ctx):
    """Koerer hele pipelinen for én tur. Returnerer dict med 'rejected' eller 'row' (+ evt. data til debug/export)."""
    points = cfg['points']
    pos = D.order[D.starts[ti]: D.starts[ti] + D.counts[ti]]
    trip_ref = D.trip_ids[ti]
    first = pos[0]
    køredag = D.day[first]
    if køredag is not None and not isinstance(køredag, str) and pd.isna(køredag):
        køredag = None

    # Retning: første udfyldte Retningsflag i turen
    direction = None
    raw_dir = None
    for v in D.dirflag[pos]:
        if not pd.isna(v):
            raw_dir = v
            break
    if raw_dir is None:
        return {'rejected': {'Turreference': trip_ref, 'Årsag': 'ingen_retningsflag', 'Køredag': køredag},
                'direction': None}
    direction = _to_int(raw_dir)
    if direction is None:
        return {'rejected': {'Turreference': trip_ref, 'Årsag': 'ugyldigt_retningsflag', 'Køredag': køredag},
                'direction': None}
    dir_key = f'direction_{direction}'

    point_order_ids = cfg['point_order'].get(dir_key, [])
    if not point_order_ids:
        return {'rejected': {'Turreference': trip_ref, 'Årsag': f'ingen_point_order_{dir_key}',
                             'Retning': direction, 'Køredag': køredag}, 'direction': direction}

    def rej(reason):
        return {'rejected': {'Turreference': trip_ref, 'Årsag': reason, 'Retning': direction, 'Køredag': køredag},
                'direction': direction}

    # -- Fase 1: grovfilter ------------------------------------------------------
    stops_cfg = cfg['stops']
    if dir_key not in stops_cfg:
        return rej(f"ingen_stops_konfigureret_{dir_key}")
    s_start, s_end = stops_cfg[dir_key]['start'], stops_cfg[dir_key]['end']
    codes = D.name_codes[pos]
    cs, ce = D.name_to_code.get(s_start), D.name_to_code.get(s_end)
    idx_s = np.flatnonzero(codes == cs) if cs is not None else np.array([], dtype=int)
    idx_e = np.flatnonzero(codes == ce) if ce is not None else np.array([], dtype=int)
    if len(idx_s) == 0 or len(idx_e) == 0:
        return rej('stop_ikke_fundet')
    row_start = min(idx_s.min(), idx_e.min())
    row_end = max(idx_s.max(), idx_e.max())
    b = P['buffer_rows']
    p0 = max(0, row_start - b)
    p1 = min(len(pos) - 1, row_end + b)
    fpos = pos[p0:p1 + 1]
    if len(fpos) < P['min_rows_after_coarse_filter']:
        return rej('for_faa_raekker_efter_stop_filter')
    if not D.is_ping[fpos].any():
        return rej('ingen_gps_trackpoints')

    fpos = fpos[_argsort_dt(D.dt[fpos])]
    flat, flon, fdt = D.lat[fpos], D.lon[fpos], D.dt[fpos]
    fstop, fproj = D.is_stop[fpos], D.proj[fpos]

    # -- Fase 2: punkt-match -----------------------------------------------------
    match = {}   # pid -> dict(row_pos, distance_m)
    search_start = 0
    for pid in point_order_ids:
        pt = points[pid]
        d = haversine_distance(flat, flon, pt['lat'], pt['lon'])
        mpos, mdist = find_nearest_row(d, search_start, P)
        match[pid] = {'row_pos': mpos, 'distance_m': mdist}
        search_start = mpos
    for pid in [p for p in ctx['dist_pids'] if p not in point_order_ids]:
        if pid in match:
            continue
        pt = points[pid]
        d = haversine_distance(flat, flon, pt['lat'], pt['lon'])
        d = np.where(np.isnan(flat) | np.isnan(flon), np.inf, d)
        mpos = int(np.argmin(d))
        match[pid] = {'row_pos': mpos, 'distance_m': float(d[mpos])}
    for pid, m in match.items():
        m['datetime'] = fdt[m['row_pos']]
        m['is_stop_row'] = bool(fstop[m['row_pos']])
        m['projection'] = bool(fproj[m['row_pos']])

    # -- Fase 3: kvalitetstjek (v1: afstand i Log; raekkefoelge/ikke_fundet er i praksis doede) --
    issues = []
    for pid in point_order_ids:
        if pid not in match:
            issues.append(f"punkt_{pid}_ikke_fundet")
    positions = [match[pid]['row_pos'] for pid in point_order_ids if pid in match]
    if positions != sorted(positions):
        issues.append("punkt_rækkefølge_forkert")
    for pid, m in match.items():
        if m['distance_m'] > P['max_match_distance_m']:
            issues.append(f"punkt_{pid}_afstand_høj_{m['distance_m']:.0f}m")
    fatal = [i for i in issues if 'ikke_fundet' in i or 'rækkefølge_forkert' in i]
    if fatal:
        return rej('; '.join(issues))
    non_fatal = issues

    # -- Fase 4: udtraek + buffer ------------------------------------------------
    ordered_positions = [match[pid]['row_pos'] for pid in point_order_ids]
    seg_start = max(0, min(ordered_positions) - b)
    seg_end = min(len(fpos) - 1, max(ordered_positions) + b)
    sl = slice(seg_start, seg_end + 1)
    spos = fpos[sl]
    # Fase 5 sorterer segmentet igen paa datetime (som v1)
    sperm = _argsort_dt(D.dt[spos])
    spos = spos[sperm]
    slat, slon, sdt, sstop = D.lat[spos], D.lon[spos], D.dt[spos], D.is_stop[spos]

    status, dist_out, tdiff_out, speed_ok, raw_dist, raw_dt = calculate_speeds(slat, slon, sdt, sstop, P)
    for pid, m in match.items():
        pt = points[pid]
        m['speed'] = get_speed_at_point(slat, slon, status, speed_ok, pt['lat'], pt['lon'], P['speed_nearest_pings'])

    # -- Fase 6: koeretider ------------------------------------------------------
    travel = {}
    for did, dcfg in cfg['distances'].items():
        nm = str(dcfg.get('name', did))
        fp, tp = dcfg['from'], dcfg['to']
        if fp in match and tp in match:
            tf, tt = match[fp]['datetime'], match[tp]['datetime']
            if not (np.isnat(tf) or np.isnat(tt)):
                seconds = abs((tt.astype('int64') - tf.astype('int64')) / 1e9)
                travel[nm] = int(round(seconds))
            else:
                travel[nm] = None
        else:
            travel[nm] = None

    # -- Fase 7: output-raekke ---------------------------------------------------
    row = {'Turreference': trip_ref, 'Køredag': køredag, 'Periode': ctx['period_name'], 'Retning': direction}
    flags = []
    for pid, m in match.items():
        name = str(points[pid].get('name', pid))
        row[f'{name} - nærmeste afstand (m)'] = round(m['distance_m'], 1)
        row[f'{name} - projektion'] = m['projection']
        row[f'{name} - hastighed (km/t)'] = round(float(m['speed']), 1) if pd.notna(m['speed']) else None
        m['flags'] = []
        if m['distance_m'] > P['max_match_distance_m']:
            m['flags'].append('afstand')
        if m['projection']:
            m['flags'].append('projektion')
        if m['is_stop_row']:
            m['flags'].append('stoprække')
        flags += [f'{f}_{pid}' for f in m['flags']]
    for nm, secs in travel.items():
        row[f'{nm} - køretid (sek)'] = secs
    cnt = np.bincount(status, minlength=10)
    row['Antal Stop'] = int(cnt[ST_STOP])
    row['Antal Stoppested'] = int(cnt[ST_STOPPESTED])
    row['Antal SkipEfterstop'] = int(cnt[ST_SKIP])
    row['Antal Tidsfejl'] = int(cnt[ST_TIDSFEJL])
    row['Antal Hastighed over max'] = int(cnt[ST_OVER])
    row['Antal Hastighed under 0'] = int(cnt[ST_UNDER])
    row['Log'] = '; '.join(non_fatal) if non_fatal else ''
    row['Flag'] = '; '.join(flags)

    return {'row': row, 'direction': direction, 'match': match, 'flags': flags,
            'filtered': {'pos': fpos, 'lat': flat, 'lon': flon, 'dt': fdt, 'stop': fstop, 'proj': fproj},
            'segment': {'pos': spos, 'lat': slat, 'lon': slon, 'dt': sdt, 'stop': sstop, 'status': status,
                        'dist': dist_out, 'speed': speed_ok, 'raw_dist': raw_dist, 'raw_dt': raw_dt},
            'travel': travel, 'issues': non_fatal, 'køredag': køredag}


# -- Debug / inspect / eksport ---------------------------------------------------------

def _segment_frame(D, res, period_name, cfg, P):
    seg = res['segment']
    names = np.array(status_names(P), dtype=object)
    n = len(seg['lat'])
    with np.errstate(invalid='ignore', divide='ignore'):
        speed = np.where((seg['raw_dt'] > 0), (seg['raw_dist'] / 1000.0) / (seg['raw_dt'] / 3600.0), np.nan)
    match_pts = np.full(n, '', dtype=object)
    # markér hvilke pings der blev matchet til et punkt (position i det fulde, sorterede udsnit -> findes via pos)
    fpos = res['filtered']['pos']
    pos_to_i = {int(p): i for i, p in enumerate(seg['pos'])}
    for pid, m in res['match'].items():
        gp = int(fpos[m['row_pos']])
        i = pos_to_i.get(gp)
        if i is not None:
            match_pts[i] = (match_pts[i] + ';' if match_pts[i] else '') + pid
    return pd.DataFrame({
        'Turreference': res['row']['Turreference'], 'Periode': period_name,
        'Retning': res['direction'], 'Køredag': res['køredag'],
        'datetime': pd.to_datetime(seg['dt']).strftime('%Y-%m-%d %H:%M:%S'),
        'lat': seg['lat'], 'lon': seg['lon'],
        'afstand_til_forrige_m': np.round(seg['raw_dist'], 2),
        'tid_til_forrige_s': seg['raw_dt'],
        'hastighed_kmh': np.round(speed, 2),
        'status': names[seg['status']],
        'er_stoprække': seg['stop'].astype(int),
        'Projektion': np.where(D.proj[seg['pos']], P['projection_value'], ''),
        'match_punkt': match_pts,
    })


def _save_inspect(D, res, period_name, cfg, P, output_dir):
    """Gemmer mellemliggende data for én tur til <output>/inspect/<tur>/ (som v1)."""
    trip_ref = res['row']['Turreference']
    d = Path(output_dir) / 'inspect' / str(trip_ref)
    d.mkdir(parents=True, exist_ok=True)
    f = res['filtered']
    f1 = pd.DataFrame({'Stop-navn': [D.name_uniques[c] if c >= 0 else None for c in D.name_codes[f['pos']]],
                       'lat': f['lat'], 'lon': f['lon'], 'datetime': f['dt'],
                       'er_stoprække': f['stop'], 'Projektion': f['proj']})
    for pid, pt in cfg['points'].items():
        nm = pt.get('name', pid)
        f1[f'afstand til {nm} (m)'] = np.round(haversine_distance(f['lat'], f['lon'], pt['lat'], pt['lon']), 1)
        f1[f'fase2_match_{pid}'] = ''
        if pid in res['match']:
            rp = res['match'][pid]['row_pos']
            f1.at[rp, f'fase2_match_{pid}'] = f"VALGT (fase2: {round(res['match'][pid]['distance_m'], 1)}m)"
    f1.to_csv(d / 'fase1_filtered.csv', index=True, sep=';', encoding='utf-8')
    pd.DataFrame([{'punkt_id': pid, 'row_pos': m['row_pos'], 'distance_m': round(m['distance_m'], 1),
                   'datetime': m['datetime'], 'er_stoprække': m['is_stop_row'], 'projektion': m['projection']}
                  for pid, m in res['match'].items()]).to_csv(d / 'fase2_matches.csv', index=False, sep=';', encoding='utf-8')
    with open(d / 'fase3_quality.txt', 'w', encoding='utf-8') as fh:
        fh.write(f"Tur: {trip_ref}  Retning: {res['direction']}\nIssues: {res['issues'] if res['issues'] else 'ingen'}\n"
                 f"Flag: {res['flags'] if res['flags'] else 'ingen'}\n")
    _segment_frame(D, res, period_name, cfg, P).to_csv(d / 'fase5_speeds.csv', index=True, sep=';', encoding='utf-8')
    with open(d / 'fase6_travel_times.txt', 'w', encoding='utf-8') as fh:
        for name, secs in res['travel'].items():
            fh.write(f"{name}: {secs} sek\n")
    logger.info(f"  [inspect-trip {trip_ref}] Gemt til: {d}")


# -- Hoved-pipeline pr. periode ---------------------------------------------------------

def process_period(cfg, period_id, period_cfg, data_cfg, args, output_dir, quality, seg_writer):
    P = cfg['_params']
    period_label = f"[Periode {period_id}]"
    period_name = period_cfg['name']
    logger.info(f"\n{'=' * 60}\n{period_label} {period_name}\n{'=' * 60}")

    details_path, list_path = data_cfg['details_csv'], data_cfg['list_csv']
    t0 = time.time()
    D = load_data(details_path, list_path, period_cfg, P, cfg, max_trips=args.max_trips)
    logger.info(f"{period_label} Indlæst på {time.time() - t0:.1f}s")

    for k, v in D.list_counts.items():
        quality.add(period_name, k, 'ture_i_list', n=v)

    all_trips = list(range(len(D.trip_ids)))
    if args.max_trips:
        all_trips = all_trips[:args.max_trips]
        logger.info(f"{period_label} --max-trips: behandler kun {len(all_trips)} ture")
    logger.info(f"{period_label} Fase 1-7: {len(all_trips):,} ture")

    distances = cfg['distances']
    dist_pids = []   # punkter brugt i distances; ekstra (ikke i turens point_order) fuld-scannes i process_trip
    for dcfg in distances.values():
        for k in ('from', 'to'):
            if dcfg[k] not in dist_pids:
                dist_pids.append(dcfg[k])
    ctx = {'period_name': period_name, 'dist_pids': dist_pids}

    out_rows, rejected = [], []
    phase1_debug, phase2_debug, phase5_stats = [], [], []
    inspect_trip = getattr(args, 'inspect_trip', None)
    inspect_n = getattr(args, 'inspect_n', None)
    inspect_count = 0
    sev_fatal = 0

    t1 = time.time()
    trip_iter = tqdm(all_trips, desc=f"  {period_label}", unit="ture", ncols=80) if TQDM_AVAILABLE else all_trips
    log_every = max(1, len(all_trips) // 20)
    for n_done, ti in enumerate(trip_iter):
        if not TQDM_AVAILABLE and n_done > 0 and n_done % log_every == 0:
            el = time.time() - t1
            eta = (len(all_trips) - n_done) / (n_done / el) if el > 0 else 0
            logger.info(f"  {period_label} {n_done:,}/{len(all_trips):,} ({n_done / len(all_trips) * 100:.0f}%) - ETA {eta:.0f}s")

        res = process_trip(D, ti, cfg, P, ctx)
        direction = res['direction']
        dir_label = str(direction) if direction is not None else 'ukendt'
        quality.add(period_name, dir_label, 'ture_i_details')

        if 'rejected' in res:
            rej = res['rejected']
            rejected.append(rej)
            quality.add(period_name, dir_label, 'kasseret', aarsag=rej['Årsag'])
            if 'punkt_' in rej['Årsag']:
                sev_fatal += 1
            continue

        quality.add(period_name, dir_label, 'beholdt')
        for pid, m in res['match'].items():
            for fl in m['flags']:
                quality.add(period_name, dir_label, 'flag', aarsag=fl, punkt=pid)
        if res['flags']:
            quality.add(period_name, dir_label, 'flag', aarsag='mindst_ét_flag')
        out_rows.append(res['row'])

        if args.debug:
            f = res['filtered']
            dts = pd.Series(f['dt'])
            phase1_debug.append({
                'Turreference': res['row']['Turreference'], 'Retning': direction, 'Køredag': res['køredag'],
                'Antal_rækker': len(f['pos']), 'Første_tid': dts.min(), 'Sidste_tid': dts.max(),
                'Antal_GPS': int((~D.is_stop[f['pos']]).sum()),
                'Antal_stop': int(D.stopnum_notna[f['pos']].sum()),
            })
            for pid, m in res['match'].items():
                phase2_debug.append({
                    'Turreference': res['row']['Turreference'], 'Retning': direction, 'punkt_id': pid,
                    'punkt_navn': cfg['points'][pid].get('name', pid), 'row_pos': m['row_pos'],
                    'distance_m': round(m['distance_m'], 1), 'datetime': m['datetime']})
            cnt = np.bincount(res['segment']['status'], minlength=10)
            phase5_stats.append({
                'Turreference': res['row']['Turreference'], 'Retning': direction, 'Køredag': res['køredag'],
                'n_raekker': len(res['segment']['lat']), 'n_OK': int(cnt[ST_OK]), 'n_Stop': int(cnt[ST_STOP]),
                'n_Stoppested': int(cnt[ST_STOPPESTED]), 'n_SkipEfterstop': int(cnt[ST_SKIP]),
                'n_Tidsfejl': int(cnt[ST_TIDSFEJL]), 'n_Hastighed_over': int(cnt[ST_OVER]),
                'n_Manglende': int(cnt[ST_NOTIME] + cnt[ST_NOCOORD])})

        trip_str = str(res['row']['Turreference'])
        if (inspect_trip and trip_str == str(inspect_trip)) or (inspect_n and inspect_count < inspect_n):
            _save_inspect(D, res, period_name, cfg, P, output_dir)
            inspect_count += 1

        if seg_writer is not None:
            seg_writer.write(_segment_frame(D, res, period_name, cfg, P))

    logger.info(f"\n{period_label} Færdig: {len(out_rows):,} ture OK, {len(rejected):,} kasseret | {time.time() - t1:.1f}s")
    reasons = defaultdict(int)
    for r in rejected:
        reasons[r['Årsag']] += 1
    for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
        logger.info(f"  - {k}: {v:,}")

    for r in rejected:
        r['Periode'] = period_name

    if args.debug:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        for fname, rows in [(f'debug_phase1_trips_{period_id}.csv', phase1_debug),
                            (f'debug_phase2_matches_{period_id}.csv', phase2_debug),
                            (f'debug_phase5_stats_{period_id}.csv', phase5_stats)]:
            if rows:
                pd.DataFrame(rows).to_csv(out_path / fname, index=False, sep=';', encoding='utf-8')
                logger.info(f"  Debug: {out_path / fname}")
        if rejected:
            pd.DataFrame([{k: v for k, v in r.items() if k != 'Periode'} for r in rejected]).to_csv(
                out_path / f'debug_rejected_{period_id}.csv', index=False, sep=';', encoding='utf-8')
            logger.info(f"  Debug: {out_path / f'debug_rejected_{period_id}.csv'}")
    return out_rows, rejected




# -- Kvalitetsoversigt -----------------------------------------------------------------

class QualityCounters:
    """Taeller (periode, retning, kategori, aarsag, punkt) -> antal."""

    def __init__(self):
        self.c = defaultdict(int)

    def add(self, periode, retning, kategori, aarsag='', punkt='', n=1):
        self.c[(periode, str(retning), kategori, aarsag, punkt)] += n

    def to_frame(self):
        rows = [dict(zip(['Periode', 'Retning', 'Kategori', 'Årsag', 'Punkt', 'Antal'], k + (v,)))
                for k, v in sorted(self.c.items())]
        return pd.DataFrame(rows, columns=['Periode', 'Retning', 'Kategori', 'Årsag', 'Punkt', 'Antal'])


def _day_table(rej, kept_rows):
    """v2.1: beholdt/kasseret pr. periode og koeredag (kasseret ogsaa pr. aarsag)."""
    keys = ['Periode', 'Køredag']
    kept = pd.DataFrame(kept_rows, columns=keys)
    k = kept.groupby(keys).size().rename('beholdt').reset_index()
    if len(rej):
        r = (rej.assign(Årsag='kasseret: ' + rej['Årsag'].astype(str))
             .groupby(keys + ['Årsag']).size().unstack(fill_value=0).reset_index())
        r.columns.name = None
    else:
        r = pd.DataFrame(columns=keys)
    # merge (ikke concat): virker ogsaa naar en eller begge sider er tomme
    t = k.merge(r, on=keys, how='outer')
    kas = sorted(c for c in t.columns if str(c).startswith('kasseret: '))
    t[['beholdt'] + kas] = t[['beholdt'] + kas].fillna(0).astype(int)
    t['kasseret'] = t[kas].sum(axis=1) if kas else 0
    tot = t['kasseret'] + t['beholdt']
    t['kasseret_andel'] = (t['kasseret'] / tot.where(tot > 0)).round(3)
    t = t.sort_values(keys).reset_index(drop=True)
    return t[keys + ['beholdt', 'kasseret', 'kasseret_andel'] + kas]


def _date_runs(dates):
    """Sorterede datoer -> 'fra–til (n dage)'-tekster for sammenhaengende kalenderdage."""
    ds = sorted(pd.to_datetime(pd.Series(dates)).dt.date.unique())
    runs, start, prev = [], None, None
    for d in ds:
        if start is None:
            start = prev = d
        elif (d - prev).days == 1:
            prev = d
        else:
            runs.append((start, prev))
            start = prev = d
    if start is not None:
        runs.append((start, prev))
    return [f"{a}" + (f" – {b}" if b != a else "") + f" ({(b - a).days + 1} dage)" for a, b in runs]


def write_quality(quality, cfg, out_dir, rejected_all, args, kept_rows=None):
    P = cfg['_params']
    df = quality.to_frame()
    df.to_csv(Path(out_dir) / 'kvalitet.csv', index=False, sep=';', encoding='utf-8')
    rej = pd.DataFrame(rejected_all, columns=['Turreference', 'Køredag', 'Retning', 'Årsag', 'Periode'])
    rej.to_csv(Path(out_dir) / 'kasserede_ture.csv', index=False, sep=';', encoding='utf-8')
    days = _day_table(rej, kept_rows or [])
    days.to_csv(Path(out_dir) / 'kvalitet_pr_dag.csv', index=False, sep=';', encoding='utf-8')

    points = cfg['points']
    lines = ["# Datakvalitet", "",
             f"Genereret af analyse_v{VERSION}. Config: `{cfg.get('_config_path', '')}`.", ""]
    if args.max_trips:
        lines += [f"> OBS: kørt med --max-trips {args.max_trips}. 'Ture i List' tæller hele List-filen, "
                  f"men 'ture med rækker i Details' er kun de første {args.max_trips} ture.", ""]
    lines += ["Kolonner = retning (retning fra List.csv; 'ukendt' = tur uden retningsflag). "
              "Flag tælles pr. beholdt tur og punkt; en tur kan have flere flag. "
              "`stoprække` = det matchede ping er en stop-række (planlagt position, Stop-nummer udfyldt).", ""]
    for periode in df['Periode'].unique():
        sub = df[df['Periode'] == periode]
        dirs = sorted(sub['Retning'].unique(), key=lambda x: (x == 'ukendt', x))

        def row(label, kat, aarsag=None, punkt=None):
            s = sub[sub['Kategori'] == kat]
            if aarsag is not None:
                s = s[s['Årsag'] == aarsag]
            if punkt is not None:
                s = s[s['Punkt'] == punkt]
            vals = [int(s[s['Retning'] == d]['Antal'].sum()) for d in dirs]
            return f"| {label} | " + " | ".join(str(v) for v in vals) + f" | {sum(vals)} |"

        lines += [f"## Periode: {periode}", "",
                  "| | " + " | ".join(f"Retning {d}" for d in dirs) + " | I alt |",
                  "|---|" + "---:|" * (len(dirs) + 1),
                  row("Ture i List i perioden", 'ture_i_list'),
                  row("Ture med rækker i Details", 'ture_i_details'),
                  row("**Beholdt**", 'beholdt')]
        reasons = sorted(sub[sub['Kategori'] == 'kasseret']['Årsag'].unique())
        lines.append(row("**Kasseret i alt**", 'kasseret'))
        for r in reasons:
            lines.append(row(f"- kasseret: {r}", 'kasseret', r))
        for fl, lab in [('afstand', f"afstand > {P['max_match_distance_m']:g} m"), ('projektion', 'projektion'),
                        ('stoprække', 'stoprække (planlagt position)')]:
            pids = sorted(sub[(sub['Kategori'] == 'flag') & (sub['Årsag'] == fl)]['Punkt'].unique())
            for pid in pids:
                lines.append(row(f"- flag {lab}: {points[pid].get('name', pid)} ({pid})", 'flag', fl, pid))
        lines.append(row("Beholdte ture med mindst ét flag", 'flag', 'mindst_ét_flag', ''))
        lines.append("")
        # v2.1: dage - hvor mange dage bidrager, og hvilke dage er (naesten) helt kasseret?
        dsub = days[days['Periode'] == periode]
        if len(dsub):
            share = P['quality_day_share']
            bad = dsub[dsub['kasseret_andel'] >= share]
            lines += [f"**Dage:** {int((dsub['beholdt'] > 0).sum())} dage med beholdte ture, "
                      f"{int(((dsub['beholdt'] == 0) & (dsub['kasseret'] > 0)).sum())} dage med kun kasserede ture. "
                      f"Dage med kasseret-andel ≥ {share:.0%}: {len(bad)}"
                      + (" — " + "; ".join(_date_runs(bad['Køredag'])) if len(bad) else "") + ".",
                      "Pr. dag: `kvalitet_pr_dag.csv`. Mange dage i træk med høj kasseret-andel tyder på "
                      "omkørsel eller ændret stopnavn — tjek før perioderne sammenlignes.", ""]
    with open(Path(out_dir) / 'kvalitet.md', 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))


# -- Eksport af segment-pings -----------------------------------------------------------

class SegmentWriter:
    def __init__(self, path):
        self.path = Path(path)
        self.first = True
        self.n = 0

    def write(self, frame):
        frame.to_csv(self.path, mode='w' if self.first else 'a', header=self.first,
                     index=False, sep=';', encoding='utf-8', float_format='%.6f')
        self.first = False
        self.n += len(frame)


# -- Percentil-opsummering ---------------------------------------------------------------

def build_summary(result_df, cfg):
    P = cfg['_params']
    pcts = P['percentiles']
    df = result_df
    if P['summary_only_empty_log']:
        df = df[df['Log'].fillna('') == '']
    for fl in P['summary_exclude_flags']:
        # Flag-tokens er '<type>_<punkt>' adskilt af ', ' (fx 'stoprække_p3')
        df = df[~df['Flag'].fillna('').str.contains(rf'(?:^|[ ,]){fl}_', regex=True)]
    rows = []
    items = []
    for did, dcfg in cfg['distances'].items():
        nm = str(dcfg.get('name', did))
        items.append(('køretid_sek', nm, f'{nm} - køretid (sek)'))
    for pid, pt in cfg['points'].items():
        nm = str(pt.get('name', pid))
        items.append(('hastighed_kmh', nm, f'{nm} - hastighed (km/t)'))
    for (periode, retning), g in df.groupby(['Periode', 'Retning'], sort=True):
        for typ, nm, col in items:
            if col not in g.columns:
                continue
            v = pd.to_numeric(g[col], errors='coerce').dropna()
            r = {'Periode': periode, 'Retning': retning, 'Type': typ, 'Navn': nm, 'n': int(len(v))}
            for p in pcts:
                r[f'p{p:g}'] = round(float(np.percentile(v, p)), 1) if len(v) else None
            rows.append(r)
    return pd.DataFrame(rows)


# -- --list-stops -----------------------------------------------------------------------

def list_stops_cmd(cfg):
    data_cfg = cfg['data']
    all_stops = set()
    for period_key in ['Periode_A', 'Periode_B']:
        if period_key not in data_cfg:
            continue
        path = data_cfg[period_key]['details_csv']
        if not Path(path).exists():
            logger.warning(f"Fil ikke fundet: {path}")
            continue
        logger.info(f"Indlæser stop-navne fra {Path(path).name}...")
        col = COLUMNS['details']['stop_name']
        header_df = pd.read_csv(path, sep=';', encoding='utf-8', nrows=0)
        actual = [c for c in header_df.columns if c.strip() == col]
        if not actual:
            logger.error(f"Kolonnen '{col}' findes ikke i {path}")
            continue
        # v2.2: i bidder, saa store filer ikke fylder hukommelsen
        for chunk in pd.read_csv(path, sep=';', encoding='utf-8', usecols=actual,
                                 chunksize=cfg['_params']['chunk_size']):
            s = chunk[actual[0]].dropna().astype(str).str.strip()
            all_stops.update(x for x in s.unique() if x)
    print(f"\n=== {len(all_stops)} unikke stop-navne ===")
    for s in sorted(all_stops):
        print(f"  {s}")


# -- Main ------------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        description='GPS Busdata Tids-analyse - måler køretid og hastighed pr. strækning',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Eksempler:
  python analyse_v2.2.py --config config_3A.yaml --list-stops
  python analyse_v2.2.py --config config_3A.yaml --max-trips 300 --debug
  python analyse_v2.2.py --config config_3A.yaml --period B --export-segments
        """)
    parser.add_argument('--config', required=True, help='Sti til config.yaml')
    parser.add_argument('--debug', action='store_true', help='Gem debug-filer (debug_phase1/2/5/rejected_*.csv)')
    parser.add_argument('--max-trips', type=int, default=None, metavar='N', help='Behandl kun første N ture (til test)')
    parser.add_argument('--list-stops', action='store_true', help='Print unikke stop-navne fra data og afslut')
    parser.add_argument('--period', choices=['A', 'B', 'both'], default='both', help='Kør kun én periode (default: both)')
    parser.add_argument('--inspect-trip', metavar='TRIP_ID', default=None,
                        help='Gem alle pipeline-steps for én tur til <output>/inspect/')
    parser.add_argument('--inspect-n', type=int, default=None, metavar='N',
                        help='Gem pipeline-steps for de første N godkendte ture til <output>/inspect/')
    parser.add_argument('--export-segments', action='store_true',
                        help='Gem alle pings i hver turs segment til segmenter.csv (til komfortmål mv.)')
    parser.add_argument('--output-dir', default=None, metavar='MAPPE',
                        help='Skriv alt output hertil i stedet for mappen fra config (data/output)')
    return parser


def run(args):
    cfg = load_config(args.config)
    cfg['_config_path'] = str(Path(args.config).resolve())
    P = cfg['_params']

    output_path = Path(cfg['data']['output'])
    if args.output_dir:
        out_dir = Path(args.output_dir).resolve()
        output_path = out_dir / output_path.name
    else:
        out_dir = output_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(args.debug, out_dir / 'analyse_log.txt')

    logger.info(f"=== GPS Busdata Tids-analyse v{VERSION} ===")
    logger.info(f"Config: {cfg['_config_path']}")
    if cfg['_defaults_used']:
        logger.info("Standardværdier brugt (ikke sat i config): " +
                    ", ".join(f"{k}={P[k]!r}" for k in cfg['_defaults_used']))
    else:
        logger.info("Alle parametre er sat i config.")

    if args.list_stops:
        list_stops_cmd(cfg)
        return 0

    if args.period == 'both':
        run_ids = ['A', 'B']
    else:
        run_ids = [args.period]
    periods, data = cfg['periods'], cfg['data']
    todo = []
    for pid in run_ids:
        if pid not in periods or f'Periode_{pid}' not in data:
            if args.period != 'both':
                raise KonfigFejl(f"Periode {pid} er ikke defineret i config (kræver både periods/{pid} og data/Periode_{pid})")
            logger.warning(f"Periode {pid} ikke defineret i config - springer over")
            continue
        todo.append(pid)
    if not todo:
        raise KonfigFejl("Ingen perioder at køre (periods og data/Periode_A/B mangler i config)")

    # Kolonnetjek af alle filer foer tung indlaesning
    all_problems = []
    for pid in todo:
        d = data[f'Periode_{pid}']
        for key in ('details_csv', 'list_csv'):
            if not Path(d[key]).exists():
                all_problems.append(f"Periode {pid}: filen findes ikke: {d[key]}")
        if all(Path(d[k]).exists() for k in ('details_csv', 'list_csv')):
            problems, warns = check_columns(d['details_csv'], d['list_csv'], P)
            all_problems += [f"Periode {pid}: {p}" for p in problems]
            for w in warns:
                logger.warning(f"  ADVARSEL (periode {pid}): {w}")
    if all_problems:
        raise KonfigFejl("Kolonne-/filtjek fejlede - ret input eller config og kør igen:\n  - " +
                         "\n  - ".join(all_problems))
    logger.info("Kolonnetjek OK.")

    do_export = args.export_segments or P['export_segments']
    seg_writer = SegmentWriter(out_dir / 'segmenter.csv') if do_export else None
    quality = QualityCounters()
    all_output, all_rejected = [], []
    t_total = time.time()
    for pid in todo:
        rows, rejected = process_period(cfg, pid, periods[pid], data[f'Periode_{pid}'], args, out_dir, quality, seg_writer)
        all_output.extend(rows)
        all_rejected.extend(rejected)

    # Kvalitet og kasserede skrives ogsaa hvis alle ture blev kasseret
    write_quality(quality, cfg, out_dir, all_rejected, args,
                  kept_rows=[(r['Periode'], r['Køredag']) for r in all_output])
    logger.info(f"Kvalitetsoversigt: {out_dir / 'kvalitet.md'} (+ kvalitet.csv, kasserede_ture.csv)")
    if seg_writer is not None:
        logger.info(f"Segment-pings: {seg_writer.path} ({seg_writer.n:,} rækker)")

    if not all_output:
        logger.error("Ingen resultater genereret!")
        return 1

    result_df = pd.DataFrame(all_output)
    # Deterministisk kolonnerækkefølge: faste kolonner, punkt-kolonner i points-rækkefølge, distancer, antal, Log, Flag
    fixed = ['Turreference', 'Køredag', 'Periode', 'Retning']
    pt_cols = []
    for pid, pt in cfg['points'].items():
        nm = str(pt.get('name', pid))
        pt_cols += [f'{nm} - nærmeste afstand (m)', f'{nm} - projektion', f'{nm} - hastighed (km/t)']
    dist_cols = [f"{str(d.get('name', k))} - køretid (sek)" for k, d in cfg['distances'].items()]
    cnt_cols = ['Antal Stop', 'Antal Stoppested', 'Antal SkipEfterstop', 'Antal Tidsfejl',
                'Antal Hastighed over max', 'Antal Hastighed under 0']
    ordered = [c for c in fixed + pt_cols + dist_cols + cnt_cols + ['Log', 'Flag'] if c in result_df.columns]
    result_df = result_df[ordered]
    result_df.to_csv(output_path, index=False, sep=';', encoding='utf-8')

    summ = build_summary(result_df, cfg)
    summ.to_csv(out_dir / 'opsummering.csv', index=False, sep=';', encoding='utf-8')

    logger.info(f"\n{'=' * 60}")
    logger.info(f"Output: {output_path}")
    logger.info(f"{len(result_df):,} rækker | Total tid: {time.time() - t_total:.1f}s")
    logger.info("\n=== VALIDERING ===")
    for periode, grp in result_df.groupby('Periode'):
        logger.info(f"Periode '{periode}': {len(grp):,} ture")
        for ret, rgrp in grp.groupby('Retning'):
            logger.info(f"  Retning {ret}: {len(rgrp):,} ture")
    logger.info("\nGennemsnitlig nærmeste afstand:")
    for pid, pt in cfg['points'].items():
        col = f"{pt.get('name', pid)} - nærmeste afstand (m)"
        if col in result_df.columns:
            logger.info(f"  {pt.get('name', pid)}: gns={result_df[col].mean():.1f}m  maks={result_df[col].max():.1f}m")
    logger.info("\nGennemsnitlig køretid:")
    for c in dist_cols:
        if c in result_df.columns:
            logger.info(f"  {c.replace(' - køretid (sek)', '')}: gns={result_df[c].mean():.1f}s")
    return 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    args = build_parser().parse_args(argv)
    setup_logging(args.debug)
    try:
        return run(args)
    except KonfigFejl as e:
        logger.error(f"FEJL: {e}")
        return 1
    finally:
        for h in list(logging.getLogger().handlers):   # luk logfilen (Windows holder ellers filen låst)
            if getattr(h, '_analyse_handler', False):
                h.flush()
                logging.getLogger().removeHandler(h)
                h.close()


if __name__ == '__main__':
    sys.exit(main())
