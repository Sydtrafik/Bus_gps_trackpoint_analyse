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


if __name__ == "__main__":
    for navn, f in list(globals().items()):
        if navn.startswith("test_"):
            f()
            print("OK", navn)
