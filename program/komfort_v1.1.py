#!/usr/bin/env python3
"""
komfort_v1.1.py - kørselskomfort pr. bustur, for en eller flere strækninger i samme config.

Ny i v1.1 (beregningen er den samme som komfort_v1.0.py, som ligger ved siden af og bruges herfra):
  - Flere strækninger: sektionen `straekninger:` i config (id, navn, fra, til, egne elementer, evt. egen `komfort:`).
  - Uændret bagudkompatibilitet: en config med den gamle form (`komfort: fra/til`, ingen `straekninger:`) er én strækning
    og giver præcis samme komfort.csv som komfort_v1.0.py.

Hvad komfortmålet er: passagerkomfort i kørslen på hele strækningen (opbremsning og acceleration langs vejen, dvs. fart
frem og tilbage), målt fra strækningens startpunkt til slutpunkt. Det er ikke stødet op og ned over selve bumpet; det kan
GPS hvert sekund ikke måle.

Input:  segmenter.csv fra analyse_v2.1.py (--export-segments). Segmenterne skal dække alle strækninger, så analysens
        start-/slut-stop (config `stops:`) skal ligge uden for den yderste strækning.
Config: points + enten `komfort: {fra, til, ...}` (én strækning) eller `straekninger:` (flere). Se config_eksempel.yaml.
Output: én række pr. tur pr. strækning.
        - Én strækning: filen i --out (komfort.csv).
        - Flere strækninger: komfort_<id>.csv ved siden af --out (fx --out ud_A/komfort.csv giver ud_A/komfort_s1.csv ...).
        - --straekning <id>: kun den strækning, skrevet præcis til --out.

    python komfort_v1.1.py --segments ud_A/segmenter.csv --config min_config.yaml --out ud_A/komfort.csv

Afhængigheder: pandas, numpy, pyyaml, komfort_v1.0.py (samme mappe). Sæt PYTHONUTF8=1 på Windows.
"""
import argparse
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import yaml

VERSION = "1.1"
HERE = Path(__file__).resolve().parent


def _load_v10():
    spec = importlib.util.spec_from_file_location("komfort_v1_0", HERE / "komfort_v1.0.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


K10 = _load_v10()


def laes_straekninger(sti):
    """Returnér (liste af strækninger, points, rå config). En strækning er et dict:
    id, navn, fra, til, komfort (færdig komfort-config for strækningen), elementer (liste), retninger (dict), raw."""
    with open(sti, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    pts = raw.get("points") or {}
    base = dict(K10.DEFAULTS)
    base["bump_vinduer"] = dict(K10.DEFAULTS["bump_vinduer"])
    user = raw.get("komfort") or {}
    base.update({k: v for k, v in user.items() if v is not None or k == "laengde_m"})
    liste = []
    if raw.get("straekninger"):
        ids = set()
        for i, s in enumerate(raw["straekninger"], 1):
            sid = str(s.get("id") or f"s{i}")
            if sid in ids:
                raise SystemExit(f"straekninger: id '{sid}' bruges to gange")
            ids.add(sid)
            for k in ("fra", "til"):
                if not s.get(k):
                    raise SystemExit(f"straekninger[{i}] ('{sid}') mangler '{k}' (punkt-id under points:)")
            kom = dict(base)
            kom["bump_vinduer"] = dict(base["bump_vinduer"])
            ov = s.get("komfort") or {}
            kom.update({k: v for k, v in ov.items() if v is not None or k == "laengde_m"})
            kom["fra"], kom["til"] = str(s["fra"]), str(s["til"])
            liste.append({"id": sid, "navn": str(s.get("navn") or sid), "fra": kom["fra"], "til": kom["til"], "komfort": kom,
                          "elementer": s.get("elementer") or [], "retninger": s.get("retninger") or {}, "raw": s})
    else:
        navn = str((raw.get("rapport") or {}).get("straekning_navn") or "Strækningen")
        liste.append({"id": "s1", "navn": navn, "fra": base["fra"], "til": base["til"], "komfort": base,
                      "elementer": raw.get("elementer") or [], "retninger": {}, "raw": {}})
    for s in liste:
        kom = s["komfort"]
        for key in (kom["fra"], kom["til"]):
            if key not in pts:
                raise SystemExit(f"Punkt '{key}' (strækning '{s['id']}': fra/til) findes ikke under points: i {sti}")
        if kom["kant"] not in ("interp", "drop"):
            raise SystemExit("komfort.kant skal være 'interp' eller 'drop'")
    return liste, pts, raw


def komfort_sti(mappe, sid, antal):
    """Sti til komfort-filen for strækning sid i en output-mappe: komfort.csv ved én strækning, ellers komfort_<id>.csv."""
    mappe = Path(mappe)
    return mappe / ("komfort.csv" if antal == 1 else f"komfort_{sid}.csv")


def _ud_sti(out, sid, antal, enkelt):
    out = Path(out)
    if antal == 1 or enkelt:
        return out
    return out.with_name(f"{out.stem}_{sid}{out.suffix}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Komfortmål pr. tur ud fra segmenter.csv, for en eller flere strækninger.")
    ap.add_argument("--segments", required=True, help="segmenter.csv")
    ap.add_argument("--config", required=True, help="YAML med points: og komfort: eller straekninger:")
    ap.add_argument("--out", required=True, help="komfort.csv (én strækning) eller sti, hvor komfort_<id>.csv lægges ved siden af")
    ap.add_argument("--straekning", default=None, help="kun denne strækning (id); skrives præcis til --out")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    liste, pts, _raw = laes_straekninger(a.config)
    valgt = liste
    if a.straekning:
        valgt = [s for s in liste if s["id"] == a.straekning]
        if not valgt:
            raise SystemExit(f"Strækning '{a.straekning}' findes ikke. Kendte id'er: {', '.join(s['id'] for s in liste)}")
    print(f"komfort_v{VERSION}: {a.segments}, {len(valgt)} strækning(er)")
    cols = ["Turreference", "Periode", "Retning", "Køredag", "datetime", "lat", "lon", "er_stoprække"]
    df = pd.read_csv(a.segments, sep=";", encoding="utf-8", usecols=cols,
                     dtype={"Turreference": "string", "Periode": "string", "Retning": "string",
                            "Køredag": "string", "datetime": "string"})
    print(f"  Rækker indlæst: {len(df):,}")
    for s in valgt:
        kom = s["komfort"]
        print(f"- Strækning {s['id']} ({s['navn']}): {kom['fra']} -> {kom['til']}")
        for k, v in kom.items():
            print(f"    {k} = {v}")
        res = K10.beregn_segmenter(df, kom, pts[kom["fra"]], pts[kom["til"]])
        sti = _ud_sti(a.out, s["id"], len(liste), bool(a.straekning))
        sti.parent.mkdir(parents=True, exist_ok=True)
        res.to_csv(sti, sep=";", index=False, encoding="utf-8", float_format="%.4f")
        n_ok = int((res["status"] == "ok").sum())
        print(f"  Skrev {len(res)} ture ({n_ok} ok, {len(res) - n_ok} ufuldstændige) -> {sti}")
        print("  Årsager (ufuldstændige): " + str(res.loc[res["status"] != "ok", "aarsag"].value_counts().to_dict()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
