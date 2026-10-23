# CryoGrid stratigraphies for the ArcSurf parameter addendum: literature compilation (draft, 2026-10-07)

Published CryoGrid layer values were found for 13 of the 18 classes. Two thirds of the value sets come from the CryoGrid lineage of Westermann and co-authors. The Southern Norway table of Westermann et al. (2013) is keyed to NGU surficial-geology classes, so it supplies the till, colluvium, regolith/blockfield, peat, (glacio)fluvial and bedrock rows directly.

What is missing:
- **No published values** for glaciolacustrine, marine, glaciomarine, eolian or undivided Quaternary deposits. Lacustrine has values only for drained-lake basins inside the Yedoma region.
- **Field capacity and saturated hydraulic conductivity** are almost never published per deposit type.
- **Permafrost_cci publishes no stratigraphy table** at all.

## 0. Method and conventions

**What was read on Albedo.** Everything was read-only; nothing was created, moved or run.
- Folder: `/albedo/work/user/hlantuit/cryogrid/`.
- `CryoGridCommunity_source` is GitHub `CryoGrid/CryoGridCommunity_source` master, commit e82b5a4 (2023-10-06), which is still the GitHub head.
- `CryoGridCommunity_run` is master, commit caede30 (2023-06-14).
- `examples_repo` is the same GitHub repository on branch `develop/main`, commit dd328ee (2021-12-06), also the head. The repository was formerly called "CryoGridExamples".
- `CryoGridDocumentation` was also read.
- The xlsx files were parsed by piping a standard-library-only script into `/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python -`, because openpyxl is not installed in that environment.

**How the literature was read.**
- The papers were read from publisher web pages and open repositories.
- Text was extracted from the PDFs with PyMuPDF; tables were read from the publisher XML or from rendered table images.
- Extracted texts, code copies and table images were kept in a temporary working folder and are not archived; nothing was written to the project folders.

**Verification.** Every table value used below was checked against the extracted text, the publisher XML, or a rendered table image.

**Marks used in the tables.**
- **(d)**: derived from published numbers; the formulas are in A4.
- **(i)**: an interpretation of a published sentence. It is not a published parameter value.
- **code**: the value appears only in published model code, not in the paper.
- **n.r.**: not reported.
- **[UNSURE]**: ambiguous in the source.
- **[GAP]**: no published CryoGrid value exists.

---

## (A) soil_type codes, units and conventions in CryoGrid

### A1. soil_type codes for the GROUND_freezeC classes

| soil_type | Meaning (comment in the code) | α [m⁻¹] | n [–] | Residual water content |
|---|---|---|---|---|
| 1 | sand | 4.06 | 2 | 0 |
| 2 | silt | 0.65 | 1.7 | 0 |
| 3 | clay | 1.49 | 1.25 | 0 |
| 4 | peat | 2.31 | 1.292 | 0. The CONSTANTS comment says: "from Hydraulic properties of fen peat soils in Poland, Gnatowski 2010" |
| 5 | "water (i.e. approximation of free water, very large-pore ground material)" | 400 | 2.5 | 0 |

**Where the codes are defined.**
- The code list is the STATVAR comment in `source/TIER_2_full_classes/GROUND_freezeC_bucketW_Xice_seb.m` line 59. The snow variant `source/TIER_3/SNOW/GROUND_freezeC_bucketW_Xice_seb_snow.m` inherits it.
- The same comment appears in `GROUND_freezeC_bucketW_seb.m:51`, `GROUND_freezeC_seb.m:44` and `ESA_CCI/GROUND/GROUND_MULTITILE_ESA_CCI.m`.

**How the code selects the parameters.**
- `finalize_init` (lines 143–145) builds `vanGen_alpha`, `vanGen_n` and `vanGen_residual_wc` in the order [sand silt clay peat water]. The array index is therefore the soil_type code.
- The lookup table is built per soil type in `create_LUT_freezeC` (`TIER_1_processes/FREEZE_CURVE_KarraPainter.m` line 852 ff.).

**Where the values come from.** They are in `CONSTANTS_excel.xlsx`, Sheet1:
- rows 39–53 in `examples_repo/param_file_templates/Excel`;
- rows 40–54 in `CryoGridCommunity_run/templates`.
The two files carry identical values.

**What the paper says.** Westermann et al. 2023 (GMD), p. 2617, states that four soil types are implemented and that users can change their α and n. The quote is: "Currently, four soil types (sand, silt, clay, peat) are implemented … it is possible to change the α and n values associated with each of them". Code 5 is not mentioned in the paper.

**What soil_type controls.** It sets only the freezing characteristic: Painter and Karra (2014), using van Genuchten α and n. In the bucket class it sets neither field capacity nor hydraulic conductivity.

**Older model versions.**
- CryoGrid 2 and 3 used the Dall'Amico et al. (2011) freezing characteristic, with "three classes, sand, silt and clay" (Westermann et al. 2016, p. 525).
- The CryoGrid 3 code comment reads "code for soil type: 1: sand, 2: silt". Its `loadSoilTypes.m` gives sand = [residual 0.00, fc, α 4.00, n 2.0] and silt = [0.05, fc, 0.65, 1.7].
- Papers using CryoGrid 2 or 3 type peat layers as "sand" or "silt". The exception is the CryoGrid 3 branch xice_mpi_IS_TC (Schneider von Deimling et al. 2021), whose code uses type 4 for peat.

### A2. STRAT_layers columns of GROUND_freezeC_bucketW_Xice_seb(_snow)

- **Column list:** `PARA.STATVAR = {'waterIce' 'mineral' 'organic' 'Xice' 'soil_type' 'field_capacity' 'satHydraulicConductivity' 'T'}` (line 426). T is supplied through STRAT_linear.
- **depth:** top of each layer, in m below the surface. The first layer starts at 0 and the last layer extends to the bottom of the domain. Grid cells are assigned by their midpoint. Sources: header and `finalize_init` of `IO/STRATIGRAPHY_STATVAR/STRAT_layers.m`; Westermann 2023 Supplement S2.7.
- **waterIce, mineral, organic:** volumetric fractions [–] of the soil matrix, meaning the soil without excess ice. Air is 1 minus their sum.
  - `convert_Xice` turns each value into a volume: value × layerThick × area / (1 + Xice).
  - Location: `IO/UNIT_CONVERSION/UNIT_CONVERSION_standard.m` lines 16–26.
- **Xice [–]:** the ratio of excess-ice volume to matrix volume.
  - In the code, XwaterIce = Xice/(1+Xice) × layer volume (line 25).
  - Westermann 2023, p. 2618: excess ice is "specified as a fraction (χ) relative to the amount of soil without excess ice; i.e., χ = 1 corresponds to a cell consisting of 50 % soil and 50 % excess ice".
  - The code sets Xice to 0 wherever the initial temperature is above 0 °C (line 20). Active-layer cells therefore cannot carry Xice.
  - Excess ice melts as free water at 0 °C (p. 2618).
- **field_capacity [–]:** a fraction of the matrix volume. Water above it drains.
  - Code: `get_derivative_water_Xice`, `TIER_1_processes/WATER_FLUXES.m` lines 317–321.
  - Paper: Westermann 2023, p. 2617, Eq. 22.
- **satHydraulicConductivity [m s⁻¹]:** the code computes K = Ksat × saturation × 10^(−7 × ice saturation) (`calculate_hydraulicConductivity_Xice`, `WATER_FLUXES.m` lines 1082–1090).
  - It must be given as a STRAT_layers column. `PARA.hydraulicConductivity` is commented out in this class, so the template row (1e-5) is ignored.
- **soil_type:** an integer from 1 to 5, as in A1.

### A3. Hard constraints and model choices

**Porosity limit.**
- The freezing-curve lookup table covers matrix porosity (1 − mineral − organic) from 0.05 to 0.95, and temperatures down to −60 °C (`FREEZE_CURVE_KarraPainter.m` lines 856–861).
- Bedrock with 3 % porosity therefore cannot sit in this class.
- Every published community-model setup puts bedrock in `GROUND_freeW_seb` instead. That class has STATVAR waterIce, mineral, organic and T, free-water freezing, and no water flow. Published depths of this switch:
  - Westermann 2023 (Bayelva): 5 m;
  - Renette 2023: 5 m;
  - Aga 2023 and Aga 2026: 9 m;
  - template and examples: 10 m.

**Thermal properties.**
- The default conductivity function is `conductivity_mixing_squares_Xice` (`HEAT_CONDUCTION.m` lines 93–101).
- It uses k_m 3, k_o 0.25, k_w 0.57, k_i 2.2 and k_a 0.025 W m⁻¹ K⁻¹, and heat capacities c_m 2.0e6, c_o 2.5e6, c_w 4.2e6 and c_i 1.9e6 J m⁻³ K⁻¹ (CONSTANTS_excel.xlsx).
- **k_m is one constant per run, not a layer column.** Rock-type-specific values (see C, bedrock row) need a separate CONSTANTS file per run.

**Glacier.**
- Glaciers use `GLACIER_freeW_seb`. Its STATVAR are waterIce, mineral, organic and T, and the code sets mineral to 0.
- Westermann 2023, §2.2.8, p. 2620, describes it as "layers of pure ice (using the free water freezing characteristic) with a user-defined constant ice thickness".

### A4. Conversion formulas used here (all marked (d))

1. **CryoGrid 3 bulk layer to community-model convention.**
   - Inputs: θwi, θm, θo and natural porosity φ, with no air.
   - Matrix volume V = (θm + θo)/(1 − φ). If V ≥ 1 there is no excess ice and the values are unchanged.
   - Otherwise: Xice = (1−V)/V; mineral = θm/V; organic = θo/V; waterIce = φ.
   - This equals Xice = θx/(1−θx), where θx = (θi−φ)/(1−φ) is the subsidence fraction of Nitzbon et al. 2021, Eq. 2.
   - **Caution:** Nitzbon 2019 and 2020 call θw0−φ "x % excess ice". For example, θw0 0.90 is described as "35 %", but the true excess-ice volume fraction of that layer is 0.78.
