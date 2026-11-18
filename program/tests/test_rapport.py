#!/usr/bin/env python3
"""
Tests for rapport/lav_rapportdata.py (v1.1) og rapport/byg_rapport.py - lille syntetisk datasæt -> rapportdata -> HTML.

Koer:  python tests/test_rapport.py        (ren python)   eller   python -m pytest tests/test_rapport.py
Sæt PYTHONUTF8=1 i miljøet. Browsertestene kræver playwright (pip install playwright, og en browser: Edge eller
Chromium); uden den springes de over ("SKIP"), og de øvrige tests kører.

Data: se tests/syntetisk.py. Før 10 m/s overalt, efter: halv fart i en zone om indsnævringen ved 300 m.
Kendt: køretid før 60 s, efter 72 s (+12 s), indsnævringens ekstra tid 12,0 s.
Tester før/efter, kun én periode, to strækninger (vælger), stoppesteder pr. kørselsretning og kortet.
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "rapport"))
import syntetisk as S  # noqa: E402
import lav_rapportdata as R  # noqa: E402
import byg_rapport as B  # noqa: E402

Z = S.Z
SKABELON = (ROOT / "rapport" / "skabelon.html").read_text(encoding="utf-8")
STOPPESTEDER = [{"navn": "Stop X", "retning": 1, "lat": S.lat_af(100), "lon": S.LON0 + 0.00002},
                {"navn": "Stop X", "retning": 2, "lat": S.lat_af(140), "lon": S.LON0 - 0.00002}]


def _doc(tmp, kun_a=False, to=False, **kw):
    cfg = Z.laes_config(S.skriv_config(tmp, to_straekninger=to, **kw))
    lg, af = (S.LAENGDE_2, S.AFSTANDE_2) if to else (S.L, S.AFSTANDE_1)
    per = S.perioder(S.fart_kink, cfg, laengde=lg, afstande=af, kun_a=kun_a)
    zj, _ = Z.beregn(cfg, per, log=lambda *a: None)
    return R.bygg(cfg, per, zj, log=lambda *a: None)


def _rap(**extra):
    return {"titel": "Test af skabelonen", "undertitel": "Syntetiske ture", "forbehold": ["Kun test."], **extra}


def test_rapportdata_indhold():
    with tempfile.TemporaryDirectory() as tmp:
        d = _doc(tmp)
    for k in ("meta", "omfang", "nogletal", "fordeling", "fartprofil", "maaned", "drift", "zonetid", "foelsomhed"):
        assert k in d, k
    assert d["meta"]["perioder"] == ["A", "B"] and [s["id"] for s in d["meta"]["straekninger"]] == ["s1"]
    assert d["omfang"] == [{"S": "s1", "Periode": "A", "Dage": 6, "Ture": 12}, {"S": "s1", "Periode": "B", "Dage": 6, "Ture": 12}], d["omfang"]
    n = {(r["Retning"], r["Gruppe"], r["Periode"]): r for r in d["nogletal"]}
    a, b = n[("B", "Uden stop", "A")], n[("B", "Uden stop", "B")]
    assert a["koretid"] == 60 and b["koretid"] == 72, (a["koretid"], b["koretid"])
    assert a["andel_stop"] == 0 and b["andel_stop"] == 0
    zt = {(r["Retning"], r["Element"]): r for r in d["zonetid"]}
    assert abs(zt[("B", "Indsnævring B")]["Lav"] - 12.0) < 0.05 and abs(zt[("B", "Indsnævring B")]["Hoej"] - 12.0) < 0.05
    assert abs(zt[("B", "Hele strækningen")]["Lav"] - 12.0) < 0.05
    assert zt[("B", "Bump A")]["Type"] == "bump"
    # retning 1 kører fra p1 mod p2 (frem), retning 2 modsat (omvendt)
    om = {r["id"]: r["omvendt"] for r in d["meta"]["straekninger"][0]["retninger"]}
    assert om == {"1": False, "2": True}, om
    # drift: 12 s ekstra x 6 ture pr. dag pr. retning = 1,2 min pr. retning
    dr = {r["Retning"]: r for r in d["drift"]}
    assert abs(dr["1"]["Ekstra_min_dag"] - 12.0 / 60) < 0.01 and abs(dr["B"]["Ekstra_min_dag"] - 24.0 / 60) < 0.01, dr
    # fartprofil: 10 m/s = 36 km/t før; i zonen 18 km/t efter (bin 300)
    pf = {(r["Retning"], r["Gruppe"], r["Periode"], r["Meter"]): r for r in d["fartprofil"]}
    assert abs(pf[("B", "Uden stop", "A", 100)]["Median"] - 36.0) < 0.5
    assert abs(pf[("B", "Uden stop", "B", 300)]["Median"] - 18.0) < 0.5, pf[("B", "Uden stop", "B", 300)]


def test_ingen_tur_id_i_rapportdata():
    with tempfile.TemporaryDirectory() as tmp:
        d = _doc(tmp)
    tekst = json.dumps(d, ensure_ascii=False)
    assert "Turreference" not in tekst
    for ref in ("A000", "A001", "B000", "B001", "A051", "B051"):
        assert ref not in tekst, ref


def test_kun_en_periode_rapportdata():
    with tempfile.TemporaryDirectory() as tmp:
        d = _doc(tmp, kun_a=True)
    assert d["meta"]["perioder"] == ["A"]
    assert d["omfang"] == [{"S": "s1", "Periode": "A", "Dage": 6, "Ture": 12}], d["omfang"]
    assert {r["Periode"] for r in d["nogletal"]} == {"A"} and {r["Periode"] for r in d["fartprofil"]} == {"A"}
    assert d["foelsomhed"] == []
    assert all("Lav" not in r and "Niveau" in r for r in d["zonetid"]), d["zonetid"][:2]
    zt = {(r["Retning"], r["Element"]): r for r in d["zonetid"]}
    assert abs(zt[("B", "Indsnævring B")]["Niveau"] - 12.0) < 0.05 and abs(zt[("B", "Hele strækningen")]["Niveau"] - 60.0) < 0.05
    assert all("Ekstra_min_dag" not in r for r in d["drift"]), d["drift"]


def test_to_straekninger_rapportdata():
    with tempfile.TemporaryDirectory() as tmp:
        d = _doc(tmp, to=True, rapport=_rap(stoppesteder=STOPPESTEDER))
    sm = {s["id"]: s for s in d["meta"]["straekninger"]}
    assert list(sm) == ["a", "b"] and sm["a"]["navn"] == "Strækning A" and sm["b"]["laengde_m"] == 600.0
    assert [e["navn"] for e in sm["a"]["elementer"]] == ["Bump A", "Indsnævring B"] and [e["navn"] for e in sm["b"]["elementer"]] == ["Bump C"]
    assert {r["S"] for r in d["nogletal"]} == {"a", "b"} and {r["S"] for r in d["zonetid"]} == {"a", "b"}
    n = {(r["S"], r["Retning"], r["Gruppe"], r["Periode"]): r for r in d["nogletal"]}
    # begge strækninger: 6 ture pr. retning pr. periode; a: 60 -> 72 s (langsom zone), b: 60 -> 60 s
    assert n[("a", "B", "Uden stop", "A")]["koretid"] == 60 and n[("a", "B", "Uden stop", "B")]["koretid"] == 72
    assert n[("b", "B", "Uden stop", "A")]["koretid"] == 60 and n[("b", "B", "Uden stop", "B")]["koretid"] == 60
    zt = {(r["S"], r["Retning"], r["Element"]): r for r in d["zonetid"]}
    assert abs(zt[("a", "B", "Hele strækningen")]["Lav"] - 12.0) < 0.05 and abs(zt[("b", "B", "Hele strækningen")]["Lav"]) < 0.05
    # stoppesteder pr. retning: hører til strækning a (position 100 og 140 m), ikke b
    sp = {(s["navn"], s["retning"]): s["s_m"] for s in sm["a"]["stoppesteder"]}
    assert set(sp) == {("Stop X", "1"), ("Stop X", "2")} and abs(sp[("Stop X", "1")] - 100) < 1 and abs(sp[("Stop X", "2")] - 140) < 1, sp
    assert sm["b"]["stoppesteder"] == []
    assert "Turreference" not in json.dumps(d)


def test_byg_html_uden_maerker_og_uden_kort():
    with tempfile.TemporaryDirectory() as tmp:
        d = _doc(tmp)
    h = B.byg(d, SKABELON)
    for mark in ("{{TITEL}}", "__RAPPORTDATA__", "/*__ECHARTS__*/", "/*__LEAFLET_JS__*/", "/*__LEAFLET_CSS__*/"):
        assert mark not in h, mark
    assert "<title>Test af skabelonen</title>" in h
    assert "Apache License" in (ROOT / "rapport" / "vendor" / "ECHARTS-LICENSE.txt").read_text(encoding="utf-8")
    assert "L.map(" in h                      # skabelonens kortkode er med, men Leaflet selv er ikke indlejret
    assert "Leaflet 1.9.4" not in h and "leaflet-container" not in h
    # selvstændig: ingen eksterne script/link-referencer
    assert "<script src" not in h and "<link " not in h
    # komfort-afgrænsningen står i skabelonen
    assert "hele strækningen (opbremsning og acceleration langs vejen), ikke stødet over selve bumpet" in h


def test_byg_html_med_kort():
    with tempfile.TemporaryDirectory() as tmp:
        d = _doc(tmp, rapport={"titel": "Med kort", "kort": True})
    assert d["meta"]["kort"]["aktiv"] is True
    h = B.byg(d, SKABELON)
    assert "leaflet-container" in h and "tile.openstreetmap.org" in h and "OpenStreetMap" in h


def test_byg_afviser_skabelon_uden_maerker():
    try:
        B.byg({"meta": {"titel": "x"}}, "<html></html>")
    except SystemExit as e:
        assert "præcis én" in str(e)
        return
    raise AssertionError("forventede SystemExit")


# ------------------------------------------------------------------ browsertests

def _browser(p):
    for kw in ({"channel": "msedge"}, {"channel": "chrome"}, {}):
        try:
            return p.chromium.launch(**kw)
        except Exception:      # noqa
            continue
    return None


def _med_browser(d, navn, fn, skabelon=None):
    """Kør fn(sider, fejl) mod HTML bygget af d. Returnerer False hvis playwright/browser mangler."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"SKIP {navn}: playwright er ikke installeret")
        return False
    with tempfile.TemporaryDirectory() as tmp:
        sti = Path(tmp) / "rapport.html"
        sti.write_text(B.byg(d, skabelon or SKABELON), encoding="utf-8")
        with sync_playwright() as p:
            b = _browser(p)
            if b is None:
                print(f"SKIP {navn}: ingen browser (Edge/Chrome/Chromium) kunne startes")
                return False
            fejl = []

            def ny(bredde):
                pg = b.new_page(viewport={"width": bredde, "height": 900})
                pg.on("pageerror", lambda e: fejl.append(str(e)))
                pg.on("console", lambda m: fejl.append(m.text) if m.type == "error" and "tile.openstreetmap" not in m.text
                      and "Failed to load resource" not in m.text and "ERR_" not in m.text else None)
                pg.goto(sti.as_uri())
                pg.wait_for_function("window.RAPPORT_KLAR === true")
                pg.wait_for_timeout(400)
                return pg
            fn(ny, fejl)
            b.close()
    return True


