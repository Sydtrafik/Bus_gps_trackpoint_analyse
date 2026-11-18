#!/usr/bin/env python3
"""
Tests for turtabel.py (v1.0) - konstruerede result.csv/segmenter.csv/List.csv med kendte tider giver kendt tabel og overblik.

Koer:  python tests/test_turtabel.py        (ren python)   eller   python -m pytest tests/test_turtabel.py
Sæt PYTHONUTF8=1 i miljøet. Ingen data fra nogen virksomhed.

To punkter p1 (Start) og p2 (Slut), én distance "Stykke". Periode A: 6 ture, B: 2 ture.
Tests af: kolonner og værdier pr. tur (dato, ugedag, dagtype, time, rute, tider), udvalg til overblikket,
percentiler, kontrollen køretid = tidsforskel (positiv og negativ), én periode, og at overblikket ikke har tur-id.
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("turtabel", HERE.parent / "turtabel.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

# (tur, køredag, retning, tid ved p1, køretid s, Log, Flag)  2025-03-03 er en mandag
TURE_A = [
    ("9001", "2025-03-03", 1, "2025-03-03 07:10:00", 60, "", ""),
    ("9002", "2025-03-03", 1, "2025-03-03 07:40:00", 70, "", ""),
    ("9003", "2025-03-03", 1, "2025-03-03 08:05:00", 80, "", ""),
    ("9004", "2025-03-03", 1, "2025-03-03 08:20:00", 500, "punkt_p2_afstand_høj_300m", "afstand_p2"),  # Log: ude
    ("9005", "2025-03-08", 1, "2025-03-08 08:30:00", 90, "", ""),                                       # lørdag: ude
    ("9006", "2025-03-04", 1, "2025-03-05 00:10:00", 100, "", "stoprække_p1"),                         # stoprække: ude
]
TURE_B = [
    ("9101", "2025-04-07", 1, "2025-04-07 07:15:00", 75, "", ""),                                      # helligdag: ude
    ("9102", "2025-04-08", 1, "2025-04-08 08:15:00", 95, "", ""),
]


def _skriv(tmp, navn, ture, rute_tab=True, retning2_slut_foerst=False):
    d = Path(tmp) / navn
    d.mkdir()
    res, seg = [], []
    for ref, dag, ret, t1, sek, log, flag in ture:
        res.append({"Turreference": ref, "Køredag": dag, "Periode": f"periode {navn}", "Retning": ret,
                    "Stykke - køretid (sek)": sek, "Log": log, "Flag": flag})
        t1 = pd.Timestamp(t1)
        t2 = t1 + pd.Timedelta(seconds=sek)
        for i, (t, mp) in enumerate([(t1 - pd.Timedelta(seconds=5), ""), (t1, "p1"),
                                     (t1 + pd.Timedelta(seconds=sek // 2), ""), (t2, "p2")]):
            seg.append({"Turreference": ref, "Periode": f"periode {navn}", "Retning": ret, "Køredag": dag,
                        "datetime": t.strftime("%Y-%m-%d %H:%M:%S"), "lat": 55.0, "lon": 8.0, "match_punkt": mp})
    pd.DataFrame(res).to_csv(d / "result.csv", sep=";", index=False, encoding="utf-8")
    pd.DataFrame(seg).to_csv(d / "segmenter.csv", sep=";", index=False, encoding="utf-8")
    # List.csv som i HAFAS: to kolonner, der hedder Turnummer (id, planlagt turnummer), og tab foran værdierne
    linjer = ['"\tTurnummer";"\tRute nr.";"\tTurnummer"']
    rute, tab = ("\t7X" if rute_tab else "7X"), "\t"
    linjer += [f"{t[0]};{rute};{tab}{int(t[0]) % 100 + 500}" for t in ture]
    (d / "List.csv").write_text("\n".join(linjer) + "\n", encoding="utf-8")
    return d


def _cfg(tmp, dagtype="hverdage"):
    sti = Path(tmp) / "config.yaml"
    sti.write_text(
        "periods:\n  A: {name: Før}\n  B: {name: Efter}\n"
        f"data:\n  Periode_A: {{list_csv: '{(Path(tmp) / 'A' / 'List.csv').as_posix()}'}}\n"
        f"  Periode_B: {{list_csv: '{(Path(tmp) / 'B' / 'List.csv').as_posix()}'}}\n"
        "points:\n  p1: {name: Start, lat: 55.0, lon: 8.0}\n  p2: {name: Slut, lat: 55.01, lon: 8.0}\n"
        "distances:\n  d1: {name: Stykke, from: p1, to: p2}\n"
        f"udvalg:\n  dagtype: {dagtype}\n  helligdage: ['2025-04-07']\n", encoding="utf-8")
    return T.laes_config(sti)


def _perioder(tmp, cfg, kun_a=False):
    out = {}
    for p in (("A",) if kun_a else ("A", "B")):
        d = Path(tmp) / p
        r = T.laes_result(d)
        out[p] = (r, T.laes_punkttider(d, set(r["Turreference"])), T.laes_rute(cfg["data"][f"Periode_{p}"]["list_csv"]))
    return out


def _byg(tmp, dagtype="hverdage"):
    _skriv(tmp, "A", TURE_A)
    _skriv(tmp, "B", TURE_B)
    cfg = _cfg(tmp, dagtype)
    return cfg, T.lav_turtabel(cfg, _perioder(tmp, cfg))


def test_turtabel_kolonner_og_vaerdier():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, (tt, k) = _byg(tmp)
    assert len(tt) == 8, len(tt)
    assert list(tt.columns[:10]) == ["Periode", "Periodenavn", "Dato", "Ugedag_nr", "Ugedag", "Dagtype", "Retning",
                                     "Rute", "Turnummer", "Time"], list(tt.columns)
    assert "Køretid Stykke (s)" in tt.columns and "Tid Start" in tt.columns and "Tid Slut" in tt.columns
    r = tt.set_index("Turreference")
    assert r.loc["9001", "Ugedag"] == "mandag" and r.loc["9001", "Ugedag_nr"] == 1
    assert r.loc["9005", "Dagtype"] == "lørdag"
    assert r.loc["9101", "Dagtype"] == "helligdag"           # helligdag fra config
    assert r.loc["9001", "Time"] == 7 and r.loc["9003", "Time"] == 8
    assert r.loc["9006", "Time"] == 0 and r.loc["9006", "Dato"] == "2025-03-04"   # over midnat: køredagen
    assert r.loc["9001", "Tid Start"] == "2025-03-03 07:10:00" and r.loc["9001", "Tid Slut"] == "2025-03-03 07:11:00"
    assert set(tt["Rute"]) == {"7X"}, set(tt["Rute"])          # tab fjernet
    assert r.loc["9001", "Turnummer"] == "501" and r.loc["9102", "Turnummer"] == "502"   # den anden Turnummer-kolonne
    assert k == {"ture": 8, "uden_tid": 0, "koretid_ok": 8, "koretid_tjekket": 8}, k


def test_udvalg_til_overblik():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, (tt, _) = _byg(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        _, (tt_alle, _) = _byg(tmp, dagtype="alle")
    inde = set(tt.loc[tt["I_overblik"] == 1, "Turreference"])
    assert inde == {"9001", "9002", "9003", "9102"}, inde      # Log, lørdag, stoprække og helligdag er ude
    inde = set(tt_alle.loc[tt_alle["I_overblik"] == 1, "Turreference"])
    assert inde == {"9001", "9002", "9003", "9005", "9101", "9102"}, inde   # dagtype alle: kun Log og stoprække ude


def test_overblik_percentiler_og_md():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, (tt, _) = _byg(tmp)
    ov = T.lav_overblik(tt, cfg)
    a = ov[(ov["Periode"] == "A") & (ov["Time"] == "alle")].iloc[0]
    assert (a["n"], a["p25"], a["median"], a["p75"]) == (3, 65.0, 70.0, 75.0), a.to_dict()   # 60, 70, 80
    h8 = ov[(ov["Periode"] == "A") & (ov["Time"] == 8)].iloc[0]
    assert (h8["n"], h8["median"]) == (1, 80.0)
    md = "\n".join(T.overblik_md(ov, cfg, ["A", "B"]))
    assert "| **alle** | 3* | 70 (65–75) | 1* | 95 (95–95) | +25 |" in md, md
    assert "Ændring median" in md
    for ref in tt["Turreference"]:
        assert ref not in md and ref not in ov.to_csv(sep=";"), ref       # ingen tur-id i overblikket


def test_kontrol_fanger_forkert_tid():
    with tempfile.TemporaryDirectory() as tmp:
        cfg, _ = _byg(tmp)
        per = _perioder(tmp, cfg)
    r, tider, rute = per["A"]
    tider = tider.copy()
    tider.loc["9001", "p2"] = "2025-03-03 07:11:07"           # 7 s forkert
    _, k = T.lav_turtabel(cfg, {"A": (r, tider, rute)})
    assert (k["koretid_ok"], k["koretid_tjekket"]) == (5, 6), k


def test_en_periode_og_manglende_list():
    with tempfile.TemporaryDirectory() as tmp:
        _skriv(tmp, "A", TURE_A)
        (Path(tmp) / "A" / "List.csv").unlink()
        cfg = _cfg(tmp)
        per = _perioder(tmp, cfg, kun_a=True)
        assert per["A"][2] is None
        tt, k = T.lav_turtabel(cfg, per)
        ov = T.lav_overblik(tt, cfg)
        md = "\n".join(T.overblik_md(ov, cfg, ["A"]))
        out = Path(tmp) / "ud"
        assert T.main(["--config", str(Path(tmp) / "config.yaml"), "--a", str(Path(tmp) / "A"), "--out", str(out)]) == 0
        assert (out / "turtabel.csv").read_bytes()[:3] == b"\xef\xbb\xbf"     # BOM til Excel
        assert (out / "overblik.md").exists() and (out / "overblik.csv").exists()
    assert set(tt["Rute"]) == {""} and set(tt["Turnummer"]) == {""} and len(tt) == 6
    assert "Ændring median" not in md and "| **alle** | 3* | 70 (65–75) |" in md, md


def test_mangler_segmenter_giver_dansk_fejl():
    with tempfile.TemporaryDirectory() as tmp:
        d = _skriv(tmp, "A", TURE_A)
        (d / "segmenter.csv").unlink()
        try:
            T.laes_punkttider(d)
        except SystemExit as e:
            assert "--export-segments" in str(e)
        else:
            raise AssertionError("ingen fejl ved manglende segmenter.csv")


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
