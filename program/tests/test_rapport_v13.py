#!/usr/bin/env python3
"""
Tests for standsning_v1.0.py, rapport/lav_rapportdata_v1.3.py, skabelon_v1.3.html og standsningsfeltet i
lav_konklusion.py / lav_konklusioner_html.py. Samme syntetiske data som test_rapport_v12.py (tests/syntetisk.py).

Koer:  python tests/test_rapport_v13.py   eller   python -m pytest tests/test_rapport_v13.py
Sæt PYTHONUTF8=1. Browsertesten kræver playwright (ellers "SKIP").

Data: før 10 m/s overalt; efter halv fart ved 240-360 m og, i "stop"-varianten, 0,2 m/s ved 395-405 m (50 s
standsning). Kendt positiv: stoppested ved 401 m -> alle efter-ture har standsning ved stop. Kendt negativ: stoppested
ved 100 m (300 m fra standsningen) -> ingen standsning ved stop, men stadig standsning i alt.
"""
import copy
import importlib.util
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rapport"))
import syntetisk as S  # noqa: E402
import byg_rapport as B  # noqa: E402
import lav_konklusion as LK  # noqa: E402
import lav_konklusioner_html as KH  # noqa: E402
import test_rapport_v12 as T12  # noqa: E402  (turtabel og hjælpere)


def _load(navn, sti):
    spec = importlib.util.spec_from_file_location(navn, sti)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R13 = _load("lav_rapportdata_v13", ROOT / "rapport" / "lav_rapportdata_v1.3.py")
R12 = T12.R
ST = _load("standsning_v10", ROOT / "standsning_v1.0.py")
Z = S.Z
SKABELON = (ROOT / "rapport" / "skabelon_v1.3.html").read_text(encoding="utf-8")
STOP_VED = [{"navn": "Ved standsningen", "lat": S.lat_af(401), "lon": S.LON0}]          # i standsningen
STOP_LANGT = [{"navn": "Langt væk", "retning": 1, "lat": S.lat_af(100), "lon": S.LON0},  # 300 m fra standsningen
              {"navn": "Langt væk", "retning": 2, "lat": S.lat_af(100), "lon": S.LON0}]


def fart_stop(s):
    return 0.2 if 395.0 <= s < 405.0 else S.fart_kink(s)


def _rapport(stoppesteder):
    r = {"titel": "Test v1.3", "undertitel": "Syntetiske ture", "forbehold": ["Kun test."]}
    if stoppesteder is not None:
        r["stoppesteder"] = stoppesteder
    return r


def _doc(tmp, stoppesteder=None, fart_b=fart_stop, flag_b=False, v12=False):
    cfg = Z.laes_config(S.skriv_config(tmp, rapport=_rapport(stoppesteder)))

    def med_flag(meta, seg):          # én efter-tur i retning 1 fravalgt: 5 ture på 6 dage = 0,83 pr. dag
        if flag_b:
            i = meta.index[meta["Retning"] == 1][0]
            meta.loc[i, "Flag"] = "stoprække_p1"
        return meta, seg
    per = S.perioder(fart_b, cfg, extra_b=med_flag)
    zj, _ = Z.beregn(cfg, per, log=lambda *a: None)
    tt = T12._turtabel(per)
    return R13.bygg(cfg, per, zj, tt, log=lambda *a: None), (R12.bygg(cfg, per, zj, tt, log=lambda *a: None) if v12 else None)


def _ng(d, grp, p, ret="B", dag="Hverdage", time=-1):
    return next(r for r in d["nogletal"] if r["Gruppe"] == grp and r["Periode"] == p and r["Retning"] == ret
                and r["Dag"] == dag and r["Rute"] == "Alle ruter" and r["Time"] == time)


