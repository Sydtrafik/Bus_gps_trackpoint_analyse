# Metode og rapportering: hvad vi rapporterede, hvordan og hvorfor

Dette dokument beskriver, hvad Sydtrafik rapporterede i analysen af to vejbump og to indsnævringer på Kvaglundvej i Esbjerg (bybus 3A, 2025), **hvordan** tallene er regnet, og **hvorfor** vi valgte og fravalgte som vi gjorde. Det er skrevet, så du kan lave en tilsvarende analyse og rapport for din egen strækning. Tal er målte fakta fra Kvaglundvej og bruges som eksempel; de gælder ikke din strækning.

Værktøjets brug står i [README.md](../program/README.md), agentinstruktion i [AGENTS.md](../AGENTS.md).

## 1. Hvad vi rapporterede (eksempel: Kvaglundvej)

Rapporten er en **præsentationsrapport med få fund og lidt interaktion**: få valgknapper (strækning, retning, med/uden standsning ved stop), ingen tabeller med rådata. Opbygningen i skabelonen følger den. Rapporttyper, titler, tekst og tjekliste står i [formidling_og_grafik.md](formidling_og_grafik.md).

**Grundlag.** Linje 3A, strækning på 626 m med to bump (110 m og 230 m fra start), to indsnævringer (395 m og 597 m) og to stoppesteder. Periode A (uden bump): 30/6-25/9 2025. Periode B (med bump): 18/10 2025-4/1 2026. 26/9-17/10 var anlægsperiode og er ikke med. Hverdage: A 44 dage og 3.995 ture, B 51 dage og 6.580 ture. Linje 3A kørte ikke strækningen 11/8-5/9 2025 (omkørsel); de 26 dage er automatisk kasseret og ikke med.

**Fire nøgletal** (medianer, ture uden standsning ved stop, begge retninger):

| Nøgletal | Før | Efter |
|---|---|---|
| Køretid over strækningen | 54 s | 66 s (+12 s) |
| Laveste fart ved bumpene (gennemsnit af de to) | ca. 42 km/t | ca. 25 km/t |
| Ture med mærkbar opbremsning | 16 % | 64 % |
| Ture med stillestand på strækningen (alle ture) | 37 % | 38 % |

**Fartprofil** langs strækningen (median og p25-p75-bånd pr. 10 m, før og efter) med elementerne markeret. Før: flad fart på 40-45 km/t. Efter: to tydelige fartdyk præcis ved bumpene (laveste median ca. 25-27 km/t), og lavere fart på resten af strækningen. Gennemsnitsfart: 42 km/t før, 34 km/t efter (ture uden standsning ved stop).

**Køretid med og uden standsning ved stop:** 54 s til 66 s uden standsning, 77 s til 87 s med standsning. Køretiden steg i begge grupper.

**Komfort** (andel ture med mindst én mærkbar hændelse, ture uden standsning ved stop, begge retninger): opbremsning 16 % til 64 %, acceleration 18 % til 47 %, opbremsning eller acceleration 24 % til 72 %. Til sammenligning havde næsten alle ture med standsning ved stop mærkbar opbremsning før bumpene, og 77 % havde kraftig. Se afsnit 2.4 for, hvad komfortmålet er, og hvad det ikke er.

**Hvor sidder den ekstra køretid** (zoner på ±60 m, gennemsnit pr. tur, ture uden standsning ved stop, begge retninger, interval):

| Element | Ekstra tid pr. tur |
|---|---|
| Bump 1 | 2,6-3,6 s |
| Bump 2 | 3,0-4,0 s |
| Indsnævring 1 | 0,4-1,4 s |
| Indsnævring 2 | 0,1-0,9 s |
| Øvrig strækning | 1,5-5,3 s |
| Hele strækningen | 11,3 s |

Bumpene giver ca. 2,6-4,0 s hver, indsnævringerne højst ca. 1,4 s hver, og resten ligger spredt på den øvrige strækning. Med zoner på ±40 m giver bumpene 2,1-3,2 s.