2. **Excess-ice volume fraction of a cell to Xice.** For χ as defined by Nitzbon et al. 2023, Xice = χ/(1−χ).
3. **Martin et al. 2021.** Their "47 % (volume of excess ice/volume of unfrozen soil)" already matches the community definition, so Xice = 0.47.
4. **Permeability to saturated hydraulic conductivity.** Ksat = k ρw g / ηw (code: `WATER_FLUXES.m` line 1103).
   - Westermann 2023, Sect. 3.1.3, equates 3.25e-13 m² with 3.2e-6 m s⁻¹ at room temperature, a factor of about 9.8e6. At 0 °C the factor is about 5.5e6.
   - Rounded results: 1e-11 m² → ~1e-4; 1e-12 → ~1e-5; 1e-13 → ~1e-6; 1e-14 → ~1e-7 m s⁻¹.
5. **Void ratio to porosity.** φ = e/(1+e), and waterIce = saturation × φ.
6. **CryoGrid 2 and 2D layers.** They are given as water/ice, mineral, organic and air, with no excess-ice concept. Values are used unchanged with Xice 0; "sand" maps to 1 and "silt" to 2.
7. **CryoGrid.jl layers.** They are given as ξxic, ξpor, ξsat and ξorg (Groenke 2023, Appendix B2.1). Then waterIce = ξpor ξsat; mineral = (1−ξpor)(1−ξorg); organic = (1−ξpor)ξorg; Xice = ξxic/(1−ξxic).

---

## (B) Published stratigraphies (one row per layer)

### Source keys

**CryoGrid community model**
- **W23**: Westermann, S. et al. 2023, GMD 16, 2607–2647, doi:10.5194/gmd-16-2607-2023. Relevant pages: p. 2617, 2618, 2620 and 2627; Supplement S2. Its parameter files are on Zenodo, doi:10.5281/zenodo.6522424 (zip, not read).
- **R23**: Renette, C. et al. 2023, Earth Surf. Dynam. 11, 33–50, doi:10.5194/esurf-11-33-2023. Table 1, p. 38; text on p. 38 and p. 40.
- **A23**: Aga, J., Boike, Langer, Ingeman-Nielsen, Westermann 2023, TC 17, 4179–4206, doi:10.5194/tc-17-4179-2023. Table 3, p. 4189; text p. 4187.
- **A26**: Aga, J., Lewkowicz, A. G., Westermann, S. 2026, TC 20, 5225–5245, doi:10.5194/tc-20-5225-2026. Table 1, p. 5231; Table 2; text p. 5230.
- **St21**: Stuenzi, S. M. et al. 2021, Biogeosciences 18, 343–365, doi:10.5194/bg-18-343-2021. Table A2, p. 357; Table A3, p. 358.
- **S23**: Schmidt, L. S. et al. 2023, TC 17, 2941–2963, doi:10.5194/tc-17-2941-2023. §4.1, p. 2946.

**CryoGrid 3**
- **W16**: Westermann, S. et al. 2016, GMD 9, 523–546, doi:10.5194/gmd-9-523-2016. Tables 2–3, p. 527; Table 4, p. 528.
- **N19**: Nitzbon, J. et al. 2019, TC 13, 1089–1123, doi:10.5194/tc-13-1089-2019. Tables 2 and 3; §2.3.3–2.3.4. Read from the publisher XML and the t02–t06 table images.
- **N20**: Nitzbon, J. et al. 2020, Nature Communications 11, 2201, doi:10.1038/s41467-020-15725-8. Supplementary Tables 3–6 (SI pp. 30–32); main-text Table 1; Methods.
- **N21**: Nitzbon, J. et al. 2021, TC 15, 1399–1422, doi:10.5194/tc-15-1399-2021. Tables 2–3.
- **M21**: Martin, L. C. P. et al. 2021, TC 15, 3423–3442, doi:10.5194/tc-15-3423-2021. §3.3.2–3.3.3 and Appendix A4. These were read from the HTML full text (two consistent reads).
- **SvD21**: Schneider von Deimling, T. et al. 2021, TC 15, 2451–2471, doi:10.5194/tc-15-2451-2021. Table 1, p. 2457; Table 2, p. 2458. Code on CryoGrid3 branch xice_mpi_IS_TC.
- **JS21**: Schmidt, J. U. et al. 2021, TC 15, 2491–2509, doi:10.5194/tc-15-2491-2021. Table 2, p. 2496.
- **CG3**: CryoGrid3 GitHub, branch xice_mpi, `CryoGrid3_xice_mpi.m` lines 24–38 and 46–60 (default stratigraphy, Samoylov forcing).

**CryoGrid 2 and CryoGrid 2D**
- **W13**: Westermann, S., Schuler, Gisnås, Etzelmüller 2013, TC 7, 719–739, doi:10.5194/tc-7-719-2013. The final PDF is 14 MB and was not readable, so the values come from the discussion paper: TCD 6, 5345–5403, Table 1 pp. 5391–5392, Sect. 3.2 pp. 5354–5357.
- **W15Z**: Westermann, S. et al. 2015, TC 9, 719–735, doi:10.5194/tc-9-719-2015 (Zackenberg). Table 1, p. 724.
- **W17**: Westermann, S. et al. 2017, TC 11, 1441–1463, doi:10.5194/tc-11-1441-2017. Table 1, read from the publisher XML twice with identical results; page number not verified.
- **C19**: Czekirda, J. et al. 2019, Frontiers in Earth Science 7:130, doi:10.3389/feart.2019.00130. Table 1, p. 6.
- **C23**: Czekirda, J. et al. 2023, TC 17, 2725–2754, doi:10.5194/tc-17-2725-2023. CryoGrid 2D; Supplementary Tables S1 and S2.
- **E22**: Etzelmüller, B. et al. 2022, Earth Surf. Dynam. 10, 97–129, doi:10.5194/esurf-10-97-2022. CryoGrid 2D; table in Fig. A1.
- **E23**: Etzelmüller, B. et al. 2023, TC 17, 5477, doi:10.5194/tc-17-5477-2023. CryoGrid 2; Table 2 (read from the PNG).
- **My19**: Myhra, K. S. et al. 2019, Frontiers in Earth Science 7:192, doi:10.3389/feart.2019.00192. CryoGrid 2D.
- **W11**: Westermann, S. et al. 2011, TC 5, 945–959. Table 2, p. 948. This is a precursor thermal model and is not named CryoGrid in the paper.

**Other CryoGrid versions and large-scale products**
- **G23**: Groenke, B. et al. 2023, TC 17, 3505–3533, doi:10.5194/tc-17-3505-2023. CryoGrid.jl; Tables B1–B5.
- **L24**: Langer, M. et al. 2024, TC 18, 363–385, doi:10.5194/tc-18-363-2024. CryoGridLite.
- **N23**: Nitzbon, J. et al. 2023, GRL 50, e2022GL102053, §2.2.3.
- **CCI**: ESA Permafrost_cci ATBD (D2.2) v3.0 (30 Nov 2020), v4.0 (31 May 2023) and v5.0 (15 Nov 2024).
- **Ob19**: Obu, J. et al. 2019, Earth-Science Reviews 193, 299–316, Table 1.
- **Pa22**: Palmtag, J. et al. 2022, ESSD 14, 4095–4110.
- **An20**: Angelopoulos, M. et al. 2020, JGR Earth Surface, doi:10.1029/2019JF005424.

### B1. CryoGrid community model (same model family as the target class)

Column abbreviations: wI = waterIce, min = mineral, org = organic, fc = field capacity, st = soil_type, Ksat = saturated hydraulic conductivity in m s⁻¹.

| Src | Site / class | Layer (m) | wI | min | org | fc | st | Ksat | Xice | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| W23 | Bayelva (Svalbard) reference run, GROUND_freezeC_bucketW_seb | 0–5 | n.r. | n.r. | n.r. | n.r. | silt | n.r. | – | "silty loam to silty clay"; numbers only in Zenodo reference_run.xlsx (not read). Set-up from Zweigel et al. 2021 (Wiley, HTTP 403). |
| W23 | same site, bedrock in GROUND_freeW_seb | >5 | n.r. | n.r. | n.r. | – | free water | – | – | "constant sum of soil water and ice contents" |
| R23 | Juvvasshøe / Ivarsfjorden: "Blocks only" | 0–5 | n.r. (air-filled voids) | 0.5 | 0 | 0.01 | free-water freezing | 1e-5 | – | porosity 0.5; "none of the stratigraphies contain soil organic matter" |
| R23 | "Blocks with sediment" | 0–5 | n.r. | 0.75 | 0 | 0.15 | free water | 1e-5 | – | porosity 0.25 |
| R23 | "Sediment only" | 0–5 | n.r. | 0.5 | 0 | 0.25 | sand | 1e-5 | – | porosity 0.5 (fine-grained sediment) |
| R23 | all three, bedrock | >5 | saturated | n.r. | 0 | – | – | n.r. | – | "3 % porosity and saturated conditions" |
| R23 | Juvvasshøe best fit (p. 40) | 0–5 | n.r. | 0.8 | 0 | n.r. | as blocks with sediment | 1e-5 | – | "porosity of 0.2 (i.e. a volumetric mineral content of 0.8)" |
| A23 | Samoylov multi-layer (after N20/W16), GROUND_freezeC_RichardsEq_seb_pressure | 0–0.15 | 0.375 (d: saturation 0.5 × φ 0.75) | 0.1 | 0.15 | Richards scheme | α 4.06/n 2.00 (= sand) | permeability 1e-12 m² → ~1e-5 (d) | 0 | void ratio e0 = 3 before pre-compaction |
| A23 | same | 0.15–0.90 | 0.65 (d) | 0.3 | 0.05 | – | α 0.65/n 1.70 (silt) | 1e-13 → ~1e-6 (d) | 0 | e0 1.86 |
| A23 | same | 0.90–9.00 | 0.40 (d) | 0.55 | 0.05 | – | sand | 1e-11 → ~1e-4 (d) | 0 | e0 0.67 |
| A23 | "Simplified sand" (0–0.15 m as multi-layer) | 0.15–9 | 0.40 (d) | 0.6 | 0 | – | sand | 1e-11 | 0 | e0 0.67 |
| A23 | "Simplified silt" | 0.15–9 | 0.45 (d) | 0.55 | 0 | – | silt | 1e-13 | 0 | e0 0.82 |
| A23 | "Simplified clay" | 0.15–9 | 0.55 (d) | 0.45 | 0 | – | clay (α 1.49/n 1.25) | 1e-14 | 0 | e0 1.22 |
| A23 | "Simplified peat" | 0.15–9 | 0.80 (d) | 0 | 0.2 | – | peat (α 2.31/n 1.29) | 1e-12 | 0 | e0 4 |
| A23 | all, base layer in GROUND_freeW_seb | >9 | 0.3 (ice) | 0.7 | 0 | – | – | – | – | static. Text: "fully saturated … only the surface layer has a saturation of 50 %"; no initial excess ice. |
| A26 | Banks Island, Jesse moraine, ice-rich glacial till, GROUND_freezeC_RichardsEq_seb_pressure | 0–0.05 | 0.5 | 0.25 | 0.25 | – | α 4.06/n 2.00 | 1e-12 → ~1e-5 (d) | – | saturation 0.5; e0 1.5 |
| A26 | same | 0.05–1.00 | 0.46 | 0.54 | 0 | – | α 1.49/n 1.25 (clay) | 1e-13 → ~1e-6 (d) | 0 | "46 % porosity on average in the glacial till" |
| A26 | same | 1.00–9.00 | 0.82 | 0.18 | 0 | – | α 1.49/n 1.25 | 1e-13 → ~1e-6 (d) | ~2.0 (d, using the 0.05–1 m till as matrix) | "total volumetric ground ice content of about 80 % below 1 m" (buried and wedge ice) |
| A26 | same, base in GROUND_freeW_seb | >9 | 0.3 (ice) | 0.7 | 0 | – | – | – | – | snow layer: fc 0.05, K 1e-4 (Table 2) |
| St21 | Nyurba (Yakutia), "Forest" | 0 | 0.6 | 0 | 0.2 | 0.5 | n.r. | 1e-5 (Table A2) | – | natural porosity 0.8 |
| St21 | same | 0.08 | 0.6 | 0.1 | 0.2 | 0.5 | n.r. | 1e-5 | – | natural porosity 0.7 |
| St21 | same | 0.16 | 0.6 | 0.4 | 0 | 0.5 | n.r. | 1e-5 | – | natural porosity 0.6 |
| St21 | Nyurba, "Grassland" | 0 | 0.5 | 0.4 | 0.1 | 0.5 | n.r. | 1e-5 | – | natural porosity 0.5 |
| St21 | same | 0.04 | 0.4 | 0.6 | 0 | 0.5 | n.r. | 1e-5 | – | natural porosity 0.4 |
| St21 | same | 0.1 | 0.4 | 0.6 | 0 | 0.5 | n.r. | 1e-5 | – | natural porosity 0.4 |
| S23 | Svalbard glaciers, GLACIER_freeW_seb | 0–20 (47 layers, 0.1–1 m) | 1 (pure ice) | 0 | 0 | – | – | – | – | ice albedo 0.4; infinite ice reservoir below |