# ---------------------------------------------------------------- standsning_v1.0 (funktionerne)
def test_ved_stop_kendt_positiv_og_negativ():
    sg = np.arange(0.0, 600.0, 1.0)
    vk = np.full_like(sg, 36.0)
    vk[(sg >= 400) & (sg <= 405)] = 1.0                       # standsning ved 400-405 m
    stop = lambda s, ret=None: {"navn": "x", "retning": ret, "s_m": s}   # noqa: E731
    assert ST.ved_stop(sg, vk, 1, [stop(410.0)], 3.6) == 1                       # 5 m væk
    assert ST.ved_stop(sg, vk, 1, [stop(440.0)], 3.6) == 1                       # 35 m væk (< 40 m)
    assert ST.ved_stop(sg, vk, 1, [stop(460.0)], 3.6) == 0                       # 55 m væk
    assert ST.ved_stop(sg, vk, 1, [stop(410.0, "2")], 3.6) == 0                  # anden retnings stoppested
    assert ST.ved_stop(sg, vk, "2", [stop(410.0, "2")], 3.6) == 1
    assert ST.ved_stop(sg, vk, 1, [], 3.6) == 0                                  # ingen stoppesteder
    assert ST.ved_stop(sg, vk, 1, [stop(460.0)], 3.6, afstand_m=60) == 1         # afstanden kan ændres
    assert ST.i_alt(vk, 3.6) == 1 and ST.i_alt(np.full_like(sg, 36.0), 3.6) == 0
    assert ST.ved_stop(sg, np.full_like(sg, 36.0), 1, [stop(410.0)], 3.6) == 0   # ingen standsning overhovedet


# ---------------------------------------------------------------- lav_rapportdata_v1.3
def test_i_alt_er_som_v12_og_ved_stop_kendt_positiv():
    with tempfile.TemporaryDirectory() as tmp:
        d, v12 = _doc(tmp, STOP_VED, v12=True)
    assert d["version"] == "1.3" and d["meta"]["standsning"]["ved_stop"] and d["meta"]["standsning"]["standard"] == "ved stop"
    assert d["meta"]["straekninger"][0]["grupper"] == ["Alle ture", "Uden ved stop", "Med ved stop", "Uden i alt", "Med i alt"]
    # "i alt" = v1.2's "Uden stop"/"Med stop" (samme tal i alle valg)
    for g13, g12 in (("Alle ture", "Alle ture"), ("Uden i alt", "Uden stop"), ("Med i alt", "Med stop")):
        a = [{k: v for k, v in r.items() if k not in ("Gruppe", "andel_stop_ved")} for r in d["nogletal"] if r["Gruppe"] == g13 and r["Rute"] == "Alle ruter"]
        b = [{k: v for k, v in r.items() if k != "Gruppe"} for r in v12["nogletal"] if r["Gruppe"] == g12 and r["Rute"] == "Alle ruter"]
        assert a == b, g13
    # kendt positiv: alle 12 efter-ture standser 1 m fra stoppestedet; før-turene standser ikke
    assert _ng(d, "Med ved stop", "B")["Ture"] == 12 and _ng(d, "Med i alt", "B")["Ture"] == 12
    assert _ng(d, "Med ved stop", "A")["Ture"] == 0 and _ng(d, "Uden ved stop", "A")["Ture"] == 12
    assert _ng(d, "Alle ture", "B")["andel_stop_ved"] == 1.0
    # fartprofil: median, 25 % og 75 % for "i alt" = v1.2 (v1.3 er kompakt: M0 + skridt på 10 m)
    p13 = {(r["Retning"], r["Gruppe"], r["Periode"]): r for r in d["fartprofil"] if r["Dag"] == "Hverdage" and r["Time"] == -1}
    p12 = {(r["Retning"], r["Gruppe"], r["Periode"]): r for r in v12["fartprofil"] if r["Dag"] == "Hverdage" and r["Rute"] == "Alle ruter" and r["Time"] == -1}
    for (ret, g12, p), r in p12.items():
        x = p13[(ret, {"Uden stop": "Uden i alt", "Med stop": "Med i alt"}.get(g12, g12), p)]
        meter = [x["M0"] + 10 * i for i, v in enumerate(x["Median"]) if v is not None]
        assert meter == r["Meter"] and [v for v in x["Median"] if v is not None] == r["Median"]
        assert [v for v in x["P25"] if v is not None] == r["P25"] and all(a <= b for a, b in zip(x["P10"], x["P25"]) if a is not None)


def test_ved_stop_kendt_negativ_og_uden_stoppesteder():
    with tempfile.TemporaryDirectory() as tmp:
        d, _ = _doc(tmp, STOP_LANGT)
    assert _ng(d, "Med ved stop", "B")["Ture"] == 0 and _ng(d, "Med i alt", "B")["Ture"] == 12   # standsningen er 300 m væk
    with tempfile.TemporaryDirectory() as tmp:
        d, _ = _doc(tmp, None)
    sn = d["meta"]["standsning"]
    assert not sn["ved_stop"] and sn["standard"] == "i alt"
    assert {r["Gruppe"] for r in d["nogletal"]} == {"Alle ture", "Uden i alt", "Med i alt"}
    assert all(r["andel_stop_ved"] is None for r in d["nogletal"])


