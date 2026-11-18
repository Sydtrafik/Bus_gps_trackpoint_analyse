#!/usr/bin/env python3
"""
Tests for rapport/lav_kryds_rapport.py (v1.0) - en konstrueret turtabel med kendte køretider giver kendte tal pr. rute,
time og planlagt tur, og HTML-filen har ingen tur-id.

Koer:  python tests/test_kryds_rapport.py   eller   python -m pytest tests/test_kryds_rapport.py
Sæt PYTHONUTF8=1 i miljøet. Ingen data fra nogen virksomhed.

Ét stykke "Ind" (p1 -> p2), retning 1. Rute 7X: planlagt tur 501 kl. 07:10 hver dag i 12 dage (køretid 60-71 s)
og tur 502 kl. 08:20 i 12 dage (køretid 30 s). Rute 9Y: tur 601 kl. 07:40 i 3 dage (køretid 40 s, under OBS_N_TUR).
Én lørdagstur (tur 501, 999 s) med stoprække-match: fravalgt pga. dårlige data, men talt synligt. Dagtype er et
synligt valg med hverdage som standard; timer og ture med få kørsler er med.
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("lav_kryds_rapport", HERE.parent / "rapport" / "lav_kryds_rapport.py")
K = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(K)


def _turtabel():
    rows, ref = [], 7000000000
    def tur(dag, rute, tn, kl, sek, med=1, periode="A"):
        nonlocal ref
        ref += 1
        t1 = pd.Timestamp(f"2025-03-{dag:02d} {kl}")
        rows.append({"Periode": periode, "Periodenavn": "Før", "Dato": t1.strftime("%Y-%m-%d"),
                     "Dagtype": "hverdag" if med else "lørdag", "Retning": 1, "Rute": rute,
                     "Turnummer": tn, "Time": t1.hour, "Køretid Ind (s)": sek,
                     "Tid Start": t1.strftime("%Y-%m-%d %H:%M:%S"),
                     "Tid Slut": (t1 + pd.Timedelta(seconds=sek)).strftime("%Y-%m-%d %H:%M:%S"),
                     "Flag": "" if med else "stoprække_p1", "Log": "", "I_overblik": med, "Turreference": str(ref)})
    for i in range(12):
        tur(i + 1, "7X", "501", "07:10:00", 60 + i)
        tur(i + 1, "7X", "502", "08:20:00", 30)
    for i in range(3):
        tur(i + 1, "9Y", "601", "07:40:00", 40)
    tur(20, "7X", "501", "07:10:00", 999, med=0)
    return pd.DataFrame(rows)


def _skriv(tmp, tt):
    cfg = Path(tmp) / "config.yaml"
    cfg.write_text("periods:\n  A: {name: Før}\npoints:\n  p1: {name: Start}\n  p2: {name: Slut}\n"
                   "point_order:\n  direction_1: [p1, p2]\ndistances:\n  d1: {name: Ind, from: p1, to: p2}\n",
                   encoding="utf-8")
    sti = Path(tmp) / "turtabel.csv"
    tt.to_csv(sti, sep=";", index=False, encoding="utf-8-sig")
    return cfg, sti


def test_tal_pr_rute_time_og_tur():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, tt = K.laes(*_skriv(tmp, _turtabel()))
    d = K.byg_data(cfg, tt)
    R = d["retninger"][0]
    assert R["navn"] == "Start → Slut" and R["ruter"] == [K.ALLE, "7X", "9Y"], R["ruter"]
    assert d["dagtyper"] == ["Hverdage", "Weekend og helligdage", "Alle dage"] and d["standard_dag"] == "Hverdage"
    alle = R["stykker"][0]["pr"]["Alle dage"]
    hverd = R["stykker"][0]["pr"]["Hverdage"]
    # stoprække-turen (lørdag, 999 s) er fravalgt pga. dårlige data, men talt synligt i obs
    assert alle[K.ALLE]["alle"]["A"]["n"] == 27 and hverd[K.ALLE]["alle"]["A"]["n"] == 27
    assert R["obs"]["Alle dage"][K.ALLE]["A"] == {"n": 28, "fravalgt": 1, "stop": 1, "afstand": 0}, R["obs"]["Alle dage"][K.ALLE]
    assert R["obs"]["Hverdage"][K.ALLE]["A"] == {"n": 27, "fravalgt": 0, "stop": 0, "afstand": 0}
    assert R["obs"]["Weekend og helligdage"][K.ALLE]["A"]["fravalgt"] == 1
    assert hverd["7X"]["alle"]["A"]["n"] == 24 and hverd["9Y"]["alle"]["A"]["m"] == 40.0
    h7 = {x["t"]: x for x in hverd["7X"]["timer"]["A"]}
    assert h7[7]["m"] == 65.5 and h7[8]["m"] == 30.0, h7        # median af 60..71 = 65,5
    assert {x["t"]: x for x in alle["7X"]["timer"]["A"]}[7]["n"] == 12   # 999-turen tæller ikke med
    assert all(x["n"] > 0 for x in hverd[K.ALLE]["timer"]["A"])         # timer med få ture er med (ingen skjules)
    ture = {r["tur"]: r for r in hverd[K.ALLE]["ture"]}
    assert set(ture) == {"501", "502", "601"}, set(ture)        # 601 med, selv med 3 kørsler (OBS i HTML)
    assert ture["601"]["A"]["n"] == 3
    assert ture["501"]["kl"] == 7 * 60 + 10 and ture["501"]["A"]["n"] == 12 and ture["501"]["A"]["m"] == 65.5
    assert [r["tur"] for r in hverd[K.ALLE]["ture"]] == ["501", "601", "502"]   # sorteret efter klokkeslæt


def test_html_uden_tur_id_og_med_titel():
    with tempfile.TemporaryDirectory() as tmp:
        tt = _turtabel()
        cfg, sti = _skriv(tmp, tt)
        out = Path(tmp) / "kryds.html"
        gammel, K.OBS_N_TIME = K.OBS_N_TIME, 5        # testdata har 12-16 ture pr. time
        try:
            assert K.main(["--config", str(cfg), "--turtabel", str(sti), "--out", str(out)]) == 0
        finally:
            K.OBS_N_TIME = gammel
        html = out.read_text(encoding="utf-8")
    # titel på hverdage (standard), alle ruter: kl. 07 = 40, 40, 40, 60..71 -> median 64; kl. 08: 30
    assert "<title>På hverdage tager stykket Ind 64 s kl. 07 mod 30 s kl. 08</title>" in html, html[:300]
    for ref in tt["Turreference"]:
        assert ref not in html, ref
    assert '"tur": "501"' in html and "__RAPPORTDATA__" not in html and "/*__ECHARTS__*/" not in html


def test_gammel_turtabel_uden_turnummer_giver_dansk_fejl():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, sti = _skriv(tmp, _turtabel().drop(columns=["Turnummer"]))
        try:
            K.laes(cfg, sti)
        except SystemExit as e:
            assert "turtabel.py v1.1" in str(e)
        else:
            raise AssertionError("ingen fejl uden Turnummer-kolonnen")


def _run_all():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
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
