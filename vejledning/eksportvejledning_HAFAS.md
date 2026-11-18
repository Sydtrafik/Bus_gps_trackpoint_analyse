# Eksportvejledning: data fra HAFAS til analyse_v2.2.py

Denne vejledning siger, hvilke to tabeller der skal eksporteres fra HAFAS, hvilke kolonner værktøjet kræver, og hvad værktøjet siger, hvis noget mangler. Resten af værktøjet er beskrevet i [README.md](../program/README.md).

**Mærkning.** Det der står uden mærke, er målt: enten i værktøjets kode (kolonnenavne) eller i rigtige eksportfiler (en rigtig `Details.csv` og `List.csv` for bybus 3A i Esbjerg, 2025) eller ved at køre værktøjet. Det der er **IKKE AFPRØVET** er markeret med det ord, og samlet i afsnit 7.

## 1. De to filer

Pr. periode skal der bruges to CSV-filer:

| Fil | Indhold | Størrelse (bybus 3A, ca. 2-3 måneder) |
|---|---|---|
| `List.csv` | Turlisten: én række pr. tur. Giver retning (`Retningsflag`) og køredag pr. tur. | ca. 5 MB, ca. 8.600 ture |
| `Details.csv` | Detaljer pr. tur: én række pr. GPS-ping og én række pr. stop. GPS-pings hedder `Pegeredskab 1`, `Pegeredskab 2` ... i kolonnen `Stop-navn`. | ca. 9 mio. rækker, 1,3-1,5 GB |

Filerne skal dække de samme ture: værktøjet kobler dem på `List.csv`-kolonnen `Turnummer` = `Details.csv`-kolonnen `Turreference`.

Navnene `List.csv` og `Details.csv` er en konvention i eksemplerne. Værktøjet bruger de stier, der står i config-filen, så filerne må gerne hedde noget andet.

## 2. Åbn kolonnevalget i HAFAS

1. Højreklik på et kolonnenavn i tabellen.
2. Vælg **"Kolonner"** i menuen. Dialogen "Konfiguration tabel-kolonner" åbnes, med "Ikke synlige kolonner" og "Synlige kolonner", pile til at flytte kolonner mellem dem, og knappen "Gendan standard-indstillinger".
3. Flyt de ønskede kolonner til "Synlige kolonner" og luk dialogen. Eksportér derefter tabellen (se afsnit 5).

Kilde: skærmbilleder af dialogen for **turlisten**. Dialogen for **Details-tabellen** er ikke dokumenteret med skærmbillede (se afsnit 7).

## 3. Format

- CSV, semikolon (`;`) som skilletegn, UTF-8. Værktøjet læser med `sep=';'` og `encoding='utf-8'`. De rigtige eksportfiler vi har set, er UTF-8 med BOM; det virker.
- Første række er kolonnenavne. HAFAS sætter et tabulatortegn foran kolonnenavne og værdier, fx `"	Turreference"`. Værktøjet fjerner dem ved indlæsning.
- Koordinater med decimalkomma (`8,440226`) er i orden; værktøjet laver dem om til punktum.
- Datoer som `ÅÅÅÅ-MM-DD` (`2025-08-04`), tider som `TT:MM:SS` (`15:27:25`). `TT` og `TT:MM` accepteres også og fyldes op til `TT:MM:SS`. Formatet er fast i koden. **IKKE AFPRØVET:** andre formater (fx `04-08-2025`).
- Ekstra kolonner er harmløse: værktøjet læser kun de kolonner, der er nævnt nedenfor.

## 4. Kolonner

### 4.1 List (turlisten)

| Kolonne | Status | Bruges til |
|---|---|---|
| `Turnummer` | **Påkrævet** | Nøgle til `Details`-kolonnen `Turreference`. |
| `Retningsflag` | **Påkrævet** | Retning 1 eller 2. Afgør hvilken `point_order` og hvilke `stops` der gælder for turen. |
| `Køredag` | Valgfri, anbefalet | Periodefilter på turlisten og datoerne i kvalitetsoversigten. Uden kolonnen: `Køredag` er tom i `result.csv`, og `kvalitet_pr_dag.csv` er tom. |

**Standardopsætningen i HAFAS mangler `Retningsflag`.** Standardopsætningen for turlisten har disse kolonner: Køredag, Rute, Turnummer, Første stop (PLANLAGT), Afgang (første stop) (PLANLAGT), Afgang (første stop) - Forsinkelse, Sidste stop (PLANLAGT), Ankomst (sidste stop) (PLANLAGT), Ankomst (sidste stop) - Forsinkelse. `Retningsflag` skal altså slås til, før eksporten laves.