def test_drift_ture_rundet_ned_og_dage():
    with tempfile.TemporaryDirectory() as tmp:
        d, v12 = _doc(tmp, STOP_VED, fart_b=S.fart_kink, flag_b=True, v12=True)
    dr = {r["Retning"]: r for r in d["drift"] if r["Dag"] == "Hverdage" and r["Rute"] == "Alle ruter" and r["Time"] == -1}
    # retning 1: 5 efter-ture på 6 dage -> 0,83 pr. dag, rundet ned 0; retning 2: 6 på 6 -> 1
    assert dr["1"]["Ture_dag"] == 0.83 and dr["1"]["Ture_dag_hel"] == 0 and dr["1"]["Ekstra_min_dag_hel"] == 0
    assert dr["2"]["Ture_dag_hel"] == 1 and abs(dr["2"]["Ekstra_min_dag_hel"] - dr["2"]["Delta_s"] / 60) < 1e-3
    assert abs(dr["B"]["Ekstra_min_dag_hel"] - dr["2"]["Ekstra_min_dag_hel"]) < 1e-3
    assert dr["B"]["Ekstra_min_dag"] > dr["B"]["Ekstra_min_dag_hel"]                  # negativ: uden nedrunding er tallet større
    a12 = {r["Retning"]: r for r in v12["drift"] if r["Dag"] == "Hverdage" and r["Rute"] == "Alle ruter" and r["Time"] == -1}
    assert all(dr[k]["Ekstra_min_dag"] == a12[k]["Ekstra_min_dag"] for k in a12)       # v1.2-feltet er uændret
    assert d["meta"]["drift_dage"]["Hverdage"] == {"uger4": 20, "aar": 250}
    assert d["meta"]["drift_dage"]["Alle dage"]["aar"] == 365


def test_total_fordeling_og_byg():
    with tempfile.TemporaryDirectory() as tmp:
        d, _ = _doc(tmp, STOP_VED)
    t = next(r for r in d["ture"] if r["Dag"] == "Hverdage" and r["Retning"] == "1" and r["Tur"] == "101")
    for grp, per in t["G"].items():
        for p, st in per.items():
            h = t["H"][grp][p]
            assert (st is None and h == []) or (st[0] == sum(n for _, n in h)), (grp, p)
    assert B.standard_skabelon(d).name == "skabelon_v1.3.html"
    assert B.standard_skabelon({"version": "1.2"}).name == "skabelon_v1.2.html"
    assert B.standard_skabelon({"version": "1.1"}).name == "skabelon.html"
    h = B.byg(d, SKABELON)
    for mark in ("{{TITEL}}", "__RAPPORTDATA__", "/*__ECHARTS__*/"):
        assert mark not in h, mark
    assert "<script src" not in h and "Turreference" not in h


# ---------------------------------------------------------------- konklusionsfilen
def test_konklusion_standsning():
    with tempfile.TemporaryDirectory() as tmp:
        d, v12 = _doc(tmp, STOP_VED, v12=True)
    ved, _ = LK.fra_rapportdata(d)
    alt, _ = LK.fra_rapportdata(d, standsning="i alt")
    gl, _ = LK.fra_rapportdata(v12)
    assert ved["standsning"] == "ved stop" and alt["standsning"] == "i alt" and gl["standsning"] == "i alt"
    assert ved["ture"] == {"foer": 12, "efter": 0} and alt["ture"] == {"foer": 12, "efter": 0}   # alle efter-ture standser
    assert {k: v for k, v in alt.items() if k not in ("vaerktoej",)} == {k: v for k, v in gl.items() if k not in ("vaerktoej",)}
    for fejl_kald in (lambda: LK.fra_rapportdata(v12, standsning="ved stop"), lambda: LK.fra_rapportdata(d, standsning="et sted")):
        try:
            fejl_kald()
        except SystemExit:
            pass
        else:
            raise AssertionError("forventede SystemExit")
    with tempfile.TemporaryDirectory() as tmp:
        d2, _ = _doc(tmp, None)
    assert LK.fra_rapportdata(d2)[0]["standsning"] == "i alt"
    tekst = LK.skriv_yaml(ved, {})
    assert 'standsning: "ved stop"' in tekst


