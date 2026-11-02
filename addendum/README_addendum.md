# ArcSurf addendum, version 1.0: keys, context and CryoGrid parameters

The addendum belongs to ArcSurf, the harmonised surficial geology map of the Arctic (Lantuit and Fritz, Earth System Science Data). It is published separately from the geology and versioned on its own.

It provides three things:
- the keys that tie model parameters to the map;
- the interpretive context that the geology deliberately does not carry: permafrost zone, Yedoma, ground ice as mapped by the source, deglaciation history;
- a first set of CryoGrid stratigraphies, assigned to every polygon.

Everything is keyed by `asid`, the persistent identifier of the polygons of the dissolved ArcSurf geometry. `unit_code` is the stable code of a native legend unit: `'U'` followed by the first 12 hexadecimal digits of sha1(`src_id|src_sheet|src_code`).

## Files

| File | One row per | Content |
|---|---|---|
| `units.csv` | native legend unit and attribute set | `unit_code`, source (`src_id`, `src_sheet`, `src_code`, `src_desc`), harmonised attributes (`hclass`, `hclass2`, `texture`, `cover`), ground ice as mapped by the source (`ice_rich`), nominal scale, publication year, area, number of polygons |
| `polygon_context.parquet` | polygon (`asid`) | `unit_code`, provenance, area; permafrost-zone area shares `pf_*` (Obu et al. 2019) and `pf_zone_major`; Yedoma area shares `yed_*` (IRYP v2, Strauss et al. 2021, 2022) and `yedoma_major`; deglaciation `deglac_*` (see "Context"); `lgm_ice_share` (Batchelor et al. 2019); `ice_rich`; `strat_index` (native age index of Russian units) |
| `piece_context.parquet` | piece of the tiled geometry | `tile_id`, `row`, `asid`, area, permafrost zone, Yedoma, deglaciation: the link from the tiled processing version to the addendum |
| `polygon_strat.parquet` | polygon (`asid`) | `template_id`, `strat_id`, thickness of the cover (`thk_min_m`, `thk_max_m`, `thk_depth_m`), `thk_tier`, `thk_basis`, `confidence` |
| `stratigraphies.csv` | layer of a distinct stratigraphy | `strat_id`, layer, `top_m`, `class`, `waterIce`, `mineral`, `organic`, `soil_type`, `field_capacity`, `satHydraulicConductivity`, `Xice`. Ready to paste into CryoGrid `STRAT_layers` |
| `cryogrid_templates.csv` | layer of a template | the published values behind the stratigraphies, with `Xice_published`, `sources`, `confidence` and notes |
| `parameter_classes.csv` | combination of (`hclass`, `hclass2`, `texture`, `cover`) | area, units, polygons, the template assigned, area by thickness tier |

## Context: how it is derived

**Permafrost zone and Yedoma.** These are exact area shares, because the tiled pieces are cut along the zone and IRYP limits. IRYP maps north of 60° N only: south of it, Yedoma is `not_assessed`, never `no`.

**Deglaciation.** The age is the time at which ice left the polygon's pieces, read at their representative points:
- NADI-1 OPTIMAL isochrones (Dalton et al. 2023) for North America;
- DATED-1 most-credible isochrones (Hughes et al. 2016) for Eurasia.

Neither reconstruction covers Greenland.

Each polygon gets four values: `deglac_dated_share`, `deglac_ka_min`, `deglac_ka_max` and `deglac_ka_wmean`, the last two over the dated part only. `deglac_status_major` is one of `dated`, `ice_free_at_lgm`, `lgm_ice_undated` or `ice_today`.

**Ground ice.** `ice_rich` is ground ice **as the source map states it**. It is never inferred from the deposit type.

## CryoGrid stratigraphies

**Target model.** CryoGrid community model (Westermann et al. 2023), class `GROUND_freezeC_bucketW_Xice_seb_snow` with `STRAT_layers`. Bedrock goes in `GROUND_freeW_seb` and glaciers in `GLACIER_freeW_seb`.

**Conventions.**

| Column | Meaning | Unit |
|---|---|---|
| `top_m` | Top of the layer below the surface | m |
| `waterIce`, `mineral`, `organic` | Volume fractions of the soil matrix (soil without excess ice); air = 1 − sum | – |
| `Xice` | Excess-ice volume divided by matrix volume | – |
| `soil_type` | Sets the freezing characteristic only | 1 sand, 2 silt, 3 clay, 4 peat, 5 free water or blocks |
| `field_capacity` | Fraction of matrix volume | – |
| `satHydraulicConductivity` | Saturated hydraulic conductivity | m s⁻¹ |

**Templates.** Each deposit type has one template, taken from published CryoGrid parameter sets. The compilation, including source keys, page references and verification, is in `addendum/cryogrid_stratigraphies_compilation_2026-10-07.md` of the code repository. The main sources are:
- Westermann et al. 2013, southern Norway, keyed to the Geological Survey of Norway surficial classes;
- Czekirda et al. 2023;
- Renette et al. 2023;
- Martin et al. 2021;
- Westermann et al. 2016 and 2017, and Nitzbon et al. 2019 and 2020, all for the Lena Delta and NE Siberia;
- Aga et al. 2023 and 2026;
- Czekirda et al. 2019, Iceland;
- Groenke et al. 2023.