**Drift:** ekstra køretid ca. 22,8 min pr. hverdag (64,4 ture × 9,94 s i den ene retning plus 64,6 ture × 11,23 s i den anden), 7,6-8,7 timer pr. måned (20-23 hverdage), 258 bump-passager pr. hverdag (129 ture × 2 bump). **Køretid pr. måned:** 59-62 s før og 71-72 s efter; stabil inden for hver periode.

**Forbehold:** ingen sammenligningsstrækning, så tallene viser, hvad der skete samtidig med bumpene; omkørselsdagene er ikke med.

## 2. Hvordan: definitioner og metode

### 2.1 Datagrundlag og udvalg af ture

- **Data:** bussernes GPS-pings fra realtidssystemet (HAFAS), ca. ét ping pr. 1-2 sekunder. Pings fra Kvaglundvej: 1,7 s mellem pings før, 2,0 s efter (65 % mod 40 % af intervallerne på 1 s).
- **Gyldig tur:** tom `Log` i `result.csv` (nærmeste ping til hvert målepunkt ligger højst 200 m væk), ingen målepunkter matchet på en stoprække (flag `stoprække_`), og komfort-trinnet har `status = ok` (fuld passage af strækningen uden huller på over 10 s mellem pings). På Kvaglundvej: 14.022 af 14.320 ture er gyldige.
- **Hverdage:** mandag-fredag, uden 24., 25., 26. og 31. december og 1. januar. Hverdage er hovedopgørelsen; alle dage, hverdage uden skoleferie og delperioder af A gav samme billede (køretid +9 til +14 s, fald i laveste fart ved bumpene 15,6-19 km/t).
- **Uden standsning ved stop:** den udglattede fart kommer ikke under 3,6 km/t (1 m/s) et sted på strækningen (kolonnen `stillestand = 0` i `komfort.csv`; i data og config hedder gruppen `Uden stop`). **Med standsning ved stop:** den kommer. Betegnelsen siger, hvad bussen gør, ikke om der ligger et stoppested på strækningen. Gruppen tæller også standsning i kø, for rødt lys eller for vigepligt; på Kvaglundvej var forskellen på standsning ved stoppested og stillestand uanset årsag 0,1-0,4 % af turene. Har din strækning signal eller vigepligt, så tjek det, og skriv det under forbehold.
- Perioderne skal vælges, så de kan sammenlignes; værktøjet korrigerer ikke for sæson, trafik, skolestart eller køreplan.
- **Datatilgængelighed:** realtidssystemet (HAFAS) gemmer kun ca. 3 måneder tilbage. En før-periode skal derfor eksporteres i god tid, **før ændringen sker**, ellers er den væk. Planlæg eksporten, så snart en ændring er besluttet.
- **Én periode:** værktøjet kan også bruges til at måle kørslen i ét område uden sammenligning (periode A alene). Så vises niveauer i stedet for før og efter: køretid, fartprofil, komfort og tid pr. zone. Ekstra køretid, intervaltabel og drift findes kun med en sammenligning.
- **Flere strækninger:** flere strækninger kan defineres i samme analyse (hver med fra- og til-punkt og egne elementer) for at isolere områder og effekter. Komfort og zonetid regnes pr. strækning, og rapporten har en strækningsvælger.

### 2.2 Køretid, fart og hastighed

- **Køretid** er tidsforskellen (hele sekunder) mellem det ping, der ligger nærmest startpunktet, og det, der ligger nærmest slutpunktet. Ingen interpolation, så tidsfejlen pr. tur er op til et halvt ping-interval (tilfældig, ikke systematisk). Brug medianer og antal ture, ikke enkelte ture.
- **Fart og acceleration** regnes ud fra GPS-positionen alene: positionen projiceres på den rette linje fra startpunkt til slutpunkt, interpoleres til et 1 s-gitter og udglattes med Savitzky-Golay (vindue 5 s, polynomium af grad 2). Fart er 1. afledte, acceleration 2. afledte. Der er ingen accelerometer.
- **Tjek af GPS-farten:** mod busudstyrets egen maksimalfart (512 ture på en 403 m lang strækning) var forskellen i median højst 0,3 km/t, korrelation 0,98-0,99.
- **Laveste fart ved et element:** mindste udglattede fart i et vindue om elementet (`komfort.bump_vinduer`, meter fra start). Det er et bedre mål end hastigheden ved et punkt i `result.csv`, der er minimum af 5 pings og afhænger af ping-tætheden. De to definitioner gav samme fald på Kvaglundvej.

