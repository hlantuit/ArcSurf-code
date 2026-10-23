#!/bin/bash
# Merge 44 (2026-10-07): GSC Map 1814A comes from the GSC release (new source ca_gsc_1814a, Open Government Licence -
# Canada) instead of the GeoAtlas copy of it (ca_nl_labrador layer 12); ca_nl_labrador keeps only the GSNL 1:50k layer
# (internal_only). Only the tiles near the two sources are merged again (merge_subset.py); then the final_m44 snapshot
# (hard links) and the GeoPackage. Run on a login node FROM scripts/:  bash run_merge44.sh
set -e
cd /albedo/work/user/hlantuit/arctic_surficial/scripts
X="--export=ALL,SURF_DOMAIN=domain -A perm_ag_coas.perm_ag_coas -p smp --qos=12h"
W=/albedo/work/user/hlantuit/arctic_surficial/work
[ ! -e $W/final_m44 ] || { echo "work/final_m44 exists already"; exit 1; }
a=$(sbatch --parsable $X -c 8 --mem=64G --time=01:00:00 -J ing_lab44 -o $W/ing_lab44.out \
    run_py.sh ingest_canada_prov.py ca_nl_labrador ca_gsc_1814a)
x=$(sbatch --parsable $X -c 16 --mem=120G --time=02:00:00 -J xw_lab44 --dependency=afterok:$a -o $W/xw_lab44.out \
    run_py.sh build_xw.py ca_nl_labrador ca_gsc_1814a)
m=$(sbatch --parsable $X -c 32 --mem=200G --time=06:00:00 -J merge44 --dependency=afterok:$x -o $W/merge44.out \
    run_py.sh merge_subset.py m44 ca_nl_labrador,ca_gsc_1814a)
s=$(sbatch --parsable $X -c 2 --mem=8G --time=00:30:00 -J snap44 --dependency=afterok:$m -o $W/snap44.out \
    --wrap "cd $W && mkdir final_m44 && ln tiles/*.parquet final_m44/ && ls final_m44 | wc -l")
co=$(sbatch --parsable $X -c 32 --mem=160G --time=03:00:00 -J coll44 --dependency=afterok:$s -o $W/coll44.out \
    run_py.sh merge_tiles.py --collect)
echo "ingest $a  xw $x  merge $m  snapshot $s  collect $co"
