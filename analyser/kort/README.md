# analyser/kort: vejkort pr. analyse

Én fil pr. analyse, `<analysens filnavn>.json`, med veje, bygninger, fodgængerfelter, stoppesteder og fartdæmpere i et lille område omkring analysens punkter. Filerne laves af `program/lav_vejkort.py` (valg 5 i `koer_analyse.bat` kalder det), og `nationale_analysekonklusioner.html` tegner dem som vejkort.

**Licens:** filerne indeholder data fra OpenStreetMap, © OpenStreetMap-bidragydere, og er tilgængelige under Open Database License (ODbL) 1.0: https://opendatacommons.org/licenses/odbl/1-0/ (se også https://www.openstreetmap.org/copyright). De er ikke omfattet af værktøjets MIT-licens. Se [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).

Ret ikke filerne i hånden; hent et nyt kort med `python program\lav_vejkort.py analyser\<fil>.yaml --overskriv`.
