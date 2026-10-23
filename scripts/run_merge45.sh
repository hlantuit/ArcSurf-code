#!/bin/bash
# Merge 45 (2026-10-08, approved by H. Lantuit): the USGS Siberian database sheets (ru_bryant_vsegei1m) get the
# publication years of the VSEGEI maps they digitise (1982-2000), and Q-50-51_g2, our colour-classified scan of the same
# printed map as USGS Q50,51, leaves the merge. Only the tiles within 1 km of the USGS footprints are merged again;
# then the dissolve, the addendum, the paper tables and the release.
# Run on a login node FROM scripts/:  bash run_merge45.sh
set -e
cd /albedo/work/user/hlantuit/arctic_surficial/scripts
X="--export=ALL,SURF_DOMAIN=domain -A perm_ag_coas.perm_ag_coas -p smp --qos=12h"
W=/albedo/work/user/hlantuit/arctic_surficial/work
PY=/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python
[ ! -e $W/final_m45 ] || { echo "work/final_m45 exists already"; exit 1; }
a=$(sbatch --parsable $X -c 4 --mem=32G --time=01:00:00 -J ing_bry45 -o $W/ing_bry45.out \
    run_py.sh ingest_bryant.py)
x=$(sbatch --parsable $X -c 8 --mem=64G --time=01:00:00 -J xw_bry45 --dependency=afterok:$a -o $W/xw_bry45.out \
    run_py.sh build_xw.py ru_bryant_vsegei1m)
d=$(sbatch --parsable $X -c 1 --mem=8G --time=00:20:00 -J dropq45 -o $W/dropq45.out \
    run_py.sh drop_sheet_footprint.py ru_vsegei_pdf Q-50-51_g2)
m=$(sbatch --parsable $X -c 32 --mem=200G --time=06:00:00 -J merge45 --dependency=afterok:$x:$d -o $W/merge45.out \
    run_py.sh merge_subset.py m45 ru_bryant_vsegei1m)
# snapshot (hard links). The dissolve runs fresh: the pass-1 outputs of merge 44 predate the GEUS licence patch
s=$(sbatch --parsable $X -c 2 --mem=8G --time=00:30:00 -J snap45 --dependency=afterok:$m -o $W/snap45.out \
    --wrap "cd $W && mkdir final_m45 && ln tiles/*.parquet final_m45/ && ls final_m45 | wc -l")
v=$(sbatch --parsable -J dissolve_m45 --dependency=afterok:$s -o $W/dissolve_m45.out run_dissolve.sh m45)
ad=$(sbatch --parsable $X -c 32 --mem=200G --time=03:00:00 -J addv10 --dependency=afterok:$v -o $W/addv10.out \
    run_py.sh addendum_v02.py $W/final_m45 $W/dissolve_m45 $W/addendum_v10)
as=$(sbatch --parsable $X -c 8 --mem=160G --time=02:00:00 -J addstrat10 --dependency=afterok:$ad -o $W/addstrat10.out \
    run_py.sh addendum_strat.py $W/dissolve_m45 $W/addendum_v10)
st=$(sbatch --parsable $X --export=ALL,SURF_DOMAIN=domain,ESSD_TILES=$W/final_m45,ESSD_OUT=$W/essd_tables_m45 \
    -c 32 --mem=200G --time=04:00:00 -J essdst45 --dependency=afterok:$s -o $W/essdst45.out run_py.sh essd/essd_stats.py)
mp=$(sbatch --parsable $X -c 32 --mem=160G --time=04:00:00 -J essdmap45 --dependency=afterok:$s -o $W/essdmap45.out \
    run_py.sh essd/essd_maps.py $W/final_m45 --export)
re=$(sbatch --parsable $X -c 32 --mem=200G --time=08:00:00 -J release45 --dependency=afterok:$v -o $W/release45.out \
    run_py.sh export_release.py m45 --full --name ArcSurf_v1.0)
ar=$(sbatch --parsable $X -c 4 --mem=96G --time=02:00:00 -J addrel45 --dependency=afterok:$as -o $W/addrel45.out \
    run_py.sh export_addendum_release.py $W/dissolve_m45 $W/addendum_v10 $W/release_m45)
nu=$(sbatch --parsable $X -c 4 --mem=96G --time=01:00:00 -J numrel45 --dependency=afterok:$as -o $W/numrel45.out \
    run_py.sh essd/numbers_release.py $W/dissolve_m45 $W/addendum_v10 $W/dissolve_m45.out $W/numbers_release_m45.json)
sr=$(sbatch --parsable $X -c 2 --mem=48G --time=00:40:00 -J srctab45 --dependency=afterok:$v -o $W/srctab45.out \
    run_py.sh essd/sources_table.py $W/dissolve_m45 $W/release_m45_sources.csv)
ll=$(sbatch --parsable $X -c 4 --mem=64G --time=01:00:00 -J leglang45 --dependency=afterok:$v -o $W/leglang45.out \
    run_py.sh essd/legend_language.py $W/dissolve_m45 $W/legend_language_m45.csv)
ri=$(sbatch --parsable $X -c 2 --mem=48G --time=00:40:00 -J ruidx45 --dependency=afterok:$v -o $W/ruidx45.out \
    run_py.sh essd/ru_index_check.py $W/dissolve_m45 $W/ru_index_check_m45.csv)
echo "ingest $a xw $x drop $d merge $m snap $s dissolve $v addendum $ad strat $as stats $st maps $mp release $re addrel $ar numbers $nu sources $sr leglang $ll ruidx $ri"
