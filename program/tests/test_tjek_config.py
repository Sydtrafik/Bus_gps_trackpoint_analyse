"""Tester skabeloner/tjek_config.py: én kendt negativ pr. fejltype og gyldige configs, der skal godkendes.

Kør: python -m pytest tests/test_tjek_config.py -q   (eller: python tests/test_tjek_config.py)
"""
import copy
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

PK = Path(__file__).resolve().parent.parent
SCRIPT = PK / "skabeloner" / "tjek_config.py"
sys.path.insert(0, str(PK / "skabeloner"))
import tjek_config as T  # noqa: E402

LAT = 55.48
GYLDIG = {
    "analysetype": "straekning",
    "periods": {"A": {"name": "Før", "start": "2025-01-01", "end": "2025-03-31"},
                "B": {"name": "Efter", "start": "2025-05-01", "end": "2025-07-31"}},
    "data": {"Periode_A": {"details_csv": "data/A/Details.csv", "list_csv": "data/A/List.csv"},
             "Periode_B": {"details_csv": "data/B/Details.csv", "list_csv": "data/B/List.csv"},
             "output": "resultat/result.csv"},
    "points": {"p1": {"name": "Vest", "lat": LAT, "lon": 8.000}, "p2": {"name": "Midt", "lat": LAT, "lon": 8.005},
               "p3": {"name": "Øst", "lat": LAT, "lon": 8.010}},
    "point_order": {"direction_1": ["p1", "p2", "p3"], "direction_2": ["p3", "p2", "p1"]},
    "distances": {"d1": {"name": "Vest-Midt", "from": "p1", "to": "p2"}, "d2": {"name": "Midt-Øst", "from": "p2", "to": "p3"}},
    "stops": {"direction_1": {"start": "S1 (By)", "end": "S5 (By)"}, "direction_2": {"start": "S5 modsat (By)", "end": "S1 modsat (By)"}},
    "straekninger": [
        {"id": "vest", "navn": "Vestlige del", "fra": "p1", "til": "p2",
         "elementer": [{"navn": "Bump 1", "type": "bump", "lat": LAT, "lon": 8.002, "radius_m": 30}]},
        {"id": "oest", "navn": "Østlige del", "fra": "p2", "til": "p3", "elementer": []}],
    "komfort": {"bump_vinduer": {}},
    "udvalg": {"dagtype": "hverdage", "helligdage": ["2025-04-17"]},
    "rapport": {"titel": "Køretid på Testvej", "stoppesteder": [], "vej": {"vejtype": "Boligvej"}},
}


