"""Tegner enkle tegninger (SVG) af de almindelige vejbumptyper i fast målestok.

Functionality: skriver en SVG pr. bumptype + en samlet oversigt til mappen bumptyper/.
Uses: kun Python standardbibliotek.
Dependencies: ingen. Kør: python tegn_bumpprofiler.py
Data: højdeværdier (mm) pr. 0,25 m fra tabellerne i Vejdirektoratets håndbogsbilag
"Geometrisk udformning af vejbump" (juni 2026). Pudebump (bilag 6-1) og kuppelafrundet
bump (bilag 7-1) er tegnet efter bilagets mål.
Målestok: enkelttegningerne følger Vejdirektoratets format (x-akse = bumpets længde, y-akse
0-125 mm, fast plotflade ca. 8:1, dvs. ca. 4-7 gange overhøjning afhængigt af længden).
Oversigten og kuppel-tværsnittet har fast målestok (PX_PR_M) og OVERHOEJNING gange overhøjning,
så bumpene kan sammenlignes. Pude-plantegningen er i 1:1.
Debugging points: tjek at hver profil starter og slutter i 0 og har den længde, bilaget angiver.
"""
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent / "bumptyper"
KILDE = "Efter Vejdirektoratet: Geometrisk udformning af vejbump (håndbogsbilag, juni 2026)"

PX_PR_M = 40.0          # vandret målestok i oversigt, pude og kuppel
OVERHOEJNING = 7        # lodret overhøjning i oversigt og kuppel (Vejdirektoratets bilag: ca. 6-7 gange)
PX_PR_MM = PX_PR_M / 1000 * OVERHOEJNING

FARVE_LINJE = "#1f5f8b"
FARVE_FYLD = "#c9dcea"
FARVE_TEKST = "#222222"
FARVE_SVAG = "#555555"
FARVE_GRID = "#d9d9d9"
FARVE_VEJ = "#e9e9e9"


def mirror(first_half):
    """Symmetrisk profil ud fra første halvdel inkl. toppen."""
    return first_half + first_half[-2::-1]


def steps(values, dx=0.25):
    return [(round(i * dx, 2), v) for i, v in enumerate(values)]


_rampe = [0, 4, 10, 19, 29, 41, 52, 62, 71, 79, 85, 91, 95, 98, 99, 100]
PROFILER = [
    ("cirkelbump_40", "Cirkelbump, 40 km/t",
     steps(mirror([0, 15, 28, 41, 52, 62, 71, 79, 85, 91, 95, 98, 99, 100])),
     "Bilag 1-3 · 6,5 m lang · 100 mm høj · busser og lastbiler: 25 km/t"),
    ("modificeret_cirkelbump_40", "Modificeret cirkelbump, 40 km/t",
     steps(mirror(_rampe)),
     "Bilag 2-3 · 7,5 m lang · 100 mm høj · busser og lastbiler: 25 km/t"),
    ("modificeret_sinusbump_50", "Modificeret sinusbump, 50 km/t",
     steps(mirror([0, 2, 6, 11, 18, 26, 34, 44, 53, 61, 68, 75, 80, 85, 88, 91, 93, 95, 95, 95])),
     "Bilag 3-1 · 9,5 m lang · 95 mm høj · busser og lastbiler: 35 km/t"),
    ("trapezbump_40", "Trapezbump, 40 km/t",
     [(0.0, 0), (1.7, 100), (5.7, 100), (7.4, 0)],
     "Bilag 4-3 · 7,4 m lang · rampe 60 ‰ · busser og lastbiler: 20 km/t"),
    ("trapezbump_mod_ramper_40", "Trapezbump med modificerede ramper, 40 km/t",
     steps(_rampe + [100] * 15 + _rampe[::-1]),
     "Bilag 5-1 · 11,5 m lang · 100 mm høj · busser og lastbiler: 25 km/t"),
    ("haevet_flade_40", "Hævet flade, eksempel",
     [(0.0, 0), (1.7, 100), (11.7, 100), (13.4, 0)],
     "Afsnit 2.9 · plan flade mindst 10 m · her ramper som trapezbump 40 km/t"),
]
XMAX = 14.0  # m; plads til den længste profil (hævet flade 13,4 m)

