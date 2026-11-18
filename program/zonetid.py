#!/usr/bin/env python3
"""
zonetid.py (v1.1) - hvor på strækningen sidder den ekstra køretid? Fordeling på elementer (bump, indsnævringer, andet)
og den øvrige strækning, med et interval pr. element. Uden periode B (kun A) giver det tid pr. zone som niveau.

Input:  output-mapperne fra analyse_v2.1.py (+ komfort_v1.1.py) for periode A (før) og, hvis der er en sammenligning, B (efter):
        <mappe>/result.csv, <mappe>/komfort.csv (eller komfort_<id>.csv ved flere strækninger) og <mappe>/segmenter.csv
        (kør analysen med --export-segments).
Config: samme YAML som resten af værktøjet. Bruger points + strækninger (eller den gamle `komfort: fra/til`) og sektionerne
        elementer: (pr. strækning, eller øverst ved én strækning), udvalg: og zonetid: (se eksempler/config_kvaglundvej.yaml).
Output: zonetid.json (maskinlæsbar, bruges af rapport/lav_rapportdata.py) og zonetid.md (til at læse).

    python zonetid.py --config min_config.yaml --a ud_A --b ud_B --out ud       (før og efter)
    python zonetid.py --config min_config.yaml --a ud_A --out ud                (kun én periode: niveauer)

Metode (kort):
 1. Strækningen er den rette linje fra strækningens fra-punkt til til-punkt (længde L). Hvert element projiceres på
    linjen (position s i meter fra start).
 2. Zoner: element +/- zonebredde (standard 60 m). Overlap mellem to zoner deles på midten. Det, der er tilbage,
    er 'øvrig strækning' (en eller flere stykker).
 3. Pr. tur måles tiden i hver zone: tidspunktet for passage af zonens slutgrænse minus startgrænse. Positionen
    er interpoleret lineært til et 1 s-gitter og gjort monoton i kørselsretningen. Kun ture med fuld passage
    og uden huller over komfort.max_hul_s.
 4. Udvalg (samme som rapporten): tom Log, ingen stoprække-match i Flag, komfort status ok, og dagtype
    (standard hverdage, uden helligdage fra config).
 5. Gennemsnit pr. zone og periode. Ekstra tid pr. element (efter - før) er den øvre grænse. Nedre grænse er
    efter - før x f, hvor f = efter/før-forholdet på øvrig strækning (generelt lavere fart). For 'øvrig strækning'
    er nedre grænse den rå ekstra tid dér, og øvre grænse den plus den generelle del inde i element-zonerne.
    Intervallerne kan ikke lægges sammen.
 6. Grupper: 'uden stop' (komfort stillestand = 0) og 'alle ture', for retning 1, 2 og begge.
 7. Flere strækninger: hver strækning regnes for sig, med sine egne elementer. En strækning uden elementer springes over.

Afhængigheder: pandas, numpy, pyyaml, komfort_v1.1.py og komfort_v1.0.py (samme mappe). Sæt PYTHONUTF8=1 på Windows.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml  # noqa: F401  (config læses via komfort_v1.1)

VERSION = "1.1"
HERE = Path(__file__).resolve().parent

DEFAULT_ZONETID = {"zonebredde_m": 60.0, "foelsomhed_zonebredde_m": [40.0]}
DEFAULT_UDVALG = {"dagtype": "hverdage", "helligdage": []}
TYPE_ALIAS = {"bump": "bump", "indsnævring": "indsnaevring", "indsnaevring": "indsnaevring", "andet": "andet"}
OVRIG = "øvrig strækning"


def _load_k11():
    spec = importlib.util.spec_from_file_location("komfort_v1_1", HERE / "komfort_v1.1.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


K11 = _load_k11()
K = K11.K10          # komfort_v1.0: geometri og udglatning


# ------------------------------------------------------------------ config

def norm_type(t):
    return TYPE_ALIAS.get(str(t or "andet").strip().lower(), "andet")


def _elementer(liste, hvor):
    els = []
    for i, e in enumerate(liste or []):
        for k in ("navn", "lat", "lon"):
            if e.get(k) is None:
                raise SystemExit(f"{hvor}[{i}] mangler '{k}' (elementer: navn, type, lat, lon)")
        els.append({"navn": str(e["navn"]), "type": norm_type(e.get("type")), "lat": float(e["lat"]), "lon": float(e["lon"])})
    navne = [e["navn"] for e in els]
    if len(set(navne)) != len(navne):
        raise SystemExit(f"Elementnavne i {hvor} skal være unikke")
    return els


def laes_config(sti):
    """Returnér dict: straekninger (liste; hver med id, navn, komfort, elementer), points, udvalg, zonetid, raw."""
    liste, pts, raw = K11.laes_straekninger(sti)
    for s in liste:
        s["elementer"] = _elementer(s["elementer"], f"elementer (strækning '{s['id']}')")
    if not any(s["elementer"] for s in liste):
        raise SystemExit(f"Sektionen 'elementer:' mangler eller er tom i {sti} (mindst ét element: navn, type, lat, lon; "
                         f"ved flere strækninger lægges elementerne under hver strækning)")
    udv = dict(DEFAULT_UDVALG)
    udv.update({k: v for k, v in (raw.get("udvalg") or {}).items() if v is not None})
    udv["helligdage"] = {str(x) for x in (udv.get("helligdage") or [])}
    if udv["dagtype"] not in ("hverdage", "alle"):
        raise SystemExit("udvalg.dagtype skal være 'hverdage' eller 'alle'")
    zt = dict(DEFAULT_ZONETID)
    zt.update({k: v for k, v in (raw.get("zonetid") or {}).items() if v is not None})
    zt["zonebredde_m"] = float(zt["zonebredde_m"])
    zt["foelsomhed_zonebredde_m"] = [float(x) for x in (zt.get("foelsomhed_zonebredde_m") or [])]
    return {"straekninger": liste, "points": pts, "udvalg": udv, "zonetid": zt, "raw": raw}


# ------------------------------------------------------------------ udvalg af ture

def laes_periode(mappe, straekninger):
    """Læs result.csv og komfort-filer fra en output-mappe. Returnér (result_df, {strækning-id: komfort_df})."""
    mappe = Path(mappe)
    n = len(straekninger)
    stier = {"result.csv": mappe / "result.csv", "segmenter.csv": mappe / "segmenter.csv"}
    for s in straekninger:
        stier[f"komfort ({s['id']})"] = K11.komfort_sti(mappe, s["id"], n)
    for navn, sti in stier.items():
        if not sti.exists():
            raise SystemExit(f"Filen findes ikke: {sti} (kør analyse_v2.1.py med --export-segments og komfort_v1.1.py først)")
    r = pd.read_csv(mappe / "result.csv", sep=";", encoding="utf-8", dtype={"Turreference": str})
    ks = {s["id"]: pd.read_csv(K11.komfort_sti(mappe, s["id"], n), sep=";", encoding="utf-8", dtype={"Turreference": str})
          for s in straekninger}
    return r, ks


def komfort_for(k, sid):
    """k er en komfort-tabel (én strækning) eller et dict {id: tabel}."""
    return k[sid] if isinstance(k, dict) else k


def gyldig_maske(r):
    """Gyldige ture: tom Log, ingen stoprække-match i Flag, komfort status ok. Kræver kolonnen 'status' (fra komfort)."""
    return (r["Log"].fillna("") == "") & ~r["Flag"].fillna("").str.contains("stoprække_") & (r["status"] == "ok")


def dagtype_maske(r, udvalg):
    if udvalg["dagtype"] == "alle":
        return pd.Series(True, index=r.index)
    d = pd.to_datetime(r["Køredag"])
    return (d.dt.dayofweek < 5) & ~r["Køredag"].isin(udvalg["helligdage"])


# ------------------------------------------------------------------ zoner og tid i zone

def tur_zonetider(t, s, L, Z, cfg):
    """Tider i zoner for én tur (dict zone -> sekunder, plus 'total'), eller None hvis ikke fuld passage."""
    o = np.argsort(t, kind="stable")
    t, s = t[o], s[o]
    keep = np.concatenate(([True], np.diff(t) > 0))
    t, s = t[keep], s[keep]
    if len(t) < 3 or np.max(np.diff(t)) > cfg["max_hul_s"]:
        return None
    m = cfg["fuld_passage_margin_m"]
    fremad = s[0] <= m and s[-1] >= L - m
    baglaens = s[0] >= L - m and s[-1] <= m
    if not (fremad or baglaens):
        return None
    grid = np.arange(t[0], t[-1] + 1e-9, 1.0)
    pos = np.interp(grid, t, s)
    x = pos if fremad else L - pos                      # kørselsretning
    xm = np.maximum.accumulate(x)
    # unik, voksende envelope til interpolation (første tidspunkt for hver position)
    xu, idx = np.unique(xm, return_index=True)
    tg = grid[idx]

    def tid_ved(xx):
        xx = min(max(xx, xu[0]), xu[-1])
        return float(np.interp(xx, xu, tg))
    res = {}
    for navn, (a, b) in Z.items():
        xa, xb = (a, b) if fremad else (L - b, L - a)    # zonegrænser i kørselsretning
        res[navn] = tid_ved(xb) - tid_ved(xa)
    res["total"] = tid_ved(L) - tid_ved(0.0)
    return res


def lav_zoner(pos, w, L):
    """Zoner (dict navn -> (fra_m, til_m)) for elementer med position pos (dict navn -> s) og zonebredde w."""
    cuts = [(n, max(0.0, s0 - w), min(L, s0 + w)) for n, s0 in pos.items()]
    cuts.sort(key=lambda c: c[1])
    for i in range(len(cuts) - 1):                       # overlap deles på midten
        if cuts[i][2] > cuts[i + 1][1]:
            mid = (cuts[i][2] + cuts[i + 1][1]) / 2
            cuts[i] = (cuts[i][0], cuts[i][1], mid)
            cuts[i + 1] = (cuts[i + 1][0], mid, cuts[i + 1][2])
    Z, prev, k = {}, 0.0, 0
    for n, a, b in cuts:
        if a > prev + 1e-6:
            Z[f"øvrig {k}"] = (prev, a)
            k += 1
        Z[n] = (a, b)
        prev = b
    if prev < L - 1e-6:
        Z[f"øvrig {k}"] = (prev, L)
    return Z


def _fmt_pm(x):
    return f"{x:+.1f}"


def beregn_straekning(s, cfg, perioder, log=print):
    """Zonetid for én strækning. Returnér (resultat-dict, md-linjer). perioder: {'A': (result, komfort, seg), ['B': ...]}."""
    pts = cfg["points"]
    kom = s["komfort"]
    lat0, lon0, enhed, L = K.linje_geometri(pts[kom["fra"]], pts[kom["til"]])
    if kom.get("laengde_m"):
        L = float(kom["laengde_m"])
    elementer = s["elementer"]
    pos, sideaf = {}, {}
    for e in elementer:
        sx, sd = K.projicer([e["lat"]], [e["lon"]], lat0, lon0, enhed)
        pos[e["navn"]] = float(sx[0])
        sideaf[e["navn"]] = float(abs(sd[0]))
        if not (0.0 <= pos[e["navn"]] <= L):
            raise SystemExit(f"Element '{e['navn']}' ligger uden for strækningen '{s['navn']}' (position {pos[e['navn']]:.0f} m, "
                             f"strækningen er 0-{L:.0f} m). Tjek lat/lon og strækningens fra/til.")
        if sideaf[e["navn"]] > kom["korridor_sideafstand_m"]:
            log(f"  ADVARSEL: element '{e['navn']}' ligger {sideaf[e['navn']]:.0f} m fra linjen "
                f"(korridor {kom['korridor_sideafstand_m']:.0f} m)")
    udv, zt = cfg["udvalg"], cfg["zonetid"]
    bredder = [zt["zonebredde_m"]] + [w for w in zt["foelsomhed_zonebredde_m"] if w != zt["zonebredde_m"]]
    navn_fra = pts[kom["fra"]].get("name", kom["fra"])
    tosidet = "B" in perioder
    res_all = {"positioner_m": {n: round(v, 1) for n, v in pos.items()}, "sideafstand_m": sideaf, "L": L,
               "hoved_zonebredde_m": zt["zonebredde_m"], "elementer": [e["navn"] for e in elementer],
               "dagtype": udv["dagtype"], "perioder": list(perioder)}
    md = []
    if tosidet:
        md += ["Interval pr. element: nedre = efter − før × f (f = efter/før-forhold på øvrig strækning), øvre = efter − før."]
    else:
        md += ["Kun én periode: gennemsnitlig tid (s) i hver zone. Ingen sammenligning, så intet interval."]
    md += [f"Positioner (m fra {navn_fra}): " + ", ".join(f"{n} {v:.0f}" for n, v in pos.items()),
           f"Udvalg: dagtype {udv['dagtype']}, tom Log, ingen stoprække-match, komfort status ok. Middel pr. tur.", ""]

    data = {}
    for p, (r, kf, seg) in perioder.items():
        kd = komfort_for(kf, s["id"])
        r = r.merge(kd[["Turreference", "status", "stillestand"]], on="Turreference")
        ok = gyldig_maske(r) & dagtype_maske(r, udv)
        meta = r[ok].set_index("Turreference")[["Retning", "Køredag", "stillestand"]]
        sg = seg[(seg["er_stoprække"] == 0) & seg["Turreference"].isin(meta.index)]
        sx, sd = K.projicer(sg["lat"].to_numpy(), sg["lon"].to_numpy(), lat0, lon0, enhed)
        sg = sg.assign(s=sx, d=sd)
        sg = sg[(sg["s"] >= -kom["korridor_margin_m"]) & (sg["s"] <= L + kom["korridor_margin_m"])
                & (sg["d"].abs() <= kom["korridor_sideafstand_m"])].copy()
        sg["t"] = (pd.to_datetime(sg["datetime"]) - pd.Timestamp("1970-01-01")).dt.total_seconds()
        data[p] = (meta, sg)
        log(f"  strækning {s['id']}, periode {p}: {len(meta)} ture i udvalget, {sg['Turreference'].nunique()} med pings i korridoren")

    for w in bredder:
        Z = lav_zoner(pos, w, L)
        rows = []
        for p, (meta, sg) in data.items():
            for ref, g in sg.groupby("Turreference", sort=False):
                z = tur_zonetider(g["t"].to_numpy(float), g["s"].to_numpy(float), L, Z, kom)
                if z is None:
                    continue
                mt = meta.loc[ref]
                rows.append(dict(periode=p, Retning=int(mt["Retning"]), Køredag=mt["Køredag"],
                                 stillestand=int(mt["stillestand"]), **z))
        df = pd.DataFrame(rows)
        ovr = [z for z in Z if z.startswith("øvrig")]
        md += [f"### Zoner ±{w:g} m: " + ", ".join(f"{n} {a:.0f}–{b:.0f}" for n, (a, b) in Z.items()), ""]
        if df.empty:
            md += ["(ingen ture med fuld passage i udvalget)", ""]
            continue
        for grp, gm in (("uden stop", df["stillestand"] == 0), ("alle ture", df["stillestand"] >= 0)):
            for ret in (0, 1, 2):
                sub = df[gm & ((df["Retning"] == ret) if ret else True)]
                sa = sub[sub["periode"] == "A"]
                if sa.empty:
                    continue
                key = f"w{w:g}|{grp}|{ret or 'begge'}"
                A = sa[list(Z) + ["total"]].mean()
                if not tosidet:
                    res_all[key] = dict(nA=int(len(sa)), zoner={n: [round(a, 1), round(b, 1)] for n, (a, b) in Z.items()},
                                        A={z: round(A[z], 2) for z in list(Z) + ["total"]})
                    if ret == 0 or (w == zt["zonebredde_m"] and grp == "uden stop"):
                        md += [f"#### {grp} · retning {ret or 'begge'} (n {len(sa)}) · tid i alt {A['total']:.1f} s", "",
                               "| Zone | gennemsnitlig tid (s) |", "|---|---|"]
                        for n in Z:
                            md.append(f"| {n} | {A[n]:.1f} |")
                        md.append("")
                    continue
                sb = sub[sub["periode"] == "B"]
                if sb.empty:
                    continue
                B = sb[list(Z) + ["total"]].mean()
                a_ovr = float(A[ovr].sum()) if ovr else 0.0
                f = float(B[ovr].sum() / a_ovr) if ovr and a_ovr > 1e-9 else 1.0
                tab = {}
                for n in pos:
                    tab[n] = (round(B[n] - A[n] * f, 2), round(B[n] - A[n], 2))
                ov_raw = float((B[ovr] - A[ovr]).sum()) if ovr else 0.0
                # øvrig strækning: nedre = rå ekstra tid dér; øvre = rå + den generelle del inde i element-zonerne
                gen_i_elem = float(sum(A[n] * (f - 1) for n in pos))
                tab[OVRIG] = (round(ov_raw, 2), round(ov_raw + gen_i_elem, 2))
                tot = float(B["total"] - A["total"])
                res_all[key] = dict(nA=int(len(sa)), nB=int(len(sb)), faktor=round(f, 4), total=round(tot, 2),
                                    interval=tab, zoner={n: [round(a, 1), round(b, 1)] for n, (a, b) in Z.items()},
                                    A={z: round(A[z], 2) for z in list(Z) + ["total"]},
                                    B={z: round(B[z], 2) for z in list(Z) + ["total"]})
                if ret == 0 or (w == zt["zonebredde_m"] and grp == "uden stop"):
                    md += [f"#### {grp} · retning {ret or 'begge'} (n {len(sa)}/{len(sb)}) · "
                           f"øvrig strækning efter/før = {f:.3f} · ekstra i alt {tot:+.1f} s", "",
                           "| Element | ekstra tid (s), interval |", "|---|---|"]
                    for n, (lo, hi) in tab.items():
                        md.append(f"| {n} | {_fmt_pm(min(lo, hi))} til {_fmt_pm(max(lo, hi))} |")
                    md.append("")
    return res_all, md


def beregn(cfg, perioder, log=print):
    """
    cfg = laes_config(...). perioder = {'A': (result_df, komfort, segment_df)[, 'B': (...)]}; komfort er en tabel (én
    strækning) eller {strækning-id: tabel}. segment_df har kolonnerne Turreference, datetime, lat, lon, er_stoprække.
    Returnér (res_all, md-linjer). res_all = {version, perioder, straekninger: {id: resultat}}.
    """
    res_all = {"version": VERSION, "perioder": list(perioder), "straekninger": {}}
    flere = len(cfg["straekninger"]) > 1
    md = ["# Ekstra køretid fordelt på elementer og øvrig strækning" if "B" in perioder else
          "# Tid fordelt på elementer og øvrig strækning (én periode)", ""]
    for s in cfg["straekninger"]:
        if flere:
            md += [f"## Strækning {s['id']}: {s['navn']}", ""]
        if not s["elementer"]:
            res_all["straekninger"][s["id"]] = {"ingen_elementer": True}
            md += ["(ingen elementer i strækningen: zonetid springes over)", ""]
            continue
        sres, smd = beregn_straekning(s, cfg, perioder, log)
        res_all["straekninger"][s["id"]] = sres
        md += smd
    return res_all, md


def resultat_for(res, sid=None):
    """Hjælper: resultatet for én strækning (standard: den første)."""
    st = res["straekninger"]
    return st[sid] if sid else next(iter(st.values()))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ekstra køretid fordelt på elementer (zonetid).")
    ap.add_argument("--config", required=True, help="YAML med points, strækninger (eller komfort), elementer, udvalg, zonetid")
    ap.add_argument("--a", required=True, help="output-mappe for periode A (før): result.csv, komfort*.csv, segmenter.csv")
    ap.add_argument("--b", default=None, help="output-mappe for periode B (efter); udelades ved kun én periode")
    ap.add_argument("--out", required=True, help="mappe til zonetid.json og zonetid.md")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cfg = laes_config(a.config)
    n_el = sum(len(s["elementer"]) for s in cfg["straekninger"])
    print(f"zonetid v{VERSION}: {len(cfg['straekninger'])} strækning(er), {n_el} elementer, zonebredde {cfg['zonetid']['zonebredde_m']:g} m, "
          f"{'før og efter' if a.b else 'én periode'}")
    perioder = {}
    for p, mappe in (("A", a.a), ("B", a.b)):
        if mappe is None:
            continue
        r, ks = laes_periode(mappe, cfg["straekninger"])
        seg = pd.read_csv(Path(mappe) / "segmenter.csv", sep=";", encoding="utf-8", dtype={"Turreference": str},
                          usecols=["Turreference", "datetime", "lat", "lon", "er_stoprække"])
        perioder[p] = (r, ks, seg)
    res, md = beregn(cfg, perioder)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "zonetid.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "zonetid.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"  Skrev {out / 'zonetid.json'} og {out / 'zonetid.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
