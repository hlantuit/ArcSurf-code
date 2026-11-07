#!/bin/bash
# Merge 47 (run 2026-11-03 15:22, without Ontario): corrections found by the random-point check of the raster extraction.
# Run log: the ingest failed at 15:37 on the combined legend rows of O-52-XXVI ('a1III3|fIII2' as one row);
#   ingest_russia.legend_rows() now matches such rows whole (work/_qc/legend_lookup_dryrun.py: 7970 keys, 0 failures)
#   and the ingest was resubmitted (ing_pdf47b). ca_gsc_scans was re-ingested for the same defect (A1686a 'Md|Mi'
#   had been coded Q) and merge47 waits on both crosswalks. Old files: _backups/ingest_m47/ on Albedo.
#  - O-42-VI and O-42-XV re-registered on frame corners measured on the scans (run_rast.sh ... --no-snap, done
#    before this script; the 1 Oct outputs are in work/jpgvec/old_qa47/, README.txt there)
#  - own legends (sources/legend_*.csv): P-54-XIX, O-52-XXVI, P-55-IX, P-55-XV (they had been read with the legends
#    of P-54-XIV, O-52-XXVII and P-55-XVII); P-55-XVI with the legend of P-55-XV (its scan has none; same palette);
#    R-39-40_pq gains mH and amH; all on corners measured on the scans
#  - 30 more sheets on corners corrected by the corner audit of 2026-11-03 (work/_qc/rerun_corners.py,
#    corner_offsets_2026-11-03.csv; unit shares unchanged to within 0.5 percentage points)
#  - Ontario (ca_on_eds014, ca_on_fnpmp) joins only with ONTARIO=1, and only once patch_licence_open.py has its
#    licence entry (like GEUS); decision expected by Fri 6 Nov
# Full merge into work/tiles_m47 (MERGE_TDIR), so final_m46 and release_m46 stay as they are.
# Run on a login node FROM scripts/:  [ONTARIO=1] bash run_merge47.sh
# Afterwards (not in this chain): data READMEs (numbers from numbers_release_m47.json), the addendum zip, the
# manuscript numbers (refresh), the package; then the upload of release_m47 to PANGAEA (PDI-45690).
set -e
cd /albedo/work/user/hlantuit/arctic_surficial/scripts
W=/albedo/work/user/hlantuit/arctic_surficial/work
PY=/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python
XA="-A perm_ag_coas.perm_ag_coas -p smp --qos=12h"
X="--export=ALL,SURF_DOMAIN=domain $XA"
RERUN="O-42-VI O-42-XV P-54-XIX O-52-XXVI P-55-IX P-55-XV P-55-XVI R-39-40_pq
       M-48-V M-50-VII N-46-XIII N-48-XXXIII N-52-VII N-52-XIII O-52-I O-52-II O-53-XII P-43-IX P-43-XVI P-43-XVII P-43-XVIII P-43-XXII P-43-XXIII P-47-XXXIII P-50-I P-50-II P-52-XXXII P-54-VIII P-55-XII P-57-V Q-41-XXV Q-54-XXVII,XXVIII M-47-48_g2 O-47-48_g2 O-50-51_g2 Q-39_g3 R-35-37_g2 Q-60-1_g2"
[ ! -e $W/final_m47 ] && [ ! -e $W/tiles_m47 ] || { echo "work/final_m47 or work/tiles_m47 exists already"; exit 1; }
# every re-extracted sheet must be in place, on measured corners (a failed re-run leaves no json)
for s in $RERUN; do
    $PY -c "import json,sys; r=json.load(open('$W/jpgvec/$s.json')); sys.exit(0 if all(c['ok']=='measured' for c in r['corners']) else 1)" \
        || { echo "$s: no record on measured corners in work/jpgvec"; exit 1; }
done

# the source list of the merge: merge 46's, plus Ontario with ONTARIO=1 (old list kept)
cp $W/merge_sources.json $W/merge_sources_m46.json
if [ "${ONTARIO:-0}" = 1 ]; then
    grep -q "ca_on_" patch_licence_open.py || { echo "ONTARIO=1: patch_licence_open.py has no Ontario entry yet"; exit 1; }
    $PY -c "import json; p='$W/merge_sources.json'; s=json.load(open(p)); s+=[x for x in ('ca_on_eds014','ca_on_fnpmp') if x not in s]; json.dump(s, open(p,'w'), indent=1); print(len(s), 'sources')"
fi
SRC=$($PY -c "import json; print(','.join(json.load(open('$W/merge_sources.json'))))")
mkdir -p $W/tiles_m47

ip=$(sbatch --parsable $X -c 16 --mem=160G --time=10:00:00 -J ing_pdf47 -o $W/ing_pdf47.out \
    run_py.sh ingest_russia.py ru_vsegei_pdf)
xp=$(sbatch --parsable $X -c 8 --mem=64G --time=02:00:00 -J xw_pdf47 --dependency=afterok:$ip -o $W/xw_pdf47.out \
    run_py.sh build_xw.py ru_vsegei_pdf)
m=$(sbatch --parsable --export=ALL,SURF_DOMAIN=domain,MERGE_TDIR=$W/tiles_m47 $XA -c 32 --mem=200G --time=12:00:00 \
    -J merge47 --dependency=afterok:$xp -o $W/merge47.out run_py.sh merge_tiles.py $SRC)