# Pukkelbump efter Vejdirektoratet: Katalog over typegodkendte bump (september 2002), bilag 5-1:
# rund pude, diameter 1,10 m, højde 60 mm; højde pr. 5 cm fra centrum ud til kanten (55 cm).
_pukkel_halv = [60, 57.5, 55, 52.5, 50, 47.5, 45, 36, 27, 18, 9, 0]
PUKKEL = [(round(i * 0.05, 2), v) for i, v in enumerate(_pukkel_halv[::-1] + _pukkel_halv[1:])]
KILDE_2002 = "Efter Vejdirektoratet: Katalog over typegodkendte bump (september 2002), bilag 5-1"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_start(w, h):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'font-family="Segoe UI, Arial, sans-serif">\n<rect width="{w}" height="{h}" fill="#ffffff"/>\n')


def tekst(x, y, s, size=11, anchor="start", fill=FARVE_TEKST, weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" '
            f'font-weight="{weight}">{esc(s)}</text>\n')


def profil_tegning(pts, x0, base, px_pr_mm, fyld=True, bredde=2.2, farve=FARVE_LINJE):
    p = " ".join(f"{x0 + x * PX_PR_M:.1f},{base - y * px_pr_mm:.1f}" for x, y in pts)
    s = ""
    if fyld:
        s += (f'<polygon points="{x0 + pts[0][0] * PX_PR_M:.1f},{base:.1f} {p} '
              f'{x0 + pts[-1][0] * PX_PR_M:.1f},{base:.1f}" fill="{FARVE_FYLD}"/>\n')
    s += f'<polyline points="{p}" fill="none" stroke="{farve}" stroke-width="{bredde}" stroke-linejoin="round"/>\n'
    return s


def meterakse(x0, y, xmax, step=2):
    s = f'<line x1="{x0}" y1="{y}" x2="{x0 + xmax * PX_PR_M:.1f}" y2="{y}" stroke="{FARVE_TEKST}" stroke-width="1.2"/>\n'
    for m in range(0, int(xmax) + 1, step):
        x = x0 + m * PX_PR_M
        s += f'<line x1="{x:.1f}" y1="{y}" x2="{x:.1f}" y2="{y + 4}" stroke="{FARVE_TEKST}"/>\n'
        s += tekst(x, y + 15, str(m), 10, "middle")
    return s


VD_PLOT_B, VD_PLOT_H = 700, 86   # plotflade som i Vejdirektoratets bilag (ca. 8:1), y-akse 0-125 mm