### B2. CryoGrid 3

Values are bulk fractions as published; φ is the natural porosity. Xice is a conversion (d) to the community-model convention. Field capacity and Ksat are global values per study.

| Src | Site / class | Layer (m) | wI | min | org | φ | st | Xice (d) | Notes |
|---|---|---|---|---|---|---|---|---|---|
| W16 T2 | Arga, Lena delta second terrace, "no excess ground ice" | 0–10 | 0.4 | 0.6 | 0.0 | 0.4 | sand | 0 | air 0 |
| W16 T2 | same | >10 | 0.3 | 0.7 | 0.0 | 0.3 | sand | 0 | |
| W16 T2/T3 | Samoylov Island, "medium excess ground-ice content" (= T3 "moist polygon center") | 0–0.15 | 0.4 | 0.1 | 0.15 | 0.75 | sand | 0 | air 0.35 |
| W16 | same | 0.15–0.9 | 0.65 | 0.3 | 0.05 | 0.65 | silt | 0 | |
| W16 | same | 0.9–9 | 0.65 | 0.3 | 0.05 | 0.4 | sand | 0.714; matrix 0.40 / 0.514 / 0.086 | super-saturated layer |
| W16 | same | >9 | 0.3 | 0.7 | 0.0 | 0.3 | sand | 0 | |
| W16 T2 | Ice complex, "high excess ground-ice content" | 0–0.15 | 0.3 | 0.1 | 0.1 | 0.8 | sand | 0 | air 0.5 |
| W16 | same | 0.15–0.55 | 0.7 | 0.25 | 0.05 | 0.7 | sand | 0 | |
| W16 | same | 0.55–20 | 0.9 | 0.05 | 0.05 | 0.4 | sand | 5.0; matrix 0.40 / 0.30 / 0.30 | |
| W16 | same | >20 | 0.3 | 0.7 | 0.0 | 0.3 | sand | 0 | |
| W16 T3 | Sa_Lake_1 thermokarst lake | 0–6 | 1.0 | 0 | 0 | 1.0 | sand | – | water column |
| W16 | same | 6–9 | 0.4 | 0.55 | 0.05 | 0.4 | sand | 0 | |
| W16 | same | >9 | 0.3 | 0.7 | 0 | 0.3 | sand | 0 | Table 4: k_m 3.0; geothermal flux 0.05 W m⁻² |
| N19 T3 | Samoylov polygon **centre**; Table 2: fc 0.50, K 1e-5 | 0–0.15 | 0.85 | 0 | 0.15 | 0.85 | sand | 0 | |
| N19 | same | 0.15–0.30 | 0.75 | 0.20 | 0.05 | 0.75 | sand | 0 | |
| N19 | same | 0.30–0.90 | 0.65 | 0.30 | 0.05 | 0.65 | silt | 0 | |
| N19 | same | 0.90–9.00 | 0.65 | 0.30 | 0.05 | 0.55 | sand | 0.286 | φ 0.55 described as "conservative" |
| N19 | same | >9.00 | 0.30 | 0.70 | 0 | 0.30 | sand | 0 | |
| N19 T3 | polygon **rim** | 0–0.10 | 0.50 | 0.10 | 0.15 | 0.75 | sand | 0 | |
| N19 | same | 0.10–0.60 | 0.65 | 0.30 | 0.05 | 0.65 | silt | 0 | |
| N19 | same | 0.60–9.40 | 0.75 | 0.20 | 0.05 | 0.55 | sand | 0.80 | |
| N19 | same | >9.40 | 0.30 | 0.70 | 0 | 0.30 | sand | 0 | |
| N19 T3 | polygon **trough** | 0–0.20 | 0.50 | 0 | 0.15 | 0.85 | sand | 0 | |
| N19 | same | 0.20–0.50 | 0.75 | 0.20 | 0.05 | 0.55 | sand | 0.80 | |
| N19 | same | 0.50–9.30 | 0.90 | 0.05 | 0.05 | 0.55 | sand | 3.5 | ice wedge |
| N19 | same | >9.30 | 0.30 | 0.70 | 0 | 0.30 | sand | 0 | measured K at the site: 1.09–46.3e-5 |
| N20 ST3 | Drained lake basins (LB), **centre**; fc 0.50 via N19; K 1e-5 (SI p. 6) | 0–0.1 | 0.85 | 0 | 0.15 | 0.85 | sand | 0 | vegetation |
| N20 | same | 0.1–0.2 | 0.75 | 0.10 | 0.15 | 0.75 | sand | 0 | |
| N20 | same | 0.2–1.0 | 0.65 | 0.25 | 0.10 | 0.65 | silt | 0 | |
| N20 | same | 1.0–10.0 | 0.65 | 0.20 | 0.15 | 0.55 | sand | 0.286; matrix 0.55 / 0.257 / 0.193 | excess-ice layer |
| N20 | same | 10–20 | 0.55 | 0.35 | 0.10 | 0.55 | sand | 0 | "younger taberit" |
| N20 | same | 20–40 | 0.45 | 0.50 | 0.05 | 0.45 | sand | 0 | "older taberit" |
| N20 | same | >40 | 0.10 | 0.90 | 0 | 0.10 | sand | 0 | bedrock |

**N20 ST3, LB rim and trough, excess-ice layers.** Values are wI/min/org, all with φ 0.55 and soil type sand:
- Rim, 0.9–10: 0.65/0.20/0.15 (Xice 0.286).
- Trough:
  - 0.6–0.8: 0.65/0.20/0.15 (Xice 0.286)
  - 0.8–1.8: 0.95/0.05/0 (Xice 8.0, ice wedge)
  - 1.8–2.8: 0.85/0.10/0.05 (Xice 2.0)
  - 2.8–3.8: 0.75/0.15/0.10 (Xice 0.8)
  - 3.8–10: 0.65/0.20/0.15 (Xice 0.286)

**N20 ST4, Holocene deposits (HD).**
- Centre: same top three layers as LB. Then 1.0–10.0: 0.65/0.20/0.15 (Xice 0.286); 10–30: 0.45/0.50/0.05 (φ 0.45); >30: 0.10/0.90 (bedrock).
- Rim, 0.9–10: 0.75/0.15/0.10 (Xice 0.8).
- Trough, 0.8–10: 0.95/0.05/0 (Xice 8.0).

**N20 ST5, Yedoma deposits (YD).**
- Centre:
  - 0–0.1: 0.85/0/0.15
  - 0.1–0.2: 0.75/0.10/0.15
  - 0.2–0.6: 0.65/0.25/0.10 (silt)
  - 0.6–20: 0.65/0.25/0.10, φ 0.55 (Xice 0.286)
  - 20–30: 0.55/0.35/0.10 (φ 0.55)
  - 30–50: 0.45/0.50/0.05 (φ 0.45)
  - >50: 0.10/0.90 (bedrock)
- Rim: 0.6–1.0: 0.65/0.25/0.10 (Xice 0.286); 1.0–20: 0.85/0.10/0.05 (Xice 2.0).
- Trough: 0.6–1.0 as the rim; 1.0–20: 0.95/0.05/0 (Xice 8.0, ice wedge).

**N20 ST6, reference run without excess ice.** 0–0.1: 0.85/0/0.15; 0.1–0.2: 0.75/0.10/0.15; 0.2–20: 0.65/0.25/0.10 (silt); 20–30: 0.55/0.35/0.10; 30–50: 0.45/0.50/0.05; >50: 0.10/0.90.

**N20 main-text Table 1, by unit (LB / HD / YD).**

| Quantity | LB | HD | YD |
|---|---|---|---|
| Ice-wedge depth | 3.8 m | 10 m | 20 m |
| Wedge-ice volume | 10 % | 30 % | 50 % |
| Excess ice content | 13 % | 19 % | 25 % |
| Ground ice content | 68 % | 74 % | 80 % |

Read as volume fractions, the excess ice contents give Xice 0.149 / 0.235 / 0.333 (d).

**How N20 assigned the units.**
- LB = 69 % of the IRYP Yedoma region (Strauss et al. 2016); YD = the remaining 31 %.
- HD = terrain 5–100 m a.s.l. with slope ≤ 4°, floodplains excluded.

