#!/usr/bin/env python3
"""
Tests for komfort_v1.0.py - syntetiske ture (ingen eksterne filer).

Koer:  python -m pytest tests/test_komfort.py      (hvis pytest findes)
       python tests/test_komfort.py                (ren python: pandas, numpy, pyyaml)
Sæt PYTHONUTF8=1 i miljøet.

Geometri: strækning p1->p5 fra config_3A (ca. 625 m). Bussen koerer langs linjen, ping hvert sekund
(hele sekunder, som i data). Kendte profiler:
  - konstant fart 40 km/t  -> a ca. 0, ingen haendelser
  - 40 -> 20 km/t med 1,2 m/s2 -> max opbremsning ca. 1,2 (klasse mellem), een haendelse ved taerskel 0,75
  - ufuldstaendige ture (kun halv strækning, hul > 10 s, ping uden for korridor)
"""
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / fname)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


K = _load("komfort_v1_0", "komfort_v1.0.py")

P1 = {"lat": 55.48040727834349, "lon": 8.467493876574624}
P5 = {"lat": 55.48511271313209, "lon": 8.47294764041854}
CFG = dict(K.DEFAULTS)
CFG["bump_vinduer"] = {"bump1": [80, 140], "bump2": [200, 260]}
LAT0, LON0, ENHED, L = K.linje_geometri(P1, P5)


# -- byggeklodser -------------------------------------------------------------------------

def s_til_latlon(s, d=0.0):
    """Punkt (lat, lon) ved position s langs linjen og sideafstand d (m)."""
    ex, ey = ENHED
    x = s * ex - d * ey
    y = s * ey + d * ex
    k = math.pi / 180 * K.EARTH_R
    return LAT0 + y / k, LON0 + x / (k * math.cos(math.radians(LAT0)))


def profil_konstant(v_ms, s_start=-40.0, s_slut=L + 40.0):
    """(t, s) for konstant fart; ping hver hele sekund."""
    n = int((s_slut - s_start) / v_ms)
    t = np.arange(n + 1, dtype=float)
    return t, s_start + v_ms * t


def profil_opbremsning(v0, v1, a_br, s_brems_start, s_start=-40.0, s_slut=L + 40.0):
    """Fart v0, bremser med a_br (m/s2) fra position s_brems_start ned til v1, derefter konstant v1."""
    t_br = (v0 - v1) / a_br
    d_br = (v0 + v1) / 2 * t_br
    t1 = (s_brems_start - s_start) / v0                  # tid til bremsestart
    t2 = t1 + t_br
    t_slut = t2 + (s_slut - s_brems_start - d_br) / v1
    t = np.arange(0, int(t_slut) + 1, dtype=float)
    s = np.empty_like(t)
    for i, ti in enumerate(t):
        if ti <= t1:
            s[i] = s_start + v0 * ti
        elif ti <= t2:
            tau = ti - t1
            s[i] = s_brems_start + v0 * tau - 0.5 * a_br * tau ** 2
        else:
            s[i] = s_brems_start + d_br + v1 * (ti - t2)
    return t, s


