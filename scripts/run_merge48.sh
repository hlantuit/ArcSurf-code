#!/bin/bash
# Merge 48 (run 2026-11-03, without Ontario): merge 47 again, with the Baikal water of M-47-48_g2 restored.
#  - the corner re-run of 2026-11-03 (work/_qc/rerun_corners.py) replayed only the extraction command of each sheet and
#    so dropped the lake fix recorded in work/jpgvec/M-47-48_g2.gpkg.fixes.txt (fix_lake_units.py: the Baikal lake
#    body reads as lIV); merge 47 maps 138 km2 of southern Baikal as L instead of H. Fix re-applied 2026-11-03 20:17
#    (WATER 2221 km2, no other unit changed; old sheet in _backups/ingest_m47/M-47-48_g2.gpkg.before_lakefix). This
#    script refuses to run when a sheet is newer than its fixes record.
#  - everything else as merge 47 (run_merge47.sh): the 38 re-extracted sheets, ingest_russia.legend_rows(), the GSC
#    crosswalk of 2026-11-03 16:21 (A1686a Md|Mi). Merge 47 runs to its end beside this one (rehearsal of the later
#    steps); its A0 map (a0pdf47) first: AFTER=48763769
#  - Ontario (ca_on_eds014, ca_on_fnpmp) joins only with ONTARIO=1, and only once patch_licence_open.py has its
#    licence entry (like GEUS); decision expected by Fri 6 Nov
# Full merge into work/tiles_m48 (MERGE_TDIR), so final_m47 and release_m47 stay as they are.
# Run on a login node FROM scripts/:  [ONTARIO=1] [AFTER=jobid] bash run_merge48.sh   (AFTER: the ingest waits for
# the end of that job, afterany)
# Afterwards (not in this chain): data READMEs (numbers from numbers_release_m48.json), the addendum zip, the
# manuscript numbers (refresh), the package; then the upload of release_m48 to PANGAEA (PDI-45690).
set -e
cd /albedo/work/user/hlantuit/arctic_surficial/scripts
W=/albedo/work/user/hlantuit/arctic_surficial/work
PY=/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python
XA="-A perm_ag_coas.perm_ag_coas -p smp --qos=12h"
X="--export=ALL,SURF_DOMAIN=domain $XA"
RERUN="O-42-VI O-42-XV P-54-XIX O-52-XXVI P-55-IX P-55-XV P-55-XVI R-39-40_pq
       M-48-V M-50-VII N-46-XIII N-48-XXXIII N-52-VII N-52-XIII O-52-I O-52-II O-53-XII P-43-IX P-43-XVI P-43-XVII P-43-XVIII P-43-XXII P-43-XXIII P-47-XXXIII P-50-I P-50-II P-52-XXXII P-54-VIII P-55-XII P-57-V Q-41-XXV Q-54-XXVII,XXVIII M-47-48_g2 O-47-48_g2 O-50-51_g2 Q-39_g3 R-35-37_g2 Q-60-1_g2"
[ ! -e $W/final_m48 ] && [ ! -e $W/tiles_m48 ] || { echo "work/final_m48 or work/tiles_m48 exists already"; exit 1; }
# every re-extracted sheet must be in place, on measured corners (a failed re-run leaves no json)
for s in $RERUN; do
    $PY -c "import json,sys; r=json.load(open('$W/jpgvec/$s.json')); sys.exit(0 if all(c['ok']=='measured' for c in r['corners']) else 1)" \
        || { echo "$s: no record on measured corners in work/jpgvec"; exit 1; }
