"""Tester lav_vejkort.py og vejkortet i konklusionsoversigten. Ingen net: Overpass erstattes af en falsk forbindelse.

Kør: python -m pytest tests/test_vejkort.py -q   (PYTHONUTF8=1; browsertesten kræver playwright, ellers SKIP)
"""
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path

import yaml

PK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PK))
import lav_vejkort as V  # noqa: E402

spec = importlib.util.spec_from_file_location("konkl_vk", PK / "lav_konklusioner_html.py")
K = importlib.util.module_from_spec(spec)
spec.loader.exec_module(K)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_konklusioner_html import GOD, SCRIPT, _skriv  # noqa: E402

# lille OSM-svar: en boligvej langs punkterne A-B (55.000-55.003, 8.000), en sti, en bygning og tre detaljer
OSM = {"elements": [
    {"type": "way", "tags": {"highway": "residential", "name": "Testvej"},
     "geometry": [{"lat": 54.9995, "lon": 8.0}, {"lat": 55.0015, "lon": 8.0001}, {"lat": 55.0035, "lon": 8.0}]},
    {"type": "way", "tags": {"highway": "footway"}, "geometry": [{"lat": 55.001, "lon": 7.999}, {"lat": 55.001, "lon": 8.001}]},
    {"type": "way", "tags": {"building": "yes"}, "geometry": [{"lat": 55.002, "lon": 8.0005}, {"lat": 55.002, "lon": 8.0008},
                                                            {"lat": 55.0022, "lon": 8.0008}, {"lat": 55.002, "lon": 8.0005}]},
    {"type": "node", "lat": 55.0012, "lon": 8.0001, "tags": {"highway": "bus_stop", "name": "Testvej v Midten (Testby)"}},
    {"type": "node", "lat": 55.0013, "lon": 7.9999, "tags": {"highway": "bus_stop", "name": "Testvej v Midten"}},
    {"type": "node", "lat": 55.002, "lon": 8.0, "tags": {"highway": "crossing"}},
    {"type": "node", "lat": 55.0025, "lon": 8.0, "tags": {"traffic_calming": "bump"}},
    {"type": "node", "lat": 55.0025, "lon": 8.0, "tags": {"amenity": "bench"}},          # ignoreres (ikke i forespørgslen)
]}