def profil_svg(titel, pts, undertekst, xlabel="Længde (m)", note=None, kilde_tillaeg="", tick=0.25, kilde=None):
    """Enkelt bump i Vejdirektoratets format: x-aksen spænder over bumpets længde,
    y-aksen 0-125 mm, fast plotflade. Overhøjningen afhænger derfor af længden."""
    ml, top = 74, 74 + (16 if note else 0)
    laengde = pts[-1][0]
    pxm = VD_PLOT_B / laengde
    pxmm = VD_PLOT_H / 125
    overh = pxmm * 1000 / pxm
    base = top + VD_PLOT_H
    w = int(ml + VD_PLOT_B + 24)
    h = int(base + 66)
    s = svg_start(w, h)
    s += tekst(ml - 60, 20, titel, 15, weight="600")
    s += tekst(ml - 60, 37, undertekst, 11)
    skala = (f"højden er overdrevet ca. {overh:.0f} gange" if overh >= 1.5
             else "bumpet er så kort, at tegningen er i næsten rigtige proportioner")
    s += tekst(ml - 60, 54, f"Samme format som Vejdirektoratets bilag: {skala}", 9, fill=FARVE_SVAG)
    if note:
        s += tekst(ml - 60, 70, note, 9, fill=FARVE_SVAG)
    s += f'<rect x="{ml}" y="{top}" width="{VD_PLOT_B}" height="{VD_PLOT_H}" fill="{FARVE_VEJ}"/>\n'
    for mm in (0, 25, 50, 75, 100, 125):
        y = base - mm * pxmm
        s += f'<line x1="{ml - 4}" y1="{y:.1f}" x2="{ml}" y2="{y:.1f}" stroke="{FARVE_TEKST}"/>\n'
        s += tekst(ml - 7, y + 3, str(mm), 9, "end")
    p = " ".join(f"{ml + x * pxm:.1f},{base - y * pxmm:.1f}" for x, y in pts)
    s += f'<polygon points="{ml:.1f},{base:.1f} {p} {ml + laengde * pxm:.1f},{base:.1f}" fill="{FARVE_FYLD}"/>\n'
    s += f'<polyline points="{p}" fill="none" stroke="{FARVE_LINJE}" stroke-width="2.2" stroke-linejoin="round"/>\n'
    s += f'<line x1="{ml}" y1="{top}" x2="{ml}" y2="{base}" stroke="{FARVE_TEKST}"/>\n'
    s += f'<line x1="{ml}" y1="{base}" x2="{ml + VD_PLOT_B}" y2="{base}" stroke="{FARVE_TEKST}"/>\n'
    n = int(round(laengde / tick))
    dec = 1 if tick >= 0.1 else 2
    for i in range(n + 1):
        x = ml + i * tick * pxm
        s += f'<line x1="{x:.1f}" y1="{base}" x2="{x:.1f}" y2="{base + (5 if i % 2 == 0 else 3)}" stroke="{FARVE_TEKST}"/>\n'
        if i % 2 == 0 or i == n:
            s += tekst(x, base + 16, f"{i * tick:.{dec}f}".replace(".", ","), 9, "middle")
    s += tekst(ml + VD_PLOT_B / 2, base + 32, xlabel, 10, "middle", weight="600")
    s += (f'<text x="{ml - 40}" y="{top + VD_PLOT_H / 2:.1f}" font-size="10" font-weight="600" fill="{FARVE_TEKST}" '
          f'text-anchor="middle" transform="rotate(-90 {ml - 40} {top + VD_PLOT_H / 2:.1f})">Højde (mm)</text>\n')
    s += tekst(ml - 60, h - 6, (kilde or KILDE) + kilde_tillaeg + ". Egen tegning.", 9, fill=FARVE_SVAG)
    return s + "</svg>\n"


def pukkel_tvaersnit_svg():
    return profil_svg(
        "Pukkelbump (tværsnit af én kuppel)", PUKKEL,
        "Katalog 2002 og 2013, bilag 5-1 · ønsket hastighed 50 km/t · Ø 1,10 m · 60 mm · dæmper biler, ikke busser",
        xlabel="Tværs over puden (m)", tick=0.05,
        note="Typen står ikke i BEK 228/2026 eller håndbogsbilaget fra 2026; kataloget fra 2002 er afløst. Se kilder/README.md om reglerne i dag.",
        kilde=KILDE_2002)


