# AGENTS.md: instruktion til en kodeagent

Denne mappe er et Python-værktøj, der måler bussers køretid, fart og kørselskomfort på en eller flere strækninger ud fra realtids-GPS (HAFAS-eksport), før og efter en vejændring (bump, indsnævring m.m.) eller for én periode alene, og laver en selvstændig HTML-rapport (en præsentationsrapport med få fund og lidt interaktion). Andre anvendelser (én periode, køretid gennem et kryds, analyse af bestemte ture via output pr. tur): README, "Anvendelser". Læs [README.md](program/README.md) for brugen, [metode_og_rapportering.md](vejledning/metode_og_rapportering.md) for, hvad der rapporteres, hvordan og hvorfor, og [formidling_og_grafik.md](vejledning/formidling_og_grafik.md), før du laver eller ændrer en rapport. Dansk i tekst og rapport, engelsk i kode.

## Mappestruktur

Roden er holdt til det, brugeren selv rører. Alt andet ligger i to mapper:

| Sted | Indhold | Hvem |
|---|---|---|
| `ny_analyse.bat` | Opretter en analysemappe (den nemme vej) | brugeren |
| `README.md` | Kort vejledning til brugeren (forsiden på GitHub) | brugeren |
| `nationale_analysekonklusioner.md` | Konklusioner fra afsluttede analyser i hele landet (regel 6) | brugeren og dig |
| `nationale_analysekonklusioner.html` | Visning af .md-filen (tabel med filtre, bumptegninger); laves af `program\lav_konklusioner_html.py`, rettes aldrig i hånden | brugeren |
| `AGENTS.md`, `CLAUDE.md` | Denne fil (`CLAUDE.md` peger hertil) | dig |
| `LICENSE`, `THIRD_PARTY_NOTICES.md`, `CONTRIBUTING.md`, `.gitignore`, `.gitattributes` | Licens (MIT), tredjepartslicenser, sådan bidrager man, git-opsætning (`.bat` med CRLF, analysedata holdes ude) | dig |
| `vejledning\` | `eksportvejledning_HAFAS.md`, `metode_og_rapportering.md`, `formidling_og_grafik.md`, `kilder\` (vejregler, bumptegninger) | brugeren og dig |
| `program\` | Alle scripts, `rapport\`, `skabeloner\`, `tests\`, `eksempler\`, `config_eksempel.yaml`, `requirements.txt`, teknisk `README.md`, `CHANGELOG.md`, `VERSION` | dig |

Brugerens analyser ligger uden for værktøjsmappen, i `trackpoint_analyser\<navn>\` ved siden af den.

## Regler for dig

1. **Ret ikke beregningen.** `analyse_v2.2.py` (og den forrige `analyse_v2.1.py`), `komfort_v1.0.py` og `zonetid.py` er verificerede. Behov for en ændring: lav en ny fil med nyt versionsnummer (`analyse_v2.3.py`), behold den gamle, og kør afstemningen nedenfor.
2. **Spørg brugeren**, før du vælger perioder, strækningernes ender, elementernes koordinater, udvalget (hverdage/helligdage) **og rapporttype og budskab** ([formidling_og_grafik.md](vejledning/formidling_og_grafik.md), afsnit 1). Det er brugerens beslutninger. Hvordan koden køres, afgør du selv.
2b. **Data forsvinder.** HAFAS gemmer kun ca. 3 måneder tilbage. Er der en ændring på vej, så sig til brugeren, at før-perioden skal eksporteres nu; den kan ikke genskabes bagefter. Mangler der en før-periode, kan du stadig køre kæden med kun periode A (niveauer, ingen sammenligning).
3. **Rådata, tur-id'er og ping-udtræk hører ikke hjemme i rapporten eller i filer, der deles.** `rapportdata.json`, `overblik.md`/`.csv` og HTML-rapporten indeholder kun aggregerede tal. `turtabel.csv` har tur-id og er til brugerens egen udforskning.
4. **Skriv output med æøå til fil**, og læs filen. Sæt `PYTHONUTF8=1`, brug UTF-8 på al fil-I/O. Brug ikke æøå i identifiers i egen kode.
5. **Store filer:** `analyse_v2.2.py` læser `Details.csv` i to gennemløb i bidder og holder kun rækkerne mellem de to stop i hukommelsen. Målt: 1,3-1,5 GB (ca. 9 mio. rækker) brugte højst 1,2-1,7 GB RAM og ca. 4-8 min pr. periode; 3,4 GB (24 mio. rækker) højst 2,2 GB RAM og ca. 9 min. Kør periode for periode, og kør de lange trin i baggrunden.
6. **Opdatér `nationale_analysekonklusioner.md`, når rapporten er færdig.** Udfyld skabelonen nederst i filen med brugerens analyse (alle felter; spørg brugeren om det, du ikke kan se i data: vejtype, bustype, type bump, om indsnævringer er nye, sving, hastighedsbegrænsning før og efter, kontaktperson). Bustype: tæl "Busnummer" i `List.csv` pr. periode (hvilke numre, og om det er de samme før og efter), og bed brugeren om drivmiddel og længde for numrene; HAFAS-eksporten har dem ikke. Komfort: regn andelen af ture med mærkbar og kraftig opbremsning, acceleration og samlet (uden standsning ved stop, før og efter, og til sammenligning med standsning ved stop) ud fra `fordeling` i `rapportdata.json` (kolonnerne `Klasse`, `KlasseAcc` og `KlasseSam`; mærkbar tæller også de kraftige med, som i rapporten), sæt dagens dato i "Opdateret", lav Google Maps-linket ud fra strækningens fra- og til-punkt (`https://www.google.com/maps/dir/?api=1&origin=<lat>,<lon>&destination=<lat>,<lon>`), sæt blokken øverst under "Analyser", tilføj en række i oversigtstabellen, og ret "Senest opdateret". Kom flere ændringer på samme tid (fx bump og ny hastighedsgrænse), så skriv i "Forbehold", at tallene ikke kan skille dem ad. Ret ikke andres blokke. Gem filen i denne mappe oven i den gamle, og kør `python program\lav_konklusioner_html.py` (skriver `nationale_analysekonklusioner.html`; skriv "Type bump" med skabelonens betegnelser, så tegningen findes, og tjek at kortet viser den). Del den derefter via repoet: forbered en pull request med begge filer (eller, hvis brugeren ikke bruger git, en issue-tekst med blokken). Send ikke selv; brugeren godkender. Kontaktperson = GitHub-brugernavn; navn og organisation er valgfrie; ingen mail eller telefon (filen er offentlig). Regel 3 gælder: kun aggregerede fund.
7. **Ændrer du noget i pakken** (tekst, tegning, ny fil, ny beregningsfil), så skriv en linje øverst under `## [Ikke udgivet]` i `program\CHANGELOG.md` (dato, hvem: organisation, evt. navn eller GitHub-brugernavn, hvad, filer). Skal ændringen deles: følg README afsnit 11 (pull request mod repoet på GitHub). Pusher du selv til `main` (efter brugerens ok), så udgiv i samme omgang: nyt versionsafsnit og `program\VERSION` efter MAJOR/MINOR/PATCH; workflowen `.github\workflows\udgiv.yml` laver tag `vX.Y.Z` og GitHub Release (afsnittet "Vedligeholdelse af repoet"). `[Ikke udgivet]` må ikke ligge på `main`, for så er zip-filen under Releases ikke den nyeste. Får brugeren en ny udgave: hent den med git (eller som zip fra GitHub), og flet efter afsnit 11; kør testene bagefter. Læg ikke nye filer i roden (roden har kun `README.md`, `ny_analyse.bat`, `nationale_analysekonklusioner.md` og `.html`, `AGENTS.md`, `CLAUDE.md`, `LICENSE`, `THIRD_PARTY_NOTICES.md`, `CONTRIBUTING.md`, `.gitignore` og `.gitattributes`).

