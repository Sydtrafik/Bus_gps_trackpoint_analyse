"""
syntetisk.py - hjælpefunktioner til test_zonetid.py, test_rapport.py og test_komfort_v11.py: konstruerede ture på en
ret nord-syd-linje.

Én strækning er 600 m (p1 = syd, p2 = nord). Med to strækninger er den anden 700-1300 m (p3 -> p4) på samme linje.
Bussen kører med kendt fart, ping hvert sekund, så zonetider kan regnes i hånden. Ingen data fra nogen virksomhed.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import zonetid as Z  # noqa: E402

K11 = Z.K11
K = Z.K
KM = 3.141592653589793 / 180.0 * 6371000.0       # meter pr. breddegrad (samme som komfort_v1.0.py)
LAT0, LON0 = 55.0, 9.0
L = 600.0
KT_KOLONNE = "Teststraekning - køretid (sek)"
KT_KOLONNE2 = "Teststraekning2 - køretid (sek)"
AFSTANDE_1 = ((KT_KOLONNE, 0.0, 600.0),)
AFSTANDE_2 = ((KT_KOLONNE, 0.0, 600.0), (KT_KOLONNE2, 700.0, 1300.0))
LAENGDE_2 = 1300.0


def lat_af(s):
    return LAT0 + s / KM


def config_tekst(extra_elementer=None, udvalg=None, rapport=None, zonetid=None, to_straekninger=False):
    pts = {"p1": {"name": "Syd", "lat": lat_af(0), "lon": LON0}, "p2": {"name": "Nord", "lat": lat_af(L), "lon": LON0}}
    dist = {"d1": {"name": "Teststraekning", "from": "p1", "to": "p2"}}
    cfg = {
        "periods": {"A": {"name": "Før", "start": "2025-08-01", "end": "2025-08-31"},
                    "B": {"name": "Efter", "start": "2025-10-01", "end": "2025-10-31"}},
        "data": {"Periode_A": {"details_csv": "a/Details.csv", "list_csv": "a/List.csv"},
                 "Periode_B": {"details_csv": "b/Details.csv", "list_csv": "b/List.csv"}, "output": "ud/result.csv"},
        "points": pts,
        "point_order": {"direction_1": ["p1", "p2"], "direction_2": ["p2", "p1"]},
        "distances": dist,
        "stops": {"direction_1": {"start": "A", "end": "B"}, "direction_2": {"start": "B", "end": "A"}},
        "komfort": {"fra": "p1", "til": "p2", "bump_vinduer": {"v1": [80, 120], "v2": [280, 320]}},
        "udvalg": udvalg or {"dagtype": "hverdage", "helligdage": []},
        "zonetid": zonetid or {"zonebredde_m": 60, "foelsomhed_zonebredde_m": [40]},
        "rapport": rapport or {"titel": "Test af skabelonen", "undertitel": "Syntetiske ture", "forbehold": ["Kun test."]},
    }
    els = extra_elementer or [{"navn": "Bump A", "type": "bump", "lat": lat_af(100), "lon": LON0},
                              {"navn": "Indsnævring B", "type": "indsnævring", "lat": lat_af(300), "lon": LON0}]
    if not to_straekninger:
        cfg["elementer"] = els
    else:
        pts["p3"] = {"name": "Midt", "lat": lat_af(700), "lon": LON0}
        pts["p4"] = {"name": "Langt nord", "lat": lat_af(1300), "lon": LON0}
        dist["d2"] = {"name": "Teststraekning2", "from": "p3", "to": "p4"}
        cfg["komfort"] = {"bump_vinduer": {"v1": [80, 120], "v2": [280, 320]}}      # fælles standard; fra/til pr. strækning
        cfg["straekninger"] = [
            {"id": "a", "navn": "Strækning A", "fra": "p1", "til": "p2", "elementer": els},
            {"id": "b", "navn": "Strækning B", "fra": "p3", "til": "p4",
             "elementer": [{"navn": "Bump C", "type": "bump", "lat": lat_af(1000), "lon": LON0}]},
        ]
    return yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)


def skriv_config(mappe, **kw):
    p = Path(mappe) / "config.yaml"
    p.write_text(config_tekst(**kw), encoding="utf-8")
    return p


def kor(fart, retning, base, ref, laengde=L, afstande=AFSTANDE_1):
    """Én tur: ping hvert sekund fra 10 m før start til 10 m efter slut. fart(s) = m/s ved position s (fra p1).
    Returnér (liste af segment-rækker, {køretidskolonne: sekunder})."""
    s = -10.0 if retning == 1 else laengde + 10.0
    t = 0
    pk = []
    # Turen fortsætter ca. 15 m forbi enden: værktøjets 1 s-gitter (np.arange med epoke-sekunder) udelader det sidste ping,
    # så ét ping ud over strækningens ende skal til, for at hele strækningen dækkes.
    while (s <= laengde + 14.9) if retning == 1 else (s >= -14.9):
        pk.append((t, s))
        v = fart(s if retning == 1 else s - 1e-6)      # samme zone i begge retninger (zonen er halvåben [a, b))
        s += v if retning == 1 else -v
        t += 1
    ts = np.array([x[0] for x in pk], float)
    ss = np.array([x[1] for x in pk], float)

    def tid(a, b):
        if retning == 1:
            return float(np.interp(b, ss, ts) - np.interp(a, ss, ts))
        return float(np.interp(a, ss[::-1], ts[::-1]) - np.interp(b, ss[::-1], ts[::-1]))
    tider = {kol: tid(a, b) for kol, a, b in afstande}
    rows = [{"Turreference": ref, "datetime": (base + timedelta(seconds=int(tt))).strftime("%Y-%m-%d %H:%M:%S"),
             "lat": lat_af(sv), "lon": LON0, "er_stoprække": 0} for tt, sv in pk]
    return rows, tider


def bygg_periode(navn, fart, dage, laengde=L, afstande=AFSTANDE_1):
    """Ture for en periode: 1 tur pr. retning pr. dag. Returnér (result_df, seg_df)."""
    seg_rows, res_rows = [], []
    for i, dag in enumerate(dage):
        for retning in (1, 2):
            ref = f"{navn}{i:02d}{retning}"
            base = datetime.strptime(dag + " 08:00:00", "%Y-%m-%d %H:%M:%S")
            rows, tider = kor(fart, retning, base, ref, laengde, afstande)
            seg_rows += rows
            res_rows.append({"Turreference": ref, "Køredag": dag, "Periode": navn, "Retning": retning,
                             **{k: round(v) for k, v in tider.items()}, "Log": "", "Flag": ""})
    return pd.DataFrame(res_rows), pd.DataFrame(seg_rows)


def komfort_af(meta, seg, cfg):
    """Komfort pr. strækning: {strækning-id: tabel}."""
    pts = cfg["points"]
    df = seg.merge(meta[["Turreference", "Periode", "Retning", "Køredag"]], on="Turreference")
    ut = {}
    for s in cfg["straekninger"]:
        k = s["komfort"]
        ut[s["id"]] = K.beregn_segmenter(df, k, pts[k["fra"]], pts[k["til"]], log=lambda *a, **kw: None)
    return ut


HVERDAGE_A = ["2025-08-04", "2025-08-05", "2025-08-06", "2025-08-07", "2025-08-08", "2025-08-11"]
HVERDAGE_B = ["2025-10-06", "2025-10-07", "2025-10-08", "2025-10-09", "2025-10-10", "2025-10-13"]


def fart_foer(s):
    return 10.0


def fart_kink(s):
    return 5.0 if 240.0 <= s < 360.0 else 10.0     # halv fart i zonen om elementet ved 300 m


def fart_jaevn(s):
    return 8.0


def perioder(fart_b, cfg, dage_a=None, dage_b=None, extra_a=None, extra_b=None, laengde=L, afstande=AFSTANDE_1, kun_a=False):
    """Byg {'A': (result, komfort, seg), 'B': ...}. extra_*: funktion der må ændre (meta, seg) før komfort beregnes."""
    out = {}
    for navn, fart, dage, extra in (("A", fart_foer, dage_a or HVERDAGE_A, extra_a), ("B", fart_b, dage_b or HVERDAGE_B, extra_b)):
        if kun_a and navn == "B":
            continue
        meta, seg = bygg_periode(navn, fart, dage, laengde, afstande)
        if extra:
            meta, seg = extra(meta, seg)
        out[navn] = (meta, komfort_af(meta, seg, cfg), seg)
    return out
