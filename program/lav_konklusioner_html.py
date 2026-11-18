"""Laver nationale_analysekonklusioner.html: en overskuelig visning af nationale_analysekonklusioner.md.

Functionality: læser .md-filen (den er stadig kilden, der rettes og flettes) og skriver én selvstændig
HTML-fil ved siden af den med tre faner: "Tabel" (én række pr. analyse, søgning, filtre og sortering),
"Analyser" (ét kort pr. analyse med alle felter, kortlink og tegning af bumptypen) og "Bumptyper"
(alle tegninger fra vejledning\\kilder\\bumptyper). Tegningerne er indlejret, så HTML-filen kan sendes alene.
Uses: kun Python standardbibliotek. Ingen beregning; .md-filen ændres ikke.
    python program\\lav_konklusioner_html.py                 # standard: værktøjsmappens .md -> .html
    python program\\lav_konklusioner_html.py --md <fil.md> --out <fil.html>
Debugging points: analyser findes som "### <titel>" under "## Analyser" med en tabel | Felt | Værdi |;
oversigtstabellen under "## Oversigt" kobles på titlen uden årstal i parentes. Bumptypen findes ud fra
teksten i feltet "Type bump" før første parentes (fx "Cirkelbump eller modificeret cirkelbump").
"""
import argparse
import base64
import html
import json
import re
from pathlib import Path

PROGRAM = Path(__file__).resolve().parent
ROD = PROGRAM.parent
BUMPMAPPE = ROD / "vejledning" / "kilder" / "bumptyper"

# (søgeord i "Type bump", visningsnavn, tegninger). Længste/mest specifikke først: de fjernes fra teksten,
# når de er fundet, så "modificeret cirkelbump" ikke også tæller som "cirkelbump".
BUMPTYPER = [
    ("trapezbump med modificerede ramper", "Trapezbump med modificerede ramper", ["trapezbump_mod_ramper_40"]),
    ("modificeret cirkelbump", "Modificeret cirkelbump", ["modificeret_cirkelbump_40"]),
    ("modificeret sinusbump", "Modificeret sinusbump", ["modificeret_sinusbump_50"]),
    ("cirkelbump", "Cirkelbump", ["cirkelbump_40"]),
    ("trapezbump", "Trapezbump", ["trapezbump_40"]),
    ("hævet flade", "Hævet flade", ["haevet_flade_40"]),
    ("pudebump", "Pudebump", ["pudebump_40"]),
    ("kuppelafrundet", "Kuppelafrundet bump", ["kuppelafrundet_40"]),
    ("pukkelbump", "Pukkelbump (ældre type)", ["pukkelbump_50_tvaersnit", "pukkelbump_50_plan"]),
    ("præfabrikeret", "Præfabrikeret bump", []),
]
ALLE_TEGNINGER = [("oversigt_laengdeprofiler", "Oversigt: længdeprofiler")] + [
    (f, navn) for _, navn, filer in BUMPTYPER for f in filer]

# Kolonner i tabellen: (overskrift, felt i blokken, kolonne i oversigtstabellen der foretrækkes, filter?)
KOLONNER = [
    ("By", "By", None, True),
    ("Vejtype", "Vejtype", None, True),
    ("Bumptype", None, None, True),           # udledt af "Type bump"
    ("Indsnævring", "Indsnævring", None, False),
    ("Hastighedsgrænse", "Hastighedsbegrænsning", None, False),
    ("Bustype", "Bustype", "Bustype", False),
    ("Perioder", "Perioder for data", "Periode(r)", False),
    ("Køretid", "Fund: køretid", "Køretid (median, uden standsning ved stop)", False),
    ("Komfort", "Fund: komfort (opbremsning og acceleration langs vejen)",
     "Komfort (uden standsning ved stop, andel ture)", False),
    ("Kontakt", "Kontaktperson", "Kontakt", False),
    ("Opdateret", "Opdateret", "Opdateret", False),
]


def _celler(linje):
    """| a | b | -> ['a', 'b'] (tåler \\| i en celle)."""
    s = linje.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", s)]


