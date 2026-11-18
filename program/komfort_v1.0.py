#!/usr/bin/env python3
"""
komfort_v1.0.py - kørselskomfort pr. bustur på en strækning, ud fra GPS-pings.

Input:  segmenter.csv fra analyse_v2.0.py (--export-segments / export_segments: true) - pings pr. tur.
Config: samme YAML som analyse_v2.0.py (points: pX: {lat, lon, name}) + en sektion `komfort:`.
Output: én række pr. tur (komfort.csv): Turreference + komfortmål + status ok/ufuldstændig.

    python komfort_v1.0.py --segments seg/A/segmenter.csv --config config_3A.yaml --out komfort_A.csv

Metode (kort):
 1. Kun GPS-pings (er_stoprække = 0). Hver ping projiceres på linjen fra->til (lokal flad projektion,
    meter): s = afstand fra start langs linjen, d = sideafstand. Korridor: s i [-margin, L+margin]
    og |d| <= sideafstand.
 2. Fuld passage kræves: første ping nær start, sidste nær slut (eller omvendt), intet hul > max_hul_s.
 3. Position interpoleres lineært til et fast tidsgitter (1 s), og Savitzky-Golay (vindue 5 s, grad 2)
    giver fart (1. afledte) og acceleration (2. afledte). Implementeret med numpy (ingen scipy).
 4. Mål beregnes kun på selve strækningen 0 <= s <= L.

Afhængigheder: pandas, numpy, pyyaml. Sæt PYTHONUTF8=1 på Windows.
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

VERSION = "1.0"

# Standardværdier for config-sektionen `komfort:` (se config_eksempel.yaml for forklaringer).
DEFAULTS = {
    "fra": "p1",
    "til": "p5",
    "laengde_m": None,
    "korridor_margin_m": 15.0,
    "korridor_sideafstand_m": 15.0,
    "fuld_passage_margin_m": 15.0,
    "max_hul_s": 10.0,
    "gitter_s": 1.0,
    "sg_vindue_s": 5.0,
    "sg_orden": 2,
    "kant": "interp",
    "taerskler_ms2": [0.75, 1.35],
    "haendelse_min_s": 2.0,
    "stillestand_kmh": 3.6,
    "std_ddof": 0,
    "bump_vinduer": {"bump1": [80, 140], "bump2": [200, 260]},
}

EARTH_R = 6371000.0


# ------------------------------------------------------------------ geometri

def lokal_xy(lat, lon, lat0, lon0):
    """Lokal flad projektion (meter) omkring (lat0, lon0): x = øst, y = nord."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    k = math.pi / 180.0 * EARTH_R
    x = (lon - lon0) * k * math.cos(math.radians(lat0))
    y = (lat - lat0) * k
    return x, y


def linje_geometri(p_fra, p_til):
    """Returnér (lat0, lon0, enhedsvektor (ex, ey), længde L i meter) for linjen fra->til."""
    x1, y1 = lokal_xy(p_til["lat"], p_til["lon"], p_fra["lat"], p_fra["lon"])
    L = float(math.hypot(x1, y1))
    if L <= 0:
        raise ValueError("fra- og til-punkt er sammenfaldende")
    return p_fra["lat"], p_fra["lon"], (float(x1) / L, float(y1) / L), L


def projicer(lat, lon, lat0, lon0, enhed):
    """Projicér pings på linjen: returnér (s, d) i meter (s langs linjen fra start, d = sideafstand, uden fortegn tabt)."""
    x, y = lokal_xy(lat, lon, lat0, lon0)
    ex, ey = enhed
    s = x * ex + y * ey
    d = -x * ey + y * ex
    return s, d


# ------------------------------------------------------------------ Savitzky-Golay