**N21 Tables 2–3, generic Samoylov column.** fc 0.5; K_subs 1e-5.

| Layer (m) | wI | min | org | φ | st | Notes |
|---|---|---|---|---|---|---|
| 0–0.1 | 0.85 | 0 | 0.15 | 0.85 | sand | |
| 0.1–0.2 | 0.75 | 0.10 | 0.15 | 0.75 | sand | |
| 0.2 to dx−0.2 | 0.65 | 0.25 | 0.10 | 0.65 | silt | |
| dx−0.2 to dx | 0.65 | 0.20 | 0.15 | 0.55 | sand | |
| dx to 10 | θi | (1.05−θi)/2 | (0.95−θi)/2 | 0.55 | sand | |
| 10–30 | 0.45 | 0.50 | 0.05 | 0.45 | sand | |
| 30–1000 | 0.10 | 0.90 | 0 | 0.10 | sand | |

- Tile parameters (Table 3): dx is 1.0 / 0.9 / 0.7 / 0.9 m and θi is 0.65 / 0.75 / 0.95 / 0.75 for the centre / rim / trough / homogeneous tile.
- Homogeneous tile H, 0.9–10 m: 0.75 / 0.15 / 0.10 gives Xice 0.80 (d).

**M21, Šuoššjávri peat plateau (northern Norway), CryoGrid 3.**
- Mire peat, 0–3 m: "5 % mineral and 15 % organic material and a porosity of 80 %", unfrozen and saturated. That gives wI 0.80 (i).
- Silt, 3–10 m: "saturated mineral silt layer with 50 % porosity", giving wI 0.50 and mineral 0.50 (i).
- Bedrock: "3 % porosity".
- Plateau excess ice: "47 % (volume of excess ice/volume of unfrozen soil)", distributed between the base of the active layer (0.7 m) and the mineral base layer. That is Xice 0.47.
- Appendix A4: fc 0.55; K 1e-5.

**SvD21 Table 1, Prudhoe Bay tundra.**

| Layer (m) | wI | min | org | φ | Type |
|---|---|---|---|---|---|
| 0–0.3 | 0.7 | 0.05 | 0.2 | 0.75 | "Organic" |
| 0.3–2.3 | 0.4 | 0.55 | 0.05 | 0.4 | Silt |
| 2.3–10 | 0.4 | 0.55 | 0.05 | 0.4 | Sand |
| >10 | 0.3 | 0.7 | 0.0 | 0.3 | Sand |

- **Road centre** (heights above the tundra surface):
  - 2.5 to 2.4 m: 0.05/0.8/0, φ 0.2, "fine-grained gravel".
  - 2.4 to −1.5 m: 0.2/0.7/0, φ 0.3, "coarse-grained gravel".
  - Below that: the tundra silt and sand layers.
- **Code, "vulnerable" toe setting** (line 245 ff.): 1.0–2.0 m: 0.9/0.1/0.0, type 2, φ 0.4, comment "xice (50%)", which gives Xice 5.0 (d). The peat layer is type 4 in the code.
- **Code field capacities** (`main.m` lines 58–61): sandy mineral soil 0.25; peat 0.5; gravel 0.1.
- **Table 2:** K 1e-5; k_m 3.0; geothermal flux 0.05.

**JS21 Table 2, Kongsfjorden carbonate rock walls (Svalbard).** Mineral 0.97, waterIce 0.03 ("saturated"); water bucket depth 0.001 m.

**CG3 code default** (xice_mpi; the code says "default stratigraphy used in publication", without naming which publication).

| Layer top (m) | wI | min | org | Type | φ | Xice (d) |
|---|---|---|---|---|---|---|
| 0.0 | 0.80 | 0.05 | 0.15 | 1 | 0.80 | 0 |
| 0.1 | 0.80 | 0.15 | 0.05 | 1 | 0.80 | 0 |
| 0.4 | 0.80 | 0.15 | 0.05 | 1 | 0.55 | 1.25 |
| 3.0 | 0.50 | 0.50 | 0.00 | 1 | 0.50 | 0 |
| 10.0 | 0.30 | 0.70 | 0.00 | 1 | 0.30 | 0 |

The code also sets fieldCapacity 0.5, hydraulic_conductivity 1e-5, Qgeo 0.05 and kh_bedrock 3.0.

**Branch xice_mpi_flake, code only.** Columns are top (m), wI, min, org, type, φ: 0.0: 0.60/0.10/0.15, type 1, φ 0.75; 0.15: 0.65/0.3/0.05, type 2, φ 0.65; 0.9: 0.65/0.3/0.05, type 1, φ 0.65; 9.0: 0.30/0.70/0, type 1, φ 0.30.

### B3. CryoGrid 2 and CryoGrid 2D

Values are water/ice / mineral / organic / air, then type. These versions have no hydrology and no excess-ice concept.

**W13 (TCD Table 1), South Norway, classes keyed to the NGU surficial-sediment map.**

| Class (NGU codes) | Layer (m) | Values |
|---|---|---|
| Till and coarse colluvium (diamicton), thick (11, 15, 81) | 0–2 | 0.3/0.6/0.0/0.1 sand |
| | 2–10 | 0.4/0.6/0/0 sand |
| | >10 | 0.03/0.97/0/0 sand |
| Thin till and colluvium (12, 140) | 0–1 | 0.3/0.6/0/0.1 sand |
| | >1 | 0.03/0.97 sand |
| Bedrock (130) | >0 | 0.03/0.97/0/0 sand |
| Glaciofluvial sand/gravel (20, 21) | 0–1 | 0.1/0.6/0/0.3 sand |
| | 1–20 | 0.4/0.6/0/0 sand |
| | >20 | 0.03/0.97 sand |
| Esker (22) | 0–5 | 0.1/0.6/0/0.3 sand |
| | >5 | 0.03/0.97 sand |
| Recent fluvial sand/gravel (50) | 0–1 | 0.1/0.6/0/0.3 sand |
| | 1–10 | 0.4/0.6/0/0 sand |
| | >10 | 0.03/0.97 sand |
| Regolith (coarse), thin (70) | 0–1 | 0.1/0.6/0/0.3 sand |
| | 1–2 | 0.4/0.6 sand |
| | >2 | 0.03/0.97 sand |
| Regolith (coarse), thick (71) | 0–1 | 0.1/0.6/0/0.3 sand |
| | 1–5 | 0.4/0.6 sand |
| | >5 | 0.03/0.97 sand |
| Block fields (73) | 0–2 | 0.1/0.6/0/0.3 sand |
| | 2–5 | 0.4/0.6 sand |
| | >5 | 0.03/0.97 sand |
| Organic accumulation (bogs and mires) (90) | 0–0.5 | 0.3/0.2/0.3/0.2 sand |
| | 0.5–2 | 0.5/0.2/0.3/0 sand |
| | 2–10 | 0.5/0.4/0.1/0 silt |
| | >10 | 0.03/0.97 sand |
| Thin organic cover over bedrock or shallow regolith (100) | 0–0.5 | 0.5/0.5/0.1/0.0 sand **[UNSURE: sums to 1.1; C23 prints 0.40/0.50/0.10]** |
| | >0.5 | 0.03/0.97 sand |

**W13 text (Sect. 3.2)**, given as paraphrases with key quotes.
- Till: thick tills are 10 m with 40 % porosity; thin tills 1 m with 40 % porosity. The authors assume "a water/ice content of 30 % as an annual average … as some silt and clay in the tills increase the field capacity".
- Organics: thick deposits are 10 m, with "porosity of 50 % down to 2 m, organic content of 30 %". Organics over bedrock are 0.5 m with 50 % porosity.
- Glaciofluvial and fluvial: thick deposits are 20 m with 40 % porosity and "dry upper layers with 10 % water content", reflecting their "low water holding capacity".
- Colluvium: "the same ground properties as for thick till deposits".
- Weathered material and blockfields: 5 m, 40 % porosity, "low water/ice content within the upper 2 m".
- Bedrock: "constant porosity (3 %) and saturated".
- k_m is set per grid cell from NGU bedrock maps.
- Each 1 km cell takes its dominant sediment class (author response C3143).

**W15Z Table 1, Zackenberg (NE Greenland).** Classes come from an NDVI classification.

| Class | Layer (m) | Values |
|---|---|---|
| Fell | 0–3 | 0.05/0.6/0/0.35 sand |
| | 3–10 | 0.4/0.6 sand |
| | >10 | 0.03/0.97 sand |
| Dryas | 0–1 | 0.15/0.55/0/0.3 sand |
| | 1–10 | 0.4/0.6 sand |
| | >10 | 0.03/0.97 |
| Cassiope heath | 0–0.8 | 0.25/0.55/0/0.2 sand |
| | 0.8–10 | 0.4/0.6 sand |
| | >10 | 0.03/0.97 |
| Wetland | 0–0.6 | 0.5/0.45/0.05/0 silt |
| | 0.6–10 | 0.4/0.6/0/0 silt |
| | >10 | 0.03/0.97 sand |

Other W15Z parameters: k_m 3.0; k_organic 0.25.

**W17 Table 1, Lena delta.** Terraces from the Morgenstern et al. 2011 map, gridded to 1 km.

| Unit | Layer (m) | Values |
|---|---|---|
| First terrace (also assigned to active floodplains) | 0–0.15 | 0.6/0.1/0.15/0.15 sand |
| | 0.15–9 | 0.65/0.3/0.05/0 silt |
| | >9 | 0.3/0.7 sand |
| Second terrace | 0–10 | 0.4/0.6/0/0 sand |
| | >10 | 0.3/0.7 sand |
| Third terrace (Yedoma) | 0–0.15 | 0.3/0.1/0.1/0.5 sand |
| | 0.15–20 | 0.7/0.25/0.05/0 sand |
| | >20 | 0.3/0.7 sand |

- The authors deliberately assign "sand" to the ice-rich silt so that its freezing characteristic resembles "that of free water/ice rather than that of saturated silt".
- k_m 3.0; geothermal flux 50 mW m⁻².

**C19 Table 1, Iceland (CryoGrid 2).** Classes come from the Iceland soil map (Arnalds). FC is the freeze-curve type: 1 = sand, 2 = silt.

