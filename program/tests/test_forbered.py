"""Tester skabeloner/forbered.py (den nemme vej) på konstruerede data. Ingen rigtige data nødvendig.

Kør: python -m pytest tests/test_forbered.py -q   (eller: python tests/test_forbered.py)
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

PK = Path(__file__).resolve().parent.parent
SCRIPT = PK / "skabeloner" / "forbered.py"
LAT = 55.48
# Stoppesteder langs en lige vej (længdegrad). Strækningen går fra 8.000 (p1) til 8.010 (p2), ca. 630 m.
STOP_LON = [7.985, 7.990, 7.995, 8.004, 8.015, 8.020, 8.025]


def _cfg(mappe, **ekstra):
    cfg = {
        "periods": {"A": {"name": "Før", "start": "2025-01-01", "end": "2025-01-31"}},
        "data": {"Periode_A": {"details_csv": "data/A/Details.csv", "list_csv": "data/A/List.csv"}, "output": "resultat/result.csv"},
        "points": {"p1": {"name": "Vest", "lat": LAT, "lon": 8.000}, "p2": {"name": "Øst", "lat": LAT, "lon": 8.010}},
        "komfort": {"fra": "p1", "til": "p2", "bump_vinduer": {}},
        "elementer": [{"navn": "Bump 1", "type": "bump", "lat": LAT, "lon": 8.002},
                      {"navn": "Bump 2", "type": "bump", "lat": LAT, "lon": 8.008, "radius_m": 50},
                      {"navn": "Indsnævring", "type": "indsnævring", "lat": LAT, "lon": 8.005}],
    }
    cfg.update(ekstra)
    (Path(mappe) / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return Path(mappe) / "config.yaml"


def _data(mappe, retning_vest_oest="1"):
    """To ture pr. retning. Mod øst hedder stoppene 'S0'..'S6', mod vest 'S6 modsat'..'S0 modsat'."""
    d = Path(mappe) / "data" / "A"
    d.mkdir(parents=True)
    andet = "2" if retning_vest_oest == "1" else "1"
    rows = ["Turreference;Stop-navn;Stop-nummer;Breddegrad (PLANLAGT);Længdegrad (PLANLAGT)"]
    liste = ["Turnummer;Retningsflag"]
    for tur in ("t1", "t2"):
        liste.append(f"{tur};{retning_vest_oest}")
        for i, lon in enumerate(STOP_LON):
            rows.append(f"{tur};S{i} (By);{i};{LAT};{lon}")
            rows.append(f"{tur};Pegeredskab {i};;{LAT};{lon + 0.001}")
    for tur in ("t3", "t4"):
        liste.append(f"{tur};{andet}")
        for i, lon in reversed(list(enumerate(STOP_LON))):
            rows.append(f"{tur};S{i} modsat (By);{i + 10};{LAT + 0.0002};{lon}")
    (d / "Details.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (d / "List.csv").write_text("\n".join(liste) + "\n", encoding="utf-8")


def _koer(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, encoding="utf-8")


def test_bump_vinduer_ud_fra_radius_og_absolutte_stier():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        ud = Path(tmp) / "resultat" / "config_beregnet.yaml"
        r = _koer("config", "--config", cfg, "--out", ud)
        assert r.returncode == 0, r.stderr
        b = yaml.safe_load(ud.read_text(encoding="utf-8"))
        v = b["komfort"]["bump_vinduer"]
        assert set(v) == {"Bump 1", "Bump 2"}                       # indsnævringer får ikke vindue
        assert v["Bump 1"] == [96, 156]                             # 0,002 grader ved 55,48° N = 126 m, standardradius 30
        assert v["Bump 2"][1] - v["Bump 2"][0] == 100              # radius_m 50
        assert Path(b["data"]["Periode_A"]["details_csv"]).is_absolute()


def test_udfyldte_bump_vinduer_bruges_som_de_er():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, komfort={"fra": "p1", "til": "p2", "bump_vinduer": {"x": [1, 2]}})
        ud = Path(tmp) / "b.yaml"
        assert _koer("config", "--config", cfg, "--out", ud).returncode == 0
        assert yaml.safe_load(ud.read_text(encoding="utf-8"))["komfort"]["bump_vinduer"] == {"x": [1, 2]}


def test_stopnavne_pr_retning_med_forslag():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        _data(tmp)
        ud = Path(tmp) / "stopnavne.txt"
        r = _koer("stopnavne", "--config", cfg, "--out", ud)
        assert r.returncode == 0, r.stderr
        t = ud.read_text(encoding="utf-8")
        assert "Pegeredskab" not in t
        assert 'direction_1: {start: "S1 (By)", end: "S5 (By)"}' in t
        assert 'direction_2: {start: "S5 modsat (By)", end: "S1 modsat (By)"}' in t
        assert "OBS" not in t


def test_stopnavne_siger_til_naar_p1_og_p2_skal_byttes():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        _data(tmp, retning_vest_oest="2")      # retning 1 kører mod vest, altså fra p2 mod p1
        ud = Path(tmp) / "stopnavne.txt"
        assert _koer("stopnavne", "--config", cfg, "--out", ud).returncode == 0
        t = ud.read_text(encoding="utf-8")
        assert "OBS: retning 1 kører fra p2 mod p1" in t and "stops:" not in t


def test_stopnavne_bruger_de_yderste_punkter_ved_flere_punkter():
    """Tre punkter (p1, p3, p2 i køreorden): forslaget gælder fra det første til det sidste punkt, ikke p1-p2."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, points={"p1": {"name": "Vest", "lat": LAT, "lon": 8.000}, "p3": {"name": "Midt", "lat": LAT, "lon": 8.004},
                                "p2": {"name": "Øst", "lat": LAT, "lon": 8.016}},
                   point_order={"direction_1": ["p1", "p3", "p2"], "direction_2": ["p2", "p3", "p1"]})
        _data(tmp)
        ud = Path(tmp) / "stopnavne.txt"
        assert _koer("stopnavne", "--config", cfg, "--out", ud).returncode == 0
        t = ud.read_text(encoding="utf-8")
        assert 'direction_1: {start: "S1 (By)", end: "S6 (By)"}' in t, t       # S5 (8.015) ligger før p2 (8.016)
        assert "OBS" not in t


