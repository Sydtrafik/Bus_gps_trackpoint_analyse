"""Tester lav_konklusioner_html.py på pakkens egen konklusionsfil og en konstrueret fil med to analyser.

Kør: python -m pytest tests/test_konklusioner_html.py -q
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

PK = Path(__file__).resolve().parent.parent
SCRIPT = PK / "lav_konklusioner_html.py"
MD = PK.parent / "nationale_analysekonklusioner.md"

spec = importlib.util.spec_from_file_location("konkl", SCRIPT)
K = importlib.util.module_from_spec(spec)
spec.loader.exec_module(K)

BLOK = """### {titel}

| Felt | Værdi |
|---|---|
| Opdateret | 2026-11-13 |
| By | {by} |
| Kort | [Strækningen](https://www.google.com/maps/dir/?api=1&origin=1,2&destination=3,4) |
| Vejtype | Boligvej |
| Type bump | {bump} |
| Fund: køretid | Uden standsning ved stop: median 50 → 60 s (+10 s). |
| Kontaktperson | Test \\| Person |
"""


def _md(*blokke):
    return ("# X\n\n**Senest opdateret:** 2026-11-13 af test\n\n## Oversigt\n\n| Vej, by | Opdateret |\n|---|---|\n"
            "| Atest, By1 | 2026-11-13 |\n\n## Analyser\n\n" + "\n".join(blokke)
            + "\n---\n\n## Skabelon\n\n```markdown\n### <Vejnavn>, <by>\n\n| Felt | Værdi |\n|---|---|\n| By | |\n```\n")


def test_links_kun_http_anker_og_relative():
    # filen tager imod bidrag fra andre: javascript:/data: må ikke blive til links
    assert 'href="https://example.org/a"' in K.inline("[kort](https://example.org/a)")
    assert 'href="#oversigt"' in K.inline("[op](#oversigt)")
    assert 'href="vejledning/kilder/README.md"' in K.inline("[kilder](vejledning/kilder/README.md)")
    for ond in ("javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,x", "vbscript:x"):
        ud = K.inline(f"[klik]({ond})")
        assert "href" not in ud, ud


def test_bumptyper_fra_tekst():
    navne = [n for n, _ in K.bumptyper("Cirkelbump eller modificeret cirkelbump (ikke bekræftet; modificerede sinusbump ...)")]
    assert navne == ["Cirkelbump", "Modificeret cirkelbump"]
    assert [n for n, _ in K.bumptyper("Trapezbump med modificerede ramper")] == ["Trapezbump med modificerede ramper"]
    assert K.bumptyper("ingen bump") == []
    # sinusbump får ingen tegning (kun den modificerede har en); den modificerede tæller ikke også som sinusbump
    assert K.bumptyper("Sinusbump (oplyst)") == [("Sinusbump", [])]
    assert [n for n, _ in K.bumptyper("Modificeret sinusbump")] == ["Modificeret sinusbump"]


def test_laes_md_springer_skabelon_over():
    d = K.laes_md(_md(BLOK.format(titel="Atest, By1 (2026)", by="By1", bump="Pudebump"),
                      BLOK.format(titel="Btest, By2 (2025)", by="By2", bump="Hævet flade")))
    assert [t for t, _ in d["analyser"]] == ["Atest, By1 (2026)", "Btest, By2 (2025)"]
    assert d["analyser"][0][1]["Kontaktperson"] == "Test | Person"
    assert d["senest"].startswith("2026-11-13")


def test_html_med_to_analyser():
    with tempfile.TemporaryDirectory() as t:
        md = Path(t) / "k.md"
        md.write_text(_md(BLOK.format(titel="Atest, By1 (2026)", by="By1", bump="Pudebump"),
                          BLOK.format(titel="Btest, By2 (2025)", by="By2", bump="Hævet flade")), encoding="utf-8")
        r = subprocess.run([sys.executable, str(SCRIPT), "--md", str(md)], capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        h = (Path(t) / "k.html").read_text(encoding="utf-8")
        assert h.count('<tr data-f0=') == 2
        assert 'alt="Pudebump"' in h and 'alt="Hævet flade"' in h
        assert "data:image/svg+xml;base64," in h
        assert "&lt;Vejnavn&gt;" not in h          # skabelonen er ikke med


def test_pakkens_konklusionsfil():
    with tempfile.TemporaryDirectory() as t:
        ud = Path(t) / "k.html"
        r = subprocess.run([sys.executable, str(SCRIPT), "--out", str(ud)], capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        h = ud.read_text(encoding="utf-8")
        assert "Kvaglundvej, Esbjerg (2025)" in h
        foer = h.split('id="bump-fane"')[0]                 # alt før galleriet med alle tegninger
        assert "Bumptype: Sinusbump" in foer and "Ingen tegning af denne bumptype" in foer   # Kvaglundvej (Anthon 2026-11-19)
        assert 'alt="Modificeret sinusbump"' not in foer and 'alt="Cirkelbump"' not in foer
        assert "google.com/maps" in h