| Class | Layers (top–bottom m: wI/min/org/air, FC) |
|---|---|
| Cambic Vitrisol | 0–4: 0.04/0.60/0/0.36, 1; 4–10: 0.20/0.80/0/0, 1; >10: 0.08/0.92, 1 |
| Arenic Vitrisol | 0–4: 0.04/0.60/0/0.36; 4–10: 0.40/0.60; >10: 0.08/0.92 (all 1) |
| Pumice Vitrisol | 0–0.1: 0.20/0.20/0/0.60; 0.1–4: 0.04/0.60/0/0.36; 4–10: 0.20/0.80; >10: 0.08/0.92 (all 1) |
| Leptosol (lava surfaces, scree) | 0–1: 0.10/0.60/0/0.30; 1–10: 0.40/0.60; >10: 0.08/0.92 (all 1) |
| Brown Andosol | 0–1: 0.25/0.22/0.03/0.50, 2; 1–1.5: 0.75/0.22/0.03/0, 2; 1.5–10: 0.40/0.60, 1; >10: 0.08/0.92, 1 |
| Gleyic Andosol | 0–0.5: 0.30/0.14/0.06/0.50, 2; 0.5–1.5: 0.80/0.14/0.06/0, 2; 1.5–10: 0.40/0.60, 1; >10: 0.08/0.92, 1 |
| Histic Andosol | 0–0.5: 0.40/0.08/0.12/0.40, 2; 0.5–2: 0.80/0.11/0.09/0, 2; 2–10: 0.40/0.60, 1; >10: 0.08/0.92, 1 |
| Histosol | 0–0.5: 0.60/0.06/0.14/0.20, 2; 0.5–2: 0.80/0.08/0.12/0, 2; 2–10: 0.40/0.60, 1; >10: 0.08/0.92, 1 |
| Cryosol | 0–0.5: 0.30/0.12/0.08/0.50, 2; 0.5–2: 0.80/0.16/0.04/0, 2; 2–10: 0.40/0.60, 1; >10: 0.08/0.92, 1 |

Notes on C19:
- Bedrock is basalt with 8 % porosity.
- Mineral/rock conductivity is 2 W m⁻¹ K⁻¹.
- Soil complexes take the mean of their component stratigraphies.

**C23 Supplementary Table S1, Norway rock walls (CryoGrid 2D).** Values follow W13 except rock porosity, which is 5 %. Every class is underlain by class "a".

| Class | Layers (m: wI/min/org/air) |
|---|---|
| a, bedrock (NGU 130) | >0: 0.05/0.95/0/0 |
| b, thin till (NGU 12); c, thin colluvium (NGU 82) | 0–1: 0.30/0.60/0/0.10 |
| d, medium-thick till | 0–1: 0.30/0.60/0/0.10; 1–2: 0.40/0.60 |
| e, thick till (NGU 11); f, thick colluvium (NGU 81) | 0–2: 0.30/0.60/0/0.10; 2–10: 0.40/0.60 |
| g, weathered material | 0–2: 0.10/0.60/0/0.30 |
| h, thin organic cover over bedrock (NGU 100) | 0–0.5: 0.40/0.50/0.10/0 |
| i, thin regolith (NGU 72) | 0–1: 0.10/0.60/0/0.30; 1–2: 0.40/0.60 |
| j, medium-thick regolith | 0–1: 0.20/0.60/0/0.20; 1–4: 0.40/0.60 |
| k, fluvial/alluvial (NGU 50) | 0–1: 0.10/0.60/0/0.30; 1–10: 0.40/0.60 |
| l, blockfields (NGU 73) | 0–2: 0.10/0.60/0/0.30; 2–5: 0.40/0.60 |
| m, rock glacier (NGU 88) | 0–2: 0.05/0.60/0/0.35; 2–5: 0.10/0.60/0/0.30; 5–35: 0.40/0.60 |
| n, scree | 0–5: 0.02/0.40/0/0.58; 5 m to various depths: 0.60/0.40 |
| o, fractured bedrock | 0–10: 0.05/0.80/0/0.15; below 10 m: 0.10/0.90 |
| p, heavily fractured bedrock | 0–10: 0.05/0.75/0/0.20; below 10 m: 0.15/0.80/0/0.05 |
| q, very thick colluvium | 0–2: 0.05/0.60/0/0.35; 2–5: 0.10/0.60/0/0.30; 5–30: 0.40/0.60 |

Table S2 gives k_m per site of 2.3–3.1 W m⁻¹ K⁻¹.

**E22, Fig. A1 table** (Mannen and Gámanjunni; read from the image).

| Class | Layers (m: wI/min/org/air) |
|---|---|
| Bedrock | 0–100: 0.05/0.95/0/0 |
| Fluvial sediments | 0–1: 0.10/0.60/0/0.30; 1–10: 0.40/0.60; 10–100: 0.05/0.95 |
| Fractured bedrock | 0–10: 0.05/0.80/0/0.15; >10: 0.10/0.90 |
| Heavily fractured bedrock | 0–10: 0.05/0.75/0/0.20; >10: 0.15/0.80/0/0.05 |
| Scree | 0–5: 0.02/0.40/0/0.58; >5: **0.40/0.60** (My19 and C23 give 0.60/0.40) |
| Thick colluvium | 0–2: 0.30/0.60/0/0.10; 2–10: 0.40/0.60; 10–100: 0.05/0.95 |
| Thin colluvium | 0–1: 0.30/0.60/0/0.10; 1–100: 0.05/0.95 |
| Thick till | 0–2: 0.30/0.60/0/0.10; 2–10: 0.40/0.60; 10–20: 0.05/0.95 (the table is cut off below this) |

Bedrock conductivity in E22: 2.5 W m⁻¹ K⁻¹.

**E23 Table 2** (values are water/mineral/organic in %).

| Site | Layers | Bedrock k (W m⁻¹ K⁻¹) | Geothermal flux (W m⁻²) |
|---|---|---|---|
| Iskoras BH2 (quartzite) | <1.5 m: 10/75/0; 1.5–2 m: 20/75/0; >2 m: 2/98/0 | 5.5 | 0.05 |
| Tronfjell BH1 (schist) | <1.5 m: 15/85/0; 1.5–3 m: 10/90/0; >3 m: 3/98/0 (sums to 101 % as printed) | 4 | 0.03 |

**My19.**
- Solid bedrock: 98 % mineral, 2 % water.
- Talus, blocky surface (0–5 m): 40 % mineral, 2 % water, 58 % air.
- Talus, water-rich part (5–20 m): 40 % mineral, 60 % water/ice.
- k_m 3.5. The printed k_ice of 3.5 is likely a typo [UNSURE].

**W11 Table 2, Bayelva.**
- Soil, 0–10 m: maximum water content θw,max 0.30, minimum θw,min 0.05, mineral 0.60, organic 0.00, air 0.10, δ 0.17 °C.
- Bedrock, 10–100 m: only c 2.0 MJ m⁻³ K⁻¹ and k 2.5 W m⁻¹ K⁻¹.

### B4. CryoGrid.jl, CryoGridLite, Permafrost_cci and context

**G23 (CryoGrid.jl), Tables B1–B4.** Layers are top m: ξxic/ξpor/ξsat/ξorg.
- **Samoylov (B1):** 0: 0/0.80/1.0/0.50; 0.1: 0/0.80/1.0/0.25; 0.4: 0.3/0.55/1.0/0.25; 3.0: 0/0.50/1.0/0; 10: 0/0.30/1.0/0.
- **Bayelva (B2):** 0: 0/0.45/0.8/0.05; 0.1: 0/0.50/0.8/0.02; 0.5: 0/0.50/0.8/0.02; 1.0: 0/0.40/0.8/0.02; 10: 0/0.30/1.0/0.
  - G23 p. 3528: the Bayelva priors are "based on … Zweigel et al. (2021)". This is the only accessible numeric version of the W23/Zweigel Bayelva set-up.
  - Converted (d): 0–0.1 m: wI 0.36 / min 0.5225 / org 0.0275; 0.1–1 m: 0.40/0.49/0.01; 1–10 m: 0.32/0.588/0.012; >10 m: 0.30/0.70/0.
- **Barrow (B3, Romanovsky and Osterkamp 2000-based):** 0: 0/0.65/1.0/0.50; 0.2, 0.3 and 1.0: 0/0.55/1.0/0.
  - Converted (d): 0–0.2 m: wI 0.65 / min 0.175 / org 0.175; deeper: 0.55/0.45/0.
  - "both sites are known to have silty soil in the upper half meter".
- **Parsons Lake (B4):** 0: 0/0.5/0.8/0.50; 0.5: 0/0.5/0.8/0; 1.05: 0.05/0.3/0.8/0; 1.40: 0.25/0.40/0.8/0; 1.75: 0/0.30/1.0/0.
- **Table B5:** k_mineral 3.8; k_organic 0.25. Heat capacities are mineral 2.5 and organic 2.0 MJ K⁻¹ m⁻³. The CryoGrid.jl code has these two swapped [UNSURE].
- **CryoGrid.jl SamoylovDefault preset (v0.10.3), as commented in the code:**
  - 0 m: θwi 0.80, θm 0.05, θo 0.15, porosity 0.80;
  - 0.1 m: 0.80/0.15/0.05, porosity 0.80;
  - 0.4 m: 0.80/0.15/0.05, porosity 0.55, xic 0.30;
  - 3 m: 0.50/0.50/0;
  - 10 m: 0.30/0.70/0.
- **Current master preset:** adds a layer at 30 m with porosity 0.05; there is no xic field.
- **SimpleSoil code defaults:** fieldcapacity 0.20; kw_sat 1e-5.

**L24, CryoGridLite.** There is no class table. Stratigraphy is gridded from data sets:
- Organic fraction: Eq. 6, f_o = ρ_SOC / ((1−φ_o) ρ_om), with ρ_om 1300 kg m⁻³ and φ_o decreasing from 0.93 to 0.84 with depth. ρ_SOC comes from NCSCDv2.
- Mineral porosity: Eq. 8, φ_m = 0.49 − 0.11 f_sand.
- Wilting point: Eq. 9, θ_wp,m = 0.37 √f_clay.
- Mineral field capacity: Eq. 10, θ_fc,m = 0.45 f_clay^0.3496. Sand and clay fractions come from Open-ECOCLIMAP.
- Organic field capacity: 0.37–0.72.
- Soil thickness: from Pelletier et al. 2016.
- Bedrock: k_m 3.8 W m⁻¹ K⁻¹; pore space ranges from soil porosity down to 1 %.
- Excess ice is excluded.

