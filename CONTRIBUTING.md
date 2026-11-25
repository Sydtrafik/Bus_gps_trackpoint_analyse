# Sådan bidrager du

Bidrag er velkomne: rettelser, nye funktioner og konklusioner fra dine egne analyser. Den fulde
fremgangsmåde står i [program/README.md](program/README.md), afsnit 11. Kort:

## Del dine konklusioner

1. Lav din konklusionsfil (`koer_analyse.bat`, valg 6), udfyld felterne med `UDFYLD`, og tilføj
   den (valg 5). Den lægges i [analyser/](analyser) som `<vej>_<by>_<år>.yaml`, og
   `nationale_analysekonklusioner.md` og `.html` laves igen. Vejkortet hentes fra OpenStreetMap til
   `analyser/kort/`. Felterne: [analyser/README.md](analyser/README.md).
2. Lav en pull request med din fil, kortfilen og de to oversigtsfiler. Ret ikke andres filer i `analyser/`.
   Testene tjekker, at filen er gyldig, og at oversigten er lavet igen. Bruger du ikke git, så
   opret et issue "Ny analysekonklusion", og indsæt indholdet af din fil.

## Del en ændring af værktøjet

1. Skriv en linje øverst under `## [Ikke udgivet]` i [program/CHANGELOG.md](program/CHANGELOG.md):
   dato, hvem (organisation, evt. navn eller GitHub-brugernavn), hvad og hvorfor, og hvilke filer.
2. Ret ikke beregningsfilerne (`analyse_v2.x.py`, `komfort_v1.x.py`, `zonetid.py` og rapportens
   beregning). En ændret beregning er en ny fil med nyt filversionsnummer.
3. Kør testene ([program/README.md](program/README.md), afsnit 9), og lav en pull request. Bruger
   du ikke git, så opret et issue, der beskriver ændringen.

Versionsnummer, git-tag og GitHub Release sættes af vedligeholderen, ikke i en pull request. Alt, der kommer på `main`, udgives med det samme, så zip-filen under Releases altid er den nyeste udgave.

## Det må ikke komme med

Repoet er offentligt, og alt, der kommer med, kan ikke fjernes fra historikken igen.

- Ingen rådata: HAFAS-eksporter (`Details.csv`, `List.csv`), ping-udtræk, `turtabel.csv` eller
  andre filer med tur-id. Kun aggregerede tal.
- Ingen mailadresser eller telefonnumre. Kontaktperson er et GitHub-brugernavn; navn og
  organisation er valgfrie.
