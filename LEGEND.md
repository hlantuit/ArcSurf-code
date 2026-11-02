# Pan-Arctic surficial geology — harmonised legend and output schema

Extent: AMAP area polygon (`raw/amap/amaplim_lam_poly.shp`), land only.
Output: `/albedo/work/user/hlantuit/arctic_surficial/out/arctic_surficial_geology.gpkg`
CRS: stored in EPSG:6931 (WGS 84 / NSIDC EASE-Grid 2.0 North, equal-area) so
polygon areas are meaningful; EPSG:3995 (polar stereographic) distorts area.

## Principle

Every source legend is genetic (process/origin) first; only Yukon, Bryant
(ClastSize) and NOAA ESI carry texture. So the harmonised class is GENETIC, and
texture / thickness are separate columns filled only where the source says so —
`unknown` is never guessed from the genetic class.

The native unit is always kept (`src_code`, `src_desc`), so any crosswalk
decision can be revisited without re-harvesting.

## `hclass` — harmonised genetic class (level 1)

| code | name | typical source units |
|---|---|---|
| `R`   | Bedrock (exposed or thin, discontinuous cover) | GSC R, Rv; NGU "bart fjell"; VSEGEI pre-Quaternary |
| `T`   | Till / morainal (ground, hummocky, end moraine) | GSC Tb/Th/Tm/Tv; NGU morene |
| `GF`  | Glaciofluvial (ice-contact + outwash, eskers, kames) | GSC GFc/GFp; NGU breelvavsetning |
| `GL`  | Glaciolacustrine | GSC GLn/GLo |
| `GM`  | Glaciomarine | GSC GMn/GMo/GMv; NGU fjord-/havavsetning (glasimarin) |
| `M`   | Marine and littoral (incl. raised beaches, tidal flats) | GSC Mn/Mo; NGU marin strandavsetning; VSEGEI m |
| `F`   | Fluvial / alluvial / deltaic (incl. alluvial-marine) | GSC A; NGU elveavsetning; VSEGEI a, am |
| `L`   | Lacustrine (non-glacial) | GSC Ln/Lo; VSEGEI l |
| `K`   | Thermokarst / alas (lacustrine-palustrine in drained basins) | VSEGEI alas; Veremeeva Alas complex |
| `Y`   | Ice complex / Yedoma (syngenetic ice-rich silt) | Veremeeva Yedoma IC; VSEGEI Ice Complex |
| `E`   | Eolian | GSC E; NGU vindavsetning |
| `C`   | Colluvial / mass-wasting (talus, landslide, solifluction, rock glacier) | GSC C/Cv; NGU skredmateriale |
| `W`   | Residual / weathered regolith (in-situ weathering, blockfields) | GSC W/Wv; NGU forvitringsmateriale |
| `O`   | Organic (peat, bog, fen) | GSC O; NGU torv og myr |
| `V`   | Quaternary volcanic | GSC V; Iceland postglacial lava |
| `X`   | Anthropogenic (fill, tailings) | NGU fyllmasse |
| `I`   | Glacier / perennial ice | GSC I; GEUS ice; NPI glaciers |
| `Q`   | Quaternary undivided / unconsolidated, origin unknown | backdrops (GUM, GLiM "su") |
| `H`   | Water body, as mapped by the source | Bryant "Water"; GSC/NGU lakes |
| `U`   | Unmapped / no data | gaps inside AMAP land |

Water bodies are KEPT as `H`, not dropped: the land mask (OSM land polygons) is
"everything that is not ocean", so it contains lakes and delta channels, and a
dropped source lake would reappear as `U` (tested: 40% U on a Lena Delta tile).
`DROP` in a crosswalk is for units that are not land (e.g. "sea") AND for units a
source labels "unmapped" (GSC SDM 794 "Unmapped Area", GEUS UNMAP, GTK
kartoittamaton). An unmapped statement must fall through to the next-coarser
source; coding it `U` would claim the land and block that source (CGM249's
"Unmapped Area" alone is 9,037 km², mostly sea). `U` is only what NO source covers.

## Other harmonised columns

| column | values | filled from |
|---|---|---|
| `hclass` | table above | crosswalk, per source |
| `hclass2` | second component where the source has a composite unit (e.g. GSC "Tv/R") | GSC components B/C, NGU sekundær |
| `texture` | `gravel`, `sand`, `fines` (silt/clay), `diamicton`, `mixed`, `organic`, `bouldery`, `unknown` | only explicit source texture fields |
| `cover` | `blanket`, `veneer`, `discontinuous`, `unknown` | GSC expression b/v; NGU "tynt dekke" |
| `ice_rich` | `yes`, `no`, `unknown` | only where the SOURCE maps ice (Yedoma/IC units), never inferred |
| `coastal` | 1 if the polygon touches the coastline (GSHHG full / OSM land polygons) | computed |
| `pf_zone` | `continuous`, `discontinuous`, `sporadic`, `isolated` (isolated patches), `none` | Obu et al. (2019) permafrost zones; polygons crossed by a zone limit are split |
| `yedoma` | `yes`, `uncertain`, `no`, `not_assessed` | Database of Ice-Rich Yedoma Permafrost v2 (IRYP v2; Strauss et al. 2021/2022, PANGAEA doi:10.1594/PANGAEA.940078): `yes` = IRYP confirmed or likely, `uncertain` = IRYP uncertain, `no` = north of 60 N outside the IRYP polygons, `not_assessed` = south of 60 N (IRYP maps north of 60 N only). Polygons crossed by an IRYP limit are split. Independent of `hclass`: the source's own class and description are kept (H. Lantuit 2026-10-04) |
| `yedoma_conf` | `confirmed`, `likely`, `uncertain`, empty | IRYP v2 confidence class of the piece |