TOMME = ("[...document.querySelectorAll('.graf')].filter(e => { const c = echarts.getInstanceByDom(e); "
         "return !c || !c.getOption().series.length || e.clientWidth < 100; }).map(e => e.id)")
TXT = "(i) => document.getElementById(i).innerText.replace(/\\s+/g,' ').trim()"


def test_browser_foer_efter_ingen_js_fejl_og_klik():
    with tempfile.TemporaryDirectory() as tmp:
        d = _doc(tmp)

    def fn(ny, fejl):
        for bredde in (1440, 375):
            pg = ny(bredde)
            assert pg.evaluate(TOMME) == [], pg.evaluate(TOMME)
            assert pg.evaluate("document.documentElement.scrollWidth") <= pg.evaluate("window.innerWidth"), f"vandret scroll ved {bredde} px"
            if bredde == 1440:
                k1 = pg.evaluate(TXT, "k1")
                assert "+12 s" in k1 and "60 → 72 s" in k1, k1
                assert "Indsnævring B 12,0–12,0 s" in pg.evaluate(TXT, "t-zone") and "Hele strækningen 12,0 s" in pg.evaluate(TXT, "t-zone")
                assert pg.evaluate("document.querySelectorAll('#s-knapper button').length") == 0      # én strækning: ingen vælger
                pg.click('.knapper[data-f="ret"] button:nth-child(3)')
                pg.click('.knapper[data-f="stop"] button:nth-child(2)')
                pg.click('.valg button:nth-child(3)')
                assert pg.evaluate("window.RAPPORT.state") == {"s": "s1", "ret": "2", "stop": "Alle ture", "komfort": "Samlet"}
                assert "+12 s" in pg.evaluate(TXT, "k1")
                assert len(pg.evaluate("[...document.querySelectorAll('.knapper button.on, .valg button.on')].map(b => b.innerText)")) == 3
                # komfort nævnes i overskrifterne; forklaringen står i ⓘ og ikke i noten under grafen
                assert pg.evaluate(TXT, "h-brems").startswith("Passagerkomfort:"), pg.evaluate(TXT, "h-brems")
                assert pg.evaluate(TXT, "k3").startswith("Komfort: ture med mærkbar opbremsning")
                for sel in ("#h-brems .info", "#k3 .info"):
                    t = pg.evaluate("(s) => document.querySelector(s).dataset.t", sel)
                    assert "hele strækningen" in t and "ikke stødet over selve bumpet" in t, (sel, t)
                assert "stødet" not in pg.evaluate(TXT, "n-brems") and "komfort" not in pg.evaluate(TXT, "n-brems").lower()
                assert "Linje = median. Skygge = midterste halvdel af turene (25-75 %)." in pg.evaluate(TXT, "n-fart")
                assert "median · ture uden standsning ved stop" in k1, k1
                assert [b.strip() for b in pg.evaluate("[...document.querySelectorAll('.knapper[data-f=\"stop\"] button')].map(b => b.innerText)")] == ["Uden standsning ved stop", "Alle ture", "Med standsning ved stop"]
                assert "Til sammenligning" not in pg.evaluate(TXT, "n-brems")      # syntetiske data har 0 ture med standsning: ingen sammenligning
                assert pg.evaluate("window.RAPPORT_KONTRAST") == [], pg.evaluate("window.RAPPORT_KONTRAST")      # standardpaletten består kontrolkravet
                # direkte navne ved linjerne i stedet for legende på bred skærm
                assert pg.evaluate("echarts.getInstanceByDom(document.getElementById('c-fart')).getOption().legend[0].show") is False
                assert pg.evaluate("echarts.getInstanceByDom(document.getElementById('c-fart')).getOption().series.filter(s => s.endLabel && s.endLabel.show).map(s => s.name)") == ["Før", "Efter"]
                assert "Før 01-08-2025 til 31-08-2025: 6 hverdage, 12 ture" in pg.evaluate(TXT, "omfang"), pg.evaluate(TXT, "omfang")
                assert "Antal ture: uden standsning ved stop" in pg.evaluate(TXT, "n-tid") and "ingen " in pg.evaluate(TXT, "n-klasse")
                assert "Rapport bygget " in pg.evaluate("document.getElementById('fod').innerText")
            pg.close()
        assert fejl == [], fejl
    _med_browser(d, "test_browser_foer_efter", fn)