def pukkel_plan_svg():
    """Plantegning i 1:1 efter katalog 2002, bilag 5-1, kørebane 6,20 m: puder med diameter a=1,10 m,
    b=0,25 m mellem rækkerne, c=1,80 m pudezone pr. spor, d=1,00 m ved midten, e=0,80 m til kantsten.
    Række 1 og 3 ligger mod midten, række 2 mod kantstenen."""
    ml, top = 56, 64
    vej_l, vej_b = 14.0, 6.2
    a, b, c, d = 1.10, 0.25, 1.80, 1.00
    w = int(ml + vej_l * PX_PR_M + 24)
    h = int(top + vej_b * PX_PR_M + 60)
    s = svg_start(w, h)
    s += tekst(ml, 20, "Pukkelbump (set ovenfra)", 15, weight="600")
    s += tekst(ml, 37, "Katalog 2002 og 2013, bilag 5-1 · 6 kupler, tre forskudt i hvert spor · mindst 25 m fra vejkryds", 11)
    X = lambda m: ml + m * PX_PR_M
    Y = lambda m: top + m * PX_PR_M
    s += f'<rect x="{X(0)}" y="{Y(0)}" width="{vej_l * PX_PR_M}" height="{vej_b * PX_PR_M}" fill="{FARVE_VEJ}"/>\n'
    for yy in (0, vej_b):
        s += f'<line x1="{X(0)}" y1="{Y(yy)}" x2="{X(vej_l)}" y2="{Y(yy)}" stroke="{FARVE_TEKST}" stroke-width="2"/>\n'
    s += f'<line x1="{X(0)}" y1="{Y(vej_b / 2)}" x2="{X(vej_l)}" y2="{Y(vej_b / 2)}" stroke="#ffffff" stroke-width="2" stroke-dasharray="12 10"/>\n'
    midt = vej_b / 2
    x_start = (vej_l - (3 * a + 2 * b)) / 2 + a / 2
    for spor in (-1, 1):                      # -1 = øverste spor, 1 = nederste
        naer = midt + spor * (d / 2 + a / 2)
        fjern = midt + spor * (d / 2 + c - a / 2)
        for r, yy in enumerate((naer, fjern, naer)):
            cx = x_start + r * (a + b)
            s += (f'<circle cx="{X(cx):.1f}" cy="{Y(yy):.1f}" r="{a / 2 * PX_PR_M:.1f}" '
                  f'fill="{FARVE_FYLD}" stroke="{FARVE_LINJE}" stroke-width="1.5"/>\n')
    s += tekst(X(0.2), Y(midt) - 6, "kørselsretning →", 10)
    s += tekst(X(0.2), Y(vej_b) - 6, "kørebane 6,20 m", 10)
    s += meterakse(ml, Y(vej_b) + 8, vej_l, 1)
    s += tekst(ml, h - 18, "Rigtige proportioner. Steler ved kantsten valgfri (eftergivelige, min. 30 cm fra asfaltkant).", 9, fill=FARVE_SVAG)
    s += tekst(ml, h - 6, "Efter Vejdirektoratet: Katalog over typegodkendte bump (2002 og 2013), bilag 5-1. Egen tegning.", 9, fill=FARVE_SVAG)
    return s + "</svg>\n"


def oversigt_raekker():
    """Rækker i oversigten: de seks længdeprofiler + pude- og kuppelbump, som i længderetningen
    har samme profil som hhv. cirkelbump 40 og modificeret cirkelbump 40 (bilag 6-1 og 7-1)."""
    p = {navn: (titel, pts) for navn, titel, pts, _ in PROFILER}
    r = [(p[n][0], p[n][1], "") for n in ("cirkelbump_40", "modificeret_cirkelbump_40", "modificeret_sinusbump_50",
                                         "trapezbump_40", "trapezbump_mod_ramper_40")]
    r.append(("Pudebump, 40 km/t", p["cirkelbump_40"][1],
              "samme længdeprofil som cirkelbump 40 km/t; puden er smallere end bussen"))
    r.append(("Kuppelafrundet vejbump, 40 km/t", p["modificeret_cirkelbump_40"][1],
              "samme længdeprofil som modificeret cirkelbump 40 km/t; afrundet på tværs"))
    r.append((p["haevet_flade_40"][0], p["haevet_flade_40"][1], ""))
    r.append(("Pukkelbump (katalog 2002/2013: 50 km/t)", PUKKEL,
              "én kuppel, Ø 1,10 m, 60 mm; tre pr. spor; dæmper biler, ikke busser; ikke i reglerne fra 2026"))
    return r