def _skriv(mappe, cfg=None, tekst=None, data=True):
    m = Path(mappe)
    if data:
        for p in ("A", "B"):
            (m / "data" / p).mkdir(parents=True, exist_ok=True)
            for f in ("Details.csv", "List.csv"):
                (m / "data" / p / f).write_text("x\n", encoding="utf-8")
    sti = m / "config.yaml"
    sti.write_text(tekst if tekst is not None else yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return sti


def _tjek(cfg=None, tekst=None, trin="fuld", data=True):
    with tempfile.TemporaryDirectory() as tmp:
        return T.tjek(_skriv(tmp, cfg, tekst, data), trin)


def _med(aendring):
    c = copy.deepcopy(GYLDIG)
    aendring(c)
    return c


def _fejl_om(t, *ord_):
    tekst = "\n".join(t.fejl)
    return all(o in tekst for o in ord_)


# ------------------------------------------------------------------ kendt positiv
def test_gyldig_config_godkendes():
    t = _tjek(GYLDIG)
    assert t.fejl == [], t.tekst()


def test_gyldig_via_kommandolinje_exit_0_og_fejl_exit_1():
    env = {**os.environ, "PYTHONUTF8": "1"}
    with tempfile.TemporaryDirectory() as tmp:
        sti = _skriv(tmp, GYLDIG)
        ok = subprocess.run([sys.executable, str(SCRIPT), "--config", str(sti)], capture_output=True, text=True, encoding="utf-8", env=env)
        assert ok.returncode == 0, ok.stdout
        sti.write_text(yaml.safe_dump(_med(lambda c: c["points"].pop("p3"))), encoding="utf-8")
        nej = subprocess.run([sys.executable, str(SCRIPT), "--config", str(sti)], capture_output=True, text=True, encoding="utf-8", env=env)
        assert nej.returncode == 1 and "FEJL" in nej.stdout


def test_eksisterende_configs_godkendes():
    """Eksemplet, Kvaglundvej-formen fra 1.10.0 (kort config) og en kryds-config uden analysetype."""
    eks = yaml.safe_load((PK / "eksempler" / "config_kvaglundvej.yaml").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        m = Path(tmp)
        for p in ("data_A", "data_B"):
            (m / p).mkdir()
            for f in ("Details.csv", "List.csv"):
                (m / p / f).write_text("x\n", encoding="utf-8")
        sti = m / "config.yaml"
        shutil.copyfile(PK / "eksempler" / "config_kvaglundvej.yaml", sti)
        t = T.tjek(sti)
        assert t.fejl == [], t.tekst()
    kort = {k: copy.deepcopy(GYLDIG[k]) for k in ("periods", "data", "udvalg", "rapport")}
    kort.update({"points": {"p1": {"name": "A", "lat": LAT, "lon": 8.0}, "p2": {"name": "B", "lat": LAT, "lon": 8.01}},
                 "point_order": {"direction_1": ["p1", "p2"], "direction_2": ["p2", "p1"]},
                 "distances": {"d1": {"name": "Strækningen", "from": "p1", "to": "p2"}},
                 "stops": GYLDIG["stops"], "komfort": {"fra": "p1", "til": "p2", "bump_vinduer": {}},
                 "elementer": [{"navn": "Bump 1", "type": "bump", "lat": LAT, "lon": 8.004, "radius_m": 30},
                               {"navn": "Indsnævring 1", "type": "indsnævring", "lat": LAT, "lon": 8.006}]})
    assert _tjek(kort).fejl == []
    kryds = {"periods": {"A": GYLDIG["periods"]["A"]}, "data": {"Periode_A": GYLDIG["data"]["Periode_A"], "output": "result.csv"},
             "points": GYLDIG["points"], "point_order": {"direction_2": ["p1", "p2", "p3"]},
             "distances": GYLDIG["distances"], "stops": {"direction_2": {"start": "S1 (By)", "end": "S5 (By)"}},
             "buffer_rows": 50, "speed_max_kmh": 110}
    t = _tjek(kryds)
    assert t.fejl == [] and t.type == "kryds", t.tekst()


def test_skabelonen_er_gyldig_naar_den_er_udfyldt():
    cfg = yaml.safe_load((PK / "skabeloner" / "config.yaml").read_text(encoding="utf-8"))
    assert _tjek(cfg).fejl                                   # pladsholdere -> fejl
    cfg["points"] = {"p1": {"name": "Vest", "lat": LAT, "lon": 8.0}, "p2": {"name": "Øst", "lat": LAT, "lon": 8.01}}
    cfg["stops"] = GYLDIG["stops"]
    cfg["straekninger"][0]["elementer"] = [{"navn": "Bump 1", "type": "bump", "lat": LAT, "lon": 8.004, "radius_m": 30}]
    t = _tjek(cfg)
    assert t.fejl == [], t.tekst()
    t = _tjek(yaml.safe_load((PK / "skabeloner" / "config.yaml").read_text(encoding="utf-8")), trin="stopnavne")
    assert all("Filen findes ikke" not in f for f in t.fejl) and t.fejl == [], t.tekst()   # valg 1 virker før punkterne


# ------------------------------------------------------------------ én kendt negativ pr. fejltype
def test_yaml_syntaksfejl_med_linjenummer():
    tekst = "periods:\n  A:\n    name: \"Før\n    start: 2025\npoints: [\n"
    t = _tjek(tekst=tekst)
    assert len(t.fejl) == 1 and "linje" in t.fejl[0] and "YAML" in t.fejl[0]


def test_tabulator_og_dobbelt_noegle():
    tekst = yaml.safe_dump(GYLDIG, allow_unicode=True, sort_keys=False)
    t = _tjek(tekst=tekst.replace("  p2:", "\tp2:", 1))
    assert _fejl_om(t, "tabulator")
    t = _tjek(tekst=tekst.replace("  p3:", "  p2:", 1))
    assert _fejl_om(t, '"p2" står to gange')


def test_pladsholder_koordinat():
    t = _tjek(_med(lambda c: c["points"]["p3"].update(lat=55.0, lon=8.0)))
    assert _fejl_om(t, "points > p3", "pladsholder")
    t = _tjek(_med(lambda c: c["points"]["p3"].update(lat=55.0, lon=8.0)), trin="stopnavne")
    assert not t.fejl and any("pladsholder" in a for a in t.advarsler)    # valg 1: kun advarsel


def test_punkt_id_findes_ikke():
    for aendring, hvor in [(lambda c: c["point_order"]["direction_1"].append("p9"), "point_order > direction_1"),
                           (lambda c: c["distances"]["d2"].update(to="p4"), "distances > d2 > to"),
                           (lambda c: c["straekninger"][1].update(til="p33"), "straekninger > oest > til")]:
        t = _tjek(_med(aendring))
        assert _fejl_om(t, hvor, "findes ikke"), t.tekst()
    t = _tjek(_med(lambda c: c["straekninger"][1].update(koretid_afstand="d7")))
    assert _fejl_om(t, "koretid_afstand", '"d7"')


def test_manglende_og_tomme_stop():
    t = _tjek(_med(lambda c: c["stops"].pop("direction_2")))
    assert _fejl_om(t, "stops > direction_2", "ingen stop")
    t = _tjek(_med(lambda c: c["stops"]["direction_1"].update(end="")))
    assert _fejl_om(t, "stops > direction_1 > end", "tomt")
    t = _tjek(_med(lambda c: c["stops"]["direction_1"].update(start="Stop før p1 (By)")))
    assert _fejl_om(t, "pladsholder")


def test_stopnavn_findes_ikke_i_data():
    with tempfile.TemporaryDirectory() as tmp:
        sti = _skriv(tmp, _med(lambda c: c["stops"]["direction_1"].update(end="S55 (By)")))
        (Path(tmp) / "resultat").mkdir()
        (Path(tmp) / T.CACHE).write_text(yaml.safe_dump({"retninger": {
            "1": {"stop": [{"navn": f"S{i} (By)", "lat": LAT, "lon": 8.0} for i in range(7)]},
            "2": {"stop": [{"navn": f"S{i} modsat (By)", "lat": LAT, "lon": 8.0} for i in range(7)]}}}, allow_unicode=True), encoding="utf-8")
        t = T.tjek(sti)
        assert _fejl_om(t, '"S55 (By)" findes ikke i data', 'Mente du "S5 (By)"?')
        sti.write_text(yaml.safe_dump(GYLDIG, allow_unicode=True), encoding="utf-8")
        assert T.tjek(sti).fejl == []


def test_datoer_forkert_format_og_omvendt():
    t = _tjek(_med(lambda c: c["periods"]["A"].update(start="01-01-2025")))
    assert _fejl_om(t, "periods > A > start", "ÅÅÅÅ-MM-DD")
    t = _tjek(_med(lambda c: c["periods"]["B"].update(start="2025-02-30")))
    assert _fejl_om(t, "ikke en gyldig dato")
    t = _tjek(_med(lambda c: c["periods"]["A"].update(start="2025-04-01")))
    assert _fejl_om(t, "periods > A", "ligger efter end")
    t = _tjek(_med(lambda c: c["udvalg"].update(helligdage=["17-04-2025"])))
    assert _fejl_om(t, "udvalg > helligdage")


def test_datafil_mangler():
    with tempfile.TemporaryDirectory() as tmp:
        sti = _skriv(tmp, GYLDIG)
        (Path(tmp) / "data" / "B" / "List.csv").unlink()
        t = T.tjek(sti)
        assert _fejl_om(t, "data > Periode_B > list_csv", "findes ikke")
        assert not T.tjek(sti, "stopnavne").fejl            # valg 1 bruger kun data A
        assert not T.tjek(sti, "fuld", ["A"]).fejl          # PERIODER=A


def test_periode_uden_data_koeres_ikke():
    t = _tjek(_med(lambda c: c["data"].pop("Periode_B")))
    assert not t.fejl and t.koeres == ["A"] and any("køres ikke" in a for a in t.advarsler)


def test_element_uden_for_straekningen_og_langt_fra_linjen():
    t = _tjek(_med(lambda c: c["straekninger"][0]["elementer"][0].update(lon=8.007)))
    assert _fejl_om(t, "straekninger > vest > elementer > Bump 1", "uden for strækningen")
    t = _tjek(_med(lambda c: c["straekninger"][0]["elementer"][0].update(lat=LAT + 0.0005)))
    assert not t.fejl and any("fra linjen" in a for a in t.advarsler)


def test_ukendte_noegler_og_stavefejl_med_forslag():
    t = _tjek(_med(lambda c: c.update(distance=c.pop("distances"))))
    assert _fejl_om(t, 'Nøglen "distance" kendes ikke', 'Mente du "distances"?')
    t = _tjek(_med(lambda c: c["straekninger"][0].update(elemeter=[])))
    assert _fejl_om(t, "straekninger > vest > elemeter", '"elementer"')
    t = _tjek(_med(lambda c: c["rapport"]["vej"].update(bumptyp="x")))
    assert _fejl_om(t, "rapport > vej > bumptyp", '"bumptype"')
    t = _tjek(_med(lambda c: c["points"]["p1"].update(nme="x")))
    assert _fejl_om(t, "points > p1 > nme", '"name"')
    t = _tjek(_med(lambda c: c["straekninger"][0]["elementer"][0].update(type="bmp")))
    assert _fejl_om(t, "type", '"bump"')


def test_kryds_med_komfort_krav_afvises():
    t = _tjek(_med(lambda c: c.update(analysetype="kryds")))
    assert _fejl_om(t, "Et kryds bruger ikke straekninger")
    t = _tjek(_med(lambda c: c.update(analysetype="krydds")))
    assert _fejl_om(t, "analysetype")


def test_straekning_uden_distance_og_dobbelt_id():
    t = _tjek(_med(lambda c: c["distances"].pop("d2")))
    assert _fejl_om(t, "straekninger > oest", "Ingen distance går fra p2 til p3")
    t = _tjek(_med(lambda c: c["straekninger"][1].update(id="vest")))
    assert _fejl_om(t, 'id "vest" bruges to gange')


def test_typer_og_navne():
    t = _tjek(_med(lambda c: c["points"]["p1"].update(lat="55,48")))
    assert _fejl_om(t, "points > p1", "skal være tal")
    t = _tjek(_med(lambda c: c["points"]["p1"].update(lat=8.0, lon=55.48)))
    assert _fejl_om(t, "byttet om")
    t = _tjek(_med(lambda c: c["points"]["p2"].update(name="Vest")))
    assert _fejl_om(t, '"Vest" bruges også af p1')
    t = _tjek(_med(lambda c: c["straekninger"][0]["elementer"][0].update(radius_m=0)))
    assert _fejl_om(t, "radius_m")
    t = _tjek(_med(lambda c: c["udvalg"].update(dagtype="weekend")))
    assert _fejl_om(t, "udvalg > dagtype")
    t = _tjek(_med(lambda c: c["rapport"].update(stoppesteder=[{"navn": "X", "retning": 3, "lat": LAT, "lon": 8.0}])))
    assert _fejl_om(t, "retning")


def test_review_fund_afvises_uden_exception():
    """Fund fra review: ugyldigt strækning-id, distance uden/dobbelt navn, uventede typer, ukendt strækning på stop."""
    t = _tjek(_med(lambda c: c["straekninger"][0].update(id="a&b")))
    assert _fejl_om(t, 'id "a&b" må kun have')
    t = _tjek(_med(lambda c: c["distances"]["d1"].pop("name")))
    assert _fejl_om(t, "distances > d1 > name", "intet navn")
    t = _tjek(_med(lambda c: c["distances"]["d2"].update(name="Vest-Midt")))
    assert _fejl_om(t, '"Vest-Midt" bruges også af d1')
    for aendring in (lambda c: c["straekninger"][0].update(komfort=["x"]),
                     lambda c: c["distances"]["d1"].update({"from": ["p1"]}),
                     lambda c: c["data"]["Periode_A"].update(details_csv=5),
                     lambda c: c["periods"]["A"].update(start=__import__("datetime").datetime(2025, 1, 1, 8, 0))):
        assert _tjek(_med(aendring)).fejl                  # fejl, ikke exception
    t = _tjek(_med(lambda c: c["rapport"].update(stoppesteder=[{"navn": "X", "retning": 1, "lat": LAT, "lon": 8.0, "straekning": "nord"}])))
    assert _fejl_om(t, 'Strækningen "nord" findes ikke')


def test_proeve_kraever_kun_data_a():
    with tempfile.TemporaryDirectory() as tmp:
        sti = _skriv(tmp, GYLDIG)
        (Path(tmp) / "data" / "B" / "Details.csv").unlink()
        assert not T.tjek(sti, "proeve").fejl and T.tjek(sti, "fuld").fejl


# ------------------------------------------------------------------ nøglesættet følger programmerne
def _modul(navn, fil):
    spec = importlib.util.spec_from_file_location(navn, fil)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_noeglesaet_daekker_programmernes_standardvaerdier():
    a = _modul("analyse_v22", PK / "analyse_v2.2.py")
    assert set(a.DEFAULTS) <= T.ANALYSE_PARAMS, set(a.DEFAULTS) - T.ANALYSE_PARAMS
    k = _modul("komfort_v10", PK / "komfort_v1.0.py")
    assert set(k.DEFAULTS) <= T.KOMFORT, set(k.DEFAULTS) - T.KOMFORT
    eks = yaml.safe_load((PK / "config_eksempel.yaml").read_text(encoding="utf-8"))
    assert set(eks) <= T.TOP and set(eks["rapport"]) <= T.RAPPORT and set(eks["komfort"]) <= T.KOMFORT


if __name__ == "__main__":
    for navn, f in list(globals().items()):
        if navn.startswith("test_"):
            f()
            print("OK", navn)