def _er_skillelinje(celler):
    return all(re.fullmatch(r":?-{2,}:?", c) for c in celler if c)


def laes_md(tekst):
    """Returnerer dict med senest (str), oversigt (liste af dicts) og analyser (liste af (titel, {felt: værdi}))."""
    senest, oversigt, analyser = "", [], []
    afsnit, hoved, aktuel, i_kode = None, None, None, False
    for linje in tekst.splitlines():
        if linje.strip().startswith("```"):
            i_kode = not i_kode
            continue
        if i_kode:
            continue
        m = re.match(r"\*\*Senest opdateret:\*\*\s*(.*)", linje.strip())
        if m:
            senest = m.group(1)
        if linje.startswith("## "):
            afsnit = linje[3:].strip().lower()
            hoved, aktuel = None, None
            continue
        if afsnit and afsnit.startswith("skabelon"):
            continue
        if afsnit == "analyser" and linje.startswith("### "):
            aktuel = (linje[4:].strip(), {})
            analyser.append(aktuel)
            continue
        if not linje.strip().startswith("|"):
            continue
        c = _celler(linje)
        if _er_skillelinje(c):
            continue
        if afsnit == "oversigt":
            if hoved is None:
                hoved = c
            else:
                oversigt.append(dict(zip(hoved, c)))
        elif afsnit == "analyser" and aktuel is not None and len(c) >= 2:
            if c[0] == "Felt" and c[1] == "Værdi":
                continue
            aktuel[1][c[0]] = c[1]
    return {"senest": senest, "oversigt": oversigt, "analyser": analyser}


def inline(tekst):
    """Lidt Markdown i en celle: `kode`, **fed**, [tekst](url). Alt andet escapes."""
    s = html.escape(tekst, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)

    def link(m):
        url = m.group(2).replace('"', "%22")
        # Kun http(s), anker og relative stier: filen tager imod bidrag fra andre (pull requests),
        # så javascript:, data: o.l. vises som tekst i stedet for som link.
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", url) and not re.match(r"^https?://", url, re.I):
            return m.group(0)
        ekstern = url.lower().startswith("http")
        return f'<a href="{url}"' + (' target="_blank" rel="noopener"' if ekstern else "") + f">{m.group(1)}</a>"
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)


def kort_tekst(tekst, n=90):
    """Første del af en lang værdi: før første ' (' eller '. ', højst n tegn."""
    t = re.split(r" \(|\. ", tekst, maxsplit=1)[0].strip().rstrip(".")
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def bumptyper(type_bump):
    """'Cirkelbump eller modificeret cirkelbump (ikke bekræftet; ...)' -> [(navn, [tegninger]), ...]."""
    tekst = type_bump.split("(")[0].lower()
    fundet = []
    for ord_, navn, filer in BUMPTYPER:
        pos = tekst.find(ord_)
        if pos >= 0:
            fundet.append((pos, navn, filer))
            tekst = tekst.replace(ord_, " " * len(ord_))   # samme længde, så positionerne holder
    return [(navn, filer) for _, navn, filer in sorted(fundet)]


def tegning(navn, mappe):
    """SVG (foretrækkes) eller PNG som data-URI; None hvis filen mangler."""
    for ext, mime in (("svg", "image/svg+xml"), ("png", "image/png")):
        p = Path(mappe) / f"{navn}.{ext}"
        if p.exists():
            return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")
    return None


def _uden_aar(titel):
    return re.sub(r"\s*\([^)]*\)\s*$", "", titel).strip().lower()