### 2.3 Hændelser og klasser

- En **hændelse** er et sammenhængende forløb på mindst 2 sekunder, hvor opbremsningen (eller accelerationen) er over en tærskel.
- Tærsklerne er **0,75 og 1,35 m/s² på den udglattede (SG 5 s) skala**. Det svarer til ca. **1,0 og 1,8 m/s²** på en uudglattet skala, som er de grænser, forskningen bruger for stående buspassagerer (Krašna m.fl. 2021; Keller og Krašna 2023, se afsnit 5). Udglatningen over 5 s bevarer ca. 70-90 % af en reel top på 8-12 s (simulering), derfor er tærsklen skaleret med ca. 0,75.
- **Mærkbar** = mindst én hændelse over den første tærskel. **Kraftig** = mindst én over den anden. Rapporten viser opbremsning, acceleration og samlet (opbremsning eller acceleration).
- Absolutte niveauer er en underkant. Brug samme metode og udglatning i før og efter.

### 2.4 Hvad komfortmålet er, og hvad det ikke er

**Komfortmålet er passagerkomfort i kørslen på hele strækningen:** opbremsning og acceleration langs vejen, altså fart frem og tilbage (længdeaccelerationen), målt fra strækningens startpunkt til slutpunkt. Opbremsningen ned mod et bump og accelerationen væk fra det er en del af det. Det er det, en stående passager mærker som at blive skubbet frem ved opbremsning og tilbage ved acceleration.

**Det måler ikke stødet op og ned, når bussen kører over selve bumpet.** GPS hvert sekund kan ikke måle det: et stød varer brøkdele af et sekund, og positionen har en usikkerhed på flere meter. Skriv derfor aldrig i en rapport, at bumpet "er hårdt" eller "giver stød" ud fra dette mål. Skriv "opbremsning og acceleration i kørslen på strækningen". Vil du belyse stødet, kræver det et accelerometer eller en måling i bussen.

### 2.5 Zonetid: hvor sidder den ekstra køretid?

1. Strækningen deles i **zoner på ±60 m** om hvert element (bump, indsnævring, andet). Overlap mellem to zoner deles på midten. Det, der er tilbage, er den **øvrige strækning**.
2. Pr. tur måles tiden i hver zone som tidspunktet for passage af zonens slutgrænse minus startgrænse (position interpoleret til 1 s-gitter, gjort monoton i kørselsretningen). Kun ture med fuld passage.
3. **Gennemsnit** pr. zone og periode. Elementets **øvre grænse** er hele den ekstra tid i zonen (efter minus før). Den **nedre grænse** er det, der er ud over, at farten også er lavere på den øvrige strækning: efter minus før × f, hvor f er forholdet efter/før på den øvrige strækning. For den øvrige strækning er nedre grænse den rå ekstra tid dér, og øvre grænse den plus den generelle del inde i element-zonerne.
4. Intervallerne kan ikke lægges sammen. Summen af øvre grænser overstiger totalen.
5. Zonebredden er et valg: ±40 m giver et lidt smallere interval for bumpene (2,1-3,2 s mod 2,6-4,0 s ved ±60 m). Rapporten viser ±60 m i tabellen og ±40 m som følsomhed.

### 2.6 Middel eller median

