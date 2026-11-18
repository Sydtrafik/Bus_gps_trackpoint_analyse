# Formidling og grafik: guide til rapporter med pakken

Til dig, der laver en rapport med værktøjet (eller beder en kodeagent om det). Rapportens kontrolkrav, titel-pladsholder og direkte navne er bygget ind i skabelonen. Reglerne er **eksempler fra praksis, ikke love**: afvig, når modtageren kræver det, og skriv hvorfor. Hvordan rapporten bygges: [README.md](../program/README.md), trin 9. Hvad der er regnet: [metode_og_rapportering.md](metode_og_rapportering.md).

## 1. Rapporttype og budskab

Spørg først: hvem læser rapporten, hvordan (mail, møde, print), og hvad skal de bruge den til?

**Budskab i én sætning:** hvad er svaret, og hvad betyder det for modtageren? Eksempel: "Køretiden steg 12 s samtidig med, at bumpene kom." Kan det ikke siges i én sætning, er analysen ikke færdig. Budskabet er en hypotese, indtil data dækker det.

**Rapporttype:** vælg sammen med bestilleren.

| Type | Til | Første skærm | Titler | Interaktion |
|---|---|---|---|---|
| Prærapport (intern) | finde pointer og dataudfald | alle grafer, ingen tolkning | beskrivende | alt |
| Datarapport | den, der vil have tallene | få grafer, detaljer bag en knap | beskrivende | filtre |
| Analyserapport | forklare et fund | svaret og 3-5 pointer med tal | siger fundet | filtre på analysesiderne |
| Præsentationsrapport | ledelse, politikere, presse | ét budskab, få pointer pr. side | siger fundet | næsten ingen, eller få enkle valgknapper (fx strækning, retning, med/uden standsning ved stop) |

**Pakkens skabelon er en præsentationsrapport med få fund og lidt interaktion:** få valgknapper, ingen tabeller med rådata, og en lille tabel kun til intervaller. "Præsentation med enkle valgknapper" er en gyldig variant af præsentationsrapporten, ikke en datarapport. Fordi knapperne ændrer billedet, har graferne **beskrivende titler**, og fundet står i en beregnet linje ved grafen (afsnit 2). Skal modtageren have tallene, så lav en datarapport ved siden af, ikke i stedet.

Byg først en prærapport, udled pointer, vælg de vigtigste, og byg så modtagerens rapport. Hver feedback-runde må også **fjerne** noget.

## 2. Titler, der siger fundet

- Brug **"Køretiden steg 12 s"**, ikke "Køretid", på pointe-sider i analyse- og præsentationsrapporter.
- Hvor et filter (retning, med/uden standsning ved stop) ændrer billedet, bliver en fast titel med et fund forkert ved filterskift. Brug en **beskrivende titel**, og lad pointen stå i en linje ved grafen, helst beregnet ud fra de viste tal.
- Ingen mærkater som "Usikkert" på grafer. Konklusionen står i teksten.
- **Logiktest:** titlerne læst i rækkefølge fortæller historien, og alt på en side støtter sidens titel. Resten flyttes bag en knap eller i et bilag.

## 3. Tekstregler

- **Kun målte fakta.** Hver påstand kan findes i en graf eller tabel. Det, der ikke er målt, er en antagelse og står som forbehold.
- **"Samtidig med", ikke "fordi".** Uden kontrolstrækning kan årsag ikke påvises.
- **Komfort betyder passagerkomfort i kørslen på hele strækningen** (opbremsning og acceleration langs vejen), ikke stødet over selve bumpet; GPS hvert sekund kan ikke måle det. Overskrifter ved komforttal nævner komfort ("Komfort: ...", "Passagerkomfort: ..."), og forklaringen står i ⓘ og i metoden, ikke i noten under grafen.
- **Få ord og én pointe pr. element og pr. graf.** Forklar én gang, ét sted. Metode ligger i det foldede afsnit.
- **Svaret først**, så forklaringen. **Ét ord pr. begreb** og samme betegnelse for hver periode overalt.
- **Forskelle i ord:** "Andelen steg 2 procentpoint", ikke "forskel +2". Upræcise ord ("ca.", "lidt") kun ved tal; præcise ord ("steg", "faldt") uden tal. Gentag ikke tal, der står lige under.
- Et forbehold siger, hvad der er tjekket. Tal, der sammenlignes, står i en lille tabel.

## 4. Nøgletal

- Et nøgletal forklarer sig selv: **enhed, periode og afgrænsning** står i kortet ("median, ture uden standsning ved stop"). Kræver det en lang note, er det ikke et nøgletal.
- Ændringer regnes af de viste, afrundede tal (54 → 66 s giver +12 s).
- Procent af meget få ture vises som "-", og antal ture står ved siden af.

## 5. Grafvalg og grafintegritet

