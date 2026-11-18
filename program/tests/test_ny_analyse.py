"""Tester ny_analyse.py og skabelonerne (den nemme vej). Ingen data nødvendig.

Kør: python -m pytest tests/test_ny_analyse.py -q   (eller: python tests/test_ny_analyse.py)
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

PK = Path(__file__).resolve().parent.parent
SCRIPT = PK / "skabeloner" / "ny_analyse.py"


def _opret(rod, navn="Testvej Ærø"):
    return _koer(SCRIPT, navn, rod)


def _koer(script, navn, rod):
    # som ny_analyse.bat: PYTHONUTF8=1, ellers skrives fejltekster med æøå i konsollens tegnsæt
    env = {**os.environ, "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, str(script), "--navn", navn, "--rod", str(rod), "--ingen-explorer"],
                          capture_output=True, text=True, encoding="utf-8", env=env)


def test_opretter_mappe_config_og_bat():
    with tempfile.TemporaryDirectory() as tmp:
        r = _opret(tmp)
        assert r.returncode == 0, r.stderr
        m = Path(tmp) / "Testvej Ærø"
        for under in ("data/A", "data/B", "resultat"):
            assert (m / under).is_dir()
        assert (m / "Vejledning - trin for trin.txt").exists()
        raw = (m / "koer_analyse.bat").read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), "bat må ikke have BOM (første linje virker så ikke)"
        assert b"\n" not in raw.replace(b"\r\n", b""), "bat skal have CRLF-linjeskift"
        tekst = raw.decode("utf-8")
        assert f'set "VAERKTOEJ={PK}"' in tekst and "__VAERKTOEJ__" not in tekst
        assert tekst.splitlines()[1].startswith("chcp 65001")


def _kopi_af_skabeloner(rod):
    # ny_analyse.py tager værktøjets sti fra sin egen placering: kopiér skabeloner\ til en sti med specialtegn
    ny = Path(rod) / "program" / "skabeloner"
    shutil.copytree(SCRIPT.parent, ny, ignore=shutil.ignore_patterns("__pycache__"))
    return ny / "ny_analyse.py"


def test_vaerktoejssti_med_og_tegn_virker_i_bat():
    with tempfile.TemporaryDirectory() as tmp:
        script = _kopi_af_skabeloner(Path(tmp) / "R&D (test)")
        r = _koer(script, "Vej", tmp)
        assert r.returncode == 0, r.stderr
        bat = (Path(tmp) / "Vej" / "koer_analyse.bat").read_text(encoding="utf-8")
        linje = next(l for l in bat.splitlines() if l.startswith('set "VAERKTOEJ='))
        if os.name != "nt":
            return
        # cmd skal kunne læse linjen og finde værktøjet bagefter (& ville ellers starte en ny kommando)
        prove = Path(tmp) / "prove.bat"
        prove.write_bytes(("@echo off\r\nchcp 65001 >nul\r\n" + linje + "\r\n"
                           'if exist "%VAERKTOEJ%\\skabeloner\\ny_analyse.py" (echo FUNDET) else (echo MANGLER)\r\n')
                          .encode("utf-8"))
        ud = subprocess.run(["cmd", "/c", str(prove)], capture_output=True, text=True)
        assert ud.stdout.strip() == "FUNDET", ud.stdout + ud.stderr


def test_vaerktoejssti_med_procent_afvises():
    with tempfile.TemporaryDirectory() as tmp:
        script = _kopi_af_skabeloner(Path(tmp) / "50% test")
        r = _koer(script, "Vej", tmp)
        assert r.returncode != 0 and "%" in r.stderr
        assert not (Path(tmp) / "Vej").exists()


def test_findes_allerede_roeres_ikke():
    with tempfile.TemporaryDirectory() as tmp:
        assert _opret(tmp).returncode == 0
        cfg = Path(tmp) / "Testvej Ærø" / "config.yaml"
        cfg.write_text("min egen", encoding="utf-8")
        r = _opret(tmp)
        assert r.returncode != 0 and "findes allerede" in (r.stderr + r.stdout)
        assert cfg.read_text(encoding="utf-8") == "min egen"


def test_ulovligt_navn():
    with tempfile.TemporaryDirectory() as tmp:
        assert _opret(tmp, "a/b").returncode != 0


def test_config_skabelon_har_det_kaeden_kraever():
    cfg = yaml.safe_load((PK / "skabeloner" / "config.yaml").read_text(encoding="utf-8"))
    assert set(cfg["periods"]) == {"A", "B"}
    assert cfg["data"]["Periode_A"]["details_csv"] == "data/A/Details.csv"
    pts = cfg["points"]
    assert cfg["komfort"]["fra"] in pts and cfg["komfort"]["til"] in pts
    assert cfg["point_order"]["direction_1"] == [cfg["komfort"]["fra"], cfg["komfort"]["til"]]
    assert cfg["distances"]["d1"]["from"] == "p1" and cfg["distances"]["d1"]["to"] == "p2"
    assert set(cfg["stops"]) == {"direction_1", "direction_2"}
    assert all(e["type"] in ("bump", "indsnævring", "andet") for e in cfg["elementer"])
    assert cfg["komfort"]["bump_vinduer"] == {}   # standardens Kvaglundvej-vinduer må ikke følge med


if __name__ == "__main__":
    for navn, f in list(globals().items()):
        if navn.startswith("test_"):
            f()
            print("OK", navn)
