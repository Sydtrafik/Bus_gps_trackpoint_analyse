## Hvad og hvorfor

<!-- Kort: hvad ændrer pull requesten, og hvorfor. -->

## Tjekliste

- [ ] Linje under `## [Ikke udgivet]` i `program/CHANGELOG.md` (dato, hvem, hvad, filer)
- [ ] Beregningsfilerne er ikke rettet; en ændret beregning er en ny fil med nyt filversionsnummer
- [ ] Testene er kørt (`python -m pytest program/tests -q`), eller jeg har skrevet, hvorfor ikke
- [ ] Ingen rådata, tur-id'er, ping-udtræk, mailadresser eller telefonnumre
- [ ] Ny analysekonklusion: én ny fil i `analyser/` (andres filer er ikke rettet) + `nationale_analysekonklusioner.md` og `.html` lavet igen med `program/lav_konklusioner_html.py`

Versionsnummer, tag og release sætter vedligeholderen, når pull requesten er merget.
