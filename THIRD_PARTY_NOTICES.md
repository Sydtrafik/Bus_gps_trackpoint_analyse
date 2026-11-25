# Tredjepart: biblioteker, data og kilder

Værktøjets egen kode er under MIT-licensen (se [LICENSE](LICENSE)). Det følgende er ikke omfattet af den.

## Biblioteker, der følger med (`program/rapport/vendor/`)

Bibliotekerne indlejres i hver rapport, så rapporten virker uden internet. Leaflet indlejres også i `nationale_analysekonklusioner.html` (med licensteksten).

| Bibliotek | Version | Licens | Filer |
|---|---|---|---|
| Apache ECharts | 5.6.0 | Apache License 2.0 | `echarts.min.js`, licens: `ECHARTS-LICENSE.txt`, notits: `ECHARTS-NOTICE.txt` |
| Leaflet | 1.9.4 | BSD 2-Clause | `leaflet.min.js`, `leaflet.min.css`, licens: `LEAFLET-LICENSE.txt` |

ECharts' NOTICE-fil (gengivet uændret, som Apache License 2.0 § 4(d) kræver):

```
Apache ECharts
Copyright 2017-2024 The Apache Software Foundation

This product includes software developed at
The Apache Software Foundation (https://www.apache.org/).
```

## Kortdata

Slås kortet til i en rapport (`kort: true`), og når `nationale_analysekonklusioner.html` viser kortet over en analyses punkter, hentes kortfliser fra OpenStreetMap (`tile.openstreetmap.org`). Kortdata © OpenStreetMap-bidragydere, tilgængelige under Open Database License (https://www.openstreetmap.org/copyright). Brugen skal følge OSM's tile-politik (https://operations.osmfoundation.org/policies/tiles/): let brug og synlig kildeangivelse. Læserens IP-adresse sendes til OSM's server, når kortet vises.

## Vejregler og bumptegninger

Tegningerne i `vejledning/kilder/bumptyper/` er egen optegning efter mål og tabelværdier i Vejdirektoratets håndbogsbilag *Geometrisk udformning af vejbump* (juni 2026) og *Katalog over typegodkendte bump* (2002); de er ikke Vejdirektoratets figurer. Kilden står på hver tegning. Vejdirektoratets dokumenter følger ikke med; de hentes på vejregler.dk.

## Varemærker

HAFAS er et varemærke, der tilhører sin ejer. Værktøjet læser en eksport fra HAFAS og er ikke tilknyttet eller godkendt af ejeren.