s=$(sbatch --parsable $X -c 2 --mem=8G --time=00:30:00 -J snap47 --dependency=afterok:$m -o $W/snap47.out \
    --wrap "cd $W && mkdir final_m47 && ln tiles_m47/*.parquet final_m47/ && ls final_m47 | wc -l")
pl=$(sbatch --parsable $X -c 4 --mem=64G --time=02:00:00 -J lic47 --dependency=afterok:$s -o $W/lic47.out \
    run_py.sh patch_licence_open.py m47)
# the dissolve proper gates the chain; its topology check runs beside it (merge 46: the check of run_dissolve.sh was
# OOM-killed after 9 h, the combined job failed and its afterok dependents had to be released by hand)
v=$(sbatch --parsable $XA -t 12:00:00 -c 32 --mem=200G -J dissolve_m47 --dependency=afterok:$pl -o $W/dissolve_m47.out \
    --wrap "cd $PWD && $PY dissolve_release.py --tiles $W/final_m47 --out $W/dissolve_m47 --workers 32")
dc=$(sbatch --parsable $XA -t 12:00:00 -c 32 --mem=200G -J dcheck_m47 --dependency=afterok:$v -o $W/dcheck_m47.out \
    --wrap "cd $PWD && $PY dissolve_check.py $W/dissolve_m47 --workers 32")
ad=$(sbatch --parsable $X -c 32 --mem=200G --time=03:00:00 -J addv12 --dependency=afterok:$v -o $W/addv12.out \
    run_py.sh addendum_v02.py $W/final_m47 $W/dissolve_m47 $W/addendum_v12)
as=$(sbatch --parsable $X -c 8 --mem=160G --time=02:00:00 -J addstrat12 --dependency=afterok:$ad -o $W/addstrat12.out \
    run_py.sh addendum_strat.py $W/dissolve_m47 $W/addendum_v12)
st=$(sbatch --parsable --export=ALL,SURF_DOMAIN=domain,ESSD_TILES=$W/final_m47,ESSD_OUT=$W/essd_tables_m47 $XA \
    -c 32 --mem=200G --time=04:00:00 -J essdst47 --dependency=afterok:$pl -o $W/essdst47.out run_py.sh essd/essd_stats.py)
mp=$(sbatch --parsable $X -c 32 --mem=160G --time=04:00:00 -J essdmap47 --dependency=afterok:$pl -o $W/essdmap47.out \
    run_py.sh essd/essd_maps.py $W/final_m47 --export)
re=$(sbatch --parsable $X -c 16 --mem=120G --time=08:00:00 -J release47 --dependency=afterok:$v -o $W/release47.out \
    run_py.sh export_release.py m47 --full --name ArcSurf_v1.0)
ar=$(sbatch --parsable $X -c 4 --mem=96G --time=02:00:00 -J addrel47 --dependency=afterok:$as -o $W/addrel47.out \
    run_py.sh export_addendum_release.py $W/dissolve_m47 $W/addendum_v12 $W/release_m47)
nu=$(sbatch --parsable $X -c 4 --mem=96G --time=01:00:00 -J numrel47 --dependency=afterok:$as -o $W/numrel47.out \
    run_py.sh essd/numbers_release.py $W/dissolve_m47 $W/addendum_v12 $W/dissolve_m47.out $W/numbers_release_m47.json)
sr=$(sbatch --parsable $X -c 2 --mem=48G --time=00:40:00 -J srctab47 --dependency=afterok:$v -o $W/srctab47.out \
    run_py.sh essd/sources_table.py $W/dissolve_m47 $W/release_m47_sources.csv)
ll=$(sbatch --parsable $X -c 4 --mem=64G --time=01:00:00 -J leglang47 --dependency=afterok:$v -o $W/leglang47.out \
    run_py.sh essd/legend_language.py $W/dissolve_m47 $W/legend_language_m47.csv)
ri=$(sbatch --parsable $X -c 2 --mem=48G --time=00:40:00 -J ruidx47 --dependency=afterok:$v -o $W/ruidx47.out \
    run_py.sh essd/ru_index_check.py $W/dissolve_m47 $W/ru_index_check_m47.csv)
a0=$(sbatch --parsable $X -c 16 --mem=200G --time=04:00:00 -J a0pdf47 --dependency=afterok:$pl -o $W/a0pdf47.out \
    run_py.sh a0_map.py layout --dpi 300 --tiles ../work/final_m47 --pdf)
# PANGAEA files (15 GB per file): one-layer release gpkg + zipped tiled gpkg, as split46 for release_m46
sp=$(sbatch --parsable $XA -c 4 --mem=16G --time=04:00:00 -J split47 --dependency=afterok:$re:$ar -o $W/split47.out \
    --wrap "$PY -I /albedo/work/user/hlantuit/arctic_surficial/scripts/split_release_by_geometry.py $W/release_m47/ArcSurf_v1.0_CC-BY-4.0.gpkg $W/release_m47 /albedo/scratch/user/hlantuit/arcsurf_split47 && echo DONE")
echo "ing_pdf $ip xw_pdf $xp merge $m snap $s licence $pl dissolve $v check $dc addendum $ad strat $as stats $st maps $mp" \
     "release $re addrel $ar numbers $nu sources $sr leglang $ll ruidx $ri a0 $a0 split $sp"
