#!/usr/bin/env python3
"""
Tests for komfort_v1.1.py: flere strækninger, og bagudkompatibilitet med komfort_v1.0.py (samme config-form, samme tal).

Koer:  python tests/test_komfort_v11.py        (ren python)   eller   python -m pytest tests/test_komfort_v11.py
Sæt PYTHONUTF8=1 i miljøet. Ingen data fra nogen virksomhed.
"""
import sys
import tempfile
from pathlib import Path

import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import syntetisk as S  # noqa: E402

K11 = S.K11
K10 = S.K


def _skriv_segmenter(tmp, laengde=S.L, afstande=S.AFSTANDE_1, fart=S.fart_kink):
    meta, seg = S.bygg_periode("A", fart, S.HVERDAGE_A[:3], laengde, afstande)
    df = seg.merge(meta[["Turreference", "Periode", "Retning", "Køredag"]], on="Turreference")
    sti = Path(tmp) / "segmenter.csv"
    df.to_csv(sti, sep=";", index=False, encoding="utf-8")
    return sti


def test_samme_config_form_giver_samme_komfort_som_v10():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = S.skriv_config(tmp)
        seg = _skriv_segmenter(tmp)
        u10, u11 = Path(tmp) / "k10.csv", Path(tmp) / "k11.csv"
        assert K10.main(["--segments", str(seg), "--config", str(cfg), "--out", str(u10)]) == 0
        assert K11.main(["--segments", str(seg), "--config", str(cfg), "--out", str(u11)]) == 0
        assert u10.read_bytes() == u11.read_bytes(), "komfort_v1.1 skal give præcis samme fil som v1.0 ved én strækning"
        k = pd.read_csv(u11, sep=";")
        assert len(k) == 6 and (k["status"] == "ok").all(), k["status"].tolist()


def test_to_straekninger_giver_en_fil_pr_straekning():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = S.skriv_config(tmp, to_straekninger=True)
        seg = _skriv_segmenter(tmp, S.LAENGDE_2, S.AFSTANDE_2)
        out = Path(tmp) / "ud" / "komfort.csv"
        assert K11.main(["--segments", str(seg), "--config", str(cfg), "--out", str(out)]) == 0
        fa, fb = out.with_name("komfort_a.csv"), out.with_name("komfort_b.csv")
        assert fa.exists() and fb.exists() and not out.exists(), sorted(p.name for p in out.parent.iterdir())
        assert K11.komfort_sti(out.parent, "a", 2) == fa and K11.komfort_sti(out.parent, "x", 1) == out
        a, b = pd.read_csv(fa, sep=";"), pd.read_csv(fb, sep=";")
        assert len(a) == 6 and len(b) == 6 and (a["status"] == "ok").all() and (b["status"] == "ok").all()
        # strækning a har en langsom zone (min fart ca. 18 km/t), strækning b kører 36 km/t overalt
        assert a["min_fart_kmh"].median() < 25 and abs(b["min_fart_kmh"].median() - 36.0) < 1.0, (a["min_fart_kmh"].median(), b["min_fart_kmh"].median())
        assert abs(b["gns_fart_kmh"].median() - 36.0) < 0.5


def test_en_straekning_vaelges_med_straekning_og_skrives_til_out():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = S.skriv_config(tmp, to_straekninger=True)
        seg = _skriv_segmenter(tmp, S.LAENGDE_2, S.AFSTANDE_2)
        out = Path(tmp) / "kun_b.csv"
        assert K11.main(["--segments", str(seg), "--config", str(cfg), "--out", str(out), "--straekning", "b"]) == 0
        assert out.exists() and len(pd.read_csv(out, sep=";")) == 6


def test_fejl_paa_dansk():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = S.skriv_config(tmp, to_straekninger=True)
        seg = _skriv_segmenter(tmp, S.LAENGDE_2, S.AFSTANDE_2)
        try:
            K11.main(["--segments", str(seg), "--config", str(cfg), "--out", str(Path(tmp) / "x.csv"), "--straekning", "findes_ikke"])
            raise AssertionError("forventede SystemExit")
        except SystemExit as e:
            assert "findes ikke" in str(e) and "a, b" in str(e), str(e)
        raw = yaml.safe_load(Path(cfg).read_text(encoding="utf-8"))
        raw["straekninger"][1].pop("til")
        (Path(tmp) / "c2.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
        try:
            K11.laes_straekninger(Path(tmp) / "c2.yaml")
            raise AssertionError("forventede SystemExit")
        except SystemExit as e:
            assert "mangler 'til'" in str(e), str(e)
        raw["straekninger"][1]["til"] = "p9"
        (Path(tmp) / "c3.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
        try:
            K11.laes_straekninger(Path(tmp) / "c3.yaml")
            raise AssertionError("forventede SystemExit")
        except SystemExit as e:
            assert "p9" in str(e) and "findes ikke under points" in str(e), str(e)
        raw["straekninger"][1]["til"] = "p4"
        raw["straekninger"][0]["id"] = "b"
        (Path(tmp) / "c4.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
        try:
            K11.laes_straekninger(Path(tmp) / "c4.yaml")
            raise AssertionError("forventede SystemExit")
        except SystemExit as e:
            assert "bruges to gange" in str(e), str(e)


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