def test_konklusionsfil_felt_standsning():
    god = copy.deepcopy(__import__("test_konklusioner_html").GOD)
    assert KH.tjek_analyse(god) == []                                          # uden feltet: stadig gyldig (ældre filer)
    for v in ("ved stop", "i alt"):
        assert KH.tjek_analyse({**god, "standsning": v}) == [], v
    assert any("'standsning'" in f for f in KH.tjek_analyse({**god, "standsning": "ved stoppet"}))
    assert any("ukendt felt 'standsninger'" in f for f in KH.tjek_analyse({**god, "standsninger": "i alt"}))
    md = KH.byg_md([("x", {**god, "standsning": "ved stop"})], "2026-11-26")
    assert "Tallene bygger på:** ture uden standsning ved stop" in md
    assert "Tallene bygger på" not in KH.byg_md([("x", god)], "2026-11-26")


# ---------------------------------------------------------------- browser
def test_browser_standsning_total_og_drift():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP test_browser_standsning_total_og_drift: playwright er ikke installeret")
        return
    with tempfile.TemporaryDirectory() as tmp:
        d, _ = _doc(tmp, STOP_VED)
        sti = Path(tmp) / "rapport.html"
        sti.write_text(B.byg(d, SKABELON), encoding="utf-8")
        # forventet total-række (alle ture, hverdage, begge retninger): alle kørsler samlet, numpy-percentil
        alle = {p: [] for p in ("A", "B")}
        for r in d["ture"]:
            if r["Dag"] == "Hverdage" and r["Rute"] == "Alle ruter":
                for p in alle:
                    alle[p] += [v for v, n in r["H"]["Alle ture"][p] for _ in range(n)]
        with sync_playwright() as pw:
            b = None
            for kw in ({"channel": "msedge"}, {"channel": "chrome"}, {}):
                try:
                    b = pw.chromium.launch(**kw)
                    break
                except Exception:      # noqa
                    continue
            if b is None:
                print("SKIP test_browser_standsning_total_og_drift: ingen browser")
                return
            for bredde in (1440, 375):
                fejl = []
                pg = b.new_page(viewport={"width": bredde, "height": 900})
                pg.on("pageerror", lambda e: fejl.append(str(e)))
                pg.on("console", lambda m: fejl.append(m.text) if m.type in ("error", "warning") else None)
                pg.goto(sti.as_uri())
                pg.wait_for_function("window.RAPPORT_KLAR === true")
                assert pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0, bredde
                assert pg.evaluate("window.RAPPORT_KONTRAST") == []
                assert pg.evaluate("window.RAPPORT.state.stop") == "Uden ved stop"                 # standard med stoppesteder
                assert "uden standsning ved stop" in pg.inner_text("#tiles-tekst")
                assert "Samlet" in pg.inner_text(".valg button.on")
                pg.click(".knapper[data-f=stop] button[data-v='Alle ture']")
                celler = pg.evaluate("[...document.querySelector('#t-ture tr.total').cells].map(c => c.innerText)")
                assert celler[0].startswith("I alt (2 planlagte ture)"), celler
                assert celler[2] == str(len(alle["A"])) and celler[4] == str(len(alle["B"]))
                for txt, v in ((celler[1], alle["A"]), (celler[3], alle["B"])):
                    med = float(txt.split(" s")[0].replace(",", "."))
                    assert abs(med - np.percentile(v, 50)) < 0.051, (txt, np.percentile(v, 50))
                # kendt negativ: sikkerhed "høj" (min. 20 kørsler) giver ingen rækker (6 kørsler pr. tur)
                assert pg.evaluate("document.querySelector('.mini[data-f=sik] button[data-v=hoej]').disabled")
                pg.click(".mini[data-f=sik] button[data-v=lav]")
                assert pg.evaluate("document.querySelectorAll('#t-ture tbody tr:not(.total)').length") == 2
                # drift: hele ture pr. dag (1) og 4 uger = 20 dage
                assert "1 ture ×" in pg.inner_text("#d1") and "20 hverdage" in pg.inner_text("#d2") and "250 hverdage" in pg.inner_text("#d3")
                assert "Bump for ruten pr. driftsdøgn" in pg.inner_text("#d4")
                assert fejl == [], fejl
                pg.close()
            b.close()


if __name__ == "__main__":
    for navn, fn in list(globals().items()):
        if navn.startswith("test_"):
            fn()
            print("OK", navn)