- **Udvikling** = linje. **Få grupper** = søjler. **Fordeling** = bånd eller histogram. **Ændring** = vandrette søjler om nul med tallet ved søjlen.
- **Søjler starter i nul.** Linjer må have afkortet akse, hvis den er tydelig. Ingen 3D, ingen sekundær y-akse.
- **Samme måling i grafer side om side har samme skala.**
- **Fremhæv højst ca. 10 % af fladen:** én serie i farve, resten grå. Se på et screenshot i 5 sekunder: lander blikket, hvor titlen peger?
- **Vis usikkerhed eller nævn den.** Et bånd forklares på siden, ikke kun i tooltip. Ingen årsagsord, når data kun viser samtidighed.
- Lyse, vandrette gitterlinjer, ingen skrå tekst, få skriftstørrelser.
- **Farve er aldrig eneste kode:** navnet står ved farven, og tallet ved søjlen, især ved grøn/rød.

## 6. Direkte navne og legende

- Ved op til ca. 5 serier i en statisk graf: **navnet direkte ved linjen eller søjlen**, ikke i en forklaring ved siden af.
- En legende kan **ikke klikkes**, medmindre det at skjule en serie hjælper læseren. Et klikbart signal lover en funktion.
- Samme kategori har samme farve i alle grafer, tabeller og knapper.

## 7. Interaktion kun, hvor den gør noget

- Filtre og knapper skal ændre noget, læseren har brug for (fx retning). Resten fjernes eller ligger bag "Sådan har vi målt".
- **Hover-markering** (skygge, fremhævning) kun på grafer, hvor et klik filtrerer. På de øvrige en tynd hjælpelinje til aflæsning eller intet.
- Ingen animation. Tooltips tilføjer noget (fordeling) og gentager ikke bare tallet.
- Test på ca. 375 px bredde uden vandret scroll.

## 8. Farver og kontrast

- **Alle farver er variabler** (`:root` øverst i skabelonen). Ret dem ét sted.
- **Kontrast beregnes, ikke vurderes med øjet** (WCAG AA): tekst mindst **4,5:1** mod baggrunden, stor tekst 3:1. Relativ luminans L = 0,2126·R + 0,7152·G + 0,0722·B (lineariseret sRGB); kontrast = (L lys + 0,05) / (L mørk + 0,05).
- **Tekst på farve:** vælg sort eller hvid efter beregning (hvid på en mellemtone giver ofte under 3:1). Datalabels på mellemtoner står uden for søjlen i tekstfarven.
- **Datamærker, der bærer budskabet:** mindst 3:1 mod baggrunden. Nedtonede kontekstserier (resten grå) må ligge lavere. Er en farve under 3:1, står navnet eller tallet ved mærket.
- Grøn mod rød kræver tal ved siden af. Mørk mod lys (fx blå mod orange) er farveblind-sikkert.

## 9. Dansk dato- og talformat

- Dato med dagen først: **27-09-2026**, kun dag og måned 27-09. I løbende tekst med ord og uden "d.": "fra 29. maj til 13. august". Sortér på en ISO-nøgle bag visningen.
- Tal: punktum som tusindtalsseparator, komma som decimal (1.350 og 2,6), mellemrum før enhed (12 s, 16 %), minus som "−", intervaller med bindestreg ("2,6-3,6 s"). Tomme tal vises som "-".

## 10. Tjekliste før deling

**Må ikke ske:** forkert graftype · misvisende skala · farve som eneste kode · tekst under 4,5:1 · påstand uden belæg i en graf eller tabel · graf, der modsiger teksten uden note · rådata, tur-id'er eller interne stier i filen.

**Bør rettes:** ingen tydelig pointe på en pointe-side · over ca. 5 linjer eller 15 søjler uden gruppering · enhed, periode eller afgrænsning mangler · uklar definition · årsagsord uden belæg · klikbart signal uden funktion.

**Pynt:** blandede størrelser eller farver for samme ting · tunge gitterlinjer · samme forklaring flere steder.

Til sidst: budskabet kan siges i én sætning · første skærm viser svaret og graferne, ikke metode · samme begreb og farve overalt · tal i teksten passer til graferne · afsender, kilde, udtræksdato og forbehold står i fodnoten.

**Friske øjne:** lad en anden eller en agent læse kun teksten og screenshots (med alle detaljer åbne), uden kode og data, og skrive højst 12 fund: hvad læseren ser, hvorfor det forvirrer, forslag. Rigtige tal er ikke det samme som en forståelig rapport.

---

*Kilder.* Budskab i én sætning, titler, der siger fundet, logiktest, 10 %-reglen og tjeklisten (må ikke ske / bør rettes / pynt) er tilpasset fra **dataink** (github.com/oh-da/dataink, MIT-licens, © 2026 Ohad Dahan), som bygger på Knaflic, Few og Tufte. Teksten er en tilpasning, ikke en kopi. Resten bygger på erfaringer fra rapporter, Sydtrafik har lavet til kommuner og andre bestillere (2026), målt på få rapporter og dermed eksempler. Sydtrafik er afsender af værktøjet. Kontrastkravet er WCAG 2.x AA.
