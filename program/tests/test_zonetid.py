#!/usr/bin/env python3
"""
Tests for zonetid.py (v1.1) - konstruerede ture med kendt fart giver kendte zonetider.

Koer:  python tests/test_zonetid.py        (ren python)   eller   python -m pytest tests/test_zonetid.py
Sæt PYTHONUTF8=1 i miljøet. Ingen data fra nogen virksomhed.

Strækning 600 m, elementer ved 100 m (bump) og 300 m (indsnævring), zonebredde 60 m:
  zoner: øvrig 0 0-40, Bump A 40-160, øvrig 1 160-240, Indsnævring B 240-360, øvrig 2 360-600.
Før: 10 m/s overalt (element-zone 120 m = 12,0 s).
Tests af: kendt zonetid og interval, udvalg, kun én periode (niveauer) og to strækninger i samme analyse.
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import syntetisk as S  # noqa: E402

Z = S.Z


def _cfg(tmp, **kw):
    return Z.laes_config(S.skriv_config(tmp, **kw))


def R1(res):
    return Z.resultat_for(res)           # den første (eneste) strækning


def test_zoner_og_overlap():
    zon = Z.lav_zoner({"a": 100.0, "b": 300.0}, 60, 600.0)
    assert list(zon) == ["øvrig 0", "a", "øvrig 1", "b", "øvrig 2"], list(zon)
    assert zon["a"] == (40.0, 160.0) and zon["b"] == (240.0, 360.0)
    assert zon["øvrig 2"] == (360.0, 600.0)
    # overlap deles på midten: zoner 70-190 og 150-270 -> grænse 170
    zon = Z.lav_zoner({"a": 130.0, "b": 210.0}, 60, 600.0)
    assert zon["a"][1] == zon["b"][0] == 170.0, zon
    # element ved kanten: zone klippes til 0..L
    zon = Z.lav_zoner({"a": 10.0}, 60, 600.0)
    assert zon == {"a": (0.0, 70.0), "øvrig 0": (70.0, 600.0)}, zon


def test_bagudkompatibel_config_er_en_straekning():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
    assert len(cfg["straekninger"]) == 1 and cfg["straekninger"][0]["id"] == "s1"
    assert cfg["straekninger"][0]["komfort"]["fra"] == "p1" and cfg["straekninger"][0]["komfort"]["til"] == "p2"
    assert [e["navn"] for e in cfg["straekninger"][0]["elementer"]] == ["Bump A", "Indsnævring B"]


def test_kendt_zonetid_ingen_generel_nedsat_fart():
    """Kun indsnævringen er langsommere (5 m/s i zonen): ekstra 12,0 s, nedre = øvre fordi øvrig strækning er uændret."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        res, md = Z.beregn(cfg, S.perioder(S.fart_kink, cfg), log=lambda *a: None)
    v = R1(res)["w60|uden stop|begge"]
    assert v["nA"] == 12 and v["nB"] == 12, (v["nA"], v["nB"])
    assert abs(v["A"]["Indsnævring B"] - 12.0) < 0.05 and abs(v["B"]["Indsnævring B"] - 24.0) < 0.05, (v["A"], v["B"])
    assert abs(v["faktor"] - 1.0) < 1e-3
    lo, hi = v["interval"]["Indsnævring B"]
    assert abs(lo - 12.0) < 0.05 and abs(hi - 12.0) < 0.05, (lo, hi)
    assert abs(v["interval"]["Bump A"][0]) < 0.05 and abs(v["interval"]["Bump A"][1]) < 0.05
    assert abs(v["interval"][Z.OVRIG][0]) < 0.05 and abs(v["interval"][Z.OVRIG][1]) < 0.05
    assert abs(v["total"] - 12.0) < 0.05, v["total"]
    # retning 1 og 2 giver samme tal (zonerne vendes for modsat retning)
    for ret in ("1", "2"):
        w = R1(res)[f"w60|uden stop|{ret}"]
        assert abs(w["interval"]["Indsnævring B"][1] - 12.0) < 0.05, (ret, w["interval"])
    assert "w40|uden stop|begge" in R1(res) and "w60|alle ture|begge" in R1(res)
    assert res["perioder"] == ["A", "B"] and list(res["straekninger"]) == ["s1"]


