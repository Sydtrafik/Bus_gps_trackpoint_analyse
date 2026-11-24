# Trackpoint-værktøjet

Værktøjet måler bussers køretid, fart og passagerkomfort på en strækning før og efter en
vejændring (bump, indsnævring m.m.) ud fra bussernes GPS fra HAFAS, og laver en rapport som én
HTML-fil, du kan sende videre. Det kører på Windows og kræver Python (testet på 3.13; 3.10 eller
nyere forventes at virke), men du skriver ingen kommandoer.

Det kan bruges til:

- Før og efter en vejændring: hvad ændrede bump, indsnævringer m.m. ved køretid, fart og komfort.
- Én periode, uden før-måling: hvordan bussen påvirkes, og hvordan der køres på en strækning i dag
  (fart, opbremsning, acceleration, hvor bussen standser). Sæt `PERIODER=A` i `koer_analyse.bat`.
- Køretid gennem et trafikeret kryds, for én retning, med flere punkter (før køen, stoplinjen,
  i krydset, efter krydset): køretid pr. stykke. Det kræver den fulde config og en agent eller
  Python-erfaring. Giver en rapport med køretid pr. stykke over døgnet, pr. rute og pr. planlagt
  tur. Se [program/README.md](program/README.md), "Kryds".

Køretiden findes også pr. tur i `resultat\turtabel.csv` (dato, ugedag, time, retning, rute,
planlagt turnummer, køretid og tidspunkt ved hvert punkt) og pr. time i `resultat\overblik.md`.
Alt kommer fra HAFAS-eksporten; der slås ikke op i andre kilder.


## Hent værktøjet

- **Uden git:** tryk på den grønne knap **Code** øverst på siden, og vælg **Download ZIP**. Pak
  zip-filen ud i en mappe, du selv kan skrive i. Mappens sti må ikke indeholde `%`.
- **Med git:** `git clone https://github.com/Sydtrafik/Bus_gps_trackpoint_analyse.git`

Python skal være installeret; krav og pakker står i [program/README.md](program/README.md), afsnit 2.
Valg 0 i `koer_analyse.bat` installerer pakkerne.


## Hvad ligger her

| Fil eller mappe | Indhold |
|---|---|
| `ny_analyse.bat` | Start her: opretter en mappe til din analyse |
| [nationale_analysekonklusioner.md](nationale_analysekonklusioner.md) | Konklusioner fra analyser i hele landet; tilføj dine |
| `nationale_analysekonklusioner.html` | Samme konklusioner til at læse: tabel med filtre og tegning af bumptypen (laves af `koer_analyse.bat`, valg 5). Åbn den lokalt i en browser; GitHub viser kun kildekoden. |
| [vejledning/](vejledning) | Læs efter behov (se nedenfor) |
| [program/](program) | Selve programmet; rør ikke |
| [AGENTS.md](AGENTS.md), `CLAUDE.md` | Til en AI-agent (fx Claude Code), hvis du bruger en |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Sådan deler du en ændring eller dine konklusioner |
| [LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | Licens (MIT) og licenser for de medfølgende biblioteker |

Ret ikke i filerne her, undtagen `nationale_analysekonklusioner.md`. Dit eget arbejde og dine data
ligger i din analysemappe, ved siden af værktøjsmappen. Kommer der en ny version af værktøjet,
erstatter du hele værktøjsmappen; dine analyser røres ikke.


## Sådan laver du en analyse

0. I god tid: eksportér før-perioden fra HAFAS, FØR ændringen sker. HAFAS gemmer kun ca. 3 måneder.
   Vejledning: [vejledning/eksportvejledning_HAFAS.md](vejledning/eksportvejledning_HAFAS.md)

1. Dobbeltklik på `ny_analyse.bat`, og skriv et navn (fx Kvaglundvej Esbjerg). Den opretter
   `trackpoint_analyser\<navn>\` ved siden af værktøjsmappen med:

   ```
   data\A\                          her lægger du HAFAS-eksporten for før-perioden (Details.csv og List.csv)
   data\B\                          her lægger du HAFAS-eksporten for efter-perioden
   config.yaml                      indstillinger, du udfylder
   koer_analyse.bat                 kører analysen
   Vejledning - trin for trin.txt   de samme trin som her
   resultat\                        tal og rapport
   ```

2. Åbn `config.yaml` i Notesblok, og udfyld felterne mærket `<-- UDFYLD`: perioder, strækningens
   to ender (koordinater fra Google Maps) og bump/indsnævringer.

3. Dobbeltklik på `koer_analyse.bat`, og vælg:

   ```
   0  første gang: installér og test (ca. 1 min)
   1  stoppesteder pr. retning, med forslag til, hvad du skriver i config.yaml
   2  prøvekørsel på 300 ture: tjek, at næsten alle ture er beholdt
   3  fuld analyse og rapport (10-30 min), også køretid pr. tur og pr. time
   4  byg rapporten igen, når du har skrevet titlen og teksterne i config.yaml
   ```

4. Læs rapporten. Forbehold og hvordan tallene er regnet:
   [vejledning/metode_og_rapportering.md](vejledning/metode_og_rapportering.md)

5. Tilføj dine fund i `nationale_analysekonklusioner.md`, og del dem via repoet på GitHub
   (pull request, eller et issue med din blok; se [CONTRIBUTING.md](CONTRIBUTING.md)). Ingen
   mailadresser i filen; den er offentlig.


## Hvad skal jeg læse, og hvornår

- Før ændringen sker: [vejledning/eksportvejledning_HAFAS.md](vejledning/eksportvejledning_HAFAS.md)
- Før du deler en rapport: [vejledning/metode_og_rapportering.md](vejledning/metode_og_rapportering.md)
  (hvad tallene betyder, forbehold)
- Skriver du selv rapportens tekst: [vejledning/formidling_og_grafik.md](vejledning/formidling_og_grafik.md)
- Skal analysen bruges i en konkret sag om vejregler: [vejledning/kilder/README.md](vejledning/kilder/README.md)
- Teknisk reference, flere strækninger og fejlfinding: [program/README.md](program/README.md)

Version: se [program/VERSION](program/VERSION). Ændringer: [program/CHANGELOG.md](program/CHANGELOG.md).


## Licens og forbehold

- Koden er udgivet under MIT-licensen (se [LICENSE](LICENSE)). ECharts og Leaflet følger med under
  deres egne licenser (se [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
- Rapporten virker uden internet. Slår du kortet til (`kort: true` i `config.yaml`), henter
  rapporten kortfliser fra OpenStreetMap, og læserens IP-adresse sendes til deres server.
- HAFAS er et varemærke, der tilhører sin ejer. Værktøjet læser kun en eksport fra HAFAS og er
  ikke tilknyttet eller godkendt af ejeren.
