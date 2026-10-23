# ArcSurf code

Code, crosswalk tables, legend transcriptions and georeferencing records of ArcSurf, the harmonised surficial geology map of the Arctic (Lantuit and Fritz, Earth System Science Data, @PAPER_DOI@; data on PANGAEA: geology and A0 wall map @DATA_DOI@, addendum @ADDENDUM_DOI@).

With these files and the published source maps (Appendix A of the paper; `sources.csv` of the data release), the ArcSurf layer can be rebuilt.

## Contents

| Folder | Content |
|---|---|
| `scripts/` | The processing chain: ingest of every source (`ingest_*.py`), extraction of vector PDFs (`pdf_to_polygons.py`), colour scans and previews (`jpg_to_polygons.py`) and line maps (`line_georef_ingest.py`, `ingest_gsc_lines.py`), crosswalks (`build_xw.py`, `check_xwalk.py`), the precedence merge (`merge_tiles.py`, `merge_subset.py`), glaciers (`ice_*.py`), Yedoma and permafrost-zone splits, the dissolved release geometry with persistent identifiers (`dissolve_release.py`, `dissolve_check.py`), the addendum (`addendum_*.py`), the release exports (`export_release.py`, `export_addendum_release.py`) and the figures and statistics of the paper (`essd/`) |
| `xwalk/` | Crosswalk tables from the native units of every source to the ArcSurf attributes (`hclass`, `hclass2`, `texture`, `cover`) |
| `legends/` | Legend transcriptions of the Russian sheets and of the scanned Canadian maps: one table per sheet with the unit index, swatch colour, description and harmonised attributes |
| `georef/` | Georeferencing record of every Russian sheet as used in the map: projection, frame corners and graticule ties, residuals, pixel size and classification statistics (`pdfvec*/<sheet>_qa.json` for vector PDFs, `jpgvec/<sheet>.json` for scans and previews) |
| `sources/` | Source registries (sheet lists, footprints and metadata used by the ingest scripts) |
| `addendum/` | Documentation of the addendum: column definitions, cover-term thicknesses by legend system and the compilation of published CryoGrid stratigraphies |
| `LEGEND.md` | The harmonised legend |

## Processing chain

1. **Ingest:** each source is read in its native form and standardised to one schema with its provenance (source, sheet, native code and description, scale, year, licence).
2. **Crosswalk:** native units are translated into the harmonised attributes with the tables in `xwalk/` and `legends/`.
3. **Merge:** 100 km tiles in EPSG:6931; source footprints are ranked by scale, confidence tier and year, and each claims the land not yet claimed.
4. **Glaciers:** all glacier ice is taken from PROMICE-2022 and the Randolph Glacier Inventory 6.0.
5. **Splits:** the pieces are cut at the limits of the permafrost zones (Obu et al., 2019) and of the IRYP v2 Yedoma domain.
6. **Release geometry:** pieces with identical attributes are merged across the tile seams and these limits, and every polygon receives its persistent identifier `asid`.
7. **Addendum:** polygon context and CryoGrid stratigraphies.
8. **Exports:** the release (`export_release.py`, `export_addendum_release.py`), split into one GeoPackage per geometry for the repository (`split_release_by_geometry.py`); statistics and figures of the paper.

The scripts were run on the Albedo high-performance computer of the Alfred Wegener Institute (SLURM wrappers `run_py.sh`, `run_dissolve.sh`, `run_merge46.sh`); paths in the scripts point to its file system. Python 3.11 with GeoPandas 1.1, Shapely 2.1 (GEOS 3.14.1), pyogrio 0.12, pandas 3.0, NumPy 2.4, SciPy 1.17, PyMuPDF and Pillow.

## Licence

The scripts are licensed under the MIT licence (`LICENSE`); the tables and documents (`xwalk/`, `legends/`, `georef/`, `sources/`, `addendum/`, `LEGEND.md`) under CC BY 4.0 (`LICENSE-TABLES.md`). The source maps remain under the terms of their publishers; the original GEUS datasets remain available from GEUS Dataverse under CC BY-SA 4.0, and the GEUS-derived component of ArcSurf is published under CC BY 4.0 with separate permission from GEUS.

## Citation

Please cite this code with the DOI of its version (`CITATION.cff`, Zenodo), together with the data release and the data paper. Contact: Hugues Lantuit, Alfred Wegener Institute, Helmholtz Centre for Polar and Marine Research, Potsdam, Germany (hugues.lantuit@awi.de).

## Funding

This work was supported by the European Union’s Horizon Europe Research and Innovation Programme, ILLUQ Project [101133587].