def test_browser_kun_en_periode_viser_niveauer():
    with tempfile.TemporaryDirectory() as tmp:
        d = _doc(tmp, kun_a=True)

    def fn(ny, fejl):
        for bredde in (1440, 375):
            pg = ny(bredde)
            assert pg.evaluate(TOMME) == [], pg.evaluate(TOMME)
            assert pg.evaluate("document.documentElement.scrollWidth") <= pg.evaluate("window.innerWidth")
            if bredde == 1440:
                k1 = pg.evaluate(TXT, "k1")
                assert "Køretid på strækningen" in k1 and "60 s" in k1 and "→" not in k1 and "Ekstra" not in k1, k1
                krop = pg.evaluate("document.body.innerText")
                for forbudt in ("Ekstra køretid", "Hvor sidder den ekstra", "→", "Hvad betyder det i drift", "Intervallerne"):
                    assert forbudt not in krop, forbudt
                assert pg.evaluate("!!document.getElementById('drift')") is False
                assert "Tid pr. zone" in pg.evaluate(TXT, "h-zone") and "Indsnævring B 12,0 s" in pg.evaluate(TXT, "t-zone"), pg.evaluate(TXT, "t-zone")
                assert "af turene har" in pg.evaluate(TXT, "h-brems")
                assert pg.evaluate("echarts.getInstanceByDom(document.getElementById('c-tid')).getOption().series.length") == 1
                assert "6 hverdage, 12 ture" in pg.evaluate("document.getElementById('omfang').innerText")
                assert pg.evaluate("echarts.getInstanceByDom(document.getElementById('c-maaned')).getOption().series.length") == 1
                pg.click('.knapper[data-f="ret"] button:nth-child(2)')
                pg.click('.valg button:nth-child(2)')
                assert "60 s" in pg.evaluate(TXT, "k1")
            pg.close()
        assert fejl == [], fejl
    _med_browser(d, "test_browser_kun_en_periode", fn)


