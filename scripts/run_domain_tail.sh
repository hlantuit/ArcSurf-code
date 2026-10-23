#!/bin/bash
# Resubmit the TAIL of the domain build (xw -> merge -> outputs) after adding a source.
# usage: run_domain_tail.sh <afterany-dependency list ":id:id...">   (the ingest job ids)
set -e
cd /albedo/work/user/hlantuit/arctic_surficial/scripts
W=/albedo/work/user/hlantuit/arctic_surficial/work
X="--export=ALL,SURF_DOMAIN=domain -A perm_ag_coas.perm_ag_coas -p smp --qos=12h -c 32 --mem=200G -o $W/%x.out"
sb() { sbatch --parsable $X "$@"; }
ING="$1"
SRC=$(python3 -c "import json;s=json.load(open('$W/merge_sources.json'));s+=[x for x in ['ca_qc_nord','ca_ab_ags','ca_sk_250k','ca_on_fnpmp','fo_us_lendisslog'] if x not in s];print(','.join(s))")
b3=$(sb -J dom_xw --dependency=afterany$ING --time=06:00:00 run_py.sh build_xw.py ${SRC//,/ })
b4=$(sb -J dom_merge --dependency=afterany:$b3 --time=12:00:00 --wrap="cd /albedo/work/user/hlantuit/arctic_surficial/scripts && S=\$(python3 -c \"import os;print(','.join(s for s in '$SRC'.split(',') if os.path.exists('$W/xw/'+s+'.gpkg')))\") && rm -rf $W/tiles && mv -f $W/merge_tiles.log $W/old/merge_tiles_run10.log 2>/dev/null; /albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python merge_tiles.py \$S")
b5=$(sb -J dom_collect --dependency=afterok:$b4 --time=06:00:00 run_py.sh merge_tiles.py --collect)
b6=$(sb -J dom_qa --dependency=afterok:$b5 --time=12:00:00 run_py.sh qa_merge.py)
b7=$(sb -J dom_cov --dependency=afterok:$b4 --time=04:00:00 run_py.sh coverage_map.py)
b8=$(sb -J dom_web --dependency=afterok:$b4 --time=04:00:00 run_py.sh export_coverage_web.py)
b9=$(sb -J dom_pending --dependency=afterok:$b8 --time=01:00:00 run_py.sh export_pending_web.py)
sb -J dom_status --dependency=afterany:$b6:$b7:$b9 --time=00:20:00 run_py.sh domain_build_status.py
echo "tail submitted after$ING: xw $b3 merge $b4 collect $b5 qa $b6 cov $b7 web $b8 pending $b9"