Hvad retning 1 og 2 betyder, afgøres af HAFAS. Se efter i `List.csv`: kolonnerne `Første stop (PLANLAGT)` og `Sidste stop (PLANLAGT)` viser, hvor turene med `Retningsflag` 1 og 2 starter og slutter. I eksporten for 3A starter retning 1 ved "Gjesing Nord, Thulevej (Esbjerg)" og retning 2 ved "Esbjerg Busterminal".

**To kolonner hedder `Turnummer`.** I den eksport for 3A vi har set, findes `Turnummer` to gange: først en lang 10-cifret værdi (det samme som `Turreference` i Details), senere et kort tal på 4-5 cifre. Værktøjet bruger den første. **IKKE AFPRØVET:** om standardopsætningens `Turnummer` er den lange nøgle. Tjek: åbn begge filer og se, at en værdi i `List.csv`'s `Turnummer` også findes i `Details.csv`'s `Turreference`.

**Personfølsomme kolonner.** Turlisten kan indeholde kolonner som Chauffør-ID og Telefonnummer. Værktøjet læser dem ikke, og ingen outputfil indeholder dem. Fjern dem alligevel fra eksporten, hvis de ikke skal bruges, så de ikke ligger i de filer, der deles.

### 4.2 Details (turdetaljer)

**Påkrævede** (værktøjet stopper før indlæsning, hvis en mangler):

| Kolonne | Bruges til |
|---|---|
| `Turreference` | Tur-nøgle (matcher `List`-kolonnen `Turnummer`). |
| `Stop-navn` | Skelner GPS-pings (`Pegeredskab N`) fra stop; grovfilter mellem start- og slut-stop. |
| `Stop-nummer` | Udfyldt = stop-række (planlagt position), tom = GPS-ping. |
| `Breddegrad (PLANLAGT)` | Position. For GPS-pings er det den målte position, for stop-rækker stoppets planlagte position. |
| `Længdegrad (PLANLAGT)` | Som ovenfor. |

Hertil kommer **mindst én dato-kolonne og mindst én tids-kolonne** fra listerne nedenfor. Pr. række bruges den første udfyldte i rækkefølgen. Hvilke kolonner der bruges, kan ændres i config (`date_columns`, `time_columns`).

| Dato-kolonner (prioritet) | Tids-kolonner (prioritet) |
|---|---|
| 1. `Ankomst-dato (REALTID)` | 1. `Tid (REALTID) (+sekunder)` |
| 2. `Afgangs-dato (REALTID)` | 2. `Ankomst-tid (REALTID)` |
| 3. `Ankomst-dato (PLANLAGT)` | 3. `Afgangs-tid (REALTID) (+sekunder)` |
| | 4. `Tid (PLANLAGT)` |

**Anbefalet: slå alle syv til.** I den rigtige eksportfil er GPS-pings (af de kolonner værktøjet bruger) kun udfyldt i `Ankomst-dato (REALTID)` og `Ankomst-tid (REALTID)`. Stop-rækker har `Tid (REALTID) (+sekunder)` og afgangs-kolonner; det første stop på en tur havde ingen ankomst. Med færre kolonner kan nogle rækker få intet tidsstempel (rækken er så ubrugelig til tidsmåling).

**Valgfri:**

| Kolonne | Uden den |
|---|---|
| `Projektion` | Advarsel; flaget `projektion_<punkt>` udelades. Værdien `X` betyder estimeret (ikke målt) position. |

Kolonnen `Nr.` er ikke nødvendig. Alle andre kolonner i Details læses ikke.

Til sammenligning: Details i den rigtige eksport vi har brugt har 52 kolonner (alle de ovenstående og bl.a. `Nr.`, forsinkelses-, belægnings- og km/h-kolonner). Det er et kendt fungerende sæt; det er ikke nødvendigt at slå alle til.

## 5. Eksportér

Eksportér hver af de to tabeller som CSV (`;`, UTF-8) for hver periode, fx til `data_A\List.csv`, `data_A\Details.csv`, `data_B\List.csv`, `data_B\Details.csv`. Vælg køredage i HAFAS, så de dækker perioden. Værktøjet filtrerer selv på periodens start og slut fra config, så en eksport, der er lidt bredere, er i orden.

**IKKE AFPRØVET her:** menupunktet eller knappen i HAFAS der eksporterer, valget af CSV, skilletegn og tegnsæt i HAFAS, og hvordan køredage og linje vælges i HAFAS. De er ikke beskrevet i det materiale, denne vejledning er skrevet fra. Krav til resultatet: se afsnit 3.

Store filer kan eksporteres som de er: `analyse_v2.2.py` læser `Details.csv` i bidder og holder kun rækkerne mellem de to stop i hukommelsen (målt: højst 2,2 GB RAM på en fil på 3,4 GB med 24 mio. rækker, ca. 9 min).

