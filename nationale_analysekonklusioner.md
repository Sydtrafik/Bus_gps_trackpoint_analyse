# Nationale analysekonklusioner

Afsluttede trackpoint-analyser i hele landet, så vi kan lære af hinandens fund. Tallene er medianer på hverdage for ture **uden standsning ved stop**, begge retninger.

**Laves af** `program/lav_konklusioner_html.py` ud fra filerne i [analyser/](analyser/) (én fil pr. analyse). Ret aldrig denne fil i hånden. Se tabellen med graf, filtre og tegninger i `nationale_analysekonklusioner.html`. Sådan tilføjer du din analyse: [CONTRIBUTING.md](CONTRIBUTING.md).

**Senest opdateret:** 2026-11-25 · 1 analyse(r)

| Vej, by | Type | År | Længde | Fartdæmpere | Hastighed (km/t) | Køretid (s) | Ændring | Pr. 100 m | Laveste fart ved fartdæmper (km/t) | Mærkbar opbremsning (%) | Ture |
|---|---|---|--:|---|---|---|--:|--:|---|---|---|
| [Kvaglundvej, Esbjerg](analyser/kvaglundvej_esbjerg_2025.yaml) | Før/efter | 2025 | 626 m | 2 sinusbump, 2 indsnævringer | 50 → 40 | 54 → 66 | +12 s | 1,9 | 42 → 25 | 16 → 64 | 2.516 → 4.095 |

Ændring = køretid efter minus før. Pr. 100 m = ændringen delt med strækningens længde, så strækninger af forskellig længde kan sammenlignes. Laveste fart ved fartdæmper = median af den laveste fart pr. tur ved fartdæmperne (bump o.l.); tom, hvis analysen ikke har målt den.

## Kvaglundvej, Esbjerg (2025)

- **Ændring:** 2 sinusbump + 2 indsnævringer, 50 → 40 km/t (anlagt 26/9-17/10 2025)
- **Perioder:** før 2025-06-30 til 2025-09-25 (44 hverdage); efter 2025-10-18 til 2026-01-04 (51 hverdage)
- **Vejtype:** Gennemkørselsvej i boligkvarter
- **Linje(r):** 3A, begge retninger (ca. 129 ture pr. hverdag)
- **Bustype:** Elbusser (alle ture); længde ikke oplyst
- **Mærkbar acceleration (% af turene):** 18 → 47
- **Gennemsnitsfart (km/t):** 42 → 34
- **Ekstra tid pr. element (s, interval, kan ikke lægges sammen):** Indsnævring 2 0,1–0,8; Indsnævring 1 0,4–1,4; Bump 2 2,9–4,0; Bump 1 2,5–3,6; Øvrig strækning 1,6–5,4; Hele strækningen 11,3
- **Vejregler:** Vejreglerne har ingen passagehastighed for almindelige sinusbump (kun modificeret sinusbump til 50 km/t: 35 km/t), så den målte fart er ikke sammenlignet. Håndbog Fartdæmpere anbefaler at undgå bump på veje med busser i fast rute.
- **Forbehold:** Ingen sammenligningsstrækning: tallene viser, hvad der skete samtidig med bumpene.
- **Forbehold:** Bump, indsnævringer og den lavere hastighedsgrænse kom på samme tid, så tallene kan ikke skille deres virkning ad.
- **Forbehold:** Linje 3A kørte ikke strækningen 11/8-5/9 2025 (omkørsel); de dage er ikke med.
- [Strækningen i Google Maps](https://www.google.com/maps/dir/?api=1&origin=55.48511,8.47295&destination=55.48041,8.46749&travelmode=driving)
- **Kontakt:** Sydtrafik (GitHub: Anfuth) · opdateret 2026-11-25
