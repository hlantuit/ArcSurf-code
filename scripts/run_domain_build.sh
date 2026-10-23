#!/bin/bash
# Unattended permafrost-region build (Hugues 2026-09-30: "run everything on the HPC").
# Domain = AMAP UNION Obu 2019 permafrost minus the Caucasus (SURF_DOMAIN=domain).
# Chain (sbatch dependencies): backup AMAP build -> obu_domain -> prep_land -> all ingests
# (parallel) -> build_xw (all sources) -> merge -> collect -> QA + coverage + web export +
# pending outlines -> status report (work/DOMAIN_BUILD_STATUS.txt).
# Rollback: work/old/land_amap_coast.gpkg + work/old/tiles_merge10/ (the AMAP build).
set -e
cd /albedo/work/user/hlantuit/arctic_surficial/scripts
W=/albedo/work/user/hlantuit/arctic_surficial/work
X="--export=ALL,SURF_DOMAIN=domain -A perm_ag_coas.perm_ag_coas -p smp --qos=12h -c 32 --mem=200G -o $W/%x.out"
sb() { sbatch --parsable $X "$@"; }

b0=$(sb -J dom_backup --time=01:00:00 --wrap="mkdir -p $W/old && cp -n $W/land_amap.gpkg $W/old/land_amap_coast.gpkg && (test -d $W/old/tiles_merge10 || cp -r $W/tiles $W/old/tiles_merge10) && echo BACKUP_OK")
b1=$(sb -J dom_obu --dependency=afterok:$b0 --time=04:00:00 run_py.sh obu_domain.py)
b2=$(sb -J dom_land --dependency=afterok:$b1 --time=06:00:00 run_py.sh prep_land.py)
ING=""
for spec in "ing_alaska:ingest_alaska.py" "ing_cgm:ingest_canada.py cgm" "ing_legacy:ingest_canada.py legacy" \
            "ing_prov:ingest_canada_prov.py" "ing_lab:ingest_canada_prov.py ca_nl_labrador" "ing_scans:ingest_gsc_scans.py" \
            "ing_nordic:ingest_nordic.py" "ing_rupdf:ingest_russia.py ru_vsegei_pdf" "ing_dprov:ingest_domain_prov.py" "ing_faroe:ingest_faroe.py ingest"; do
  n=${spec%%:*}; c=${spec#*:}
  j=$(sb -J $n --dependency=afterok:$b2 --time=12:00:00 run_py.sh $c)
  ING="$ING:$j"
done
SRC=$(python3 -c "import json;s=json.load(open('$W/merge_sources.json'));s+=[x for x in ['ca_qc_nord','ca_ab_ags','ca_sk_250k','ca_on_fnpmp','fo_us_lendisslog'] if x not in s];print(','.join(s))")
b3=$(sb -J dom_xw --dependency=afterany$ING --time=06:00:00 run_py.sh build_xw.py ${SRC//,/ })
b4=$(sb -J dom_merge --dependency=afterany:$b3 --time=12:00:00 --wrap="cd /albedo/work/user/hlantuit/arctic_surficial/scripts && S=\$(python3 -c \"import os;print(','.join(s for s in '$SRC'.split(',') if os.path.exists('$W/xw/'+s+'.gpkg')))\") && rm -rf $W/tiles && mv -f $W/merge_tiles.log $W/old/merge_tiles_run10.log 2>/dev/null; /albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python merge_tiles.py \$S")
b5=$(sb -J dom_collect --dependency=afterok:$b4 --time=06:00:00 run_py.sh merge_tiles.py --collect)
b6=$(sb -J dom_qa --dependency=afterok:$b5 --time=12:00:00 run_py.sh qa_merge.py)
b7=$(sb -J dom_cov --dependency=afterok:$b4 --time=04:00:00 run_py.sh coverage_map.py)
b8=$(sb -J dom_web --dependency=afterok:$b4 --time=04:00:00 run_py.sh export_coverage_web.py)
b9=$(sb -J dom_pending --dependency=afterok:$b8 --time=01:00:00 run_py.sh export_pending_web.py)
sb -J dom_status --dependency=afterany:$b6:$b7:$b9 --time=00:20:00 run_py.sh domain_build_status.py
echo "submitted: backup $b0 obu $b1 land $b2 ingests$ING xw $b3 merge $b4 collect $b5 qa $b6 cov $b7 web $b8 pending $b9"