def sg_afledte(y, vindue=5, orden=2, dt=1.0, kant="interp"):
    """
    Savitzky-Golay 1. og 2. afledte af y (jævnt gitter, skridt dt) via mindste kvadraters polynomiefit.
    Returnér (d1, d2). Vindue = antal punkter (ulige).
    kant = "interp": de yderste (vindue//2) punkter bruger polynomiet fra det første/sidste hele vindue
                     (asymmetrisk fit, som scipy mode='interp').
    kant = "drop":   de yderste (vindue//2) punkter sættes til NaN.
    """
    y = np.asarray(y, dtype=float)
    n = len(y)
    m = vindue // 2
    d1 = np.full(n, np.nan)
    d2 = np.full(n, np.nan)
    if vindue % 2 == 0 or vindue <= orden or n < vindue:
        return d1, d2
    offs = np.arange(-m, m + 1, dtype=float)
    A = np.vander(offs, orden + 1, increasing=True)      # kolonner: 1, k, k^2 ...
    P = np.linalg.pinv(A)                                # polynomiekoefficienter c_j = P[j] @ vindue
    # indre punkter: korrelation med koefficientrækken
    d1[m:n - m] = np.correlate(y, P[1], mode="valid") / dt
    d2[m:n - m] = 2.0 * np.correlate(y, P[2], mode="valid") / dt ** 2
    if kant == "interp" and orden >= 2:
        c_foer = P @ y[:vindue]
        c_efter = P @ y[n - vindue:]
        for i in range(m):
            t = i - m                                    # forskydning fra vinduets midte
            d1[i] = (c_foer[1] + 2 * c_foer[2] * t) / dt
            d2[i] = 2 * c_foer[2] / dt ** 2
            j = n - m + i
            t2 = j - (n - 1 - m)
            d1[j] = (c_efter[1] + 2 * c_efter[2] * t2) / dt
            d2[j] = 2 * c_efter[2] / dt ** 2
    return d1, d2


# ------------------------------------------------------------------ pr. tur

def antal_forloeb(maske, min_punkter):
    """Antal sammenhængende True-forløb på mindst min_punkter punkter."""
    n = 0
    run = 0
    for v in maske:
        if v:
            run += 1
        else:
            if run >= min_punkter:
                n += 1
            run = 0
    if run >= min_punkter:
        n += 1
    return n


def klasse(vaerdi, taerskler):
    """lav < t0 <= mellem < t1 <= høj."""
    if vaerdi is None or not np.isfinite(vaerdi):
        return ""
    if vaerdi < taerskler[0]:
        return "lav"
    if vaerdi < taerskler[1]:
        return "mellem"
    return "høj"


def kolonnesuffix(t):
    return f"t{int(round(t * 100)):03d}"


def kolonnenavne(cfg):
    kol = ["status", "aarsag", "antal_pings", "daekning_m", "koretid_s", "gns_fart_kmh", "min_fart_kmh",
           "max_fart_kmh", "spaend_kmh", "std_fart_kmh", "sum_abs_dfart_kmh", "max_opbremsning_ms2",
           "max_acceleration_ms2"]
    for t in cfg["taerskler_ms2"]:
        kol.append(f"opbr_haendelser_{kolonnesuffix(t)}")
    for t in cfg["taerskler_ms2"]:
        kol.append(f"acc_haendelser_{kolonnesuffix(t)}")
    kol += ["klasse_opbremsning", "klasse_acceleration", "stillestand", "min_fart_s_m"]
    for navn in cfg["bump_vinduer"]:
        kol += [f"{navn}_min_fart_kmh", f"{navn}_max_opbremsning_ms2"]
    return kol


