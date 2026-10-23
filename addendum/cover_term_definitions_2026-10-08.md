# Cover-term thickness definitions by legend system (research report, 2026-10-08)

These definitions were compiled for the ArcSurf addendum from the published sources listed at the end. Quotes are verbatim and short; S-numbers refer to the source list at the end. The values used in the addendum are encoded in `scripts/addendum_params.py` (`COVER_DEFS`, `SRC_SYSTEM`). They were checked against the crosswalks of the sources:
- Québec: only `Tm` is coded veneer and only `Tc` blanket; `Tb`, till bosselé, is not read as blanket.
- Finland: kalliomaa, i.e. rock with a thin cover, is veneer; thin peat is veneer and thick peat is blanket.

| Legend system | Term | Thickness | Verbatim quote | Citation | Confidence |
|---|---|---|---|---|---|
| GSC Surficial Data Model (v2.0 / 2.3.0 / 2.5.1) | veneer (Tv, Mv, GMv, GLv, Lv, Av, Ev, Cv, GFv, Wv) | < 2 m | "Till veneer sediments < 2 m." | S1 App. 4; S2 App. A ("Feature notes" = "<2 m"); S3 Table 2, p. 117 | stated |
| GSC SDM | blanket (Tb, Mb, ...) | > 2 m | "Till blanket sediments > 2 m." | S1, S2, S3 | stated |
| GSC SDM | Ov / Ob | none | Feature notes "nil" | S2 | not stated |
| CGM 219 (example) | Tv / Tb | < 2 m / > 2 m | "diamicton; less than 2 m thick" / "diamicton; greater than 2 m thick" | S4 | stated |
| CGM 195 (Surficial geology of Canada) | Tv | < 2 m (French legend only) | FR "inférieur à 2 m d'épaisseur"; EN "thin and discontinuous" | S5 | stated (FR) |
| CGM 195 | Tb | none | "diamicton; thick and continuous" | S5 | not stated |
| CGM 195 | Cv, Wv / GMv / O | < 2 m / none / > 2 m | "less than 2 m thick" / "thin to discontinuous sediment veneer" / "generally greater than 2 m thick" | S5 | stated / not / stated |
| BC Terrain Classification System 1997 | b blanket | > 1 m | "A blanket is greater than 1 metre thick" | S6 p. 29 | stated |
| BC TCS 1997 | v veneer | ~0.1–1 m | "between about 10 cm and 1m in thickness" | S6 pp. 39–40 | stated |
| BC TCS 1997 | x thin veneer | ~0.02–0.2 m | "about 2-20 cm in thickness" | S6 p. 41 | stated |
| BC TCS 1997 | w mantle of variable thickness | typically 0–3 m | "variable thickness (typically 0 to 3 m)" | S6 p. 40 | stated |
| BC TCS 1988 (MOE Manual 10) | v / b | 0.1–1 m / > 1 m | "ranges in thickness from 10 cm to 1 metre" | S7 pp. 38, 28 | stated |
| Yukon (YGS 2023 compilation) | b / v / x | > 1 m / 0.1–1 m / 2–20 cm | "veneer (0.1 - 1 m thick)"; "blanket (>1 m thick)"; "thin veneer (2 - 20 cm thick)" | S8 | stated |
| Québec SIGÉOM | Tc / Tm | > 1 m / < 1 m | "dont l'épaisseur est supérieure à 1 m" / "Diamicton de moins de 1 m d'épaisseur" | S9 | stated |
| Newfoundland and Labrador 1:50k | b / v | > 1.5 m / < 1.5 m | "Any deposit greater than 1.5 m thick" / "Any deposit less than 1.5 m thick" | S10 | stated |
| NL 1:50k | c concealed by vegetation; w weathered | < 1 m | "shallow (less than 1 m), discontinuous overburden" | S10 | stated |
| Ontario EDS014 | bedrock with thin drift | none | "covered by a discontinuous, thin layer of drift" | S12 | not stated |
| Saskatchewan 1:1M | Mv | 0.1–1 m | "10 cm to 1 m thick" | S13 | stated |
| Saskatchewan 1:250k | veneers | not in the product; CSSC convention 0.1–1 m | CSSC: "A veneer ranges from 10-100 cm in thickness" | S13, S14 | inferred |
| Norway (NGU) | usammenhengende eller tynt dekke (codes 12, 43, 52, 55) | < 0.5 m | "sjelden mer enn 0.5 m tykk"; "normalt mindre enn 0,5 m" | S15 | stated |
| NGU | sammenhengende dekke (11, 41, 71) | >= 0.5 m | "tykkelse fra 0,5 m til flere ti-talls meter" | S16 pp. 9–10; S15 | stated |
| Finland (GTK) 1:20k/50k | Ka (rock with thin till) | till < 1 m | "ohuesti (alle 1 m) moreenin peittämää kalliota" | S18 p. 3 | stated |
| GTK 1:200k | ohut turve / paksu turve (thin / thick peat) | 0.3–0.6 m / > 0.6 m | "ohuena turpeena (0,3-0,6 m turvetta)" | S19 | stated |
| Sweden (SGU) 1:25k–100k | tunt eller osammanhängande ytlager | < ~0.5 m | "mäktighet mindre än ca 0,5 m eller osammanhängande" | S20 p. 6 | stated |
| USGS SIM 3340 (Alaska) | none | no veneer / blanket terms | – | S22 | not found |
| Alaska DGGS | b′ thinly covered bedrock | < 0.9 m (one map) | "Subcrops covered by less than 0.9 m of loess" | S23 | stated (map-specific) |

