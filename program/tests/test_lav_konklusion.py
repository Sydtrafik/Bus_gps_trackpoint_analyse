"""Tester lav_konklusion.py: tallene i konklusionsfilen = rapportens nøgletal (standardvalget), kryds fra overblik.csv.

Kør: python -m pytest tests/test_lav_konklusion.py -q   (PYTHONUTF8=1)
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

PK = Path(__file__).resolve().parent.parent
SCRIPT = PK / "lav_konklusion.py"
spec = importlib.util.spec_from_file_location("lavk", SCRIPT)
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)
spec2 = importlib.util.spec_from_file_location("konkl2", PK / "lav_konklusioner_html.py")
K = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(K)


def _nog(p, gruppe, koretid, dag="Hverdage", rute="Alle ruter", time=-1, ret="B"):
    return {"S": "s1", "Retning": ret, "Gruppe": gruppe, "Periode": p, "Ture": 10, "koretid": koretid, "gnsfart": 40.04,
            "minfart_straek": 20, "minfart": {"Bump 1": 30.0, "Bump 2": 20.0}, "andel_opbr": 0.25, "andel_stop": 0,
            "Dag": dag, "Rute": rute, "Time": time}


def _doc():
    """Lille rapportdata v1.2 med lokkerækker (andre dage, ruter, timer, grupper), så forkert udvalg giver forkerte tal."""
    nog = []
    for p, kt in (("A", 54.0), ("B", 66.0)):
        nog.append(_nog(p, "Uden stop", kt))
        nog.append(_nog(p, "Alle ture", 99.0))
        nog.append(_nog(p, "Med stop", 98.0))
        nog.append(_nog(p, "Uden stop", 97.0, dag="Alle dage"))
        nog.append(_nog(p, "Uden stop", 96.0, rute="3A"))
        nog.append(_nog(p, "Uden stop", 95.0, time=7))
        nog.append(_nog(p, "Uden stop", 94.0, ret="1"))
    nog[7]["minfart"] = {"Bump 1": 26.0, "Bump 2": 24.86}
    # fordeling: 8 ture uden stop pr. periode på hverdage (2 mærkbar opbremsning = 25 %), acc 1 mærkbar + 1 kraftig = 25 %
    ford = []
    for p in ("A", "B"):
        for kl, acc, n in (("Maerkbar", "Kraftig", 1), ("Kraftig", "Ingen", 1), ("Ingen", "Maerkbar", 1), ("Ingen", "Ingen", 5)):
            ford.append({"S": "s1", "Periode": p, "Retning": "1", "Stop": "Uden stop", "Klasse": kl, "KlasseAcc": acc,
                         "KlasseSam": "Ingen", "Dagtype": "hverdag", "Rute": "3A", "Time": 7, "n": n})
        ford.append({"S": "s1", "Periode": p, "Retning": "1", "Stop": "Uden stop", "Klasse": "Kraftig", "KlasseAcc": "Kraftig",
                     "KlasseSam": "Kraftig", "Dagtype": "lørdag", "Rute": "3A", "Time": 7, "n": 50})      # weekend: må ikke tælle
        ford.append({"S": "s1", "Periode": p, "Retning": "1", "Stop": "Med stop", "Klasse": "Kraftig", "KlasseAcc": "Kraftig",
                     "KlasseSam": "Kraftig", "Dagtype": "hverdag", "Rute": "3A", "Time": 7, "n": 50})     # med stop: må ikke tælle
    strk = {"id": "s1", "navn": "Strækningen", "laengde_m": 626.0, "vinduer": ["Bump 1", "Bump 2"],
            "linje": [[55.1, 8.1], [55.2, 8.2]],
            "elementer": [{"navn": "Bump 1", "type": "bump"}, {"navn": "Bump 2", "type": "bump"}, {"navn": "I", "type": "indsnaevring"}]}
    meta = {"perioder": ["A", "B"], "standard_dag": "Hverdage", "alle_ruter": "Alle ruter", "alle_timer": -1,
            "dagtyper": [{"navn": "Hverdage", "dagtyper": ["hverdag"]}, {"navn": "Alle dage", "dagtyper": None}],
            "perioder_datoer": {"A": ["2025-06-30", "2025-09-25"], "B": ["2025-10-18", "2026-01-04"]},
            "straekninger": [strk], "forbehold": ["Ingen sammenligningsstrækning."],
            "vej": {"vejtype": "Almindelig vej i boligområde", "hastighed": "50 → 40 km/t", "bumptype": "Modificeret cirkelbump (antaget)"}}
    omf = [{"S": "s1", "Dag": "Hverdage", "Rute": "Alle ruter", "Time": -1, "Periode": p, "Dage": d, "Ture": 1} for p, d in (("A", 44), ("B", 51))]
    zt = [{"S": "s1", "Retning": "B", "Element": "Bump 1", "Type": "bump", "Lav": 2.55, "Hoej": 3.58},
          {"S": "s1", "Retning": "1", "Element": "Bump 1", "Type": "bump", "Lav": 9, "Hoej": 9}]
    return {"version": "1.2", "meta": meta, "nogletal": nog, "fordeling": ford, "omfang": omf, "zonetid": zt}


def test_kendt_positiv_standardvalget():
    ud, _kom = L.fra_rapportdata(_doc())
    assert ud["type"] == "foer_efter" and ud["aar"] == 2025
    assert ud["koeretid_s"] == {"foer": 54, "efter": 66}
    assert ud["laveste_fart_kmt"] == {"foer": 25, "efter": 25.4}           # gennemsnit af vinduernes medianer, som rapporten
    assert ud["maerkbar_opbremsning_pct"] == {"foer": 25, "efter": 25}
    assert ud["maerkbar_acceleration_pct"] == {"foer": 25, "efter": 25}     # kun hverdage, uden stop
    assert ud["perioder"]["efter"] == {"fra": "2025-10-18", "til": "2026-01-04", "dage": 51}
    assert ud["fartdaempere"] == [{"type": "modificeret cirkelbump", "antal": 2, "antaget": True}, {"type": "indsnævring", "antal": 1}]
    assert (ud["vejtype"], ud["omraade"]) == ("almindelig vej", "boligområde")     # område ud af vejtypen
    d = _doc()
    d["meta"]["vej"] = {"vejtype": "Trafikvej"}                                    # ingen bumptype, intet område
    ud2, _ = L.fra_rapportdata(d)
    assert ud2["fartdaempere"][0] == {"type": L.UDFYLD, "antal": 2} and ud2["vejtype"] == "trafikvej" and "omraade" not in ud2
    assert ud["hastighed_kmt"] == {"foer": 50, "efter": 40}
    assert ud["ekstra_tid_pr_element_s"] == [{"element": "Bump 1", "lav": 2.55, "hoej": 3.58}]


def test_kendt_negativ_fordeling_passer_ikke():
    d = _doc()
    d["nogletal"][0]["andel_opbr"] = 0.5                     # nøgletallet passer ikke med fordelingen
    try:
        L.fra_rapportdata(d)
    except SystemExit as e:
        assert "passer ikke" in str(e)
    else:
        raise AssertionError("forventede SystemExit")


def test_fil_kan_udfyldes_og_tilfoejes():
    with tempfile.TemporaryDirectory() as t:
        rd = Path(t) / "rapportdata.json"
        rd.write_text(json.dumps(_doc(), ensure_ascii=False), encoding="utf-8")
        ud = Path(t) / "konklusion.yaml"
        r = subprocess.run([sys.executable, str(SCRIPT), "--rapportdata", str(rd), "--out", str(ud)], capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        tekst = ud.read_text(encoding="utf-8")
        fejl = K.tjek_analyse(yaml.safe_load(tekst))
        assert fejl and all("UDFYLD" in f for f in fejl)                    # kun de felter, personen skal udfylde
        fyldt = yaml.safe_load(tekst.replace('"UDFYLD"', '"x"'))
        assert {f.split("'")[1] for f in K.tjek_analyse(fyldt)} == {"buslommer", "parkering_paa_vejen"}   # kun ja/nej/ukendt
        fyldt.update(buslommer="nej", parkering_paa_vejen="ukendt")
        assert K.tjek_analyse(fyldt) == []
        # overskriver ikke en udfyldt fil
        r = subprocess.run([sys.executable, str(SCRIPT), "--rapportdata", str(rd), "--out", str(ud)], capture_output=True, text=True, encoding="utf-8")
        assert r.returncode != 0 and "findes allerede" in r.stderr


def test_kryds_fra_overblik():
    rk = [{"Stykke": s, "Retning": "2", "Periode": p, "Time": t, "n": n, "median": m}
          for s, p, t, n, m in (("A-P1", "A", "alle", "2153", "11.0"), ("A-P1", "A", "7", "10", "99.0"), ("A-P1", "B", "alle", "2386", "11.0"),
                                ("P1-B", "A", "alle", "2153", "24.0"), ("P1-B", "B", "alle", "2386", "24.0"),
                                ("A-B", "A", "alle", "2153", "35.0"), ("A-B", "B", "alle", "2386", "36.0"))]
    cfg = {"points": {"pA": {"lat": 55.0, "lon": 8.0}, "p1": {"lat": 55.001, "lon": 8.0}, "pB": {"lat": 55.002, "lon": 8.0}},
           "point_order": {"direction_1": ["pB", "p1", "pA"]},
           "distances": {"d1": {"name": "A-P1", "from": "pA", "to": "p1"}, "d3": {"name": "A-B", "from": "pA", "to": "pB"}},
           "periods": {"A": {"start": "2024-08-01", "end": "2024-09-18"}, "B": {"start": "2024-09-19", "end": "2024-11-05"}}}
    ud, _ = L.fra_overblik(rk, cfg)
    assert ud["koeretid_s"] == {"foer": 35, "efter": 36} and ud["ture"] == {"foer": 2153, "efter": 2386}
    assert [s["stykke"] for s in ud["kryds_stykker"]] == ["A-P1", "P1-B", "A-B"] and ud["kryds_stykker"][0]["foer"] == 11
    assert 220 <= ud["laengde_m"] <= 224                       # 2 × ca. 111 m
    assert ud["aar"] == 2024


if __name__ == "__main__":
    for navn, fn in list(globals().items()):
        if navn.startswith("test_"):
            fn()
            print("OK", navn)