def beregn_tur(t, s, L, cfg):
    """
    Komfortmål for én tur. t = tidsstempler (sekunder, float), s = position langs linjen fra start (m),
    begge for pings i korridoren. Returnér dict med kolonnenavne fra kolonnenavne(cfg).
    """
    res = {k: np.nan for k in kolonnenavne(cfg)}
    res["status"] = "ufuldstændig"
    res["aarsag"] = ""
    res["antal_pings"] = int(len(t))

    def afvis(aarsag):
        res["aarsag"] = aarsag
        return res

    if len(t) < 3:
        return afvis("for_faa_pings")
    ordn = np.argsort(t, kind="stable")
    t = np.asarray(t, dtype=float)[ordn]
    s = np.asarray(s, dtype=float)[ordn]
    keep = np.concatenate(([True], np.diff(t) > 0))       # drop duplikerede tidsstempler (behold første)
    t, s = t[keep], s[keep]
    res["antal_pings"] = int(len(t))
    if len(t) < 3:
        return afvis("for_faa_pings")

    m = cfg["fuld_passage_margin_m"]
    fremad = s[0] <= m and s[-1] >= L - m
    baglaens = s[0] >= L - m and s[-1] <= m
    if not (fremad or baglaens):
        return afvis("ikke_fuld_passage")
    if np.max(np.diff(t)) > cfg["max_hul_s"]:
        return afvis("hul_over_max")

    dt = float(cfg["gitter_s"])
    vindue = int(round(cfg["sg_vindue_s"] / dt))
    if vindue % 2 == 0:
        vindue += 1
    grid = np.arange(t[0], t[-1] + 1e-9, dt)
    if len(grid) < vindue:
        return afvis("for_kort_til_sg")
    sg = np.interp(grid, t, s)
    # x = position i kørselsretningen (vokser med tiden)
    ret = 1.0 if fremad else -1.0
    x = sg if fremad else L - sg
    v, a = sg_afledte(x, vindue, int(cfg["sg_orden"]), dt, cfg["kant"])    # m/s, m/s^2
    gyldig = np.isfinite(v) & np.isfinite(a)

    maske = (x >= 0) & (x <= L) & gyldig
    if maske.sum() < 3:
        return afvis("for_faa_punkter_paa_straekning")

    # køretid og gennemsnitsfart på den dækkede del af strækningen (interpoleret ved x=0 og x=L)
    xs0 = max(0.0, x[0])
    xs1 = min(L, x[-1])
    # første passage af xs0 og xs1: x er (næsten) voksende, brug np.interp på den monotone envelope
    xm = np.maximum.accumulate(x)
    t_a = float(np.interp(xs0, xm, grid)) if xm[0] < xs0 else float(grid[0])
    t_b = float(np.interp(xs1, xm, grid))
    if t_b <= t_a:
        return afvis("ugyldig_koretid")
    gns_ms = (xs1 - xs0) / (t_b - t_a)
    res["daekning_m"] = xs1 - xs0
    res["koretid_s"] = L / gns_ms

    vk = v[maske] * 3.6
    ak = a[maske]
    sk = sg[maske]
    res["gns_fart_kmh"] = gns_ms * 3.6
    res["min_fart_kmh"] = float(vk.min())
    res["max_fart_kmh"] = float(vk.max())
    res["spaend_kmh"] = res["max_fart_kmh"] - res["min_fart_kmh"]
    res["std_fart_kmh"] = float(np.std(vk, ddof=int(cfg["std_ddof"]))) if len(vk) > int(cfg["std_ddof"]) else np.nan
    res["sum_abs_dfart_kmh"] = float(np.abs(np.diff(vk)).sum())
    res["max_opbremsning_ms2"] = float(np.max(-ak))
    res["max_acceleration_ms2"] = float(np.max(ak))
    minpkt = max(1, int(round(cfg["haendelse_min_s"] / dt)))
    for tt in cfg["taerskler_ms2"]:
        res[f"opbr_haendelser_{kolonnesuffix(tt)}"] = antal_forloeb(-ak > tt, minpkt)
        res[f"acc_haendelser_{kolonnesuffix(tt)}"] = antal_forloeb(ak > tt, minpkt)
    res["klasse_opbremsning"] = klasse(res["max_opbremsning_ms2"], cfg["taerskler_ms2"])
    res["klasse_acceleration"] = klasse(res["max_acceleration_ms2"], cfg["taerskler_ms2"])
    res["stillestand"] = int(vk.min() < cfg["stillestand_kmh"])
    res["min_fart_s_m"] = float(sk[int(np.argmin(vk))])
    for navn, (lo, hi) in cfg["bump_vinduer"].items():
        w = (sk >= lo) & (sk <= hi)
        if w.any():
            res[f"{navn}_min_fart_kmh"] = float(vk[w].min())
            res[f"{navn}_max_opbremsning_ms2"] = float(np.max(-ak[w]))
    res["status"] = "ok"
    return res


# ------------------------------------------------------------------ hele filen