def byg_html(data, mappe):
    over = {_uden_aar(r.get("Vej, by", "")): r for r in data["oversigt"]}
    cache = {}

    def img(navn):
        if navn not in cache:
            cache[navn] = tegning(navn, mappe)
        return cache[navn]

    rækker, kort, filtre = [], [], {k[0]: set() for k in KOLONNER if k[3]}
    for i, (titel, felter) in enumerate(data["analyser"]):
        o = over.get(_uden_aar(titel), {})
        typer = bumptyper(felter.get("Type bump", ""))
        bumpnavne = ", ".join(n for n, _ in typer) or kort_tekst(felter.get("Type bump", "")) or "ikke oplyst"
        celler, attrs = [], {}
        for overskrift, felt, ov_kol, er_filter in KOLONNER:
            if overskrift == "Bumptype":
                vis, fuld = bumpnavne, felter.get("Type bump", "")
                vaerdier = [n for n, _ in typer] or [bumpnavne]
            else:
                fuld = felter.get(felt, "") if felt else ""
                vis = o.get(ov_kol) if ov_kol and o.get(ov_kol) else kort_tekst(fuld)
                vaerdier = [vis]
            if er_filter:
                for v in vaerdier:
                    if v:
                        filtre[overskrift].add(v)
                attrs[overskrift] = "|".join(vaerdier)
            celler.append(f'<td title="{html.escape(fuld)}">{inline(vis)}</td>')
        data_attr = " ".join(f'data-f{j}="{html.escape(attrs[k[0]])}"'
                             for j, k in enumerate(KOLONNER) if k[3])
        rækker.append(f'<tr {data_attr} data-id="a{i}"><td><a href="#a{i}" class="til-kort">{html.escape(titel)}</a></td>'
                      + "".join(celler) + "</tr>")

        billeder = []
        for navn, filer in typer:
            for f in filer:
                src = img(f)
                if src:
                    billeder.append(f'<figure><img src="{src}" alt="{html.escape(navn)}"><figcaption>{html.escape(navn)}</figcaption></figure>')
        if typer and not billeder:
            billeder.append('<p class="note">Ingen tegning af denne bumptype i kilder\\bumptyper.</p>')
        kortlink = ""
        m = re.search(r"\((https?://[^)\s]+)\)", felter.get("Kort", ""))
        if m:
            kortlink = f'<a class="knap" href="{html.escape(m.group(1))}" target="_blank" rel="noopener">Se strækningen i Google Maps</a>'
        felt_rk = "".join(f"<tr><th>{html.escape(k)}</th><td>{inline(v)}</td></tr>" for k, v in felter.items())
        kort.append(
            f'<article class="kort" id="a{i}"><h2>{html.escape(titel)}</h2>{kortlink}'
            + (f'<div class="tegninger"><h3>Bumptype: {html.escape(bumpnavne)}</h3>{"".join(billeder)}'
               '<p class="note">Tegningerne viser bumptypens standardprofil efter vejreglerne '
               '(vejledning\\kilder), ikke opmålte bump.</p></div>' if billeder else "")
            + f'<table class="felter">{felt_rk}</table></article>')

    filter_html = ""
    for j, k in enumerate(KOLONNER):
        if k[3]:
            opts = "".join(f'<option value="{html.escape(v)}">{html.escape(v)}</option>' for v in sorted(filtre[k[0]]))
            filter_html += (f'<label>{html.escape(k[0])}<select data-filter="f{j}"><option value="">Alle</option>{opts}'
                            "</select></label>")
    galleri = "".join(
        f'<figure><img src="{img(f)}" alt="{html.escape(n)}"><figcaption>{html.escape(n)}</figcaption></figure>'
        for f, n in ALLE_TEGNINGER if img(f))
    hoved = "".join(f'<th data-kol="{j + 1}">{html.escape(k[0])}</th>' for j, k in enumerate(KOLONNER))
    antal = len(data["analyser"])
    return SKABELON.format(
        senest=inline(data["senest"]) if data["senest"] else "ikke angivet",
        antal=antal, filtre=filter_html, hoved=hoved, raekker="".join(rækker) or
        f'<tr><td colspan="{len(KOLONNER) + 1}">Ingen analyser endnu.</td></tr>',
        kort="".join(kort), galleri=galleri, js=JS)