- **Medianer** i nøgletal, fartprofil, køretid og månedsgrafen: robuste over for enkelte ture med ventetid eller huller.
- **Gennemsnit** i zonetid og drift: gennemsnit kan lægges sammen (zonerne summerer til strækningen), og ekstra køretid pr. dag er gennemsnitlig ekstra tid × antal ture. Rapporten skriver det, hvor det er gennemsnit.
- Drift: (gennemsnitlig køretid efter minus før) × ture pr. hverdag efter, pr. retning, lagt sammen. Gælder alle ture, uanset stop-valg.

### 2.7 Stoprækker bruges ikke

I HAFAS' detaljefil har stop-rækker (planlagte positioner) et tidsstempel, der ligger **efter** bussens passage: i 61.865 stoprækker (3A, før og efter) lå bussen median 75-85 m forbi stoppet (90 % under ca. 112 m, loft ca. 115 m), og tidsstemplet var median 8-9 s efter nærmeste ping. Stopkoordinaten er præcis (nærmeste ping 6 m). Derfor bruges stop-rækker hverken til fart, komfort eller zoner, og ture, hvor et målepunkt blev matchet på en stoprække, flagges og udelades (65 af 14.320 ture på Kvaglundvej).

## 3. Hvorfor: valg og fravalg

1. **Komfort for ture uden standsning ved stop.** Opbremsningen til et stop dominerer: ture med standsning ved stop har max opbremsning ca. 1,7-1,8 m/s² både før og efter og skjuler effekten af bumpene. Derfor er komfortgrafen og nøgletallet for ture uden standsning ved stop som standard; "alle ture" og "med standsning ved stop" kan vælges. En almindelig standsning ved stop giver næsten altid en mærkbar opbremsning (99,7 % af turene med standsning før bumpene) og oftest en kraftig (77 %). Rapporten viser det som sammenligning under komfortgrafen, så læseren kan se, at en mærkbar opbremsning er det niveau, et almindeligt stop næsten altid når. Køretiden vises for begge grupper, fordi den steg i begge.
2. **Interval i stedet for ét tal for hvert element.** Det kan ikke afgøres ud fra data, om den generelt lavere fart (ca. 10 % mere tid på den øvrige strækning) også gælder inde ved bump og indsnævringer. Øvre grænse antager, at al ekstra tid i zonen skyldes elementet; nedre grænse antager, at zonen er lige så meget langsommere som resten. Et punktestimat ville foregive en præcision, vi ikke har.
3. **Ingen signifikanstest.** Ture fra samme dag og samme kørsel er ikke uafhængige, så en test ville overdrive sikkerheden. I stedet vises spredning (p25-p75) og stabilitet over tid: ugemedianer før og efter overlapper ikke (køretid i retning 2: 54-59 s før, 66,5-71 s efter; typisk ændring fra uge til uge 1-1,5 s mod et spring på 13 s).
4. **Stoprækker bruges ikke.** Forsøg på at rette dem fejlede: korrektion af tidsstemplet (forsinkelsen er ikke fast pr. stop, 20-40 s mellem p10 og p90), og nærmeste GPS-ping i stedet (346 af 376 stoprække-matchede punkter havde nærmeste ping over 200 m væk, fordi GPS-hullet dækker hele strækningen). Turene med stoprække-match er 0,4-0,5 % af turene.
5. **Hverdage som hovedopgørelse, andre udvalg som robusthed.** Det holder sammenligningen ens og viste samme billede i alle varianter. Ingen tal pr. chauffør eller pr. kørselstime (ikke relevant for fundet).
6. **Zonebredde ±60 m.** Vores valg: zoner, der er brede nok til at rumme fartdykket om et element, men smalle nok til, at der er øvrig strækning tilbage mellem elementerne. ±40 m vises som følsomhed, så læseren kan se, hvor meget valget betyder.
7. **Ingen kontrolstrækning, derfor "samtidig med".** Sæson og andre samtidige ændringer kan ikke skilles fra bumpene. Fartdykkene sidder præcis ved bump-positionerne og findes ikke før, men det er ikke testet mod sæson. Rapporten skriver, hvad der skete samtidig med bumpene, og ikke hvad bumpene forårsagede.
8. **Rapport som præsentation med enkle valgknapper.** Få fund, få ord, lidt interaktion (få valgknapper, ingen tabeller med rådata), ét budskab pr. graf. Fordi knapperne ændrer billedet, har graferne beskrivende titler, og fundet står i en beregnet linje. Detaljer og definitioner ligger i et foldet afsnit ("Sådan har vi målt"), ikke i hovedteksten.