def test_browser_to_straekninger_vaelger_stop_pr_retning_og_kort():
    with tempfile.TemporaryDirectory() as tmp:
        d = _doc(tmp, to=True, rapport=_rap(stoppesteder=STOPPESTEDER, kort=True))

    def marks(pg):
        return pg.evaluate("""() => { const s = echarts.getInstanceByDom(document.getElementById('c-fart')).getOption().series.find(x => x.markLine);
            return s.markLine.data.map(m => [m.label.formatter, m.xAxis]); }""")

    def fn(ny, fejl):
        for bredde in (1440, 375):
            pg = ny(bredde)
            assert pg.evaluate(TOMME) == [], pg.evaluate(TOMME)
            assert pg.evaluate("document.documentElement.scrollWidth") <= pg.evaluate("window.innerWidth"), f"vandret scroll ved {bredde} px"
            if bredde == 375:
                pg.close()
                continue
            vael = pg.evaluate("[...document.querySelectorAll('#s-knapper button')].map(b => b.innerText)")
            assert vael == ["Strækning A", "Strækning B"], vael
            assert pg.evaluate("document.querySelector('#s-knapper button.on').innerText") == "Strækning A"
            assert "Strækning A" in pg.evaluate(TXT, "omfang")
            assert "+12 s" in pg.evaluate(TXT, "k1") and "Indsnævring B" in pg.evaluate(TXT, "t-zone")
            # stoppesteder pr. retning i fartprofilen: begge retninger -> begge stolper med retning i navnet
            navne = [m[0] for m in marks(pg)]
            assert "Stop X (retn. 1)" in navne and "Stop X (retn. 2)" in navne, navne
            n_b = pg.evaluate("window.RAPPORT_KORT.eachLayer ? (() => { let n = 0; window.RAPPORT_KORT.eachLayer(l => { if (l.getTooltip && l.getTooltip()) n++; }); return n; })() : -1")
            pg.click('.knapper[data-f="ret"] button:nth-child(2)')                  # retning 1
            m1 = marks(pg)
            assert [m for m in m1 if m[0].startswith("Stop X")] == [["Stop X", "100"]], m1
            n_1 = pg.evaluate("(() => { let n = 0; window.RAPPORT_KORT.eachLayer(l => { if (l.getTooltip && l.getTooltip()) n++; }); return n; })()")
            assert n_1 == n_b - 1, (n_1, n_b)                                       # kortet viser kun retning 1's stolpe
            pg.click('.knapper[data-f="ret"] button:nth-child(3)')                  # retning 2 (omvendt: kørselsretningen fra venstre)
            m2 = marks(pg)
            bin_max = d["meta"]["straekninger"][0]["bin_max_m"]                     # 590: strækningen er 599,99999 m
            assert [m for m in m2 if m[0].startswith("Stop X")] == [["Stop X", str(int(bin_max - 140))]], m2
            # skift til strækning B: nye elementer, nøgletal og tabel; ingen stoppesteder; retningsvalget nulstilles ikke ugyldigt
            pg.click('#s-knapper button:nth-child(2)')
            assert pg.evaluate("window.RAPPORT.state.s") == "b"
            assert "Strækning B" in pg.evaluate(TXT, "omfang")
            assert pg.evaluate("[...echarts.getInstanceByDom(document.getElementById('c-fart')).getOption().series.find(x => x.markLine).markLine.data.map(m => m.label.formatter)]") == ["Bump C"]
            assert "Bump C" in pg.evaluate(TXT, "t-zone") and "Indsnævring B" not in pg.evaluate(TXT, "t-zone")
            assert pg.evaluate("document.getElementById('t-zone').innerText").count("Bump C") == 1
            k1 = pg.evaluate(TXT, "k1")
            assert "60 → 60 s" in k1, k1
            assert pg.evaluate(TOMME) == []
            pg.close()
        assert fejl == [], fejl
    _med_browser(d, "test_browser_to_straekninger", fn)