## 6. Hvad værktøjet siger, hvis noget mangler

Kolonnerne tjekkes først. Kun filens første række læses, og alle problemer samles i én besked, før den tunge indlæsning starter. Kørslen stopper med exit-kode 1.

Eksempel, målt: `Details.csv` uden `Breddegrad (PLANLAGT)` og uden datokolonner, og en `List.csv` uden `Retningsflag`:

```
  ADVARSEL (periode A): Details: valgfri kolonne mangler: Projektion (projektions-flag udelades)
  ADVARSEL (periode A): Details: kolonne fra prioritetskæden findes ikke og springes over: Ankomst-dato (REALTID)
  ADVARSEL (periode A): Details: kolonne fra prioritetskæden findes ikke og springes over: Afgangs-dato (REALTID)
  ADVARSEL (periode A): Details: kolonne fra prioritetskæden findes ikke og springes over: Ankomst-dato (PLANLAGT)
  ADVARSEL (periode A): List: valgfri kolonne mangler: Køredag (Køredag udelades)
FEJL: Kolonne-/filtjek fejlede - ret input eller config og kør igen:
  - Periode A: Details (Details.csv): PÅKRÆVEDE kolonner mangler: Breddegrad (PLANLAGT)
  - Periode A: Details (Details.csv): ingen af datokolonnerne findes (mindst én påkrævet): Ankomst-dato (REALTID), Afgangs-dato (REALTID), Ankomst-dato (PLANLAGT)
  - Periode A: List (List.csv): PÅKRÆVEDE kolonner mangler: Retningsflag
```

(Af pladshensyn er advarslerne om tids-kolonnerne udeladt her; de kommer på samme form.) Linjerne under `FEJL` er dem, der skal rettes. `ADVARSEL` er ikke fatale.

Andre fejl, målt:

| Problem i filen | Hvad værktøjet siger |
|---|---|
| Komma i stedet for semikolon | Alle påkrævede kolonner meldes manglende (hele headeren læses som én kolonne): `PÅKRÆVEDE kolonner mangler: Turreference, Stop-navn, Stop-nummer, Breddegrad (PLANLAGT), Længdegrad (PLANLAGT)` og tilsvarende for `List`. |
| Windows-1252 i stedet for UTF-8 | `FEJL: Kan ikke læse headeren i <sti>\Details.csv: 'utf-8' codec can't decode byte 0xe6 in position 2: invalid continuation byte` |
| Filen findes ikke (kørsel) | `Periode A: filen findes ikke: <sti>` under kolonnetjekket. |
| Filen findes ikke (`--list-stops`) | Kun en advarsel `Fil ikke fundet: <sti>`, derefter `0 unikke stop-navne` og exit-kode 0. Tjek stien, hvis listen er tom. |
| `Turnummer` i List svarer ikke til `Turreference` i Details | Kolonnetjekket består, men alle ture kasseres med årsag `ingen_retningsflag` ("ingen_retningsflag: N" i loggen). Hvis ingen tur matcher, stopper kørslen derefter med en Python-fejl (`ValueError: cannot concatenate unaligned mixed dimensional NDFrame objects` i `_day_table`): det er en fejl i v2.1, ikke i dine data. Årsagen står i linjen lige over fejlen. `kasserede_ture.csv` og `kvalitet.csv` er skrevet. |

## 7. Hvad er IKKE afprøvet

1. **Kolonnevalget for Details-tabellen i HAFAS** er ikke dokumenteret med skærmbillede. Kolonnenavnene i afsnit 4.2 er hentet fra værktøjets kode og fra en rigtig Details-fil, ikke fra HAFAS' dialog for Details.
2. **Selve eksporten** (menupunkt/knap, valg af CSV, skilletegn og tegnsæt, valg af køredage og linje i HAFAS).
3. **Minimalt kolonnesæt på en rigtig HAFAS-eksport.** Det mindste sæt (de fem påkrævede, ét dato- og ét tidsfelt, plus `Turnummer`/`Retningsflag` i List) er kørt gennem værktøjet på en konstrueret datafil, ikke på en eksport fra HAFAS.
4. **Om HAFAS' standard-`Turnummer` er nøglen** (afsnit 4.1).
5. **Andre datoformater, andre HAFAS-versioner, andre kolonnenavne** (fx engelsk brugerflade). Kolonnemapping findes ikke endnu. Kolonnenavnene står ét sted i koden (`COLUMNS` i `analyse_v2.2.py`); kolonnemapping i config er planlagt.
6. **Windows PowerShell 5.1.** Kommandoer i README er kørt i PowerShell 7.
