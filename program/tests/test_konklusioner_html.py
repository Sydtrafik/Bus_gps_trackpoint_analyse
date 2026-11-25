"""Tester lav_konklusioner_html.py: tjek af filerne i analyser\\, HTML og Markdown, og at rodens filer er lavet igen.

Kør: python -m pytest tests/test_konklusioner_html.py -q   (PYTHONUTF8=1; browsertesten kræver playwright, ellers SKIP)
"""
import copy
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

PK = Path(__file__).resolve().parent.parent
ROD = PK.parent
SCRIPT = PK / "lav_konklusioner_html.py"

spec = importlib.util.spec_from_file_location("konkl", SCRIPT)
K = importlib.util.module_from_spec(spec)
spec.loader.exec_module(K)

GOD = {
    "skema": 1, "type": "foer_efter", "vej": "Testvej", "by": "Testby", "aar": 2025, "vejtype": "Boligvej",
    "linjer": "1", "bustype": "ikke oplyst", "aendring": "2 cirkelbump",
    "fartdaempere": [{"type": "cirkelbump", "antal": 2}], "hastighed_kmt": {"foer": 50, "efter": 40},
    "laengde_m": 400, "kort": "https://www.google.com/maps/dir/?api=1&origin=1,2&destination=3,4",
    "dage": "hverdage",
    "perioder": {"foer": {"fra": "2025-01-01", "til": "2025-02-01", "dage": 20},
                 "efter": {"fra": "2025-03-01", "til": "2025-04-01", "dage": 21}},
    "ture": {"foer": 100, "efter": 120}, "koeretid_s": {"foer": 40, "efter": 50}, "gnsfart_kmt": {"foer": 36, "efter": 29},
    "laveste_fart_kmt": {"foer": 40, "efter": 22}, "maerkbar_opbremsning_pct": {"foer": 10.5, "efter": 50.25},
    "maerkbar_acceleration_pct": {"foer": 12, "efter": 40},
    "forbehold": ["Kun test."], "sammenligning_vejregler": "ikke sammenlignet", "vaerktoej": "test",
    "opdateret": "2026-11-25", "kontakt": "testbruger",
}


def _skriv(mappe, navn, d):
    p = Path(mappe) / navn
    p.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return p


def _fejl(**aendr):
    d = copy.deepcopy(GOD)
    for k, v in aendr.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    return " | ".join(K.tjek_analyse(d))


def test_god_fil_godkendes():
    assert K.tjek_analyse(copy.deepcopy(GOD)) == []
    en = copy.deepcopy(GOD)
    en.update(type="en_periode", perioder={"periode": GOD["perioder"]["foer"]}, ture={"periode": 100},
              koeretid_s={"periode": 40}, hastighed_kmt={"periode": 40}, gnsfart_kmt=None, laveste_fart_kmt=None,
              maerkbar_opbremsning_pct=None, maerkbar_acceleration_pct=None)
    assert K.tjek_analyse(en) == []


def test_kendte_negative_afvises_med_felt():
    # hver fejl skal give en besked, der nævner feltet (kendt negativ: skal kunne sige nej)
    assert "'type' skal være foer_efter, en_periode eller kryds" in _fejl(type="før")
    assert "'kontakt' mangler" in _fejl(kontakt=None)
    assert "'vej' mangler" in _fejl(vej="")
    assert "'koeretid_s' efter skal være et tal" in _fejl(koeretid_s={"foer": 40, "efter": "50"})   # tal som tekst
    assert "'laengde_m' skal være et tal" in _fejl(laengde_m="400 m")
    assert "'by' er ikke udfyldt" in _fejl(by="UDFYLD")
    assert "mailadresse" in _fejl(kontakt="navn@example.org")
    assert "ukendt felt 'koretid_s'" in _fejl(koretid_s={"foer": 1})
    assert "'kort' skal være et link" in _fejl(kort="javascript:alert(1)")
    assert "perioderne foer, efter" in _fejl(perioder={"periode": GOD["perioder"]["foer"]})
    assert "'aar' skal være et heltal" in _fejl(aar="2025")