## Glaciers and ice sheets — one ice layer everywhere (merge 42 on)

Glacier outlines in the source maps date from 1950–2010 and are drawn at very different scales. Where they
disagree with a dated glacier inventory, the inventory wins, and the source's own class is kept underneath
(H. Lantuit 2026-10-01 and 2026-10-06; `scripts/ice_build.py`, `scripts/ice_apply.py`).

- **Outlines.**
  - The Greenland Ice Sheet and its connected glaciers come from PROMICE 2022 Ice Mask v3 (Sentinel-2, 10 m).
    It wins its own margin.
  - Everything else comes from RGI 6.0, glacier by glacier, regions 01–10.
  - Gaps narrower than 60 m between neighbouring outlines are closed, so no strips of geology remain inside
    the ice.
  - RGI fringes narrower than 120 m along the PROMICE margin are dropped. These are the 2000 outlines of
    RGI region 05, left outside the 2022 margin.
- **Under the ice.** Each polygon's part inside an outline becomes `hclass` = `I`. `hclass2`, `texture`,
  `cover` and `ice_rich` are cleared, but the provenance columns stay, because they describe the mapped
  geology under the ice.
- **Slivers.** Some geology polygons are narrower than *w* and hug the ice: at least 25 % of the polygon's
  outline lies on the ice edge. Both whole polygons and appendages of larger ones count. These polygons are
  by-products of the overlay, and they join the ice.
  - *w* is 0.5 mm at the source scale: 50 m at 1:100k, 125 m at 1:250k, 500 m at 1:1M and coarser.
  - Narrow mapped units that only touch the ice are real mapping and stay. A river strip ending at a glacier
    snout is one example.
  - `ice_apply.sliver_check` must return 0 on every tile.
- **Source ice outside the outlines.** A source may map ice where the inventory has none, wider than *w*.
  This happens where ice has gone since the source map was made, or where the source is generalised. Such
  areas become `U`, with `ice_note` = `source_ice_outside_outline`. Their source attributes are kept, so
  they can be re-classified later.

| column | meaning |
|---|---|
| `hclass_under_ice` | on ice rows: the source's own `hclass` under the outline (`''` where the source mapped ice too) |
| `ice_src` | `PROMICE2022` or `RGI6-<region>` (01–10); `''` off the ice |
| `ice_year` | PROMICE: 2022; RGI: the area-weighted median outline year of the glaciers in the part |
| `ice_note` | `source_ice_outside_outline` (see above); `ice_override_failed` if the overlay failed on a tile (the tile is kept unmodified) |

Known limits, from `scripts/ice_audit.py` on merge 40:
- Most RGI 6.0 outlines date from 1999–2011, but pre-1980 outlines remain in regions 02, 04, 07 and 10.
  Their areas are 515, 610, 121 and 81 km².
- In region 09 (Russian Arctic) the geology sources map no ice: they class the ice caps as `U`, `M` or `L`.
  There, the ice comes from RGI alone.
- Median offsets between source ice and RGI are 100–450 m. The worst cases are region 05 at 756 m, region 10
  at 868 m and the Greenland Ice Sheet at 4.4 km.

## Provenance columns (per polygon — so resolution changes along the coast are visible)

| column | meaning |
|---|---|
| `src_id` | product id from `sources/*.json` |
| `src_sheet` | sheet / quadrangle / tile id |
| `src_code`, `src_desc` | native unit code and description, verbatim |
| `scale_den` | nominal source scale denominator |
| `pub_year`, `survey_years` | publication year; field/imagery epoch where stated |
| `conf_tier` | source's own confidence where published (GSC Surficial/Reconnaissance/Predictive, IRYP confirmed/likely/uncertain), else null |
| `licence`, `redistribution` | exact licence string; `open` / `internal_only` / `unknown` |
| `xwalk_note` | why this `hclass` was chosen when ambiguous |

## Precedence (where sources overlap)

1. Finest nominal scale wins; ties go to the newer, field-checked source.
   Exception (H. Lantuit 2026-10-04): sources that are not surficial-geology maps (the BC soil surveys,
   `ca_bc_soil`) rank below every surficial / Quaternary geology map of any scale and only replace the
   ≥1:2.5M fallbacks (`merge_tiles.PREC_SCALE`; their own `scale_den` is kept on the polygons).
2. GSC per-sheet tier: Surficial > Reconnaissance > Predictive, *within* equal scale.
3. Backdrops (≥1:2,500,000) fill only what nothing finer covers, and carry
   `scale_den` so they can be filtered out.
Overlaps are resolved by clipping the coarser source by the finer one's footprint
(sheet extent, not polygon union — a finer map's un-mapped holes stay holes rather
than being back-filled with a different legend, and are coded `U` if the sheet
says "not mapped").