class Svar(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _aabner(rk):
    """Falsk urlopen: tager svar fra listen rk (en HTTP-kode = fejl, ellers OSM-dict) og gemmer forespørgslerne."""
    kald = []

    def aabn(req, timeout=None):
        kald.append(req)
        x = rk.pop(0)
        if isinstance(x, int):
            raise urllib.error.HTTPError(req.full_url, x, "fejl", {}, None)
        return Svar(json.dumps(x).encode("utf-8"))
    return aabn, kald


def _afkod(f, s0, w0, en):
    y = x = 0
    ud = []
    for i in range(0, len(f), 2):
        y += f[i]
        x += f[i + 1]
        ud.append((round(s0 + y * en, 5), round(w0 + x * en, 5)))
    return ud


def test_omraade_og_kompakt():
    bb = V.omraade(GOD["punkter"])
    s, w, n, e = bb
    assert s < 55.0 and n > 55.003 and w < 8.0 < e
    assert (e - w) * V._meter(55.0)[0] >= (n - s) * 110540 * 1.6 - 1          # mindst 16:10
    k = V.kompakt(OSM, bb, hentet="2026-11-25")
    assert [v[:2] for v in k["veje"]] == [[3, "Testvej"], [5, ""]]
    assert _afkod(k["veje"][0][2], s, w, k["enhed"]) == [(54.9995, 8.0), (55.0015, 8.0001), (55.0035, 8.0)]   # ca. 1 m nøjagtighed
    assert len(k["bygninger"]) == 1
    assert sorted(d[0] for d in k["detaljer"]) == ["bump", "kryds", "stop", "stop"]
    assert {d[1] for d in k["detaljer"] if d[0] == "stop"} == {"Testvej v Midten"}   # "(Testby)" fjernet; begge sider har navn
    assert "ODbL" in k["licens"] and k["hentet"] == "2026-11-25"


def test_hent_proever_igen_og_giver_op():
    vent = []
    aabn, kald = _aabner([502, OSM])
    assert V.hent((1, 2, 3, 4), aabn=aabn, vent=vent.append) == OSM
    assert len(kald) == 2 and vent == [5]
    assert "trackpoint_vaerktoej" in kald[0].get_header("User-agent")
    assert b"node%5Bhighway%3Dbus_stop%5D" in kald[0].data
    # kendt negativ: bliver ved med at fejle -> klar besked efter 3 forsøg; 429 venter 30 s
    aabn, kald = _aabner([429, 503, 504])
    vent = []
    try:
        V.hent((1, 2, 3, 4), aabn=aabn, vent=vent.append)
        assert False, "skulle give op"
    except V.VejkortFejl as e:
        assert "HTTP 504" in str(e) and len(kald) == 3 and vent == [30, 10]
    # 400 (forkert forespørgsel) prøves ikke igen
    aabn, kald = _aabner([400])
    try:
        V.hent((1, 2, 3, 4), aabn=aabn, vent=lambda s: None)
        assert False
    except V.VejkortFejl:
        assert len(kald) == 1


def test_lav_gemmer_og_genbruger():
    with tempfile.TemporaryDirectory() as t:
        a = _skriv(t, "testvej_testby_2025.yaml", GOD)
        antal = []
        hent = lambda bb: antal.append(bb) or OSM          # noqa: E731
        p = V.lav(a, hent_fn=hent)
        assert p == Path(t) / "kort" / "testvej_testby_2025.json" and p.exists() and len(antal) == 1
        assert V.lav(a, hent_fn=hent) == p and len(antal) == 1               # findes og dækker punkterne: ingen ny hentning
        flyttet = {**GOD, "punkter": [{"navn": "A", "lat": 56.0, "lon": 9.0}]}
        a.write_text(yaml.safe_dump(flyttet, allow_unicode=True), encoding="utf-8")
        V.lav(a, hent_fn=hent)
        assert len(antal) == 2                                                # punktet ligger uden for kortet: hent igen
        uden = _skriv(t, "uden.yaml", {**GOD, "punkter": []})
        assert V.lav(uden, hent_fn=hent) is None and len(antal) == 2
        # oversigten læser kortet; en ødelagt fil stopper med besked
        assert K.laes_vejkort(Path(t) / "kort", "testvej_testby_2025")["omraade"][0] < 56.0
        (Path(t) / "kort" / "x.json").write_text("{ikke json", encoding="utf-8")
        try:
            K.laes_vejkort(Path(t) / "kort", "x")
            assert False
        except SystemExit as e:
            assert "ikke et gyldigt vejkort" in str(e)
        assert K.laes_vejkort(Path(t) / "kort", "findes_ikke") is None


def test_browser_vejkort_zoom_og_traek():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP test_browser_vejkort_zoom_og_traek: playwright er ikke installeret")
        return
    with tempfile.TemporaryDirectory() as t:
        mappe = Path(t) / "analyser"
        mappe.mkdir()
        a = _skriv(mappe, "testvej_testby_2025.yaml", GOD)
        V.lav(a, hent_fn=lambda bb: OSM)
        _skriv(mappe, "uden_kort_2025.yaml", {**GOD, "vej": "Uden kort"})       # punkter, men ingen kortfil
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
                print("SKIP test_browser_vejkort_zoom_og_traek: ingen browser")
                return
            for bredde in (1280, 375):
                fejl, net = [], []
                pg = b.new_page(viewport={"width": bredde, "height": 900})
                pg.on("pageerror", lambda e: fejl.append(str(e)))
                pg.on("console", lambda m: fejl.append(m.text) if m.type == "error" else None)
                pg.on("request", lambda rq: net.append(rq.url) if not rq.url.startswith(("file:", "data:")) else None)
                pg.goto(ud.as_uri())
                assert pg.locator(".vk").count() == 2
                med = pg.locator(".vk", has=pg.locator(".vk-vej"))
                assert med.locator(".vk-vej").count() == 2 and med.locator(".vk-bygn").count() == 1
                assert pg.locator(".vk-vej").count() == 2                     # analysen uden kortfil har kun punkterne
                med.scroll_into_view_if_needed()
                svg, vb = med.locator(".vk-svg"), lambda: med.locator(".vk-indre").get_attribute("viewBox")   # noqa: E731
                start = vb()
                assert med.locator(".vk-detalje").first.bounding_box() is None       # detaljer først ved zoom
                for _ in range(3):
                    med.locator("button[data-z=ind]").click()
                assert vb() != start and med.locator(".vk-detalje").first.bounding_box() is not None
                h = med.locator(".vk-lbl").first.bounding_box()["height"]
                assert 10 < h < 20, h                                              # teksten har fast skærmstørrelse
                bb = svg.bounding_box()
                foer = vb()
                pg.mouse.click(5, 5)                                               # kortet er ikke aktivt
                pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
                pg.mouse.wheel(0, -200)
                pg.wait_for_timeout(100)
                assert vb() == foer                                                # hjulet scroller siden, zoomer ikke
                bb = svg.bounding_box()                                            # siden har flyttet sig
                pg.mouse.move(bb["x"] + bb["width"] * 0.3, bb["y"] + bb["height"] * 0.3)
                pg.mouse.down()
                pg.mouse.move(bb["x"] + bb["width"] * 0.6, bb["y"] + bb["height"] * 0.6, steps=6)
                pg.mouse.up()
                assert vb() != foer and pg.evaluate("window.getSelection().toString()") == ""   # træk flytter, markerer intet
                efter_traek = vb()
                pg.mouse.wheel(0, -200)                                            # efter klik i kortet zoomer hjulet
                pg.wait_for_timeout(100)
                assert vb() != efter_traek
                assert fejl == [] and net == [], (fejl, net)                       # ingen netkald (ingen kortfliser)
                assert pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0
                pg.close()
            b.close()


if __name__ == "__main__":
    for navn, fn in list(globals().items()):
        if navn.startswith("test_"):
            fn()
            print("OK", navn)