def test_ugyldig_fil_stopper_kørslen():
    with tempfile.TemporaryDirectory() as t:
        _skriv(t, "god_by_2025.yaml", GOD)
        _skriv(t, "darlig_by_2025.yaml", {**GOD, "type": "foer/efter"})
        r = subprocess.run([sys.executable, str(SCRIPT), "--analyser", t, "--tjek"], capture_output=True, text=True, encoding="utf-8")
        assert r.returncode != 0
        assert "darlig_by_2025.yaml" in r.stderr and "'type'" in r.stderr and "god_by_2025" not in r.stderr


def test_udledte_tal_og_flertal():
    x = K.raekke("a", copy.deepcopy(GOD))
    assert x["delta"] == 10 and x["delta100"] == 2.5 and x["opbrPP"] == 39.8
    assert K.daemper_tekst([{"type": "sinusbump", "antal": 2}, {"type": "indsnævring", "antal": 2}]) == "2 sinusbump, 2 indsnævringer"
    assert K.bumptype("modificeret sinusbump")[0] == "Modificeret sinusbump"
    assert K.bumptype("sinusbump") == ("Sinusbump", [])          # ingen tegning: vejreglerne har kun modificeret sinusbump
    assert K.bumptype("indsnævring") == (None, [])


def test_html_md_og_tilfoej():
    with tempfile.TemporaryDirectory() as t:
        mappe = Path(t) / "analyser"
        mappe.mkdir()
        _skriv(mappe, "testvej_testby_2025.yaml", GOD)
        ny = _skriv(t, "konklusion.yaml", {**GOD, "vej": "Anden </script><b>vej", "by": "Æby", "type": "en_periode",
                                            "perioder": {"periode": GOD["perioder"]["foer"]}, "ture": {"periode": 5},
                                            "koeretid_s": {"periode": 30}, "hastighed_kmt": {"periode": 30},
                                            "gnsfart_kmt": None, "laveste_fart_kmt": None, "maerkbar_opbremsning_pct": None,
                                            "maerkbar_acceleration_pct": None, "fartdaempere": []})
        ud = Path(t) / "k.html"
        r = subprocess.run([sys.executable, str(SCRIPT), "--analyser", str(mappe), "--out", str(ud), "--tilfoej", str(ny)],
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        assert (mappe / "anden_script_b_vej_aeby_2025.yaml").exists()
        h = ud.read_text(encoding="utf-8")
        assert "</script><b>" not in h                              # brugertekst kan ikke bryde ud af data-blokken
        assert h.count('"id": "') == 2 and "data:image/svg+xml;base64," in h and "<polygon" in h   # mini-tegning af cirkelbump
        md = ud.with_suffix(".md").read_text(encoding="utf-8")
        assert "| [Testvej, Testby](analyser/testvej_testby_2025.yaml) | Før/efter | 2025 | 400 m | 2 cirkelbump | 50 → 40 | 40 → 50 | +10 s | 2,5 |" in md
        assert "Senest opdateret:** 2026-11-25" in md
        # en anden kontakt må ikke overskrive en eksisterende analyse
        anden = _skriv(t, "anden.yaml", {**GOD, "kontakt": "en_anden"})
        r = subprocess.run([sys.executable, str(SCRIPT), "--analyser", str(mappe), "--out", str(ud), "--tilfoej", str(anden)],
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode != 0 and "anden kontakt" in r.stderr


def test_pakkens_analyser_er_gyldige_og_filerne_lavet_igen():
    # fanger en pull request, hvor en analyse er tilføjet, men .html/.md ikke er lavet igen (eller rettet i hånden)
    with tempfile.TemporaryDirectory() as t:
        ud = Path(t) / "nationale_analysekonklusioner.html"
        r = subprocess.run([sys.executable, str(SCRIPT), "--out", str(ud)], capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        for navn in ("nationale_analysekonklusioner.html", "nationale_analysekonklusioner.md"):
            ny = (Path(t) / navn).read_text(encoding="utf-8")
            assert ny == (ROD / navn).read_text(encoding="utf-8"), f"{navn} er ikke lavet igen: kør python program/lav_konklusioner_html.py"
    kv = yaml.safe_load((ROD / "analyser" / "kvaglundvej_esbjerg_2025.yaml").read_text(encoding="utf-8"))
    assert kv["koeretid_s"] == {"foer": 54, "efter": 66}                      # rapportens nøgletal (A15)


def test_browser_sortering_filter_og_mobil():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP test_browser_sortering_filter_og_mobil: playwright er ikke installeret")
        return
    with tempfile.TemporaryDirectory() as t:
        mappe = Path(t) / "analyser"
        mappe.mkdir()
        _skriv(mappe, "a.yaml", GOD)
        _skriv(mappe, "b.yaml", {**GOD, "vej": "Bvej", "by": "Bby", "laengde_m": 900, "koeretid_s": {"foer": 60, "efter": 65},
                                 "fartdaempere": [{"type": "sinusbump", "antal": 1}]})
        _skriv(mappe, "c.yaml", {**GOD, "vej": "Cvej", "type": "kryds", "laengde_m": 1200, "fartdaempere": [], "laveste_fart_kmt": None,
                                 "kryds_stykker": [{"stykke": "A-B", "retning": 1, "foer": 20, "efter": 26}],
                                 "koeretid_s": {"foer": 100, "efter": 103}})
        ud = Path(t) / "k.html"
        r = subprocess.run([sys.executable, str(SCRIPT), "--analyser", str(mappe), "--out", str(ud)], capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        with sync_playwright() as p:
            b = None
            for kw in ({"channel": "msedge"}, {"channel": "chrome"}, {}):
                try:
                    b = p.chromium.launch(**kw)
                    break
                except Exception:      # noqa
                    continue
            if b is None:
                print("SKIP test_browser_sortering_filter_og_mobil: ingen browser")
                return
            for bredde in (1440, 375):
                fejl = []
                pg = b.new_page(viewport={"width": bredde, "height": 900})
                pg.on("pageerror", lambda e: fejl.append(str(e)))
                pg.on("console", lambda m: fejl.append(m.text) if m.type == "error" else None)
                pg.goto(ud.as_uri())
                assert pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0, bredde
                navne = lambda: pg.eval_on_selector_all("#tabel tbody td.navn", "e => e.map(x => x.textContent)")   # noqa: E731
                assert navne() == ["Testvej, Testby", "Bvej, Bby", "Cvej, Testby"]          # standard: største ændring først (10, 5, 3)
                pg.click("#tabel th:has-text('Længde')")                  # tal sorteres som tal (som tekst ville 900 komme før 1200)
                assert navne() == ["Cvej, Testby", "Bvej, Bby", "Testvej, Testby"]
                pg.click("#tabel th:has-text('Længde')")
                assert navne()[0] == "Testvej, Testby"
                pg.select_option("#filtre select[data-i='0']", "Kryds")
                assert navne() == ["Cvej, Testby"] and pg.inner_text("#taeller") == "1 af 3 analyser"
                assert pg.locator("#graf circle").count() == 1
                pg.select_option("#filtre select[data-i='0']", "")
                pg.select_option("#filtre select[data-i='3']", "sinusbump")
                assert navne() == ["Bvej, Bby"]
                pg.select_option("#filtre select[data-i='3']", "")
                assert pg.locator("#graf circle").count() == 3 and pg.locator(".mini svg").count() == 1   # kun cirkelbump har mini
                pg.locator("#graf circle").first.click()
                pg.wait_for_timeout(200)
                assert pg.locator(".kort.valgt").count() == 1
                assert fejl == [], fejl
                pg.close()
            b.close()


if __name__ == "__main__":
    for navn, fn in list(globals().items()):
        if navn.startswith("test_"):
            fn()
            print("OK", navn)