Values marked (i) in a template interpret a published sentence, and (d) values are derived from published numbers. **Proxy** templates are borrowed from another deposit, because no CryoGrid value is published for these classes:
- glaciolacustrine;
- marine and glaciomarine;
- eolian;
- undivided Quaternary;
- lacustrine deposits in formerly glaciated terrain.

`confidence` gives the template's standing.

**Assignment rules.** The template comes from the polygon's `hclass`, `hclass2`, `texture` and `cover` (code: `addendum_params.assign`).
- Lacustrine deposits use the drained-lake-basin template of Nitzbon et al. 2020 where the polygon was mostly free of ice at the Last Glacial Maximum. Elsewhere they use the silt proxy.
- Water bodies, unmapped land and anthropogenic deposits get no ground template (`NONE`). Water belongs to CryoGrid's lake classes.

**Excess ice.** The geology does not carry ground ice, so `Xice` is 0 in every template except Yedoma. The published value is kept in `Xice_published` for users who want it, for example peat plateaus (Martin et al. 2021) or drained-lake basins (Nitzbon et al. 2020). Ground-ice overrides belong to a separate ground-ice layer, not to the geology. This version provides no such layer, so outside the Yedoma template the stratigraphies are an ice-free baseline: the excess ice of ice-rich silts, of till with massive or buried glacier ice and of peat plateaus must be added from a ground-ice product, for example the ground-ice maps of O'Neill et al. (2019) for Canada. The stratigraphies have not been tested against ground temperatures or stratigraphic logs.

## Thickness tiers

A template has one boundary whose depth depends on the unit's thickness. Usually this is the contact with bedrock. For peat it is the base of the organic deposit. The depth is taken from the best available tier:

| Tier | Source of the thickness | Example |
|---|---|---|
| **1a** | A thickness stated in the unit's own legend text (`src_desc`) or in the legend of GSC Map 1814A | "till veneer 0.5–2 m" → 1.25 m; "less than 2 m thick" → 1 m; "> 5 m" → the deeper of 5 m and the template default |
| **1b** | The cover term of the unit (`veneer`, `blanket`, `discontinuous`) as defined numerically by the source's legend system | Terrain Classification System veneer, GSC veneer, … (definitions and citations in `addendum_params.COVER_DEFS`) |
| **2** | No map value: the template default, following the strategy of Westermann et al. 2013 | thick till 10 m, thin till 1 m, regolith 5 m, glaciofluvial 20 m, fluvial 10 m, peat 2 m over mineral soil with bedrock at 10 m |

Each tier is converted to one depth:
- a closed range uses its middle;
- a stated maximum uses half of it;
- an open minimum uses the deeper of the minimum and the template default.

A veneer or a stated maximum on a deep profile (marine, fluvial fines, lacustrine) adds bedrock at that depth only when the unit is a thin cover over rock. `thk_basis` quotes the text or names the rule used for every polygon.

## Known gaps

- **Field capacity and saturated hydraulic conductivity** are rarely published per deposit type. Most templates use the generic 1e-5 m s⁻¹, and field capacities marked (i) are interpretations.
- **Regional bias.** The till, colluvium and regolith values come from coarse, sandy tills in southern Norway. Fine-grained Arctic lowland tills have no published set.
- **Salinity** of marine pore water cannot be represented in this CryoGrid class.
- **Map thickness is rare.** Tier 1 covers 8.5 % of the domain (tier 1a 1.56 %, tier 1b 6.91 %). The Russian sheets, which cover half of the domain, give no thickness in the descriptions we extracted.
- **Literature values.** The values rest on the published model literature; they are not calibrated against measurements on samples.

## Licence and citation

- All files: CC BY 4.0. The addendum covers every polygon of the ArcSurf geology (5,465,326 polygons); join its rows to the geology on `asid`.
- Greenland: the rows of the Greenland polygons are derived from the maps of the Geological Survey of Denmark and Greenland (GEUS): the seamless 1:500 000 geological map of Greenland, version 3.0 (Kokfelt, T. F., et al., GEUS Dataverse, https://doi.org/10.22008/FK2/FWX5ET, 2023), and the 1:100 000 sheets Pannertooq 72 V.2 Syd (https://doi.org/10.22008/FK2/IBHIZL), Nuugaatsiaq 71 V.2 Nord (https://doi.org/10.22008/FK2/PGSMJH) and Maarmorilik 71 V.2 Syd (https://doi.org/10.22008/FK2/07OYKX). The original GEUS datasets remain available from GEUS Dataverse under CC BY-SA 4.0; the GEUS-derived component of ArcSurf is published under CC BY 4.0 with separate permission from GEUS (22 October 2026). Please cite the GEUS datasets when using these rows.
- Labrador: the rows of the polygons of the 1:50 000 layer of the Newfoundland and Labrador GeoScience Atlas (`src_id` `ca_nl_labrador`) are reproduced with the written permission of the Geological Survey of Newfoundland and Labrador; the conditions of that permission are stated in the metadata of this dataset and must be observed.

When using the addendum, please cite it, the ArcSurf geology and the data paper.

Funding: this work was supported by the European Union’s Horizon Europe Research and Innovation Programme, ILLUQ Project [101133587].