SKABELON = """<!doctype html>
<html lang="da"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nationale analysekonklusioner</title>
<style>
:root {{ --bg:#fff; --fg:#1d1d1f; --muted:#5f6368; --line:#d9dce1; --head:#f3f4f6; --accent:#1f5fa8; --hover:#eef4fb; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16181c; --fg:#e8eaed; --muted:#a6abb3; --line:#363a42; --head:#20242a; --accent:#7fb2ee; --hover:#1f2a38; }}
  figure img {{ background:#fff; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }}
header, main {{ max-width:1400px; margin:0 auto; padding:16px; }}
h1 {{ font-size:1.5rem; margin:.2em 0; }} h2 {{ font-size:1.2rem; margin:.2em 0 .5em; }} h3 {{ font-size:1rem; margin:.2em 0; }}
.meta, .note {{ color:var(--muted); font-size:.9rem; }}
nav {{ display:flex; gap:4px; border-bottom:1px solid var(--line); margin-top:12px; }}
nav button {{ font:inherit; padding:8px 14px; border:1px solid var(--line); border-bottom:none; background:var(--head); color:var(--fg); border-radius:6px 6px 0 0; cursor:pointer; }}
nav button[aria-selected=true] {{ background:var(--bg); font-weight:600; position:relative; top:1px; }}
.fane[hidden] {{ display:none; }}
.filtre {{ display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin:12px 0; }}
.filtre label {{ display:flex; flex-direction:column; font-size:.85rem; color:var(--muted); gap:2px; }}
.filtre input, .filtre select {{ font:inherit; padding:6px 8px; border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--fg); min-width:160px; }}
.tabelboks {{ overflow-x:auto; border:1px solid var(--line); border-radius:8px; }}
table {{ border-collapse:collapse; width:100%; }}
#tabel th, #tabel td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
#tabel th {{ background:var(--head); position:sticky; top:0; cursor:pointer; white-space:nowrap; user-select:none; }}
#tabel th[data-ret=op]::after {{ content:" ▲"; }} #tabel th[data-ret=ned]::after {{ content:" ▼"; }}
#tabel tbody tr:hover {{ background:var(--hover); }}
#tabel td:first-child {{ font-weight:600; min-width:160px; }}
#tabel td:last-child {{ white-space:nowrap; }}
a {{ color:var(--accent); }}
.kort {{ border:1px solid var(--line); border-radius:10px; padding:16px; margin:16px 0; }}
.knap {{ display:inline-block; margin-bottom:12px; padding:6px 12px; border:1px solid var(--accent); border-radius:6px; text-decoration:none; }}
.tegninger {{ display:flex; flex-wrap:wrap; gap:12px; align-items:flex-start; margin-bottom:12px; }}
.tegninger h3, .tegninger .note {{ flex-basis:100%; }}
figure {{ margin:0; border:1px solid var(--line); border-radius:8px; padding:8px; max-width:520px; flex:1 1 300px; }}
figure img {{ width:100%; height:auto; display:block; }}
figcaption {{ font-size:.85rem; color:var(--muted); margin-top:4px; }}
.galleri {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:12px; }}
.felter th, .felter td {{ padding:6px 8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
.felter th {{ width:26%; min-width:140px; color:var(--muted); font-weight:600; }}
code {{ font-size:.9em; }}
@media (max-width:640px) {{ .felter th {{ width:auto; min-width:0; }} .felter th, .felter td {{ display:block; border:none; padding:2px 0; }}
  .felter tr {{ display:block; border-bottom:1px solid var(--line); padding:6px 0; }} .filtre input, .filtre select {{ min-width:0; width:100%; }} .filtre label {{ flex:1 1 140px; }} }}
</style></head>
<body>
<header>
<h1>Nationale analysekonklusioner</h1>
<p class="meta">Trackpoint-analyser i hele landet: {antal} analyse(r). Senest opdateret: {senest}.<br>
Visning af <code>nationale_analysekonklusioner.md</code>; ret og del .md-filen, og lav denne visning igen.</p>
<nav role="tablist">
<button role="tab" aria-selected="true" data-fane="tabel-fane">Tabel</button>
<button role="tab" aria-selected="false" data-fane="kort-fane">Analyser</button>
<button role="tab" aria-selected="false" data-fane="bump-fane">Bumptyper</button>
</nav>
</header>
<main>
<section id="tabel-fane" class="fane">
<div class="filtre"><label>Søg<input id="soeg" type="search" placeholder="fx Esbjerg, cirkelbump, el"></label>{filtre}
<span class="meta" id="taeller"></span></div>
<div class="tabelboks"><table id="tabel"><thead><tr><th data-kol="0">Analyse</th>{hoved}</tr></thead>
<tbody>{raekker}</tbody></table></div>
<p class="note">Klik på en overskrift for at sortere, og på en analyse for at se alle felter. Hold musen over en celle for hele teksten.</p>
</section>
<section id="kort-fane" class="fane" hidden>{kort}</section>
<section id="bump-fane" class="fane" hidden>
<p class="note">Standardprofiler efter vejreglerne (Vejdirektoratets håndbog, se vejledning\\kilder\\README.md). Tal efter navnet er hastigheden i km/t, profilen er tegnet til.</p>
<div class="galleri">{galleri}</div></section>
</main>
<script>{js}</script>
</body></html>
"""