def test_advarsel_om_standardtitel_og_forbehold():
    with tempfile.TemporaryDirectory() as tmp:
        d = _doc(tmp, rapport={"kort": False})
    assert d["meta"]["titel"] == R.STANDARD_TITEL
    a = B.advarsler(d)
    assert any("standardtitlen" in t for t in a) and any("forbehold" in t for t in a), a
    with tempfile.TemporaryDirectory() as tmp:
        d = _doc(tmp)
    assert B.advarsler(d) == []


def test_browser_kontrolkrav_advarer_og_faa_ture_vises_som_streg():
    with tempfile.TemporaryDirectory() as tmp:
        d = _doc(tmp)
    daarlig = SKABELON.replace("--farve-tekst2: #56616c;", "--farve-tekst2: #bdbdbd;").replace("--farve-stop: #7a7a7a;", "--farve-stop: #dddddd;")

    def fn(ny, fejl):
        pg = ny(1440)
        v = pg.evaluate("window.RAPPORT_KONTRAST")
        assert any("tekstfarve" in t for t in v) and any("--farve-stop" in t for t in v), v
        assert pg.evaluate("(() => { const k = (a, b) => 0; return typeof document.body.innerText; })()") == "string"
        pg.close()
    _med_browser(d, "test_browser_kontrol", fn, skabelon=daarlig)

    def fn2(ny, fejl):
        pg = ny(1440)
        assert pg.evaluate("window.RAPPORT_KONTRAST") == []
        pg.click('.knapper[data-f="stop"] button:nth-child(3)')               # "Med stop": 0 ture i syntetiske data
        assert pg.evaluate("window.RAPPORT.state.stop") == "Med stop"
        krop = pg.evaluate("document.body.innerText")
        assert "NaN" not in krop and "undefined" not in krop, "ugyldige tal i rapporten"
        k3 = pg.evaluate(TXT, "k3")
        assert "opbremsningⓘ - før -" in k3, k3                                  # få ture: "-" i stedet for en procent
        assert pg.evaluate(TXT, "k1").startswith("Ekstra køretid på strækningen - s")
        pg.close()
    _med_browser(d, "test_browser_faa_ture", fn2)


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
