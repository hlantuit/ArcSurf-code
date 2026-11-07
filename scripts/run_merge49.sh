#!/bin/bash
# Merge 49 (2026-11-06): merge 48 plus
#  - Ontario (ca_on_eds014, ca_on_fnpmp): the Ministry of Energy and Mines granted CC BY 4.0 for the OGS-derived
#    component (correspondence/2026-11-06_OGS_CC-BY_permission_received.txt); licence texts in patch_licence_open.py
#    (Crown copyright credit with the year, the statement the Ministry asked for). Their std/ and xw/ GeoPackages are
#    those of merge 45 (same schema as the current sources).
#  - the R-(60) part (177-180E) of the R-(60)-2 preview: sheet R-60-2_g2pv (ru_vsegei_preview), the west end of Wrangel
#    Island and the Chukotka mainland strip, until now on the 1:2.5M map (work/pv_wr, work_local/map_review_m48/ARTEFACTS.md). Merge 48 ingested only ru_vsegei_pdf; this chain
#    re-ingests ru_vsegei_preview (gate: its crosswalk gains exactly the 12 R-60-2_g2pv keys and N-44-XVI|WATER,
#    the Novosibirsk Reservoir fix of 2026-10-22 that fix_n44_m46.sh ingested into ru_vsegei_pdf instead of
#    ru_vsegei_preview, so merges 46-48 never had it; no class column changes).
#  - the crosswalk CSVs edited before the run (XW_EDITED, originals in _backups/ingest_m49/<src>.xwalk_m48.csv): their
#    xw GeoPackages are rebuilt from std (gate: each CSV differs from its backup only in the rows listed in XW_SPEC).
# Full merge into work/tiles_m49 (MERGE_TDIR); final_m48 and release_m48 stay as they are.
# Run on a login node FROM scripts/:  [XW_EDITED="src ..."] [AFTER=jobid] bash run_merge49.sh
# Afterwards (not in this chain): data READMEs (numbers_release_m49.json), the addendum zip, the manuscript numbers and
# the Ontario references, the package; then the upload of release_m49 to PANGAEA (PDI-45690).
set -e
cd /albedo/work/user/hlantuit/arctic_surficial/scripts
R=/albedo/work/user/hlantuit/arctic_surficial
W=$R/work
PY=/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python
XA="-A perm_ag_coas.perm_ag_coas -p smp --qos=12h"
X="--export=ALL,SURF_DOMAIN=domain $XA"
B=$R/_backups/ingest_m49
[ ! -e $W/final_m49 ] && [ ! -e $W/tiles_m49 ] || { echo "work/final_m49 or work/tiles_m49 exists already"; exit 1; }
# every in-place fix of an extracted sheet must still be in it (merge 47 lost the Baikal water of M-47-48_g2)
for f in $W/jpgvec/*.gpkg.fixes.txt; do
    if [ "${f%.fixes.txt}" -nt "$f" ]; then echo "${f%.fixes.txt} is newer than its fixes record: re-apply them"; exit 1; fi
done
# the new preview sheet: extraction record and legend in place
[ -s $W/jpgvec/R-60-2_g2pv.json ] && [ -s $R/sources/legend_R-60-2_g2pv.csv ] || { echo "R-60-2_g2pv missing"; exit 1; }
grep -q "'R-60-2_g2pv'" ingest_russia.py || { echo "R-60-2_g2pv not registered in ingest_russia.py"; exit 1; }
grep -q "ca_on_eds014" patch_licence_open.py && grep -q "ca_on_fnpmp" patch_licence_open.py \
    || { echo "patch_licence_open.py has no Ontario entry"; exit 1; }
mkdir -p $B $W/tiles_m49
cp -n $R/xwalk/ru_vsegei_preview.csv $B/ru_vsegei_preview.xwalk_m48.csv
for s in ${XW_EDITED:-}; do
    [ -s $B/$s.xwalk_m48.csv ] || { echo "$s: no backup of its crosswalk in $B"; exit 1; }
done

# the source list of the merge: merge 48's plus Ontario (old list kept)
cp $W/merge_sources.json $W/merge_sources_m48.json
$PY -c "import json; p='$W/merge_sources.json'; s=json.load(open(p)); s+=[x for x in ('ca_on_eds014','ca_on_fnpmp') if x not in s]; json.dump(s, open(p,'w'), indent=1); print(len(s), 'sources')"
SRC=$($PY -c "import json; print(','.join(json.load(open('$W/merge_sources.json'))))")
dep=${AFTER:+--dependency=afterany:$AFTER}

ip=$(sbatch --parsable $X $dep -c 16 --mem=160G --time=10:00:00 -J ing_pv49 -o $W/ing_pv49.out \
    run_py.sh ingest_russia.py ru_vsegei_preview)
g1=$(sbatch --parsable $XA -c 1 --mem=4G --time=00:10:00 -J gate1_49 --dependency=afterok:$ip -o $W/gate1_49.out \
    run_py.sh $W/_qc/gate_m49.py xwalk $B/ru_vsegei_preview.xwalk_m48.csv $R/xwalk/ru_vsegei_preview.csv 'R-60-2_g2pv|' 12     'N-44-XVI|WATER=H')
xp=$(sbatch --parsable $X -c 8 --mem=64G --time=02:00:00 -J xw_pv49 --dependency=afterok:$g1 -o $W/xw_pv49.out \
    run_py.sh build_xw.py ru_vsegei_preview)
after=$xp
for s in ${XW_EDITED:-}; do
    gs=$(sbatch --parsable $XA -c 1 --mem=4G --time=00:10:00 -J gate_${s}_49 -o $W/gate_${s}_49.out \
        run_py.sh $W/_qc/gate_m49.py same $B/$s.xwalk_m48.csv $R/xwalk/$s.csv "$(cat $B/$s.spec)")
    xs=$(sbatch --parsable $X -c 8 --mem=96G --time=02:00:00 -J xw_${s}_49 --dependency=afterok:$gs -o $W/xw_${s}_49.out \
        run_py.sh build_xw.py $s)
    after=$after:$xs
done
m=$(sbatch --parsable --export=ALL,SURF_DOMAIN=domain,MERGE_TDIR=$W/tiles_m49 $XA -c 32 --mem=200G --time=12:00:00 \
    -J merge49 --dependency=afterok:$after -o $W/merge49.out run_py.sh merge_tiles.py $SRC)
df=$(sbatch --parsable $XA -c 16 --mem=64G --time=01:00:00 -J diff49 --dependency=afterok:$m -o $W/diff49.out \
    run_py.sh $W/_qc/gate_m49.py diff tiles_m49 tiles_m48 --workers 16 \
    --expect "ca_on_eds014,ca_on_fnpmp,ca_gsc_5m,ca_gsc_scans,ca_gsc_cgm,ru_vsegei_preview,ru_vsegei_q2500,${XW_EDITED// /,}")
s=$(sbatch --parsable $X -c 2 --mem=8G --time=00:30:00 -J snap49 --dependency=afterok:$m -o $W/snap49.out \
    --wrap "cd $W && mkdir final_m49 && ln tiles_m49/*.parquet final_m49/ && ls final_m49 | wc -l")
pl=$(sbatch --parsable $X -c 4 --mem=64G --time=02:00:00 -J lic49 --dependency=afterok:$s -o $W/lic49.out \
    run_py.sh patch_licence_open.py m49)
v=$(sbatch --parsable $XA -t 12:00:00 -c 32 --mem=200G -J dissolve_m49 --dependency=afterok:$pl -o $W/dissolve_m49.out \
    --wrap "cd $PWD && $PY dissolve_release.py --tiles $W/final_m49 --out $W/dissolve_m49 --workers 32")
dc=$(sbatch --parsable $XA -t 04:00:00 -c 32 --mem=200G -J dcheck_m49 --dependency=afterok:$v -o $W/dcheck_m49.out \
    --wrap "cd $PWD && $PY dissolve_check.py $W/dissolve_m49 --workers 32 --csv $W/_qc/dcheck_m49_residual.csv --compare 1000")
ad=$(sbatch --parsable $X --exclude=prod-080 -c 32 --mem=200G --time=03:00:00 -J addv14 --dependency=afterok:$v -o $W/addv14.out \
    run_py.sh addendum_v02.py $W/final_m49 $W/dissolve_m49 $W/addendum_v14)
as=$(sbatch --parsable $X -c 8 --mem=160G --time=02:00:00 -J addstrat14 --dependency=afterok:$ad -o $W/addstrat14.out \
    run_py.sh addendum_strat.py $W/dissolve_m49 $W/addendum_v14)
st=$(sbatch --parsable --export=ALL,SURF_DOMAIN=domain,ESSD_TILES=$W/final_m49,ESSD_OUT=$W/essd_tables_m49 $XA \
    -c 32 --mem=200G --time=04:00:00 -J essdst49 --dependency=afterok:$pl -o $W/essdst49.out run_py.sh essd/essd_stats.py)
mp=$(sbatch --parsable $X -c 32 --mem=160G --time=04:00:00 -J essdmap49 --dependency=afterok:$pl -o $W/essdmap49.out \
    run_py.sh essd/essd_maps.py $W/final_m49 --export)
re=$(sbatch --parsable $X -c 16 --mem=120G --time=08:00:00 -J release49 --dependency=afterok:$v -o $W/release49.out \
    run_py.sh export_release.py m49 --full --name ArcSurf_v1.0)
ar=$(sbatch --parsable $X -c 4 --mem=96G --time=02:00:00 -J addrel49 --dependency=afterok:$as -o $W/addrel49.out \
    run_py.sh export_addendum_release.py $W/dissolve_m49 $W/addendum_v14 $W/release_m49)
# the residual count comes from the separate topology check (merge 48: numbers_release read the dissolve log, N_RESID '?')
nu=$(sbatch --parsable $X -c 4 --mem=96G --time=01:00:00 -J numrel49 --dependency=afterok:$as:$dc -o $W/numrel49.out \
    run_py.sh essd/numbers_release.py $W/dissolve_m49 $W/addendum_v14 $W/dcheck_m49.out $W/numbers_release_m49.json)
sr=$(sbatch --parsable $X -c 2 --mem=48G --time=00:40:00 -J srctab49 --dependency=afterok:$v -o $W/srctab49.out \
    run_py.sh essd/sources_table.py $W/dissolve_m49 $W/release_m49_sources.csv)
ll=$(sbatch --parsable $X -c 4 --mem=64G --time=01:00:00 -J leglang49 --dependency=afterok:$v -o $W/leglang49.out \
    run_py.sh essd/legend_language.py $W/dissolve_m49 $W/legend_language_m49.csv)
ri=$(sbatch --parsable $X -c 2 --mem=48G --time=00:40:00 -J ruidx49 --dependency=afterok:$v -o $W/ruidx49.out \
    run_py.sh essd/ru_index_check.py $W/dissolve_m49 $W/ru_index_check_m49.csv)
# the A0 sheet: a new tiles name, so its raster caches are rebuilt (classes ~30 min); tagged sRGB by a0_map.srgb()
a0=$(sbatch --parsable $X -c 16 --mem=200G --time=04:00:00 -J a0pdf49 --dependency=afterok:$pl -o $W/a0pdf49.out \
    run_py.sh a0_map.py layout --dpi 300 --tiles ../work/final_m49 --pdf)
# PANGAEA files (15 GB per file): one-layer release gpkg + zipped tiled gpkg, as split48
sp=$(sbatch --parsable $XA -c 4 --mem=16G --time=04:00:00 -J split49 --dependency=afterok:$re:$ar -o $W/split49.out \
    --wrap "$PY -I /albedo/work/user/hlantuit/arctic_surficial/scripts/split_release_by_geometry.py $W/release_m49/ArcSurf_v1.0_CC-BY-4.0.gpkg $W/release_m49 /albedo/scratch/user/hlantuit/arcsurf_split49 && echo DONE")
echo "ing_pv $ip gate1 $g1 xw_pv $xp xw_edited ${after#$xp} merge $m diff $df snap $s licence $pl dissolve $v check $dc" \
     "addendum $ad strat $as stats $st maps $mp release $re addrel $ar numbers $nu sources $sr leglang $ll ruidx $ri" \
     "a0 $a0 split $sp"