def laes_config(sti):
    with open(sti, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    kom = dict(DEFAULTS)
    kom["bump_vinduer"] = dict(DEFAULTS["bump_vinduer"])
    user = (raw.get("komfort") or {})
    kom.update({k: v for k, v in user.items() if v is not None or k == "laengde_m"})
    pts = raw.get("points") or {}
    for key in (kom["fra"], kom["til"]):
        if key not in pts:
            raise SystemExit(f"Punkt '{key}' (komfort.fra/til) findes ikke under points: i {sti}")
    if kom["kant"] not in ("interp", "drop"):
        raise SystemExit("komfort.kant skal være 'interp' eller 'drop'")
    return kom, pts


def beregn_segmenter(df, cfg, p_fra, p_til, log=print, progress_every=2000):
    """df = segmenter.csv som DataFrame. Returnér DataFrame med én række pr. tur."""
    lat0, lon0, enhed, L_geo = linje_geometri(p_fra, p_til)
    L = float(cfg["laengde_m"]) if cfg.get("laengde_m") else L_geo
    log(f"  Strækningslængde L = {L:.1f} m (geometri {L_geo:.1f} m)")

    ping = df[df["er_stoprække"] == 0].copy()
    if len(ping) == 0:
        raise SystemExit("Ingen pings (er_stoprække = 0) i filen")
    s, d = projicer(ping["lat"].to_numpy(), ping["lon"].to_numpy(), lat0, lon0, enhed)
    ping["s"] = s
    ping["d"] = d
    marg = cfg["korridor_margin_m"]
    ind = (ping["s"] >= -marg) & (ping["s"] <= L + marg) & (ping["d"].abs() <= cfg["korridor_sideafstand_m"])
    alle_ture = df["Turreference"].drop_duplicates().to_numpy()
    ping = ping[ind]
    ping = ping.copy()
    ping["t"] = (pd.to_datetime(ping["datetime"], format="%Y-%m-%d %H:%M:%S")
                 - pd.Timestamp("1970-01-01")).dt.total_seconds()
    meta = df.drop_duplicates("Turreference").set_index("Turreference")[["Periode", "Retning", "Køredag"]]

    rows = []
    grupper = {ref: g for ref, g in ping.groupby("Turreference", sort=False)}
    log(f"  Ture i filen: {len(alle_ture)}, med pings i korridoren: {len(grupper)}")
    for i, ref in enumerate(alle_ture):
        g = grupper.get(ref)
        if g is None:
            r = {k: np.nan for k in kolonnenavne(cfg)}
            r.update(status="ufuldstændig", aarsag="ingen_pings_i_korridor", antal_pings=0)
        else:
            r = beregn_tur(g["t"].to_numpy(dtype=float), g["s"].to_numpy(), L, cfg)
        r["Turreference"] = ref
        for c in ("Periode", "Retning", "Køredag"):
            r[c] = meta.at[ref, c]
        rows.append(r)
        if progress_every and (i + 1) % progress_every == 0:
            log(f"  ... {i + 1}/{len(alle_ture)} ture")
    kol = ["Turreference", "Periode", "Retning", "Køredag"] + kolonnenavne(cfg)
    ut = pd.DataFrame(rows)[kol]
    heltal = [c for c in kol if c.startswith(("opbr_haendelser_", "acc_haendelser_"))] + ["stillestand", "antal_pings"]
    for c in heltal:                                   # heltal (tomme for ufuldstændige ture) - ikke "1.0000"
        ut[c] = ut[c].astype("Int64")
    return ut


def main(argv=None):
    ap = argparse.ArgumentParser(description="Komfortmål pr. tur ud fra segmenter.csv (analyse_v2.0.py).")
    ap.add_argument("--segments", required=True, help="segmenter.csv")
    ap.add_argument("--config", required=True, help="YAML med points: og komfort:")
    ap.add_argument("--out", required=True, help="komfort.csv (en række pr. tur)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    cfg, pts = laes_config(a.config)
    print(f"komfort_v{VERSION}: {a.segments}")
    for k, v in cfg.items():
        print(f"  {k} = {v}")
    cols = ["Turreference", "Periode", "Retning", "Køredag", "datetime", "lat", "lon", "er_stoprække"]
    df = pd.read_csv(a.segments, sep=";", encoding="utf-8", usecols=cols,
                     dtype={"Turreference": "string", "Periode": "string", "Retning": "string",
                            "Køredag": "string", "datetime": "string"})
    print(f"  Rækker indlæst: {len(df):,}")
    res = beregn_segmenter(df, cfg, pts[cfg["fra"]], pts[cfg["til"]])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(a.out, sep=";", index=False, encoding="utf-8", float_format="%.4f")
    n_ok = int((res["status"] == "ok").sum())
    print(f"  Skrev {len(res)} ture ({n_ok} ok, {len(res) - n_ok} ufuldstændige) -> {a.out}")
    print("  Årsager (ufuldstændige): " + str(res.loc[res["status"] != "ok", "aarsag"].value_counts().to_dict()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