def samlet_svg():
    ml = 56
    w = int(ml + XMAX * PX_PR_M + 24)
    rk = 125 * PX_PR_MM + 26        # rækkehøjde
    top = 56
    raekker = oversigt_raekker()
    h = int(top + rk * len(raekker) + 40)
    s = svg_start(w, h)
    s += tekst(ml, 22, "Længdeprofiler for almindelige vejbump", 15, weight="600")
    s += tekst(ml, 39, f"Samme målestok i alle rækker · højden er overdrevet {OVERHOEJNING} gange", 11)
    for i, (titel, pts, note) in enumerate(raekker):
        base = top + rk * (i + 1) - 10
        y_t = base - 100 * PX_PR_MM - 6
        s += (f'<text x="{ml}" y="{y_t:.1f}" font-size="11" fill="{FARVE_TEKST}"><tspan font-weight="600">{esc(titel)}</tspan>'
              + (f'<tspan fill="{FARVE_SVAG}" font-size="10">  ({esc(note)})</tspan>' if note else "") + "</text>\n")
        s += profil_tegning(pts, ml, base, PX_PR_MM, bredde=2)
        s += f'<line x1="{ml}" y1="{base:.1f}" x2="{ml + XMAX * PX_PR_M:.1f}" y2="{base:.1f}" stroke="{FARVE_TEKST}"/>\n'
    s += meterakse(ml, top + rk * len(raekker) - 10, XMAX)
    s += tekst(ml, h - 6, KILDE + "; pukkelbump: Katalog over typegodkendte bump (2002). Egen tegning.", 9, fill=FARVE_SVAG)
    return s + "</svg>\n"


def pudebump_svg():
    """Plantegning i 1:1 efter bilag 6-1: kørebane 6,0 m, to puder 6,5 x 1,9 m
    (pude: 0,30 m skrå kant + 1,30 m top + 0,30 m skrå kant), 1,10 m mellem puderne."""
    ml, top = 56, 64
    vej_l, vej_b = 14.0, 6.0
    w = int(ml + vej_l * PX_PR_M + 24)
    h = int(top + vej_b * PX_PR_M + 60)
    s = svg_start(w, h)
    s += tekst(ml, 20, "Pudebump, 40 km/t (set ovenfra)", 15, weight="600")
    s += tekst(ml, 37, "Bilag 6-1 · to puder på 6,5 × 1,9 m på en 6,0 m bred kørebane · busser og lastbiler: 40 km/t", 11)
    X = lambda m: ml + m * PX_PR_M
    Y = lambda m: top + m * PX_PR_M
    s += f'<rect x="{X(0)}" y="{Y(0)}" width="{vej_l * PX_PR_M}" height="{vej_b * PX_PR_M}" fill="{FARVE_VEJ}"/>\n'
    s += f'<line x1="{X(0)}" y1="{Y(0)}" x2="{X(vej_l)}" y2="{Y(0)}" stroke="{FARVE_TEKST}" stroke-width="2"/>\n'
    s += f'<line x1="{X(0)}" y1="{Y(vej_b)}" x2="{X(vej_l)}" y2="{Y(vej_b)}" stroke="{FARVE_TEKST}" stroke-width="2"/>\n'
    s += f'<line x1="{X(0)}" y1="{Y(3)}" x2="{X(vej_l)}" y2="{Y(3)}" stroke="#ffffff" stroke-width="2" stroke-dasharray="12 10"/>\n'
    x0 = (vej_l - 6.5) / 2
    for y0 in (0.55, 3.55):   # 1,90 m pude, 1,10 m imellem, rest fordelt til kanterne
        s += f'<rect x="{X(x0):.1f}" y="{Y(y0):.1f}" width="{6.5 * PX_PR_M}" height="{1.9 * PX_PR_M}" fill="{FARVE_FYLD}" stroke="{FARVE_LINJE}" stroke-width="1.5"/>\n'
        s += f'<rect x="{X(x0):.1f}" y="{Y(y0 + 0.3):.1f}" width="{6.5 * PX_PR_M}" height="{1.3 * PX_PR_M}" fill="#a9c6dd" stroke="none"/>\n'
    s += tekst(X(x0 + 3.25), Y(0.55) - 4, "6,5 m", 10, "middle")
    s += tekst(X(x0 + 6.5) + 6, Y(0.55 + 0.95) + 3, "1,9 m (top 1,3 m + skrå kanter 0,3 m)", 10)
    s += tekst(X(0.2), Y(3) - 6, "kørselsretning →", 10)
    s += tekst(X(0.2), Y(vej_b) - 6, "kørebane 6,0 m", 10)
    s += meterakse(ml, Y(vej_b) + 8, vej_l)
    s += tekst(ml, h - 18, "Tegnet i rigtige proportioner. Puden er smallere end en bus' sporvidde; busser kan køre med hjulene på hver side.", 9, fill=FARVE_SVAG)
    s += tekst(ml, h - 6, KILDE + ", bilag 6-1. Egen tegning.", 9, fill=FARVE_SVAG)
    return s + "</svg>\n"