def til_dataframe(ture):
    """ture = liste af (ref, t, s[, d]) -> DataFrame i segmenter.csv-format (+ en stop-række pr. tur med forkert position)."""
    rows = []
    base = pd.Timestamp("2025-08-04 08:00:00")
    for tup in ture:
        ref, t, s = tup[0], tup[1], tup[2]
        d = tup[3] if len(tup) > 3 else np.zeros(len(t))
        for ti, si, di in zip(t, s, d):
            lat, lon = s_til_latlon(si, di)
            rows.append({"Turreference": str(ref), "Periode": "A", "Retning": "2", "Køredag": "2025-08-04",
                         "datetime": (base + pd.Timedelta(seconds=float(ti))).strftime("%Y-%m-%d %H:%M:%S"),
                         "lat": lat, "lon": lon, "er_stoprække": 0})
        # stop-række med planlagt position langt væk fra linjen - må ikke påvirke noget
        rows.append({"Turreference": str(ref), "Periode": "A", "Retning": "2", "Køredag": "2025-08-04",
                     "datetime": (base + pd.Timedelta(seconds=float(t[len(t) // 2]))).strftime("%Y-%m-%d %H:%M:%S"),
                     "lat": 55.50, "lon": 8.50, "er_stoprække": 1})
    return pd.DataFrame(rows)


def kør(ture, cfg=None):
    cfg = cfg or CFG
    df = til_dataframe(ture)
    out = K.beregn_segmenter(df, cfg, P1, P5, log=lambda *_: None, progress_every=0)
    return out.set_index("Turreference")


# -- tests ---------------------------------------------------------------------------------

def test_geometri_laengde():
    assert 623.0 < L < 627.0, L
    s, d = K.projicer(*s_til_latlon(300.0, 7.0), LAT0, LON0, ENHED)
    assert abs(s - 300.0) < 1e-6 and abs(abs(d) - 7.0) < 1e-6


def test_sg_polynomium_t2():
    """x = t^2: v = 2t, a = 2 eksakt - også i kanterne (interp)."""
    t = np.arange(0, 20, dtype=float)
    v, a = K.sg_afledte(t ** 2, 5, 2, 1.0, "interp")
    assert np.allclose(a, 2.0, atol=1e-9), a
    assert np.allclose(v, 2 * t, atol=1e-9), v
    # med skridt dt = 0.5
    t = np.arange(0, 10, 0.5)
    v, a = K.sg_afledte(t ** 2, 5, 2, 0.5, "interp")
    assert np.allclose(a, 2.0, atol=1e-9) and np.allclose(v, 2 * t, atol=1e-9)


def test_sg_kant_drop():
    v, a = K.sg_afledte(np.arange(10.0) ** 2, 5, 2, 1.0, "drop")
    assert np.isnan(a[:2]).all() and np.isnan(a[-2:]).all() and np.allclose(a[2:-2], 2.0)


def test_sg_stoej_daempes():
    """SG5 dæmper en enkelt 5 m-udsvinger i position kraftigt, men bevarer konstant fart."""
    t = np.arange(0, 30, dtype=float)
    x = 10.0 * t
    x[15] += 5.0
    v, a = K.sg_afledte(x, 5, 2, 1.0, "interp")
    assert np.max(np.abs(a)) < 5.0           # rå 2. differens ville give 10 m/s2
    assert abs(np.mean(v) - 10.0) < 0.5


def test_konstant_fart():
    t, s = profil_konstant(40 / 3.6)
    r = kør([("konst", t, s)]).loc["konst"]
    assert r["status"] == "ok", r["aarsag"]
    assert abs(r["gns_fart_kmh"] - 40.0) < 0.05
    assert abs(r["min_fart_kmh"] - 40.0) < 0.05 and abs(r["max_fart_kmh"] - 40.0) < 0.05
    assert r["spaend_kmh"] < 0.1 and r["std_fart_kmh"] < 0.05 and r["sum_abs_dfart_kmh"] < 0.1
    assert abs(r["max_opbremsning_ms2"]) < 0.02 and abs(r["max_acceleration_ms2"]) < 0.02
    for kol in ("opbr_haendelser_t075", "opbr_haendelser_t135", "acc_haendelser_t075", "acc_haendelser_t135"):
        assert r[kol] == 0, kol
    assert r["klasse_opbremsning"] == "lav" and r["klasse_acceleration"] == "lav"
    assert r["stillestand"] == 0
    assert abs(r["koretid_s"] - L / (40 / 3.6)) < 0.1
    assert abs(r["daekning_m"] - L) < 1e-6


def test_opbremsning_40_til_20_med_1_2():
    t, s = profil_opbremsning(40 / 3.6, 20 / 3.6, 1.2, s_brems_start=210.0)
    r = kør([("br", t, s)]).loc["br"]
    assert r["status"] == "ok", r["aarsag"]
    assert 1.1 < r["max_opbremsning_ms2"] < 1.25, r["max_opbremsning_ms2"]
    assert r["max_acceleration_ms2"] < 0.3
    assert r["opbr_haendelser_t075"] == 1 and r["opbr_haendelser_t135"] == 0
    assert r["acc_haendelser_t075"] == 0
    assert r["klasse_opbremsning"] == "mellem" and r["klasse_acceleration"] == "lav"
    assert 19.5 < r["min_fart_kmh"] < 20.5 and 39.5 < r["max_fart_kmh"] < 40.5
    assert 19.0 < r["spaend_kmh"] < 21.0
    assert 19.0 < r["sum_abs_dfart_kmh"] < 22.0          # monoton nedgang 40 -> 20
    assert r["stillestand"] == 0
    # bremsningen ligger i bump2-vinduet (s 200-260) og ikke i bump1 (80-140)
    assert r["bump2_max_opbremsning_ms2"] > 1.0 and r["bump1_max_opbremsning_ms2"] < 0.1
    assert 19.5 < r["bump2_min_fart_kmh"] < 40.0 and abs(r["bump1_min_fart_kmh"] - 40.0) < 0.5
    assert r["min_fart_s_m"] > 245.0                     # min-fart først efter bremsningen


def test_hard_opbremsning_giver_hoej_klasse_og_stillestand():
    t, s = profil_opbremsning(40 / 3.6, 0.5, 2.5, s_brems_start=300.0)   # til næsten stilstand
    r = kør([("stop", t, s)]).loc["stop"]
    assert r["status"] == "ok", r["aarsag"]
    assert r["klasse_opbremsning"] == "høj" and r["opbr_haendelser_t135"] >= 1
    assert r["stillestand"] == 1


def test_modsat_retning():
    """Bus fra p5 mod p1: samme fart og hændelser; min_fart_s_m er stadig s fra p1."""
    t, s = profil_opbremsning(40 / 3.6, 20 / 3.6, 1.2, s_brems_start=210.0)
    s_rev = L - s                                         # spejl: kører fra s=L+40 mod -40
    r = kør([("rev", t, s_rev)]).loc["rev"]
    assert r["status"] == "ok", r["aarsag"]
    assert 1.1 < r["max_opbremsning_ms2"] < 1.25
    assert r["opbr_haendelser_t075"] == 1
    assert r["min_fart_s_m"] < L - 245.0 + 5.0            # min-fart først efter bremsningen (s < ca. L-250, set fra p1)
    # spejlet ligger bremsningen ved s ca. 376-415, uden for begge bump-vinduer
    assert r["bump1_max_opbremsning_ms2"] < 0.1 and r["bump2_max_opbremsning_ms2"] < 0.1


def test_ufuldstaendige_ture():
    t, s = profil_konstant(40 / 3.6)
    # 1) kun første halvdel
    k1 = s <= 300
    # 2) hul på 12 s midt i
    k2 = ~((s > 250) & (s < 250 + 12 * 40 / 3.6))
    # 3) pings 30 m ved siden af linjen midt på strækningen (uden for korridor) -> hul
    d3 = np.where((s > 200) & (s < 330), 30.0, 0.0)
    ture = [("halv", t[k1], s[k1]), ("hul", t[k2], s[k2]), ("side", t, s, d3)]
    ud = kør(ture)
    assert ud.loc["halv", "status"] == "ufuldstændig" and ud.loc["halv", "aarsag"] == "ikke_fuld_passage"
    assert ud.loc["hul", "status"] == "ufuldstændig" and ud.loc["hul", "aarsag"] == "hul_over_max"
    assert ud.loc["side", "status"] == "ufuldstændig" and ud.loc["side", "aarsag"] == "hul_over_max"
    assert ud[["gns_fart_kmh", "max_opbremsning_ms2"]].isna().all().all()    # komfort sprunget over


def test_ingen_pings_i_korridor():
    t, s = profil_konstant(40 / 3.6)
    ud = kør([("langt", t, s, np.full(len(t), 80.0)), ("ok", t, s)])
    assert ud.loc["langt", "aarsag"] == "ingen_pings_i_korridor"
    assert ud.loc["ok", "status"] == "ok"


def test_duplikerede_tidsstempler_droppes():
    t, s = profil_konstant(40 / 3.6)
    t2 = np.concatenate([t[:20], t[19:20], t[20:]])         # ping 19 to gange (samme tid, anden position)
    s2 = np.concatenate([s[:20], s[19:20] + 3.0, s[20:]])
    r = kør([("dup", t2, s2)]).loc["dup"]
    assert r["status"] == "ok" and abs(r["gns_fart_kmh"] - 40.0) < 0.2


def test_kant_drop_giver_samme_konstant_resultat():
    cfg = dict(CFG)
    cfg["kant"] = "drop"
    t, s = profil_konstant(40 / 3.6)
    r = kør([("k", t, s)], cfg).loc["k"]
    assert r["status"] == "ok" and abs(r["min_fart_kmh"] - 40.0) < 0.05


def test_config_default_og_overstyring(tmp=None):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "c.yaml"
        p.write_text("points:\n  p1: {lat: 55.0, lon: 8.0}\n  p5: {lat: 55.01, lon: 8.0}\n"
                     "komfort:\n  taerskler_ms2: [0.5, 1.0]\n", encoding="utf-8")
        cfg, pts = K.laes_config(p)
    assert cfg["taerskler_ms2"] == [0.5, 1.0] and cfg["sg_vindue_s"] == 5 and cfg["bump_vinduer"]["bump1"] == [80, 140]


if __name__ == "__main__":
    fejl = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for navn, fn in tests:
        try:
            fn()
            print(f"OK    {navn}")
        except Exception as e:      # noqa: BLE001
            fejl += 1
            print(f"FEJL  {navn}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - fejl}/{len(tests)} tests bestået")
    sys.exit(1 if fejl else 0)
