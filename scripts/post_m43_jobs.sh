#!/bin/bash
# merge 43 follow-up jobs (2026-10-07): A0 (dry 40 dpi panel test -> 300 dpi PDF + 60 dpi preview), exact _planarize test
# on the 3 dense tiles, ESSD maps, addendum audit, ice sliver audit. Run on the login node: only cp -al + sbatch.
set -e
cd /albedo/work/user/hlantuit/arctic_surficial/scripts
W=/albedo/work/user/hlantuit/arctic_surficial/work
PY=/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python
X="-A perm_ag_coas.perm_ag_coas -p smp --qos=12h"
[ -d $W/a0_tiles_m43 ] || cp -al $W/tiles $W/a0_tiles_m43
echo "a0_tiles_m43: $(ls $W/a0_tiles_m43/*.parquet | wc -l) tiles"
T=$W/a0_tiles_m43
a=$(sbatch --parsable $X -c 8 --mem=100G -t 02:00:00 -J a0dry43 run_py.sh a0_map.py layout --dry --dpi 40 --tiles $T)
b=$(sbatch --parsable $X -c 8 --mem=200G -t 04:00:00 -J a0pdf43 --dependency=afterok:$a run_py.sh a0_map.py layout --dpi 300 --tiles $T --pdf)
c=$(sbatch --parsable $X -c 8 --mem=100G -t 02:00:00 -J a0p60_43 --dependency=afterok:$a run_py.sh a0_map.py layout --dpi 60 --tiles $T)
SRC=$($PY -c "import json;print(','.join(json.load(open('$W/merge_sources.json'))))")
d=$(sbatch --parsable $X -c 32 --mem=160G -t 02:00:00 -J mtest_v5 --export=ALL,SURF_DOMAIN=domain,MERGE_TDIR=$W/merge_test_v5 \
    --wrap "cd /albedo/work/user/hlantuit/arctic_surficial/scripts && $PY merge_tiles_test.py $SRC --only=-01900_-00300,-03400_-01000,-03400_-00900" -o $W/mtest_v5.out)
e=$(sbatch --parsable $X -c 4 --mem=48G -t 01:00:00 -J pdiff5 --dependency=afterok:$d -o $W/planarize_diff_v5.out run_py.sh planarize_diff.py -01900_-00300 $W/merge_test_v5)
f=$(sbatch --parsable $X -c 32 --mem=160G -t 03:00:00 -J essdmaps run_py.sh essd/essd_maps.py $T)
g=$(sbatch --parsable $X -c 32 --mem=160G -t 03:00:00 -J addaudit run_py.sh addendum_audit.py $T)
h=$(sbatch --parsable $X -c 32 --mem=160G -t 03:00:00 -J icesl43 run_py.sh ice_sliver_audit.py $T)
echo "a0dry43=$a a0pdf43=$b a0p60_43=$c mtest_v5=$d pdiff5=$e essdmaps=$f addaudit=$g icesl43=$h"