def kuppel_svg():
    """Tværsnit efter bilag 7-1 i Vejdirektoratets format: kørebane 6,0 m, 0,30 m fri til
    vejafvanding ved hver kant, kuppelafrunding 1,0-1,5 m i hver side (her 1,25 m).
    Bilaget angiver kun afrundingens bredde, ikke dens form; her en blød kurve (antaget)."""
    vej_b, afv, afr = 6.0, 0.3, 1.25
    pts = [(0.0, 0.0)]
    n = 216
    for i in range(n + 1):
        t = afv + (vej_b - 2 * afv) * i / n
        if t < afv + afr:
            y = 100 * math.sin(math.pi / 2 * (t - afv) / afr)
        elif t > vej_b - afv - afr:
            y = 100 * math.sin(math.pi / 2 * (vej_b - afv - t) / afr)
        else:
            y = 100.0
        pts.append((t, y))
    pts.append((vej_b, 0.0))
    return profil_svg(
        "Kuppelafrundet vejbump, 40 km/t (tværsnit)", pts,
        "Bilag 7-1 · kørebane 6,0 m · 0,3 m fri til vejafvanding · afrunding 1,0-1,5 m (her 1,25 m) · busser: 25 km/t",
        xlabel="Bredde på tværs af vejen (m)",
        note="Bilaget angiver kun afrundingens bredde, ikke dens form: kurven i siderne er antaget. Længdeprofil som modificeret cirkelbump 40 km/t.",
        kilde_tillaeg=", bilag 7-1")


def main():
    OUT.mkdir(exist_ok=True)
    for f in OUT.glob("*_princip.*"):
        f.unlink()  # gamle principskitser er erstattet af målfaste tegninger
    for navn, titel, pts, under in PROFILER:
        assert pts[0][1] == 0 and pts[-1][1] == 0, navn
        (OUT / f"{navn}.svg").write_text(profil_svg(titel, pts, under), encoding="utf-8")
        print(f"{navn}: {pts[-1][0]} m")
    (OUT / "pudebump_40.svg").write_text(pudebump_svg(), encoding="utf-8")
    (OUT / "kuppelafrundet_40.svg").write_text(kuppel_svg(), encoding="utf-8")
    (OUT / "pukkelbump_50_tvaersnit.svg").write_text(pukkel_tvaersnit_svg(), encoding="utf-8")
    (OUT / "pukkelbump_50_plan.svg").write_text(pukkel_plan_svg(), encoding="utf-8")
    (OUT / "oversigt_laengdeprofiler.svg").write_text(samlet_svg(), encoding="utf-8")
    # PNG-udgaverne i mappen er lavet ved at åbne SVG'erne i en browser (playwright) og tage et billede.


if __name__ == "__main__":
    main()