## Rækkefølge af kommandoer

**Brugeren kan ikke Python:** brug den nemme vej (README, "Den nemme vej"). `ny_analyse.bat --navn "<navn>"` opretter analysemappen (`trackpoint_analyser\<navn>\` ved siden af værktøjet) med den korte `config.yaml` og `koer_analyse.bat`; `koer_analyse.bat <0-4>` kører et trin uden menu (0 installér og test, 1 stoppesteder pr. retning med forslag til start/slut og tjek af om p1/p2 skal byttes, 2 prøve, 3 fuld analyse, turtabel og rapport, 4 rapport igen). Valg 3 og 4 kører på `resultat\config_beregnet.yaml` (`program\skabeloner\forbered.py config`: absolutte datastier og `komfort.bump_vinduer` = bumpets position ± `radius_m`, standard 30 m). Hjælp brugeren med at udfylde config'en; kæden er den samme som nedenfor.

`$V` = `program\` i denne mappe (der, hvor `analyse_v2.2.py` ligger), `$P` = projektmappen med config og data. PowerShell 7.

```powershell
$env:PYTHONUTF8 = "1"
python -m pip install -r "$V\requirements.txt"

# 0. Test at værktøjet virker (ingen data nødvendig, ca. 1 min)
python -m pip install pytest                           # valgfri; uden pytest: kør filerne enkeltvis (README afsnit 9)
python -m pytest "$V\tests" -q                         # eller: python "$V\tests\test_v2.py" osv.

# 1. Opsætning (README, trin 1-5): config fra config_eksempel.yaml, stopnavne, punkter, prøvekørsel
python "$V\analyse_v2.2.py" --config "$P\min_config.yaml" --list-stops
python "$V\analyse_v2.2.py" --config "$P\min_config.yaml" --max-trips 300 --debug --output-dir "$P\prove"

# 2. Fuld kørsel pr. periode, med segmenter til komfort og zonetid
python "$V\analyse_v2.2.py" --config "$P\min_config.yaml" --period A --output-dir "$P\ud_A" --export-segments
python "$V\analyse_v2.2.py" --config "$P\min_config.yaml" --period B --output-dir "$P\ud_B" --export-segments

# 2b. Turtabel (én række pr. tur: køretid pr. stykke, tid pr. punkt, time, rute) + overblik pr. time og periode
python "$V\turtabel.py" --config "$P\min_config.yaml" --a "$P\ud_A" --b "$P\ud_B" --out "$P\ud"
# Kryds (i stedet for trin 3-5): rapport over køretid pr. stykke, rute og planlagt tur (README, "Kryds")
python "$V\rapport\lav_kryds_rapport.py" --config "$P\min_config.yaml" --turtabel "$P\ud\turtabel.csv" --out "$P\ud\kryds_rapport.html"

# 3. Komfort pr. tur
python "$V\komfort_v1.1.py" --segments "$P\ud_A\segmenter.csv" --config "$P\min_config.yaml" --out "$P\ud_A\komfort.csv"
python "$V\komfort_v1.1.py" --segments "$P\ud_B\segmenter.csv" --config "$P\min_config.yaml" --out "$P\ud_B\komfort.csv"
# flere strækninger: komfort_<id>.csv skrives ved siden af --out (komfort_v1.1.py; v1.0 kan kun én strækning)

# 4. Zonetid: ekstra køretid pr. element (kræver elementer, udvalg og zonetid i config). Uden --b: tid pr. zone for én periode
python "$V\zonetid.py" --config "$P\min_config.yaml" --a "$P\ud_A" --b "$P\ud_B" --out "$P\ud"

# 5. Rapport: rapportdata.json, derefter én HTML-fil
python "$V\rapport\lav_rapportdata_v1.2.py" --config "$P\min_config.yaml" --a "$P\ud_A" --b "$P\ud_B" --turtabel "$P\ud\turtabel.csv" --zonetid "$P\ud\zonetid.json" --out "$P\ud\rapportdata.json"
python "$V\rapport\byg_rapport.py" --data "$P\ud\rapportdata.json" --out "$P\ud\rapport.html"
```

`analyse_v2.2.py` skriver en harmløs advarsel "ukendte nøgler i config ignoreres" om `elementer`, `straekninger`, `udvalg`, `zonetid` og `rapport`; de læses af trin 3-5.

**Genskab eksemplet:** kopiér `program\eksempler\config_kvaglundvej.yaml` og ret kun de fire datastier; resten kan stå.

**Kun én periode** (ingen før-måling): udelad B overalt (`--period A`, ingen `--b`, ingen B-blok i `periods:`/`data:`). Hele kæden virker, og rapporten viser niveauer og skjuler sammenligningerne. Bygger du på en før/efter-config, så skriv `rapport.titel`, `undertitel`, `straekning_tekst` og `forbehold` om (de taler om en ændring), sæt `rapport.periode_navn`, og navngiv elementerne, så de passer til perioden (rapporten skriver "ved bumpene" ud fra `type: bump`). Se README, "Én periode". **Flere strækninger:** definér dem under `straekninger:` i config (id, navn, fra, til, elementer); komfort og zonetid regnes pr. strækning, og rapporten får en strækningsvælger. En config med `komfort: fra/til` er én strækning (bagudkompatibelt).

## Sådan verificerer du

1. **Tests** (trin 0): 78 tests, ingen data nødvendig (`test_v2` 11 mod `analyse_v2.2.py`, `test_komfort` 13, `test_komfort_v11` 4, `test_zonetid` 11, `test_turtabel` 6, `test_kryds_rapport` 3, `test_rapport` 12, `test_rapport_v12` 6, `test_ny_analyse` 4, `test_forbered` 4, `test_konklusioner_html` 4; browsertestene springes over uden playwright).
2. **`kvalitet.md` i hver output-mappe** efter trin 2: antal beholdte og kasserede ture pr. årsag. Næsten alle `stop_ikke_fundet` = forkerte stopnavne eller omvendt retning. Alle `ingen_retningsflag` = `Turnummer` matcher ikke `Turreference`, eller `Retningsflag` mangler.
3. **`kvalitet_pr_dag.csv`**: dage med høj kasseret-andel i træk = omkørsel eller ændret stopnavn. Beslut sammen med brugeren, om dagene skal stå som forbehold i rapporten.
3b. **Turtabel** (trin 2b): konsollen skal skrive "køretid = tid ved til-punkt minus tid ved fra-punkt i N af N tilfælde" og "0 uden tidspunkt". Ellers er `result.csv` og `segmenter.csv` ikke fra samme kørsel.
4. **Gennemsnitlig nærmeste afstand** nederst i `analyse_log.txt`: få meter pr. punkt. Hundreder af meter = punkt eller `point_order` er forkert (opdages ikke automatisk).
5. **Afstemning af kæden** (gør det, før du melder færdig):
   - Antal ture i `zonetid.md` (n) og i rapportens omfangslinje er de samme som antal gyldige hverdagsture i `result.csv` + `komfort.csv` (tom `Log`, ingen `stoprække_` i `Flag`, `status = ok`).
   - `zonetid.md`: "ekstra i alt" er forskellen på gennemsnitlig køretid efter og før i zonerne (ikke medianen i rapportens nøgletal; de to ligger tæt, men ikke ens).
   - Elementernes positioner i `zonetid.md` ligger, hvor du forventer langs strækningen (meter fra startpunktet).
   - Åbn `rapport.html` i en browser: ingen fejl i konsollen, alle grafer har data, ingen vandret scroll på 375 px bredde, tallene i nøgletal og tabel er de samme som i `rapportdata.json`. Ved flere strækninger: skift strækning og tjek, at alt skifter; ved én periode: ingen før/efter-tekst.
   - **Kontrastkontrol:** rapporten beregner selv WCAG-kontrast for farverne i `:root` ved indlæsning og skriver advarsler i konsollen (`window.RAPPORT_KONTRAST` er tom, når alt består: tekst mindst 4,5:1, datamærker mindst 3:1). Ret farverne, hvis der er advarsler.
   - **Formidlings-review inden deling:** giv en ekstra agent **kun teksten og screenshots** (ikke kode, ikke `rapportdata.json`), og bed om højst 12 fund efter [formidling_og_grafik.md](vejledning/formidling_og_grafik.md), afsnit 10. Reglen om rådata i regel 3 gælder også her.
   - Har du et facit (tidligere kørsel), så sammenlign celle for celle og accepter ikke "tæt på".
6. **Ny strækning, første gang:** kør trin 1-3 for kun én periode og se på `result.csv`, `komfort.csv` og `kvalitet.md`, før du bruger tid på de lange kørsler.

## Faldgruber (målt)

- **HAFAS gemmer kun ca. 3 måneder tilbage.** Før-perioden skal eksporteres, før ændringen sker; ellers er den væk.
- **Stoppesteder har én position pr. side af vejen** (pr. kørselsretning). Angiv dem med `retning` under `rapport.stoppesteder`; fartprofil og kort viser dem pr. retning.

- **Stoprækkers tidsstempel ligger efter passagen:** median ca. 8-9 s og 75-85 m efter bussens nærmeste passage. Stop-rækker bruges derfor ikke til fart/komfort/zoner; ture med et målepunkt matchet på en stoprække flagges (`stoprække_<punkt>`) og udelades fra udvalget.
- **Omkørselsdage:** dage, hvor bussen ikke kører strækningen, kasseres som `stop_ikke_fundet`. Tjek `kvalitet_pr_dag.csv`, og skriv dagene i `rapport.forbehold`.
- **Ping-rate:** 1 s mod 2 s mellem pings kan ændre sig mellem perioder og påvirker nøjagtigheden af punktmålinger (tilfældig fejl op til ca. ±0,5-1 s pr. tur). Sammenlign gennemsnitligt ping-interval for A og B; brug medianer og antal ture, ikke enkelte ture.
- **`Retningsflag` mangler i HAFAS' standardopsætning** af turlisten. Slå kolonnen til før eksport ([eksportvejledning_HAFAS.md](vejledning/eksportvejledning_HAFAS.md)).
- **Dublet-`Turnummer`** i turlisten: den første kolonne bruges; tjek at en værdi findes som `Turreference` i Details.
- **Retning 1/2** bestemmes af HAFAS, ikke af dig. `point_order` for retning 2 er normalt retning 1 bagfra. Rapporten finder selv ud af, hvilken retning der kører mod strækningens slutpunkt.
- **Komfort kræver en ret strækning** (projektion på linjen fra `fra` til `til`) og fuld passage uden huller over 10 s. Buede strækninger egner sig ikke.
- **1 s-gitteret udelader det sidste ping i korridoren** (`np.arange` med epoke-sekunder, `1e-9` forsvinder i float-præcision) i `komfort_v1.0.py` og `zonetid.py`. Det påvirker højst de yderste 1-2 s uden for strækningen og er ikke rettet, så tallene er sammenlignelige. Konstruerede testture skal derfor fortsætte ca. 15 m forbi enden (se `tests/syntetisk.py`).
- **Elementer skal ligge på linjen** (højst `komfort.korridor_sideafstand_m` fra den) og inden for strækningen; ellers stopper `zonetid.py` eller advarer.
- **æøå/UTF-8:** konsol-output med æøå kan crashe på Windows (cp1252). Skriv til fil. Kolonnenavne i `result.csv` indeholder æøå (`Køredag`, `køretid`); brug string-adgang.
- **Hukommelse:** `analyse_v2.1.py` holder hele `Details.csv` i hukommelsen (ca. 20 GB RAM til en fil på 3,4 GB). Brug `analyse_v2.2.py`, som kun holder rækkerne mellem de to stop (målt højst 2,2 GB RAM på samme fil, samme resultat). Stopnavnene i config afgør, hvor meget der holdes: stop langt fra strækningen = flere rækker.

## Rapporten: tilpasning

- **Valg og datagrundlag (v1.2):** rapporten har synlige valg for dage, rute og time (standard: `udvalg.dagtype`, alle ruter, alle timer; titlen gælder standardvalget, og linjen under den siger det). Zonetid følger ikke valgene. Fravalgte ture står med antal og andel; få ture vises og markeres OBS. "Om strækningen" læser `rapport.vej` (vejtype, hastighed, bumptype, andre_foranstaltninger): spørg brugeren om dem (regel 2), `byg_rapport.py` advarer, hvis de mangler.
- **Farver og skrift:** CSS-variablerne øverst i `program\rapport\skabelon_v1.2.html` (`:root`; `skabelon.html` til rapportdata v1.1). Kør `byg_rapport.py` igen. Graferne læser de samme variabler.
- **Tekster:** sektionen `rapport:` i config (titel, undertitel, retningsnavne, stoppesteder, forbehold, kilde, målenoter). Mangler en tekst, bruges en neutral standardtekst.
- **Kort:** `rapport.kort: true` giver et Leaflet-kort med OpenStreetMap-kortfliser (kræver internet ved visning, kildeangivelse er med). Slået fra som standard.
- **Læs [formidling_og_grafik.md](vejledning/formidling_og_grafik.md), før du ændrer titler, tekst, farver eller grafer i skabelonen;** guiden er eksempler, ikke love. Titlen siger, hvad og hvor der er målt; et fund står først i titlen, når det er verificeret (Anthon 2026-11-19). Pladsholdere i titlen giver en advarsel fra `byg_rapport.py`.
- **Egen skabelon:** kopiér `skabelon_v1.2.html`, behold de fem mærker (`{{TITEL}}`, `__RAPPORTDATA__`, `/*__ECHARTS__*/`, `/*__LEAFLET_JS__*/`, `/*__LEAFLET_CSS__*/`), og kald `byg_rapport.py --skabelon <fil>`.
- Datafelterne i `rapportdata.json` er beskrevet øverst i `rapport\lav_rapportdata_v1.2.py` (v1.1: `rapport\lav_rapportdata.py`).

## Regler for rapporttekst

Reglerne står i [metode_og_rapportering.md](vejledning/metode_og_rapportering.md), afsnit 5, og [formidling_og_grafik.md](vejledning/formidling_og_grafik.md), afsnit 2-4. Det, der er specifikt for pakken:

- **Komfort = passagerkomfort i kørslen på hele strækningen** (opbremsning og acceleration langs vejen), ikke stødet over selve bumpet; det kan GPS hvert sekund ikke måle. Skriv aldrig, at et bump "er hårdt".
- **Intervaller kan ikke lægges sammen**; skriv det ved tabellen.
- Rapporten er en præsentationsrapport med få fund og lidt interaktion (få valgknapper, ingen tabeller med rådata).

## Filer

| Fil | Hvad |
|---|---|
| `program\analyse_v2.2.py` | Hovedværktøj: HAFAS-eksport + config -> `result.csv`, kvalitet, `segmenter.csv`. Læser store filer i bidder. |
| `program\analyse_v2.1.py` | Forrige version (samme resultater; holder hele `Details.csv` i hukommelsen). Bliver i pakken som reference (regel 1). |
| `program\komfort_v1.1.py`, `program\komfort_v1.0.py` | Komfort pr. tur og strækning ud fra `segmenter.csv`. v1.1 er en tynd indpakning (flere strækninger) om v1.0, der holder den verificerede beregning; begge skal være der (regel 1). |
| `program\turtabel.py` | `turtabel.csv` (én række pr. tur til Excel/Power BI) og `overblik.md`/`.csv` (køretid pr. stykke pr. time og periode). Samler kun; ingen ny beregning. |
| `program\rapport\lav_kryds_rapport.py`, `kryds_skabelon.html` | Kryds-rapport (én HTML-fil) ud fra `turtabel.csv`: køretid pr. stykke over døgnet, pr. rute og planlagt tur. Kun HAFAS-data som kilde. |
| `program\zonetid.py` | Ekstra køretid pr. element (zoner, interval). |
| `program\rapport\lav_rapportdata_v1.2.py`, `byg_rapport.py`, `skabelon_v1.2.html`, `vendor\` | Strækningsrapport med valg for dage, rute og time (kræver `turtabel.csv`). |
| `program\rapport\lav_rapportdata.py`, `skabelon.html` | Forrige version (v1.1) af rapportens beregning og skabelon; rettes ikke (regel 1). |
| `program\config_eksempel.yaml`, `program\eksempler\config_kvaglundvej.yaml` | Kommenteret fuld config og et udfyldt eksempel. |
| `ny_analyse.bat`, `program\skabeloner\` | Den nemme vej: opretter en analysemappe med kort `config.yaml` (to punkter, én strækning) og `koer_analyse.bat` (menu eller argument 0-4); `forbered.py` laver stopforslag og bump-vinduer. |
| `vejledning\formidling_og_grafik.md` | Guide til rapporttype, budskab, titler, tekst, grafer, farver og tjek før deling. |
| `nationale_analysekonklusioner.md` | Konklusioner fra afsluttede analyser i hele landet; opdateres efter hver rapport (regel 6). |
| `vejledning\kilder\README.md`, `vejledning\kilder\bumptyper\` | Vejregler og ældre rapporter om bump og busser (status, version, indholdsfortegnelse, bilag, sidst tjekket) og tegninger af bumptyper. Brug den, når en analyse skal sammenholdes med regler, eller en sag skal underbygges. Tjek status på vejregler.dk igen, før en kilde citeres, og ret "Sidst tjekket". |
| `program\tests\` | Syntetiske tests. |
| `.github\` | Skabeloner til issues og pull requests, og workflows: tests ved hver push og pull request (`tests.yml`) og udgivelse, når `program\VERSION` ændres (`udgiv.yml`). |

## Vedligeholdelse af repoet

Gælder kun, når du arbejder for den, der vedligeholder repoet på GitHub (ikke for en bruger, der laver en analyse).

1. **Push og offentlige handlinger kun efter ejerens ok** i den aktuelle opgave: push, release, kommentarer på issues og pull requests, ændrede indstillinger. Repoet er offentligt, og historikken kan ikke trækkes tilbage.
2. **Commit med repoets egen identitet** (`git config user.name` og `user.email` i repoet, GitHubs noreply-adresse). Ingen personnavne, mailadresser eller interne stier i filer eller commits; hvem = organisationen i CHANGELOG.
3. **Gennemgå en pull request** i denne rækkefølge: (a) ingen rådata, tur-id'er, ping-udtræk, mail eller telefon; (b) beregningsfiler er ikke rettet (en ny beregning er en ny fil); (c) CHANGELOG-linje under `[Ikke udgivet]`; (d) testene er grønne i GitHub Actions. Skriv et udkast til svaret, og lad ejeren poste det.
4. **Udgiv ved hver push til `main`** (regel 7): flyt linjerne fra `[Ikke udgivet]` til `## [X.Y.Z] - ÅÅÅÅ-MM-DD - organisation`, ret `program\VERSION` efter MAJOR/MINOR/PATCH, kør testene, commit og push. Workflowen `udgiv.yml` laver så tag `vX.Y.Z` og en GitHub Release med versionens CHANGELOG-linjer. Tjek bagefter, at releasen er "Latest", og at dens zip har den nye `VERSION`. Den forrige release slettes ikke; dens tag bliver.
5. **Issues:** svar på dansk, kort og med fakta. En ny analysekonklusion fra et issue flyttes ind i `nationale_analysekonklusioner.md` med en pull request (regel 6), med kontaktperson som GitHub-brugernavn.