**N23, CryoGridLite with excess ice.** Excess ice is static and taken from the Brown et al. (1997) ground-ice map: χ = 0–0.1 (low), 0.1–0.2 (medium) or 0.2–0.3 (high), applied from the surface down to zχ of 10–20 m. That converts to Xice 0–0.11 / 0.11–0.25 / 0.25–0.43 (d).

**CCI (Permafrost_cci).** No accessible document publishes a stratigraphy table.
- The model is CryoGrid CCI, built on CryoGrid 2. It uses "the same equations as GROUND_freeW_ubT" and has no excess ice.
- Classes are land-cover super-classes from Landcover_cci (bare, vegetated tundra, grassland, shrub, coniferous forest, deciduous forest, wetland) plus Yedoma tundra and Yedoma forest from an AWI binary Yedoma map.
- The stratigraphies come from "approx. 6500 samples from 700 pedons", grouped by land cover and clustered to seven depths. ATBD v4.0 Fig. 3 shows only the mineral fraction as a graph.
- In year 1 the project used generic stratigraphies from earlier CryoGrid studies (Langer 2013; Westermann 2013, 2016, 2017; ATBD v3.0 p. 19).
- The source code mirrors this. `ESA_CCI/DATA/LANDCOVER_CCI.m` groups CCI land-cover codes, and the Yedoma fraction splits the sparse-vegetation and deciduous-forest groups. `ESA_CCI/STRATIGRAPHY/STRAT_layers_confining_stratigraphies.m` mixes an "organic" and a "mineral" end-member with a stratigraphy_fraction. The end-member values are in parameter files that are not published.
- The pedon base is very likely Palmtag et al. 2022 ESSD ("651 soil pedons … more than 6500 samples"; same Yedoma classes). This is an inference, not stated in the documents.

**Context only (not CryoGrid stratigraphies).**
- **Ob19 (TTOP) rk by land-cover group** (Table 1): bare 0.95, grass/crop 0.75, shrub 0.8, deciduous forest 0.95, evergreen forest 0.9, wetland 0.55, urban 0.7.
- **An20 (CryoGrid 2 with salt, subsea)**: "5 m of silt was underlain by sand"; porosity 0.5 at the surface decreasing to 0.33 at 814 m; k_m 3.0 for silt and 5.0 for sand.

### B5. Repository examples (unpublished; for completeness)

**Template and example3.** File: `param_file_templates/Excel/GROUND_freezeC_bucketW_Xice_seb_snow.xlsx`; example3.xlsx has the same values.

| Layer top (m) | wI | min | org | Xice | fc | st |
|---|---|---|---|---|---|---|
| 0 | 0.3 | 0.5 | 0 | 0 | 0.3 | 1 |
| 0.5 | 0.5 | 0.5 | 0 | 0.5 | 0.3 | 2 |
| 10 | 0.5 | 0.5 | 0 | 0 | 0.3 | 1 |

- `GROUND_freeW_seb` takes over from 10 m.
- There is no satHydraulicConductivity column.
- Latitude and longitude are placeholders (79/10 or 70/10).

**Herschell_test_1/2/3.xlsx.** A three-tile example from 2021 by an unknown author; lat/lon 70/10 placeholder; no Ksat column.

| File | Layer top (m) | wI | min | org | Xice | fc | st |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 0.85 | 0.1 | 0.05 | 0 | 0.05 | 1 |
| 1 | 0.15 | 0.85 | 0.1 | 0.05 | 0 | 0.15 | 1 |
| 1 | 0.3 | 0.65 | 0.3 | 0.05 | 0 | 0.3 | 2 |
| 1 | 0.9 | 0.5 | 0.45 | 0.05 | 0.2 | 0.3 | 2 |
| 1 | 9.4 | 0.3 | 0.7 | 0 | 0 | 0.3 | 1 |
| 2 | 0 | 0.5 | 0.1 | 0.05 | 0 | 0.15 | 1 |
| 2 | 0.1 | 0.6 | 0.3 | 0.1 | 0 | 0.3 | 1 |
| 2 | 0.6 | 0.5 | 0.45 | 0.05 | 0.5 | 0.3 | 1 |
| 2 | 9.8 | 0.3 | 0.7 | 0 | 0 | 0.3 | 1 |
| 3 | 0 | 0.5 | 0 | 0.2 | 0 | 0.15 | 1 |
| 3 | 0.2 | 0.5 | 0.45 | 0.05 | 0.5 | 0.3 | 2 |
| 3 | 0.5 | 0.5 | 0.45 | 0.05 | 1 | 0.3 | 2 |
| 3 | 9.7 | 0.3 | 0.7 | 0 | 0 | 0.3 | 1 |