def test_interval_ved_generel_nedsat_fart():
    """8 m/s overalt (efter) mod 10 m/s (før): f = 1,25. Zone 12,0 -> 15,0 s: øvre = 3,0 s, nedre = 15 - 12 x 1,25 = 0."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        res, _ = Z.beregn(cfg, S.perioder(S.fart_jaevn, cfg), log=lambda *a: None)
    v = R1(res)["w60|uden stop|begge"]
    assert abs(v["faktor"] - 1.25) < 0.01, v["faktor"]
    for navn, bredde in (("Bump A", 120.0), ("Indsnævring B", 120.0)):
        lo, hi = v["interval"][navn]
        assert abs(hi - (bredde / 8.0 - bredde / 10.0)) < 0.05, (navn, hi)
        assert abs(lo) < 0.1, (navn, lo)
    assert abs(v["total"] - (600 / 8.0 - 600 / 10.0)) < 0.1, v["total"]   # 75 - 60 = 15 s


def test_udvalg_dagtype_log_og_stop():
    """Weekend, helligdag, tur med Log og tur med stillestand holdes ude, hvor de skal."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, udvalg={"dagtype": "hverdage", "helligdage": ["2025-10-13"]})
        dage_b = S.HVERDAGE_B[:5] + ["2025-10-13", "2025-10-11"]       # mandag 13/10 = helligdag, lørdag 11/10

        def extra_b(meta, seg):
            meta = meta.copy()
            meta.loc[meta["Turreference"] == "B001", "Log"] = "afstand_test"
            return meta, seg
        per = S.perioder(S.fart_kink, cfg, dage_b=dage_b, extra_b=extra_b)
        # én tur med stillestand (sættes direkte i komfort-tabellen)
        r, k, s = per["B"]
        k = {sid: t.copy() for sid, t in k.items()}
        k["s1"].loc[k["s1"]["Turreference"] == "B011", "stillestand"] = 1
        per["B"] = (r, k, s)
        res, _ = Z.beregn(cfg, per, log=lambda *a: None)
    uden = R1(res)["w60|uden stop|begge"]
    alle = R1(res)["w60|alle ture|begge"]
    # B: 5 hverdage x 2 retninger = 10, minus tur B001 (Log) = 9, minus B011 (stillestand) = 8 uden stop; 9 alle ture
    assert uden["nB"] == 8, uden["nB"]
    assert alle["nB"] == 9, alle["nB"]
    assert uden["nA"] == 12


def test_alle_dage():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, udvalg={"dagtype": "alle", "helligdage": []})
        res, _ = Z.beregn(cfg, S.perioder(S.fart_kink, cfg, dage_b=S.HVERDAGE_B[:5] + ["2025-10-11"]), log=lambda *a: None)
    assert R1(res)["w60|uden stop|begge"]["nB"] == 12     # lørdag tæller med


def test_kun_en_periode_giver_niveauer():
    """Uden periode B: tid pr. zone som niveau, ingen interval og ingen 'ekstra'."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        res, md = Z.beregn(cfg, S.perioder(S.fart_kink, cfg, kun_a=True), log=lambda *a: None)
    assert res["perioder"] == ["A"]
    v = R1(res)["w60|uden stop|begge"]
    assert "interval" not in v and "B" not in v and "nB" not in v, list(v)
    assert v["nA"] == 12
    assert abs(v["A"]["Indsnævring B"] - 12.0) < 0.05 and abs(v["A"]["Bump A"] - 12.0) < 0.05 and abs(v["A"]["total"] - 60.0) < 0.05, v["A"]
    assert "ekstra" not in "\n".join(md).lower().replace("# tid fordelt", ""), "\n".join(md)


def test_to_straekninger_regnes_hver_for_sig():
    """To strækninger på samme linje (0-600 og 700-1300 m): strækning a har en langsom zone, strækning b har ingen."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, to_straekninger=True)
        assert [s["id"] for s in cfg["straekninger"]] == ["a", "b"]
        per = S.perioder(S.fart_kink, cfg, laengde=S.LAENGDE_2, afstande=S.AFSTANDE_2)
        res, md = Z.beregn(cfg, per, log=lambda *a: None)
    assert list(res["straekninger"]) == ["a", "b"]
    a = res["straekninger"]["a"]["w60|uden stop|begge"]
    b = res["straekninger"]["b"]["w60|uden stop|begge"]
    assert abs(a["interval"]["Indsnævring B"][1] - 12.0) < 0.05 and abs(a["total"] - 12.0) < 0.05, (a["interval"], a["total"])
    assert abs(b["interval"]["Bump C"][0]) < 0.05 and abs(b["interval"]["Bump C"][1]) < 0.05 and abs(b["total"]) < 0.05, (b["interval"], b["total"])
    assert res["straekninger"]["b"]["positioner_m"] == {"Bump C": 300.0}, res["straekninger"]["b"]["positioner_m"]
    assert "Strækning a: Strækning A" in "\n".join(md) and "Strækning b: Strækning B" in "\n".join(md)


def test_straekning_uden_elementer_springes_over():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, to_straekninger=True)
        cfg["straekninger"][1]["elementer"] = []
        per = S.perioder(S.fart_kink, cfg, laengde=S.LAENGDE_2, afstande=S.AFSTANDE_2)
        res, _ = Z.beregn(cfg, per, log=lambda *a: None)
    assert res["straekninger"]["b"] == {"ingen_elementer": True}
    assert "w60|uden stop|begge" in res["straekninger"]["a"]


def test_element_uden_for_straekning_giver_fejl():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, extra_elementer=[{"navn": "Langt vaek", "type": "bump", "lat": S.lat_af(900), "lon": S.LON0}])
        try:
            Z.beregn(cfg, S.perioder(S.fart_kink, cfg), log=lambda *a: None)
        except SystemExit as e:
            assert "uden for strækningen" in str(e), str(e)
            return
    raise AssertionError("forventede SystemExit for element uden for strækningen")


def test_config_fejl_paa_dansk():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "c.yaml"
        txt = S.config_tekst().replace("elementer:", "elementer_x:")
        p.write_text(txt, encoding="utf-8")
        try:
            Z.laes_config(p)
        except SystemExit as e:
            assert "elementer" in str(e)
            return
    raise AssertionError("forventede SystemExit uden 'elementer:'")


def _run_all():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:  # noqa
            failed += 1
            import traceback
            print(f"FAIL {name}: {type(e).__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed} af {len(tests)} tests bestået")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(_run_all())