def test_stopnavne_kryds_i_en_retning_siger_hvilken_retning():
    """Kryds med kun direction_1, men punkterne køres i data som retning 2: OBS + forslag for direction_2."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, analysetype="kryds", komfort=None, elementer=None,
                   points={"pA": {"name": "Før", "lat": LAT, "lon": 8.000}, "pS": {"name": "Stoplinje", "lat": LAT, "lon": 8.004},
                           "pB": {"name": "Efter", "lat": LAT, "lon": 8.010}},
                   point_order={"direction_1": ["pA", "pS", "pB"]})
        _data(tmp, retning_vest_oest="2")
        ud = Path(tmp) / "stopnavne.txt"
        assert _koer("stopnavne", "--config", cfg, "--out", ud).returncode == 0
        t = ud.read_text(encoding="utf-8")
        assert "køres i data som retning 2" in t and "Skriv direction_2 i stedet for direction_1" in t
        assert 'direction_2: {start: "S1 (By)", end: "S5 (By)"}' in t and "direction_1: {" not in t


def test_stoppesteder_paa_straekningerne_og_cache():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        _data(tmp)
        ud = Path(tmp) / "stopnavne.txt"
        assert _koer("stopnavne", "--config", cfg, "--out", ud).returncode == 0
        t = ud.read_text(encoding="utf-8")
        assert '- {navn: "S3", retning: 1, lat: 55.48, lon: 8.004}' in t                  # på strækningen, retning 1
        assert '- {navn: "S3 modsat", retning: 2, lat: 55.4802, lon: 8.004}' in t
        assert '"S4"' not in t and '"S2"' not in t                                        # uden for strækningen
        cache = yaml.safe_load((Path(tmp) / "resultat" / "stoppesteder_hafas.yaml").read_text(encoding="utf-8"))
        assert [s["navn"] for s in cache["retninger"]["1"]["stop"]] == [f"S{i} (By)" for i in range(7)]
        # config: tom rapport.stoppesteder fyldes fra cachen; udfyldt bruges som den er
        b = Path(tmp) / "b.yaml"
        assert _koer("config", "--config", cfg, "--out", b).returncode == 0
        sp = yaml.safe_load(b.read_text(encoding="utf-8"))["rapport"]["stoppesteder"]
        assert {(s["navn"], s["retning"]) for s in sp} == {("S3", 1), ("S3 modsat", 2)}
        cfg2 = _cfg(tmp, rapport={"stoppesteder": [{"navn": "Eget", "retning": 1, "lat": LAT, "lon": 8.005}]})
        assert _koer("config", "--config", cfg2, "--out", b).returncode == 0
        assert yaml.safe_load(b.read_text(encoding="utf-8"))["rapport"]["stoppesteder"][0]["navn"] == "Eget"


def test_config_flere_straekninger_faar_bump_vinduer_pr_straekning():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp, komfort={"bump_vinduer": {}}, elementer=None,
                   points={"p1": {"name": "Vest", "lat": LAT, "lon": 8.000}, "p2": {"name": "Midt", "lat": LAT, "lon": 8.005},
                           "p3": {"name": "Øst", "lat": LAT, "lon": 8.010}},
                   straekninger=[{"id": "v", "navn": "Vest", "fra": "p1", "til": "p2",
                                  "elementer": [{"navn": "Bump 1", "type": "bump", "lat": LAT, "lon": 8.002}]},
                                 {"id": "o", "navn": "Øst", "fra": "p2", "til": "p3",
                                  "elementer": [{"navn": "Bump 2", "type": "bump", "lat": LAT, "lon": 8.007, "radius_m": 40}]}])
        b = Path(tmp) / "b.yaml"
        assert _koer("config", "--config", cfg, "--out", b).returncode == 0
        c = yaml.safe_load(b.read_text(encoding="utf-8"))
        assert c["komfort"]["bump_vinduer"] == {}
        assert c["straekninger"][0]["komfort"]["bump_vinduer"] == {"Bump 1": [96, 156]}
        assert c["straekninger"][1]["komfort"]["bump_vinduer"] == {"Bump 2": [86, 166]}   # 0,002 grader = 126 m fra p2


def test_config_review_fund():
    """Tom komfort:, type Bump med stort B, fælles bump_vinduer ved strækninger, og cache fra en anden Details.csv."""
    with tempfile.TemporaryDirectory() as tmp:
        b = Path(tmp) / "b.yaml"
        cfg = _cfg(tmp, komfort=None, elementer=None,
                   straekninger=[{"id": "v", "navn": "V", "fra": "p1", "til": "p2",
                                  "elementer": [{"navn": "Bump 1", "type": "Bump ", "lat": LAT, "lon": 8.002}]}])
        r = _koer("config", "--config", cfg, "--out", b)
        assert r.returncode == 0, r.stderr
        assert yaml.safe_load(b.read_text(encoding="utf-8"))["straekninger"][0]["komfort"]["bump_vinduer"] == {"Bump 1": [96, 156]}
        cfg = _cfg(tmp, komfort={"bump_vinduer": {"x": [10, 20]}}, elementer=None,
                   straekninger=[{"id": "v", "navn": "V", "fra": "p1", "til": "p2",
                                  "elementer": [{"navn": "Bump 1", "type": "bump", "lat": LAT, "lon": 8.002}]}])
        assert _koer("config", "--config", cfg, "--out", b).returncode == 0
        c = yaml.safe_load(b.read_text(encoding="utf-8"))
        assert c["komfort"]["bump_vinduer"] == {"x": [10, 20]} and not c["straekninger"][0]["komfort"].get("bump_vinduer")
        # cache: gyldig for samme Details.csv, ignoreres efter ny eksport
        cfg = _cfg(tmp)
        _data(tmp)
        assert _koer("stopnavne", "--config", cfg, "--out", Path(tmp) / "s.txt").returncode == 0
        assert _koer("config", "--config", cfg, "--out", b).returncode == 0
        assert yaml.safe_load(b.read_text(encoding="utf-8"))["rapport"]["stoppesteder"]
        det = Path(tmp) / "data" / "A" / "Details.csv"
        det.write_text(det.read_text(encoding="utf-8") + "t9;Ny (By);1;55.48;8.0\n", encoding="utf-8")
        assert _koer("config", "--config", cfg, "--out", b).returncode == 0
        assert yaml.safe_load(b.read_text(encoding="utf-8"))["rapport"]["stoppesteder"] == []


def test_info_til_bat():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        r = _koer("info", "--config", cfg)
        assert "CFG_TYPE=straekning" in r.stdout and "CFG_PERIODER=A" in r.stdout and "CFG_ELEMENTER=1" in r.stdout
        cfg = _cfg(tmp, komfort=None, elementer=None)
        r = _koer("info", "--config", cfg)
        assert "CFG_TYPE=kryds" in r.stdout and "CFG_ANTAL=0" in r.stdout


def test_kontrolkort_uden_net():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _cfg(tmp)
        _data(tmp)
        assert _koer("stopnavne", "--config", cfg, "--out", Path(tmp) / "s.txt").returncode == 0
        ud = Path(tmp) / "kontrolkort.html"
        r = _koer("kort", "--config", cfg, "--out", ud, "--uden-net")
        assert r.returncode == 0, r.stderr
        h = ud.read_text(encoding="utf-8")
        assert "const Vejkort" in h and "Vejkort.lav(" in h                    # vejkort.js indlejret
        assert "https://www.google.com/maps?q=55.480000,8.002000" in h        # Bump 1 med link
        assert "p1 Vest" in h and "Stop 1: S3" in h and "Stop 2: S3 modsat" in h
        assert "kun punkterne" in h                                           # intet vejkort uden net
        assert "leaflet" not in h.lower() and "tile" not in h.lower()


def test_kontrolkort_overpass_fejl_giver_kun_punkterne():
    """Overpass svarer 502: kortet laves alligevel, uden vejkort, og siden siger det."""
    sys.path.insert(0, str(PK))
    sys.path.insert(0, str(SCRIPT.parent))
    import forbered
    import lav_vejkort

    def fejler(*_a, **_k):
        raise lav_vejkort.VejkortFejl("Kunne ikke hente vejkortet fra Overpass (HTTP 502).")

    gammel = lav_vejkort.hent_til
    lav_vejkort.hent_til = fejler
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(tmp)
            ud = Path(tmp) / "kontrolkort.html"
            forbered.kort(cfg, ud, hent=True)
            h = ud.read_text(encoding="utf-8")
            assert "HTTP 502" in h and "kortet viser kun punkterne" in h
            assert '"grund": null' in h and "p1 Vest" in h
    finally:
        lav_vejkort.hent_til = gammel


if __name__ == "__main__":
    for navn, f in list(globals().items()):
        if navn.startswith("test_"):
            f()
            print("OK", navn)