**Our own Tier-1 Herschel runs** (internal, not literature; CryoGridCommunity_results/*.xlsx):

| Layer top (m) | wI | min | org | Xice | Ksat | fc | st |
|---|---|---|---|---|---|---|---|
| 0 | 0.55 | 0.02 | 0.18 | 0 | 1e-4 | 0.05 | 1 |
| 0.15 | 0.35 | 0.55 | 0 | 0 | 1e-5 | 0.15 | 2 |
| top of permafrost (0.37–0.56, by site) | 0.45 | 0.55 | 0 | 0.29–0.82 | 1e-6 | 0.30 | 2 |
| 10 | 0.3 | 0.7 | 0 | 0 | 1e-6 | 0.3 | 2 |

---

## (C) Proposed default stratigraphy per ArcSurf class (proposal, with provenance)

### Shared rules for all classes

- **Classes:** GROUND_freezeC_bucketW_Xice_seb_snow down to the bedrock top or the base layer; GROUND_freeW_seb below.
- **Bedrock or base layer:** waterIce 0.03, mineral 0.97, organic 0 (W13 class 130; also M21, R23, JS21).
- **Ksat default: 1e-5 m s⁻¹** wherever no class-specific value exists. This is the value used in N19 (Table 2), N20 (SI), N21, M21 (A4), SvD21 (Table 2), St21 (Table A2), R23 (all stratigraphies) and the CG3 code.
- **Xice default: 0** in every class. This keeps ice interpretation out of the geology, in line with the addendum's rule 7.
  - Ice-rich overrides should come from a separate ground-ice layer.
  - The published rule keyed to a ground-ice map is N23: Brown et al. low / medium / high gives Xice 0–0.11 / 0.11–0.25 / 0.25–0.43 (d), applied from the surface down to 10–20 m.
  - Published class-specific examples are listed in the rows.
- **k_m 3.0 W m⁻¹ K⁻¹:** the CONSTANTS default, also used in W16, N19, St21, W15Z and W17.
- **Geothermal heat flux 0.05 W m⁻²:** W16, N19, R23, St21, SvD21.

Area figures are from the local `work_local/addendum_v01/parameter_classes.csv`; key = hclass/hclass2/texture/cover.

Column abbreviations as in B1. "[GAP]" means no published CryoGrid value.

| # | ArcSurf class (key; area) | Layer top (m) | wI | min | org | fc | st | Ksat | Xice | Provenance; confidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Glacier ice** (I; 2.15 M km²) | 0 | 1 | 0 | 0 | – | – | – | – | GLACIER_freeW_seb, "layers of pure ice" (W23 §2.2.8, p. 2620; code sets mineral to 0). S23: 20 m of ice in 47 layers, ice albedo 0.4. The bed is a **[GAP]**; C23 put bedrock "a" under glaciers with a 0 °C bed. Confidence: high for the class, gap for the bed. |
| 2 | **Bedrock** (R unknown 2.10 M; R discontinuous; R/T; R/C) | 0 | 0.03 | 0.97 | 0 | – | – (freeW) | – | 0 | W13 class 130 "3 %, saturated"; JS21 0.97/0.03; M21 and R23 3 %. If the layer must stay in the Xice class, use 0.05/0.95 (C23 "a", E22) with st 1 (W13 types it "sand"); fc and Ksat are then **[GAP]**. Variants: fractured rock (C23 "o", "p"); basalt 0.08/0.92 (C19); weathered top (E23). Rock k_m published as 2.0 (Iceland basalt, C19), 2.3–3.1 (Norway, C23 S2), 2.5 (E22), 3.5 (My19), 3.8 (L24), 4 schist and 5.5 quartzite (E23). Thin covers on bedrock: see rows 4b and 7b. Confidence: high. |
| 3 | **Colluvial bouldery** (C bouldery; 1.99 M) | 0 | 0.02 | 0.50 | 0 | 0.01 | 5 | 1e-5 | 0 | Mineral, fc and Ksat: R23 "blocks only". wI: My19/C23 blocky surface (i; mixes two sources). st 5 is the community equivalent of R23's free-water freezing, by the code comment. |
| | | 5 | 0.03 | 0.97 | 0 | – | freeW | – | 0 | R23: bedrock below 5 m. Alternatives: R23 "blocks with sediment" (min 0.75, fc 0.15, st 5); thick talus from C23 "n"/My19 (0–5 m: 0.02/0.40/0, air 0.58; then 0.60/0.40 water-saturated). Confidence: medium (Norway only). |
| 4a | **Till (diamicton)** (T diamicton 1.46 M; T unknown 0.93 M; T blanket 0.48 M; T bouldery; T/GF; T/Q) | 0 | 0.30 | 0.60 | 0 | 0.30 (i) | 1 | 1e-5 | 0 | W13 "till and coarse colluvium (diamicton), thick" (classes 11/15/81; same as C23 "e"). fc (i) from W13's sentence: "30 % … as some silt and clay in the tills increase the field capacity". Air 0.10. |
| | | 2 | 0.40 | 0.60 | 0 | 0.30 (i) | 1 | 1e-5 | 0 (ice layer) | W13 |
| | | 10 | 0.03 | 0.97 | 0 | – | freeW | – | 0 | W13 (bedrock below the 10 m "thick till"; the blanket thickness is to be fixed by the legend). Confidence: medium for coarse Fennoscandian tills; soil_type and fc uncertain for fine tills. |
| 4b | **Till veneer** (T veneer; T/R veneer; R/T veneer) | 0 | 0.30 | 0.60 | 0 | 0.30 (i) | 1 | 1e-5 | 0 | W13 thin till (classes 12/140; same as C23 "b"); bedrock from 1 m. C23 "d" medium till: 0–1 m 0.30/0.60, 1–2 m 0.40/0.60, then bedrock. |
| 4c | *Fine-matrix or ice-rich till (alternative)* | 0 | 0.50 | 0.25 | 0.25 | [GAP] | 1 | ~1e-5 (d) | 0 | A26, Banks Island (community model). |
| | | 0.05 | 0.46 | 0.54 | 0 | [GAP] | 3 | ~1e-6 (d) | 0 | A26; it used clay van Genuchten parameters. W23 (Bayelva) used silt. |
| | | 1.0 | 0.46 | 0.54 | 0 | [GAP] | 3 | ~1e-6 (d) | 2.0 (d), only where the ice layer says ice-rich | A26 total ice ~0.82 below 1 m |
| | | 9 | 0.30 | 0.70 | 0 | – | freeW | – | 0 | A26 base |
| 5 | **Colluvial fines / unknown / mixed** (C fines 0.88 M; C unknown 0.51 M; C mixed 0.40 M) | rows 4a/4b | same | same | same | 0.30 (i) | 2 (i; published value is 1) | 1e-5 | 0 | W13: colluvium has "the same ground properties as for thick till deposits". C23 "f" thick colluvium (NGU 81) and "c" thin colluvium (NGU 82, 0–1 m then bedrock). Using silt for "fines" is a choice made here; no published colluvium-fines value exists. Confidence: low–medium. |
| 6a | **Residual regolith, bouldery / blockfield** (W/C bouldery 0.83 M; W bouldery 0.23 M) | 0 | 0.10 | 0.60 | 0 | 0.15 | 5 | 1e-5 | 0 | Fractions: W13 block fields class 73 (same as C23 "l"). fc, st and Ksat: R23 "blocks with sediment" (i; mixes sources). Air 0.30. |
| | | 2 | 0.40 | 0.60 | 0 | 0.15 | 1 | 1e-5 | 0 | W13 class 73 |
| | | 5 | 0.03 | 0.97 | 0 | – | freeW | – | 0 | W13, R23. Alternative: R23 "blocks with sediment" over the whole 0–5 m (min 0.75; Juvvasshøe best fit 0.8). Confidence: medium. |
| 6b | **Residual regolith, fines / unknown** (W fines; W unknown; W/C fines, unknown, mixed) | 0 / 1 / 5 | 0.10 / 0.40 / 0.03 | 0.60 / 0.60 / 0.97 | 0 | [GAP] (0.10 i) | 1 (published) or 2 (i) | 1e-5 | 0 | W13 regolith (coarse), thick, class 71 (thin class 70: bedrock at 2 m; C23 "i", "j"). "Regolith over colluvium": no published two-unit stack exists **[GAP]**; a possible construction is thin regolith (0–2 m) over row 5. Confidence: low–medium. |
| 7a | **Organic (peat)** (O organic 0.63 M; O/L; L/O) | 0 | 0.30 | 0.20 | 0.30 | 0.55 | 4 (i) | 1e-5 | 0 | Fractions: W13 class 90 "bogs and mires" (W13 typed this layer "sand"; peat code 4 follows A23 practice). fc and Ksat from M21. Air 0.20. |
| | | 0.5 | 0.50 | 0.20 | 0.30 | 0.55 | 4 (i) | 1e-5 | 0 (palsas and peat plateaus: 0.47 from the active-layer base, M21, via the ice layer) | W13; M21 |
| | | 2 | 0.50 | 0.40 | 0.10 | 0.55 | 2 | 1e-5 | 0 | W13 (silt) |
| | | 10 | 0.03 | 0.97 | 0 | – | freeW | – | 0 | W13. Alternatives: M21 (3 m peat at 0.80/0.05/0.15 over 7 m silt at 0.50/0.50/0); A23 peat (organic 0.2, porosity 0.8, st 4, Ksat ~1e-5 d); W15Z "Wetland" for thin tundra organics; Iceland Histosol (C19). Confidence: medium. |
| 7b | **Thin organic on bedrock** (O or R veneer) | 0 | 0.40 | 0.50 | 0.10 | 0.55 | 4 (i) | 1e-5 | 0 | C23 "h", which corrects W13 class 100 (W13 prints 0.5/0.5/0.1, summing to 1.1 [UNSURE]). Bedrock from 0.5 m. |
| 8a | **Fluvial gravel / sand / unknown / mixed (upland)** (F gravel 0.43 M; F sand 0.41 M; F mixed 0.43 M; F unknown 0.42 M) | 0 | 0.10 | 0.60 | 0 | 0.10 (i) | 1 | ~1e-4 (d) | 0 | W13 "recent fluvial sand/gravel", class 50 (same as C23 "k" and E22 "fluvial"). fc (i) from W13's "dry upper layers with 10 % water content" and the SvD21 code gravel value of 0.1. Ksat (d) from A23 sand permeability (1e-11 m²). Air 0.30. |
| | | 1 | 0.40 | 0.60 | 0 | 0.10 (i) | 1 | ~1e-4 (d) | 0 | W13 |
| | | 10 | 0.03 | 0.97 | 0 | – | freeW | – | 0 | W13. Confidence: medium. |
| 8b | **Lowland alluvial sand (no shallow bedrock)** | 0 | 0.40 | 0.60 | 0 | 0.25 | 1 | ~1e-4 (d) | 0 | W16 / W17 Arga second terrace; fc from SvD21 code ("sandy soil"). |
| | | 10 | 0.30 | 0.70 | 0 | – | 1 | – | 0 | W16 / W17 |
| 8c | **Fluvial fines / alluvium with organics** (F fines; F/M fines; F/L; L/F) | 0 | 0.60 | 0.10 | 0.15 | 0.50 | 1 | 1e-5 | 0 | W17 first terrace (which "also" covers active floodplains); fc and Ksat from N19. Air 0.15. |
| | | 0.15 | 0.65 | 0.30 | 0.05 | 0.50 | 2 | 1e-5 | 0 | W17 |
| | | 9 | 0.30 | 0.70 | 0 | – | 1 | – | 0 | W17. Ice-wedge-polygon variant: W16 Samoylov 0.9–9 m (matrix 0.40/0.514/0.086, Xice 0.714 d) or N21 homogeneous tile (0.9–10 m, Xice 0.80 d). Confidence: medium (Lena delta only). |
| 9 | **Glaciofluvial** (GF gravel 0.34 M; GF unknown 0.20 M; GF sand 0.10 M) | 0 | 0.10 | 0.60 | 0 | 0.10 (i) | 1 | ~1e-4 (d) | 0 | W13 classes 20/21 (air 0.30) |
| | | 1 | 0.40 | 0.60 | 0 | 0.10 (i) | 1 | ~1e-4 (d) | 0 | W13 |
| | | 20 | 0.03 | 0.97 | 0 | – | freeW | – | 0 | W13. Esker (class 22): 0–5 m 0.10/0.60/0, air 0.3, then bedrock. Confidence: medium. |
| 10 | **Glaciolacustrine fines** (GL fines 0.23 M; GL unknown 0.21 M) **[GAP: proxy only]** | 0 | 0.375 (d) | 0.10 | 0.15 | 0.50 | 1 | ~1e-5 (d) | 0 | A23 "simplified silt" with its organic top layer; fc from N19 (site-specific). |
| | | 0.15 | 0.45 (d) | 0.55 | 0 | 0.50 | 2 | ~1e-6 (d) | 0 | A23 silt. Clay variant: 0.55 (d) / 0.45 / 0, st 3, ~1e-7 (d). |
| | | 9 | 0.30 | 0.70 | 0 | – | freeW | – | 0 | A23 base. Confidence: low. |
| 11 | **Marine / littoral** (M sand 0.16 M; M fines 0.08 M; M unknown 0.10 M; F/M); **glaciomarine** (GM ~0.22 M total) **[GAP: proxy only]** | 0 | 0.65 | 0.175 | 0.175 | 0.50 | 2 | 1e-5 | 0 | Fines: Barrow coastal-plain profile, G23 Table B3 converted (d). fc and Ksat generic (N19). |
| | | 0.2 | 0.55 | 0.45 | 0 | 0.50 | 2 | 1e-5 | 0 | G23 Table B3 (d). Alternative: SvD21 Prudhoe tundra (0–0.3 m organic 0.7/0.05/0.2; 0.3–2.3 m silt 0.4/0.55/0.05; 2.3–10 m sand; code fc mineral 0.25, peat 0.5). Sand variant: row 8b. **Pore-water salinity cannot be represented in this class [GAP].** Confidence: low. |
| 12 | **Lacustrine** (L fines; L unknown; L/F; L/O; ~0.96 M total) | 0 | 0.85 | 0 | 0.15 | 0.50 | 1 | 1e-5 | 0 | Inside the Yedoma region: N20 drained lake basins (LB), centre tile. fc from N19; Ksat from N20 SI. |
| | | 0.1 | 0.75 | 0.10 | 0.15 | 0.50 | 1 | 1e-5 | 0 | N20 LB |
| | | 0.2 | 0.65 | 0.25 | 0.10 | 0.50 | 2 | 1e-5 | 0 | N20 LB |
| | | 1.0 | 0.55 | 0.257 | 0.193 | 0.50 | 1 | 1e-5 | 0.286 (d) | N20 LB "ice-rich deposits" |
| | | 10 | 0.55 | 0.35 | 0.10 | – | 1 | 1e-5 | 0 | N20 LB |
| | | 20 | 0.45 | 0.50 | 0.05 | – | 1 | – | 0 | N20 LB |
| | | 40 | 0.10 | 0.90 | 0 | – | 1 | – | 0 | N20 LB bedrock (porosity 0.10, so it can stay in the Xice class). Outside the Yedoma region: **[GAP]**, use row 10. Lake-bottom sediment under existing lakes: W16 Sa_Lake_1 (6–9 m 0.40/0.55/0.05, sand). Confidence: medium inside the Yedoma region, low elsewhere. |
| 13 | **Thermokarst / alas** (K; 0.06 M) | as row 12 | | | | | | | | N20 LB is the closest published analogue. Central Yakutian alas: **[GAP]** (Stuenzi et al. 2025, JGR-ES, was not accessible). Confidence: low–medium. |
| 14 | **Ice complex / Yedoma** (Y; 0.29 M; Y fines, Y/L, Y/E) | 0 | 0.30 | 0.10 | 0.10 | 0.50 | 1 | 1e-5 | 0 | W16 "Ice complex, high excess ground-ice content"; fc and Ksat from N19/N20. Air 0.50. |
| | | 0.15 | 0.70 | 0.25 | 0.05 | 0.50 | 1 | 1e-5 | 0 | W16 |
| | | 0.55 | 0.40 | 0.30 | 0.30 | 0.50 | 1 | 1e-5 | 5.0 (d) | W16: bulk 0.9/0.05/0.05 with porosity 0.4 |
| | | 20 | 0.30 | 0.70 | 0 | – | 1 | – | 0 | W16. Alternatives: the N20 YD tile set (Xice centre 0.286, rim 2.0, trough 8.0 (d); landscape excess ice 25 %, ground ice 80 %); W17 Yedoma (CryoGrid 2: 0.15–20 m 0.7/0.25/0.05, no excess ice). All sources type the ice-rich silt "sand" on purpose (W17). Confidence: medium–high. |
| 15 | **Eolian** (E sand 0.06 M; E fines 0.11 M; E unknown; Y/E; E/L) **[GAP: proxy only]** | – | | | | | | | | Sand: row 8b (Arga sands are fluvial, not eolian). Loess: row 10 (A23 silt). Confidence: low. |
| 16 | **Glaciomarine** (GM) **[GAP: proxy only]** | – | | | | | | | | Fines: row 11. GM veneer: thin cover over bedrock (row 4b geometry). Confidence: low. |
| 17 | **Quaternary volcanic** (V; 0.12 M) | 0 | 0.10 | 0.60 | 0 | [GAP] | 1 | [GAP] (1e-5 generic) | 0 | C19 "Leptosol" (lava surfaces and scree; Iceland). Air 0.30. |
| | | 1 | 0.40 | 0.60 | 0 | [GAP] | 1 | 1e-5 | 0 | C19 |
| | | 10 | 0.08 | 0.92 | 0 | – | 1 | – | 0 | C19 basalt. Porosity 0.08 is above the lookup-table minimum, so it can stay in the Xice class; k_m 2.0. Tephra or volcanic sand: C19 "Cambic Vitrisol" (0–4 m: 0.04/0.60/0, air 0.36; 4–10 m: 0.20/0.80/0; >10 m: 0.08/0.92). Iceland only. Confidence: medium. |
| 18 | **Quaternary undivided** (Q; 0.38 M); also X anthropogenic and U unmapped | – | | | | | | | | **[GAP].** Two options: (a) row 4a as a generic default for glaciated terrain (i); (b) the published CryoGridLite method (L24, Eqs. 6–15) using Open-ECOCLIMAP texture, NCSCDv2 SOC and Pelletier soil thickness. Option (b) gives a method, not values. Water (H) belongs in the LAKE classes, not GROUND. |

---

## (D) Gaps and caveats

> **Verification 2026-10-08.** The final paper, Westermann et al. 2013, The Cryosphere 7, 719-739, is now in `lit_2026-10-07/westermann2013_tc-7-719-2013.pdf`. Its Table 1, p. 723, matches the discussion-version values used below for every class: 11/15/81, 12/140, 130, 20/21, 22, 50, 70, 71, 73, 90 and 100.
>
> Class 100 ("thin organic cover over bedrock or shallow regolith", 0-0.5 m) is printed as water/ice 0.5, mineral 0.5, organic 0.1 and air 0.0 in the final paper too. These sum to 1.1, so the [UNSURE] remains, and the corrected Czekirda et al. 2023 values (0.40 / 0.50 / 0.10) used in row 7b stand.
>
> The Zenodo record of Westermann et al. 2023 (doi:10.5281/zenodo.6522424, CC BY 4.0: CryoGridCommunity_run.zip, _source.zip, _parameter_files.zip, 8.7 MB) is in `lit_2026-10-07/zenodo_6522424/`. Its Bayelva reference run (`reference_run/reference_run.xlsx`, STRAT_layers; read 2026-10-08) gives two layers above the base:
>
> | Layer top | waterIce | mineral | organic | soil_type | field_capacity |
> |---|---|---|---|---|---|
> | 0 m and 0.1 m | 0.4 | 0.6 | 0 | 2 (silt) | 0.2 |
> | 5 m (bedrock) | 0.03 | 0.97 | 0 | 1 | 0.03 |
>
> - The layer table has no Xice or satHydraulicConductivity column.
> - `reference_run_sand` is identical except soil_type 1 throughout.
> - The field capacity of 0.2 for a silty mineral soil is one of the few published per-material values. It is a candidate for the fine-grained rows (5, 10, 11), which so far use the generic 0.5 or an interpretation.


**1. Documents not read, or read only in part.**
- **Westermann 2013, final paper.** All W13 values come from the TCD discussion version (Table 1, pp. 5391–5392); the final Table 1 matches them (verification of 2026-10-08 above). The two author responses mention no change to the stratigraphies. Class 100 sums to 1.1, and Czekirda 2023 prints it as 0.40 water.
- **Westermann 2023 Bayelva numbers.** They exist only in the Zenodo zip (doi:10.5281/zenodo.6522424, `reference_run/reference_run.xlsx` plus 15 variants, including `reference_run_sand`). The zip was not used here; G23 Table B2 is the closest substitute based on Zweigel.
- **Not accessible:**
  - Zweigel 2021 (Wiley, 403).
  - Langer 2013 (Remote Sensing of Environment) and Langer 2016 (JGR).
  - Martin 2019 (JGR): HAL showed a bot wall.
  - Stuenzi 2022 and 2025.
  - Gisnås 2013 and 2017.
  - Myhra 2017; Hilger 2021; Etzelmüller 2020 (QSR).
  - Several copies on AWI ePIC are behind an Anubis bot-protection page. **We did not try to get around it.**
- **Single-route reads:**
  - W17 Table 1 comes from the publisher XML only, in two identical reads.
  - M21 values come from the HTML text only, in two consistent reads.

**2. Model-generation mismatch.**
- CryoGrid 2 and 2D (W13, W15Z, W17, C19, C23, E22, E23, CCI) have no water balance and no excess-ice concept, use the Dall'Amico freezing curve, and type peat as sand or silt.
- CryoGrid 3 uses natural porosity, one global field capacity and one global K.
- The target class uses a matrix plus an Xice ratio, field capacity and Ksat per layer, and the Painter–Karra freezing curve with per-soil-type van Genuchten parameters.
- The A4 conversions are exact for mass and volume. **Thermal behaviour calibrated in CryoGrid 2 will not transfer one-to-one,** because the freezing curve and the hydrology differ.

**3. soil_type of ice-rich layers.** CryoGrid 2 and 3 deliberately type ice-rich silt as "sand" (W17 quote). In the community class the excess ice already melts as free water, so typing the matrix "silt" (2) would be physically consistent. Which convention to follow needs a decision. My rows keep the published "sand".

**4. Field capacity and saturated hydraulic conductivity.** These are the biggest gaps.
- Published per-material field capacities: R23 for blocky material (0.01 / 0.15 / 0.25); SvD21 **code only** (sandy mineral 0.25, peat 0.5, gravel 0.1); single site values of 0.50 (N19, N21, St21, CG3 code) and 0.55 (M21).
- Published Ksat: 1e-5 everywhere; texture-specific values only as permeabilities in A23 and A26, converted (d) in these rows.
- **No CryoGrid source gives either quantity for till, glaciolacustrine, marine, lacustrine or eolian deposits.** My till and gravel field capacities (0.30 / 0.10) are interpretations (i) of W13 water contents.
- A published method exists in L24, Eq. 10: θ_fc,m = 0.45 f_clay^0.3496. It needs sand and clay fractions per texture class, which would have to come from outside the CryoGrid literature.

**5. Excess ice.**
- Published Xice-type values are site-specific: Samoylov, the Lena delta, NE Siberian Yedoma, peat plateaus in N Norway, Banks Island till, and the Prudhoe Bay toe (code).
- Rule 7 says the geology should not carry ice. Xice is therefore set to 0, with the published map-keyed rule of N23 (Brown et al. 1997 classes) as the override.
- Yedoma presence is the one exception.
- The ground-ice sample database (InICE) was not used. It could later calibrate the Xice ranges and porosities.
- **Terminology trap:** N19 and N20 call θw0 − φ "x % excess ice", which is not the excess-ice volume fraction (A4).

**6. Thickness.** Published layer thicknesses are regional. W13 for South Norway uses thick till 10 m, thin till 1 m, regolith 2 or 5 m, glaciofluvial 20 m, fluvial 10 m and organics 10 m (2 m organic-rich). C19 uses a uniform 10 m regolith; W16/W17 use 9–20 m. The map's veneer and blanket terms need numeric thicknesses per legend system; this is still open in the addendum.

**7. Geographic coverage.** The published class stratigraphies come from:
- South and North Norway (W13, R23, C23, E22, E23, M21);
- Iceland (C19);
- NE Greenland (W15Z);
- Svalbard (W23, JS21, W11, G23);
- the Lena delta and NE Siberia (W16, W17, N19–N21);
- the Alaska North Slope (SvD21, G23 Barrow);
- the Mackenzie area (G23 Parsons Lake);
- Banks Island (A26);
- Yakutia (St21).

There is nothing for the Canadian Shield or the main Laurentide till sheets, the West Siberian lowland, Taymyr or Chukotka, beyond the samples behind CCI. The coarse, sandy South Norwegian till of W13 (described as "coarse-grained with dominance of sand and gravel") is probably not representative of fine Arctic lowland tills.

**8. Code constraints.**
- Porosity below 0.05 cannot be simulated in the Xice class, so bedrock must go in GROUND_freeW_seb or be set to 0.05.
- k_m is one value per run.
- Xice is set to 0 wherever the initial temperature is above 0 °C.
- Ksat must be given as a STRAT_layers column, or the class fails (the Tier-1 lesson).
- Free-water freezing (blocky material in R23) maps to soil_type 5 in this class.

**9. Inconsistencies in the sources.**
- W13 TCD class 100 sums to 1.1.
- E23 Tronfjell's >3 m row sums to 101 %.
- E22 gives scree below 5 m as 0.40/0.60, against 0.60/0.40 in My19 and C23.
- My19 prints k_ice as 3.5, likely a typo.
- G23 heat capacities are swapped relative to the CryoGrid.jl code.
- N20 gives the LB ice-wedge depth as 3.8 m in its tables and 4.0 m in the SI text.
- The CG3 code default says "used in publication" without naming the publication.

**10. Permafrost_cci and GlobPermafrost.** No stratigraphy tables are published. The classes are land cover, not geology. GlobPermafrost documents returned 403.

**11. What was created.**
- Text extractions, code copies and table renders were kept in the temporary working folder (section 0) and are not archived.
- Nothing was written to the project folders or the HPC, and no jobs were run.
