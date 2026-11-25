# analyser: én fil pr. afsluttet analyse

Her ligger de nationale analysekonklusioner som én YAML-fil pr. analyse, fx `kvaglundvej_esbjerg_2025.yaml`. Ud fra filerne laver `program/lav_konklusioner_html.py` oversigten i roden: `nationale_analysekonklusioner.html` (graf, sortérbar tabel med filtre og tegning af fartdæmperen, kort pr. analyse) og `nationale_analysekonklusioner.md` (samme tabel, som GitHub viser). Ret aldrig i de to filer; ret i filen her, og lav dem igen.

Filerne er offentlige: kun aggregerede tal, ingen mail, telefon, tur-id'er eller rådata.

## Sådan tilføjer du din analyse

1. **Lav filen:** valg 6 i din analyses `koer_analyse.bat`. Den skriver `resultat\konklusion.yaml` med tallene fra rapporten (de samme som rapportens nøgletal: hverdage, alle ruter og timer, begge retninger, ture uden standsning ved stop, median). Uden bat-filen: `python program\lav_konklusion.py --rapportdata <resultat\rapportdata.json> --out <resultat\konklusion.yaml>`. Kryds: `--overblik <resultat\overblik.csv> --config <config.yaml>` i stedet for `--rapportdata`.
2. **Udfyld** alle `UDFYLD` (vej, by, område, buslommer, parkering på vejen, linjer, bustype, ændring, sammenligning med vejregler, kontakt; ved kryds også hvor hvert punkt ligger), og tjek linjerne med "tjek" i kommentaren (vejtype, hastighed, fartdæmpere, forbehold).
3. **Tilføj den:** valg 5 i `koer_analyse.bat` (eller `python program\lav_konklusioner_html.py --tilfoej resultat\konklusion.yaml`). Filen tjekkes, kopieres hertil som `<vej>_<by>_<år>.yaml`, og oversigten laves igen. Er noget forkert, står fil og felt i beskeden.
4. **Del den** med en pull request med din fil og de to oversigtsfiler (se [CONTRIBUTING.md](../CONTRIBUTING.md)). Bruger du ikke git: opret et issue "Ny analysekonklusion", og indsæt indholdet af din fil.

En fil med samme navn og en anden kontakt overskrives ikke: ret ikke andres analyser.

## Felterne

| Felt | Hvad | Udfyldes af |
|---|---|---|
| `skema` | Altid `1` | script |
| `type` | `foer_efter`, `en_periode` eller `kryds` | script |
| `vej`, `by`, `aar` | Vejnavn, by og året for ændringen (giver filnavnet) | person (`aar`: script) |
| `vejtype` | Vejen selv, fx almindelig vej, boligvej, trafikvej, landevej | person (forslag fra config) |
| `omraade` | Området, vejen ligger i, fx boligområde, bymidte, erhvervsområde, åbent land | person |
| `buslommer` | Holder bussen i en buslomme ved stoppestederne på strækningen: `ja`, `nej` eller `ukendt` | person |
| `parkering_paa_vejen` | Må der parkeres på kørebanen: `ja`, `nej` eller `ukendt` | person |
| `linjer`, `bustype` | Linje(r) og retninger; drivmiddel og længde ("ikke oplyst", hvis ukendt) | person |
| `aendring` | Kort tekst, fx "2 modificerede cirkelbump + 2 indsnævringer, 50 → 40 km/t" | person |
| `fartdaempere` | Liste af `{type, antal}`. Type = bumptypens navn fra vejreglerne (cirkelbump, modificeret cirkelbump, modificeret sinusbump, trapezbump, pudebump, hævet flade ...) eller fx indsnævring, chikane. Første bumptype med en tegning giver tegningen. Er typen antaget (ikke opmålt), så skriv `antaget: true`. `[]` = ingen. Vejreglerne har ingen almindelig sinusbump, kun modificeret sinusbump (kun til 50 km/t) | person (forslag fra config) |
| `hastighed_kmt` | Hastighedsgrænsen pr. periode, tal uden enhed | person (forslag fra config) |
| `laengde_m`, `kort` | Den målte strækning i meter og Google Maps-link | script |
| `punkter` | Punkter til kortet: `{navn, lat, lon}` og ved kryds `beskrivelse` (hvor punktet ligger, fx "stoplinjen"). Strækning: start, fartdæmperne og slut | script (kryds: beskrivelse fra person) |
| `dage`, `perioder` | Dagtype og datoer pr. periode (`foer`/`efter`, eller `periode` ved én periode) | script |
| `ture`, `koeretid_s`, `gnsfart_kmt` | Antal ture, median køretid, median gennemsnitsfart | script |
| `laveste_fart_kmt` | Laveste fart ved fartdæmperne: medianen af den laveste fart pr. tur i hvert vindue, gennemsnit over vinduerne (som rapporten). Tom uden vinduer | script |
| `maerkbar_opbremsning_pct`, `maerkbar_acceleration_pct` | Andel ture med mærkbar (inkl. kraftig) opbremsning og acceleration | script |
| `ekstra_tid_pr_element_s` | Interval pr. element fra zonetiden (lav, hoej) | script |
| `kryds_stykker` | Kryds: median køretid pr. stykke og retning | script |
| `forbehold`, `sammenligning_vejregler` | Korte linjer | person |
| `vaerktoej`, `opdateret` | Værktøjsversion og dato | script |
| `kontakt` | GitHub-brugernavn; evt. "Organisation (GitHub: brugernavn)". Ingen mail eller telefon | person |

Tal skal stå som tal uden anførselstegn og enhed (`54`, ikke `"54 s"`), ellers afvises filen. Ændringer (efter minus før, pr. 100 m, procentpoint) regnes ved visningen og står ikke i filen.
