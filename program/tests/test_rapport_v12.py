#!/usr/bin/env python3
"""
Tests for rapport/lav_rapportdata_v1.2.py og skabelon_v1.2.html - samme syntetiske data som test_rapport.py plus en
konstrueret turtabel (dagtype, rute, planlagt tur, time).

Koer:  python tests/test_rapport_v12.py   eller   python -m pytest tests/test_rapport_v12.py
Sæt PYTHONUTF8=1 i miljøet. Browsertesten kræver playwright (ellers "SKIP").

Data (se tests/syntetisk.py): 1 tur pr. retning pr. dag. Før 10 m/s overalt (60 s), efter halv fart i en zone (72 s).
Turtabel: retning 1 kl. 08 (planlagt tur 101), retning 2 kl. 17 (tur 201); rute 7X på dagene med lige nummer (sorteret)
og 9Y på de ulige. Periode A får desuden en lørdag (weekend, 2 ture). Én tur kan få et stoprække-flag (fravalgt, men talt).
Kendt: standardvalget (hverdage, alle ruter, alle timer) = v1.1; kl. 08 = kun retning 1; weekend = lørdagens 2 ture.
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "rapport"))
import syntetisk as S  # noqa: E402
import lav_rapportdata as R11  # noqa: E402
import byg_rapport as B  # noqa: E402

_spec = importlib.util.spec_from_file_location("lav_rapportdata_v12", ROOT / "rapport" / "lav_rapportdata_v1.2.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)
Z = S.Z
SKABELON = (ROOT / "rapport" / "skabelon_v1.2.html").read_text(encoding="utf-8")
LOERDAG = "2025-08-09"


def _turtabel(per):
    rows = []
    for p, (r, _k, _s) in per.items():
        dage = sorted(r["Køredag"].unique())
        for x in r.itertuples():
            i = dage.index(x.Køredag)
            ret = int(x.Retning)
            lor = x.Køredag == LOERDAG
            rows.append({"Periode": p, "Turreference": str(x.Turreference), "Dagtype": "lørdag" if lor else "hverdag",
                         "Rute": "7X" if i % 2 == 0 else "9Y", "Turnummer": "101" if ret == 1 else "201",
                         "Time": 8 if ret == 1 else 17,
                         "Tid Start": f"{x.Køredag} {'08:05:00' if ret == 1 else '17:20:00'}"})
    tt = pd.DataFrame(rows)
    with tempfile.TemporaryDirectory() as tmp:
        sti = Path(tmp) / "turtabel.csv"
        tt.to_csv(sti, sep=";", index=False, encoding="utf-8-sig")
        return R.laes_turtabel(sti)


def _alt(tmp, loerdag=False, flag=False, **kw):
    cfg = Z.laes_config(S.skriv_config(tmp, **kw))
    dage_a = S.HVERDAGE_A + ([LOERDAG] if loerdag else [])

    def med_flag(meta, seg):
        if flag:
            meta.loc[meta.index[0], "Flag"] = "stoprække_p1"
        return meta, seg
    per = S.perioder(S.fart_kink, cfg, dage_a=dage_a, extra_a=med_flag)
    zj, _ = Z.beregn(cfg, per, log=lambda *a: None)
    return cfg, per, zj


def _doc(tmp, **kw):
    cfg, per, zj = _alt(tmp, **kw)
    return R.bygg(cfg, per, zj, _turtabel(per), log=lambda *a: None), (cfg, per, zj)


def _std(rows, d):
    m = d["meta"]
    return [{k: v for k, v in r.items() if k not in ("Dag", "Rute", "Time")} for r in rows
            if r["Dag"] == m["standard_dag"] and r["Rute"] == m["alle_ruter"] and r["Time"] == m["alle_timer"]]


def _udfold(rows):
    return [{"S": r["S"], "Retning": r["Retning"], "Gruppe": r["Gruppe"], "Periode": r["Periode"], "Meter": m, "Median": r["Median"][i],
             "P25": r["P25"][i], "P75": r["P75"][i], "Ture": r["Ture"][i]} for r in rows for i, m in enumerate(r["Meter"])]


def test_standardvalg_er_som_v11():
    with tempfile.TemporaryDirectory() as tmp:
        d, (cfg, per, zj) = _doc(tmp, loerdag=True)
        v11 = R11.bygg(cfg, per, zj, log=lambda *a: None)
    assert d["version"] == "1.2"
    for k in ("omfang", "nogletal", "drift", "maaned"):
        assert _std(d[k], d) == v11[k], k
    assert _udfold(_std(d["fartprofil"], d)) == v11["fartprofil"]
    assert d["zonetid"] == v11["zonetid"] and d["foelsomhed"] == v11["foelsomhed"]
    # fordeling er additiv: summeret over hverdage = v1.1
    acc = {}
    for r in d["fordeling"]:
        if r["Dagtype"] == "hverdag":
            k = (r["Periode"], r["Retning"], r["Stop"], r["Klasse"], r["KlasseAcc"], r["KlasseSam"])
            acc[k] = acc.get(k, 0) + r["n"]
    assert acc == {(r["Periode"], r["Retning"], r["Stop"], r["Klasse"], r["KlasseAcc"], r["KlasseSam"]): r["n"] for r in v11["fordeling"]}


def test_time_dag_og_rute():
    with tempfile.TemporaryDirectory() as tmp:
        d, _ = _doc(tmp, loerdag=True)
    om = {(r["Dag"], r["Rute"], r["Time"], r["Periode"]): r for r in d["omfang"]}
    assert om[("Hverdage", "Alle ruter", -1, "A")] == {"S": "s1", "Dag": "Hverdage", "Rute": "Alle ruter", "Time": -1, "Periode": "A", "Dage": 6, "Ture": 12}
    assert om[("Weekend og helligdage", "Alle ruter", -1, "A")]["Ture"] == 2 and om[("Weekend og helligdage", "Alle ruter", -1, "A")]["Dage"] == 1
    assert ("Weekend og helligdage", "Alle ruter", -1, "B") in om and om[("Weekend og helligdage", "Alle ruter", -1, "B")]["Ture"] == 0
    assert om[("Alle dage", "Alle ruter", -1, "A")]["Ture"] == 14
    # A har 7 dage inkl. lørdagen (nr. 5): 7X = dag 0, 2, 4, 6 = 4 hverdage = 8 ture; B: 9Y = dag 1, 3, 5 = 6 ture
    assert om[("Hverdage", "7X", -1, "A")]["Ture"] == 8 and om[("Hverdage", "9Y", -1, "B")]["Ture"] == 6
    ng = {(r["Dag"], r["Rute"], r["Time"], r["Retning"], r["Gruppe"], r["Periode"]): r for r in d["nogletal"]}
    k8a, k8b = ng[("Hverdage", "Alle ruter", 8, "B", "Alle ture", "A")], ng[("Hverdage", "Alle ruter", 8, "B", "Alle ture", "B")]
    assert k8a["Ture"] == 6 and k8a["koretid"] == 60 and k8b["koretid"] == 72        # kl. 08 = kun retning 1
    assert ng[("Hverdage", "Alle ruter", 8, "2", "Alle ture", "A")]["Ture"] == 0     # negativ: retning 2 kører kl. 17
    assert ng[("Hverdage", "Alle ruter", 17, "2", "Alle ture", "A")]["Ture"] == 6
    assert ("Hverdage", "Alle ruter", 9, "B", "Alle ture", "A") not in ng           # ingen ture kl. 09: ingen tal
    m = d["meta"]["straekninger"][0]
    assert m["ruter"] == ["Alle ruter", "7X", "9Y"] and m["timer"] == [8, 17]
    # planlagte ture: tur 101 i retning 1, hverdage: 6 kørsler før (60 s) og 6 efter (72 s), klokkeslæt 08:05
    tu = {(r["Dag"], r["Rute"], r["Retning"], r["Tur"]): r for r in d["ture"]}
    t = tu[("Hverdage", "Alle ruter", "1", "101")]
    assert t["Kl"] == 8 * 60 + 5 and t["G"]["Alle ture"]["A"][:2] == [6, 60.0] and t["G"]["Alle ture"]["B"][:2] == [6, 72.0]
    # drift kl. 08: kun retning 1, 1 tur pr. hverdag x 12 s = 0,2 min
    dr = {(r["Time"], r["Retning"]): r for r in d["drift"] if r["Dag"] == "Hverdage" and r["Rute"] == "Alle ruter"}
    assert abs(dr[(8, "B")]["Ekstra_min_dag"] - 0.2) < 0.01 and abs(dr[(-1, "B")]["Ekstra_min_dag"] - 0.4) < 0.01


def test_fravalg_synligt_og_ingen_tur_id():
    with tempfile.TemporaryDirectory() as tmp:
        d, _ = _doc(tmp, flag=True)
    fa = [r for r in d["fravalg"] if r["Periode"] == "A"]
    assert sum(r["n"] for r in fa) == 12 and sum(r["fra"] for r in fa) == 1 and sum(r["stop"] for r in fa) == 1
    om = {(r["Dag"], r["Rute"], r["Time"], r["Periode"]): r for r in d["omfang"]}
    assert om[("Hverdage", "Alle ruter", -1, "A")]["Ture"] == 11                  # den flagede tur er ikke i tallene
    tekst = json.dumps(d, ensure_ascii=False)
    assert "Turreference" not in tekst
    for ref in ("A000", "A001", "B000", "B001", "A051", "B051"):
        assert ref not in tekst, ref


def test_turtabel_mangler_eller_passer_ikke():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, per, zj = _alt(tmp)
        tt = _turtabel(per)
        try:
            R.bygg(cfg, per, zj, tt.iloc[1:], log=lambda *a: None)
        except SystemExit as e:
            assert "findes ikke i turtabel.csv" in str(e)
        else:
            raise AssertionError("forventede SystemExit ved manglende tur")
        tt2 = tt.copy()
        tt2.loc[tt2.index[0], "_dagtype"] = "helligdag"                       # passer ikke med config (ingen helligdage)
        try:
            R.bygg(cfg, per, zj, tt2, log=lambda *a: None)
        except SystemExit as e:
            assert "passer ikke med udvalg" in str(e)
        else:
            raise AssertionError("forventede SystemExit ved forkert dagtype")
        sti = Path(tmp) / "uden.csv"
        pd.DataFrame({"Periode": ["A"], "Turreference": ["x"], "Dagtype": ["hverdag"], "Rute": ["7X"], "Time": [8]}).to_csv(sti, sep=";", index=False)
        try:
            R.laes_turtabel(sti)
        except SystemExit as e:
            assert "Turnummer" in str(e)
        else:
            raise AssertionError("forventede SystemExit uden Turnummer")


def test_byg_vaelger_skabelon_og_advarer_om_vej():
    with tempfile.TemporaryDirectory() as tmp:
        d, _ = _doc(tmp, rapport={"titel": "Test v1.2", "forbehold": ["Kun test."], "vej": {"vejtype": "Boligvej"}})
    assert B.standard_skabelon(d).name == "skabelon_v1.2.html"
    assert B.standard_skabelon({"version": "1.1"}).name == "skabelon.html"
    assert d["meta"]["vej"] == {"vejtype": "Boligvej"}
    adv = " ".join(B.advarsler(d))
    assert "hastighedsgrænse" in adv and "bumptype" in adv and "vejtype" not in adv.split("mangler:")[1].split("(")[0]
    h = B.byg(d, SKABELON)
    for mark in ("{{TITEL}}", "__RAPPORTDATA__", "/*__ECHARTS__*/"):
        assert mark not in h, mark
    assert "<script src" not in h and "Turreference" not in h


def test_browser_valg_og_klik():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP test_browser_valg_og_klik: playwright er ikke installeret")
        return
    with tempfile.TemporaryDirectory() as tmp:
        d, _ = _doc(tmp, loerdag=True, rapport={"titel": "Test v1.2", "forbehold": ["Kun test."]})
        sti = Path(tmp) / "rapport.html"
        sti.write_text(B.byg(d, SKABELON), encoding="utf-8")
        with sync_playwright() as p:
            b = None
            for kw in ({"channel": "msedge"}, {"channel": "chrome"}, {}):
                try:
                    b = p.chromium.launch(**kw)
                    break
                except Exception:      # noqa
                    continue
            if b is None:
                print("SKIP test_browser_valg_og_klik: ingen browser")
                return
            for bredde in (1440, 375):
                fejl = []
                pg = b.new_page(viewport={"width": bredde, "height": 900})
                pg.on("pageerror", lambda e: fejl.append(str(e)))
                pg.on("console", lambda m: fejl.append(m.text) if m.type == "error" else None)
                pg.goto(sti.as_uri())
                pg.wait_for_function("window.RAPPORT_KLAR === true")
                assert pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0, bredde
                assert "hverdage, alle ruter og alle timer" in pg.inner_text("#h-basis")
                # rigtig museklik på søjlen kl. 08 i datagrundlaget
                pg.locator("#c-n").scroll_into_view_if_needed()
                box = pg.locator("#c-n").bounding_box()
                pos = pg.evaluate("echarts.getInstanceByDom(document.getElementById('c-n')).convertToPixel({gridIndex:0}, ['08', 1])")
                pg.mouse.click(box["x"] + pos[0], box["y"] + pos[1] - 2)
                pg.wait_for_timeout(300)
                assert pg.evaluate("window.RAPPORT.state.time") == 8
                assert "kl. 08" in pg.inner_text("#omfang") and "6 ture" in pg.inner_text("#k1")
                assert "OBS" in pg.inner_text("#k1")                                  # få ture vises og markeres
                pg.click(".vaelg .raekke[data-f=dag] button:has-text('Weekend og helligdage')")
                pg.select_option("#time-valg", "-1")
                assert "2 ture" in pg.inner_text("#omfang") or "1 weekend" in pg.inner_text("#omfang")
                assert not pg.evaluate("document.getElementById('rute-raekke').classList.contains('skjult')")   # to ruter: vælger vises
                assert fejl == [], fejl
                pg.close()
            b.close()


if __name__ == "__main__":
    for navn, fn in list(globals().items()):
        if navn.startswith("test_"):
            fn()
            print("OK", navn)
