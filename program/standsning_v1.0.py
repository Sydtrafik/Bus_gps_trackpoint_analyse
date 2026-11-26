#!/usr/bin/env python3
"""
standsning_v1.0.py - to definitioner af standsning pr. tur på en strækning, ud fra GPS-pings (segmenter.csv).

  standsning i alt     = bussen kommer under komfort.stillestand_kmh (3,6 km/t) et sted på strækningen, uanset hvor.
                         Samme tal som `stillestand` i komfort_v1.0.py (samme udjævnede fart, samme strækning).
  standsning ved stop  = bussen kommer under komfort.stillestand_kmh højst VED_STOP_M (40 m) fra et stoppested i
                         config (rapport.stoppesteder: navn, retning, lat, lon; ét pr. side af vejen). Et stoppested
                         med retning gælder kun ture i den retning (HAFAS' Retning 1/2); uden retning gælder det begge.
                         Standsning andre steder (kø, kryds, rødt lys) tæller ikke med.

Hvilke stoppesteder hører til strækningen: som i rapporten (lav_rapportdata_v1.2.py): feltet `straekning`, eller
ellers dem, der ligger på strækningen (0 <= s <= L) højst 40 m fra linjen. Uden stoppesteder på strækningen er
"standsning ved stop" 0 for alle ture, og rapporten viser kun "standsning i alt".

Hvorfor 40 m: bussen holder med fordøren ved stoppestedet (positionen i config), GPS-antennen sidder et sted på en 12-13 m
lang bus, GPS-positionen kan ligge 5-10 m ved siden af, og en bus bag en anden ved stoppestedet holder 15-25 m længere
tilbage. 40 m dækker det uden at nå de fleste kryds; afstanden kan ændres med --ved-stop-m (målt følsomhed: A15b).

Bruges af rapport/lav_rapportdata_v1.3.py (funktionen ved_stop pr. tur). Kan også køres alene til kontrol:

    python standsning_v1.0.py --segments ud\\A\\segmenter.csv --config config.yaml --out ud\\A\\standsning.csv

Output (kun til kontrol, indeholder Turreference): én række pr. tur og strækning med status (ok = fart kunne regnes),
stand_i_alt, stand_ved_stop og antal stoppesteder brugt. Afhængigheder: pandas, numpy, pyyaml. PYTHONUTF8=1 på Windows.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "rapport"))
import zonetid as Z  # noqa: E402
import lav_rapportdata as R11  # noqa: E402  (tur_profil: samme udjævnede fart som komfort_v1.0)

K = Z.K
VERSION = "1.0"
VED_STOP_M = 40.0


def stoppesteder_for(s, rap, pts, L=None):
    """Stoppestederne fra rapport.stoppesteder, der hører til strækningen s (som i lav_rapportdata_v1.2.py).
    Returnér liste af dict(navn, retning (str eller None), s_m = position langs linjen fra fra-punktet)."""
    kom = s["komfort"]
    lat0, lon0, enhed, L_geo = K.linje_geometri(pts[kom["fra"]], pts[kom["til"]])
    L = float(kom["laengde_m"]) if kom.get("laengde_m") else (L if L is not None else L_geo)
    ud = []
    for sp in (rap or {}).get("stoppesteder") or []:
        sx, sd = K.projicer([float(sp["lat"])], [float(sp["lon"])], lat0, lon0, enhed)
        eksplicit = sp.get("straekning")
        hoerer = (str(eksplicit) == s["id"]) if eksplicit is not None else (
            0.0 <= float(sx[0]) <= L and abs(float(sd[0])) <= R11.STOP_SIDEAFSTAND_M)
        if hoerer:
            ud.append({"navn": str(sp["navn"]), "retning": (str(sp["retning"]) if sp.get("retning") is not None else None),
                       "s_m": float(sx[0])})
    return ud


def ved_stop(sg, vk, retning, stops, graense_kmh, afstand_m=VED_STOP_M):
    """1, hvis farten vk (km/t) er under graense_kmh et sted højst afstand_m fra et stoppested for turens retning.
    sg = position langs linjen fra fra-punktet (m) pr. gitterpunkt på strækningen (som tur_profil returnerer)."""
    sg = np.asarray(sg, dtype=float)
    lav = np.asarray(vk, dtype=float) < graense_kmh
    if not lav.any():
        return 0
    for sp in stops:
        if sp["retning"] is not None and str(retning) != sp["retning"]:
            continue
        if (lav & (np.abs(sg - sp["s_m"]) <= afstand_m)).any():
            return 1
    return 0


def i_alt(vk, graense_kmh):
    """1, hvis farten et sted på strækningen er under graense_kmh (= komfort_v1.0's stillestand)."""
    return int(np.min(vk) < graense_kmh)


def beregn(seg, s, rap, pts, afstand_m=VED_STOP_M, log=print):
    """seg = segmenter.csv (DataFrame med Turreference, Retning, datetime, lat, lon, er_stoprække). Én række pr. tur."""
    kom = s["komfort"]
    lat0, lon0, enhed, L = K.linje_geometri(pts[kom["fra"]], pts[kom["til"]])
    if kom.get("laengde_m"):
        L = float(kom["laengde_m"])
    stops = stoppesteder_for(s, rap, pts, L)
    navne = ", ".join("%s retn. %s" % (x["navn"], x["retning"]) for x in stops) or "ingen"
    log(f"  strækning {s['id']}: {len(stops)} stoppesteder ({navne}), ved stop = højst {afstand_m:g} m")
    meta = seg.drop_duplicates("Turreference").set_index("Turreference")["Retning"]
    p = seg[seg["er_stoprække"] == 0].copy()
    sx, sd = K.projicer(p["lat"].to_numpy(), p["lon"].to_numpy(), lat0, lon0, enhed)
    p["s"], p["d"] = sx, sd
    mg = kom["korridor_margin_m"]
    p = p[(p["s"] >= -mg) & (p["s"] <= L + mg) & (p["d"].abs() <= kom["korridor_sideafstand_m"])]
    p["t"] = (pd.to_datetime(p["datetime"], format="%Y-%m-%d %H:%M:%S") - pd.Timestamp("1970-01-01")).dt.total_seconds()
    grupper = {ref: g for ref, g in p.groupby("Turreference", sort=False)}
    rows = []
    for ref in seg["Turreference"].drop_duplicates():
        r = {"Turreference": ref, "S": s["id"], "Retning": str(meta.at[ref]), "status": "ufuldstændig",
             "stand_i_alt": pd.NA, "stand_ved_stop": pd.NA, "antal_stop": len(stops)}
        g = grupper.get(ref)
        res = None if g is None else R11.tur_profil(g["t"].to_numpy(dtype=float), g["s"].to_numpy(), L, kom)
        if res is not None:
            sg, vk, _fremad = res
            r.update(status="ok", stand_i_alt=i_alt(vk, kom["stillestand_kmh"]),
                     stand_ved_stop=ved_stop(sg, vk, r["Retning"], stops, kom["stillestand_kmh"], afstand_m))
        rows.append(r)
    ud = pd.DataFrame(rows)
    for c in ("stand_i_alt", "stand_ved_stop"):
        ud[c] = ud[c].astype("Int64")
    return ud


def main(argv=None):
    ap = argparse.ArgumentParser(description="Standsning i alt og ved stop pr. tur ud fra segmenter.csv (til kontrol).")
    ap.add_argument("--segments", required=True)
    ap.add_argument("--config", required=True, help="config med points, komfort og rapport.stoppesteder")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ved-stop-m", type=float, default=VED_STOP_M, help=f"afstand til stoppested (standard {VED_STOP_M:g} m)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cfg = Z.laes_config(a.config)
    rap = cfg["raw"].get("rapport") or {}
    seg = pd.read_csv(a.segments, sep=";", encoding="utf-8", dtype={"Turreference": str, "Retning": str},
                      usecols=["Turreference", "Retning", "datetime", "lat", "lon", "er_stoprække"])
    print(f"standsning_v{VERSION}: {a.segments}")
    ud = pd.concat([beregn(seg, s, rap, cfg["points"], a.ved_stop_m) for s in cfg["straekninger"]], ignore_index=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    ud.to_csv(a.out, sep=";", index=False, encoding="utf-8")
    ok = ud[ud["status"] == "ok"]
    print(f"  Skrev {len(ud)} rækker ({len(ok)} ok): standsning i alt {int(ok['stand_i_alt'].sum())}, ved stop {int(ok['stand_ved_stop'].sum())} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