## Conflicts noted by the research

- **GSC:** the 2 m split is the same in SDM 2.0, 2.3.0 and 2.5.1. Individual CGM legends can override it; for example, the CGM 219 glaciolacustrine blanket is "1 to greater than 5 m".
- **CGM 195** gives a number for till veneer in its French legend only.
- **BC and Yukon** use 1 m, half the GSC threshold. The Yukon compilation recodes its source maps, GSC maps included, into BC codes.
- **Québec** codes collide with GSC suffixes: Tb is hummocky till, not blanket.
- **Newfoundland** uses 1.5 m. Labrador's 1:1M map, GSC Map 1814A, uses deposit-specific 2 m and 5 m thresholds.
- **The Nordic surveys** set their thresholds by their mapping depth: NGU and SGU 0.5 m, GTK 1 m.

## Sources

- S1 GSC Open File 8236 v2.3.0 (Deblonde et al. 2017), Appendix 4: https://publications.gc.ca/collections/collection_2017/rncan-nrcan/M183-2/M183-2-8236-1-eng.pdf
- S2 GSC OF 8236 v2.5.1 (2024), doi:10.4095/332530 (Appendix A .xlsx in gid_332530.zip)
- S3 GSC OF 7631, SDM v2.0 (2014), doi:10.4095/294225
- S4 CGM 219, doi:10.4095/298704
- S5 CGM 195, doi:10.4095/295462 (map sheet https://publications.gc.ca/collections/collection_2016/rncan-nrcan/M183-1-195-2014-1.pdf)
- S6 Howes and Kenk 1997, Terrain Classification System for British Columbia v2: https://www2.gov.bc.ca/assets/gov/environment/natural-resource-stewardship/nr-laws-policy/risc/terclass_system_1997.pdf
- S7 Howes and Kenk 1988, MOE Manual 10
- S8 Lipovsky and Bond 2023, Yukon digital surficial geology compilation (metadata zip, map-data.service.yukon.ca)
- S9 MRNF Québec, symboles et abréviations, zones morphosédimentologiques: https://gq.mines.gouv.qc.ca/documentation/symboles-abreviations-carte-geoscientifique/geologie-du-quaternaire/zones-morphosedimentologiques/
- S10 GSNL 1:50 000 surficial legend, morphology: https://geoatlas.gov.nl.ca/custom/help/Surficial_Geol_50k_help_files/SurficialGeologyLegend_50k_morph.pdf
- S11 GeoAtlas Regional Surficial Geology help (after Liverman and Taylor 1990)
- S12 OGS 1997, EDS014-REV legend.txt
- S13 Saskatchewan Geological Survey, 1:1M and 1:250k geology services (gis.saskatchewan.ca)
- S14 Canadian System of Soil Classification, 3rd ed., ch. 18: https://sis.agr.gc.ca/cansis/taxa/cssc3/chpt18.html
- S15 NGU løsmassetype kodeliste: https://static.ngu.no/upload/Aktuelt/Losmassetype_kodeliste.pdf
- S16 NGU produktspesifikasjon LøsmasseN250/N50 (2010)
- S17 GTK maaperä 1:20 000 / 1:50 000 metadata: https://tupa.gtk.fi/paikkatieto/meta/maapera_20_50k.html
- S18 Kielosto et al. 2008, GTK map explanation: https://tupa.gtk.fi/kartta/maaperakartta20/mps_202109.pdf
- S19 GTK maaperä 1:200 000 metadata: https://tupa.gtk.fi/paikkatieto/meta/maapera_200k.html
- S20 SGU jordarter 1:25 000–1:100 000 beskrivning (2024): https://resource.sgu.se/dokument/produkter/jordarter-25-100000-beskrivning.pdf
- S21 SGU jordarter 1:1 miljon
- S22 USGS SIM 3340 pamphlet
- S23 Reger and Burns 2013, DGGS RI 2013-2, doi:10.14509/25179
- S24 Hubbard and Wolken 2024, DGGS PIR 2024-8