JS = """
const faner = document.querySelectorAll('nav button');
function vis(id) {
  faner.forEach(b => b.setAttribute('aria-selected', b.dataset.fane === id));
  document.querySelectorAll('.fane').forEach(s => s.hidden = s.id !== id);
}
faner.forEach(b => b.addEventListener('click', () => vis(b.dataset.fane)));
document.querySelectorAll('.til-kort').forEach(a => a.addEventListener('click', e => {
  e.preventDefault(); vis('kort-fane');
  document.getElementById(a.getAttribute('href').slice(1)).scrollIntoView({behavior: 'smooth'});
}));
const rk = [...document.querySelectorAll('#tabel tbody tr[data-id]')];
const soeg = document.getElementById('soeg');
const sel = [...document.querySelectorAll('select[data-filter]')];
function filtrer() {
  const q = soeg.value.trim().toLowerCase();
  let n = 0;
  rk.forEach(r => {
    let ok = !q || r.textContent.toLowerCase().includes(q) ||
      [...r.cells].some(c => (c.title || '').toLowerCase().includes(q));
    sel.forEach(s => { if (s.value && !(r.dataset[s.dataset.filter] || '').split('|').includes(s.value)) ok = false; });
    r.hidden = !ok; if (ok) n++;
  });
  document.getElementById('taeller').textContent = n + ' af ' + rk.length + ' analyser';
}
soeg.addEventListener('input', filtrer); sel.forEach(s => s.addEventListener('change', filtrer)); filtrer();
document.querySelectorAll('#tabel th').forEach(th => th.addEventListener('click', () => {
  const k = +th.dataset.kol, op = th.dataset.ret !== 'op';
  document.querySelectorAll('#tabel th').forEach(h => delete h.dataset.ret);
  th.dataset.ret = op ? 'op' : 'ned';
  const tb = document.querySelector('#tabel tbody');
  rk.sort((a, b) => a.cells[k].textContent.localeCompare(b.cells[k].textContent, 'da', {numeric: true}) * (op ? 1 : -1))
    .forEach(r => tb.appendChild(r));
}));
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--md", default=str(ROD / "nationale_analysekonklusioner.md"), help="konklusionsfilen (.md)")
    ap.add_argument("--out", default=None, help="HTML-fil (standard: samme navn og mappe som .md)")
    ap.add_argument("--bumptyper", default=str(BUMPMAPPE), help="mappe med tegninger af bumptyper")
    a = ap.parse_args()
    md = Path(a.md)
    if not md.exists():
        raise SystemExit(f"Filen findes ikke: {md}")
    data = laes_md(md.read_text(encoding="utf-8"))
    ud = Path(a.out) if a.out else md.with_suffix(".html")
    ud.write_text(byg_html(data, a.bumptyper), encoding="utf-8")
    print(f"{ud} ({len(data['analyser'])} analyse(r))")


if __name__ == "__main__":
    main()
