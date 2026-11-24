# Sådan bidrager du

Bidrag er velkomne: rettelser, nye funktioner og konklusioner fra dine egne analyser. Den fulde
fremgangsmåde står i [program/README.md](program/README.md), afsnit 11. Kort:

## Del dine konklusioner

1. Udfyld skabelonen nederst i [nationale_analysekonklusioner.md](nationale_analysekonklusioner.md)
   for din analyse, og lav visningen igen (`koer_analyse.bat`, valg 5).
2. Lav en pull request med begge filer (`.md` og `.html`). Bruger du ikke git, så opret et issue
   og indsæt din blok.

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