## 4. Det, der ikke er målt, og forbehold

- Årsager: værktøjet siger, hvor meget køretid, fart og komfort ændrede sig, ikke hvorfor.
- Stød over selve bumpet (afsnit 2.4), rettidighed, passagerernes oplevelse (komfort er afledt af GPS) og vejlængde (alle afstande er luftlinje).
- Ping-raten kan ændre sig mellem perioder (Kvaglundvej: 1,7 s før, 2,0 s efter). Tyndede man før-perioden ud til mindst 2 s mellem pings, blev forholdet mellem efter og før det samme. Tidsfejlen pr. tur er tilfældig (op til ca. ±0,5-1 s), ikke bias.
- `buffer_rows` er antal rækker, ikke meter eller sekunder; `Antal Stop` i `result.csv` er derfor ikke antal stop på strækningen. Brug `stillestand` fra komfort-trinnet.
- Små afvigelser, der ikke ændrer fundene: 1 s-gitteret udelader det sidste ping i korridoren (se [AGENTS.md](../AGENTS.md)).

## 5. Regler for rapporttekst

- **Kun målte fakta.** Hver påstand skal kunne findes i data. Ord uden tal skal være præcise ("steg", "faldt"); upræcise ord ("ca.", "omkring") kun ved tal.
- **"Samtidig med", ikke "fordi".** Uden kontrolstrækning kan årsag ikke påvises.
- **Få ord.** Titel, der siger fundet, hvor intet filter ændrer billedet, og først når fundet er verificeret; beskrivende titel og beregnet pointe ved filtrerede grafer (se [formidling_og_grafik.md](formidling_og_grafik.md)); ingen forklarende afsnit i hovedteksten.
- **Én pointe pr. element og pr. graf.**
- **Komfort = passagerkomfort i kørslen på hele strækningen** (opbremsning og acceleration langs vejen), aldrig "stød". Overskrifter ved komforttal nævner komfort; forklaringen står i ⓘ og her, ikke i noten under grafen.
- **Intervaller kan ikke lægges sammen**; skriv det ved tabellen.
- **Tal med enhed og antal.** Skriv antal dage og ture, så læseren kan vurdere grundlaget.
- Forbehold i en kort boks nederst; definitioner i det foldede afsnit.

## 6. Kilder

- [formidling_og_grafik.md](formidling_og_grafik.md) er delvist tilpasset fra **dataink** (github.com/oh-da/dataink, MIT-licens, © 2026 Ohad Dahan), som bygger på Knaflic, Few og Tufte. Kontrastkravet er WCAG 2.x AA.
- Krašna, S., Keller, A., Linder, A., Silvano, A. P., Xu, C., Thomson, R. og Klug, C. (2021). *Human Response to Longitudinal Perturbations of Standing Passengers on Public Transport During Regular Operation.* Frontiers in Bioengineering and Biotechnology 9:680883. Slæde-forsøg med stående frivillige; opbremsning på 1,0 m/s² var den eneste testede puls, hvor de kunne genvinde balancen uden kompenserende skridt; forfatternes anbefalede tærskelinterval for offentlig transport er 1,0-1,8 m/s².
- Keller, A. og Krašna, S. (2023). *Accelerations of public transport vehicles: A method to derive representative generic pulses for passenger safety testing.* Frontiers in Future Transportation 4:931780. Målinger i Zürich-busser: typisk opbremsning 0,12-0,15 g, maksimalt 0,279 g.
- Der findes ingen verificeret kilde til grænser for jerk (3. afledte) i busser; jerk bruges derfor ikke.