done
# every in-place fix of an extracted sheet must still be in it: a sheet written after its last fix record has been
# re-extracted and has lost the fix (merge 47: M-47-48_g2)
for f in $W/jpgvec/*.gpkg.fixes.txt; do
    if [ "${f%.fixes.txt}" -nt "$f" ]; then echo "${f%.fixes.txt} is newer than its fixes record: re-apply them"; exit 1; fi
done

# the source list of the merge: merge 47's, plus Ontario with ONTARIO=1 (old list kept)
cp $W/merge_sources.json $W/merge_sources_m47.json
if [ "${ONTARIO:-0}" = 1 ]; then
    grep -q "ca_on_" patch_licence_open.py || { echo "ONTARIO=1: patch_licence_open.py has no Ontario entry yet"; exit 1; }
    $PY -c "import json; p='$W/merge_sources.json'; s=json.load(open(p)); s+=[x for x in ('ca_on_eds014','ca_on_fnpmp') if x not in s]; json.dump(s, open(p,'w'), indent=1); print(len(s), 'sources')"
fi
SRC=$($PY -c "import json; print(','.join(json.load(open('$W/merge_sources.json'))))")
mkdir -p $W/tiles_m48
dep=${AFTER:+--dependency=afterany:$AFTER}

ip=$(sbatch --parsable $X $dep -c 16 --mem=160G --time=10:00:00 -J ing_pdf48 -o $W/ing_pdf48.out \
    run_py.sh ingest_russia.py ru_vsegei_pdf)
xp=$(sbatch --parsable $X -c 8 --mem=64G --time=02:00:00 -J xw_pdf48 --dependency=afterok:$ip -o $W/xw_pdf48.out \
    run_py.sh build_xw.py ru_vsegei_pdf)
m=$(sbatch --parsable --export=ALL,SURF_DOMAIN=domain,MERGE_TDIR=$W/tiles_m48 $XA -c 32 --mem=200G --time=12:00:00 \
    -J merge48 --dependency=afterok:$xp -o $W/merge48.out run_py.sh merge_tiles.py $SRC)
s=$(sbatch --parsable $X -c 2 --mem=8G --time=00:30:00 -J snap48 --dependency=afterok:$m -o $W/snap48.out \
    --wrap "cd $W && mkdir final_m48 && ln tiles_m48/*.parquet final_m48/ && ls final_m48 | wc -l")
pl=$(sbatch --parsable $X -c 4 --mem=64G --time=02:00:00 -J lic48 --dependency=afterok:$s -o $W/lic48.out \
    run_py.sh patch_licence_open.py m48)
# the dissolve proper gates the chain; its topology check runs beside it (merge 46: the check of run_dissolve.sh was
# OOM-killed after 9 h, the combined job failed and its afterok dependents had to be released by hand)
v=$(sbatch --parsable $XA -t 12:00:00 -c 32 --mem=200G -J dissolve_m48 --dependency=afterok:$pl -o $W/dissolve_m48.out \
    --wrap "cd $PWD && $PY dissolve_release.py --tiles $W/final_m48 --out $W/dissolve_m48 --workers 32")
dc=$(sbatch --parsable $XA -t 12:00:00 -c 32 --mem=200G -J dcheck_m48 --dependency=afterok:$v -o $W/dcheck_m48.out \
    --wrap "cd $PWD && $PY dissolve_check.py $W/dissolve_m48 --workers 32")
# the addendum not on prod-080 (merge 46: addv11 hung there for 2 h 50 min; the re-run took 4 min)
ad=$(sbatch --parsable $X --exclude=prod-080 -c 32 --mem=200G --time=03:00:00 -J addv13 --dependency=afterok:$v -o $W/addv13.out \
    run_py.sh addendum_v02.py $W/final_m48 $W/dissolve_m48 $W/addendum_v13)
as=$(sbatch --parsable $X -c 8 --mem=160G --time=02:00:00 -J addstrat13 --dependency=afterok:$ad -o $W/addstrat13.out \
    run_py.sh addendum_strat.py $W/dissolve_m48 $W/addendum_v13)
st=$(sbatch --parsable --export=ALL,SURF_DOMAIN=domain,ESSD_TILES=$W/final_m48,ESSD_OUT=$W/essd_tables_m48 $XA \
    -c 32 --mem=200G --time=04:00:00 -J essdst48 --dependency=afterok:$pl -o $W/essdst48.out run_py.sh essd/essd_stats.py)
mp=$(sbatch --parsable $X -c 32 --mem=160G --time=04:00:00 -J essdmap48 --dependency=afterok:$pl -o $W/essdmap48.out \
    run_py.sh essd/essd_maps.py $W/final_m48 --export)
re=$(sbatch --parsable $X -c 16 --mem=120G --time=08:00:00 -J release48 --dependency=afterok:$v -o $W/release48.out \
    run_py.sh export_release.py m48 --full --name ArcSurf_v1.0)
ar=$(sbatch --parsable $X -c 4 --mem=96G --time=02:00:00 -J addrel48 --dependency=afterok:$as -o $W/addrel48.out \
    run_py.sh export_addendum_release.py $W/dissolve_m48 $W/addendum_v13 $W/release_m48)
nu=$(sbatch --parsable $X -c 4 --mem=96G --time=01:00:00 -J numrel48 --dependency=afterok:$as -o $W/numrel48.out \
    run_py.sh essd/numbers_release.py $W/dissolve_m48 $W/addendum_v13 $W/dissolve_m48.out $W/numbers_release_m48.json)
sr=$(sbatch --parsable $X -c 2 --mem=48G --time=00:40:00 -J srctab48 --dependency=afterok:$v -o $W/srctab48.out \
    run_py.sh essd/sources_table.py $W/dissolve_m48 $W/release_m48_sources.csv)
ll=$(sbatch --parsable $X -c 4 --mem=64G --time=01:00:00 -J leglang48 --dependency=afterok:$v -o $W/leglang48.out \
    run_py.sh essd/legend_language.py $W/dissolve_m48 $W/legend_language_m48.csv)
ri=$(sbatch --parsable $X -c 2 --mem=48G --time=00:40:00 -J ruidx48 --dependency=afterok:$v -o $W/ruidx48.out \
    run_py.sh essd/ru_index_check.py $W/dissolve_m48 $W/ru_index_check_m48.csv)
a0=$(sbatch --parsable $X -c 16 --mem=200G --time=04:00:00 -J a0pdf48 --dependency=afterok:$pl -o $W/a0pdf48.out \
    run_py.sh a0_map.py layout --dpi 300 --tiles ../work/final_m48 --pdf)
# PANGAEA files (15 GB per file): one-layer release gpkg + zipped tiled gpkg, as split46 for release_m46
sp=$(sbatch --parsable $XA -c 4 --mem=16G --time=04:00:00 -J split48 --dependency=afterok:$re:$ar -o $W/split48.out \
    --wrap "$PY -I /albedo/work/user/hlantuit/arctic_surficial/scripts/split_release_by_geometry.py $W/release_m48/ArcSurf_v1.0_CC-BY-4.0.gpkg $W/release_m48 /albedo/scratch/user/hlantuit/arcsurf_split48 && echo DONE")
echo "ing_pdf $ip xw_pdf $xp merge $m snap $s licence $pl dissolve $v check $dc addendum $ad strat $as stats $st maps $mp" \
     "release $re addrel $ar numbers $nu sources $sr leglang $ll ruidx $ri a0 $a0 split $sp"
