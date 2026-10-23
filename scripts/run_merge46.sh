#!/bin/bash
# Merge 46 (prepared 2026-10-22): the corrections of the error screen and the licence decisions of October 2026.
#  - O-53-XII is extracted again with its own legend (it had been read with the Aldan-series legend of O-52-XXVII)
#  - legends (synced from the laptop): limno-alluvium L/F on 20 sheets, Eyk suite of R-50_g3 E
#  - Ontario (ca_on_eds014, ca_on_fnpmp) and the Crown-copyright BC sets (ca_bc_tem_extra; ca_gsc_bc_ofs EOF2011-2)
#    leave the map; the GSC 1:5M map and the other BC sources take their land
#  - licences (patch_licence_open.py): Russian sources, Labrador 1:50k layer and the PAGE21 maps open; Greenland stays
#    open_sa until GEUS answers (then: patch_licence_open.py m46 --greenland, and the export again)
# Full merge into work/tiles_m46 (MERGE_TDIR), so work/tiles and the snapshot final_m45 stay as they are.
# Run on a login node FROM scripts/ after sync_m46.sh:  bash run_merge46.sh
set -e
cd /albedo/work/user/hlantuit/arctic_surficial/scripts
W=/albedo/work/user/hlantuit/arctic_surficial/work
PY=/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python
XA="-A perm_ag_coas.perm_ag_coas -p smp --qos=12h"
X="--export=ALL,SURF_DOMAIN=domain $XA"
[ ! -e $W/final_m46 ] && [ ! -e $W/tiles_m46 ] || { echo "work/final_m46 or work/tiles_m46 exists already"; exit 1; }
# O-53-XII: its outputs of 1 Oct are MOVED aside, so a failed re-extraction leaves no json and fails its job (a copy
# would let the old, wrong-legend sheet pass on to the merge)
mkdir -p $W/jpgvec/old_qa46
mv $W/jpgvec/O-53-XII.gpkg $W/jpgvec/O-53-XII.json $W/jpgvec/O-53-XII.log $W/jpgvec/O-53-XII_class.png $W/jpgvec/old_qa46/

# the source list of the merge, without Ontario and the BC Crown-copyright set (old list kept)
cp $W/merge_sources.json $W/merge_sources_m45.json
$PY -c "import json; p='$W/merge_sources.json'; s=json.load(open(p)); s=[x for x in s if x not in ('ca_on_eds014','ca_on_fnpmp','ca_bc_tem_extra')]; json.dump(s, open(p,'w'), indent=1); print(len(s), 'sources')"
SRC=$($PY -c "import json; print(','.join(json.load(open('$W/merge_sources.json'))))")
mkdir -p $W/tiles_m46

# A0 cartography of the 22 Oct review, tested at once on a blank map face (labels, lines, frame; the inset rasters of
# final_m45 are not cached, one pass over its tiles first, single process): out/a0/a0_layout_60dpi.png and the log line
# of the dropped water names
dry=$(sbatch --parsable $X -c 2 --mem=32G --time=02:00:00 -J a0dry46 -o $W/a0dry46.out \
    run_py.sh a0_map.py layout --dpi 60 --dry --tiles ../work/final_m45)
# O-53-XII with its own legend, through work/run_rast.sh with the frame corners of its 1 Oct run (its record holds no
# command line, so rerun_jpg.py cannot replay it)
rr=$(sbatch --parsable $X -c 8 --mem=120G --time=02:00:00 -J rr_o53 -o $W/rr_o53.out \
    $W/run_rast.sh O-53-XII "593,818;3947,818;3979,5206;559,5206")
ip=$(sbatch --parsable $X -c 16 --mem=160G --time=10:00:00 -J ing_pdf46 --dependency=afterok:$rr -o $W/ing_pdf46.out \
    run_py.sh ingest_russia.py ru_vsegei_pdf)
xp=$(sbatch --parsable $X -c 8 --mem=64G --time=02:00:00 -J xw_pdf46 --dependency=afterok:$ip -o $W/xw_pdf46.out \
    run_py.sh build_xw.py ru_vsegei_pdf)
iv=$(sbatch --parsable $X -c 8 --mem=128G --time=06:00:00 -J ing_pv46 -o $W/ing_pv46.out run_py.sh ingest_russia.py ru_vsegei_preview)
xv=$(sbatch --parsable $X -c 8 --mem=64G --time=02:00:00 -J xw_pv46 --dependency=afterok:$iv -o $W/xw_pv46.out \
    run_py.sh build_xw.py ru_vsegei_preview)
dr=$(sbatch --parsable $X -c 1 --mem=8G --time=00:20:00 -J drop_bc46 -o $W/drop_bc46.out \
    run_py.sh drop_sheet_footprint.py ca_gsc_bc_ofs EOF2011-2)
m=$(sbatch --parsable --export=ALL,SURF_DOMAIN=domain,MERGE_TDIR=$W/tiles_m46 $XA -c 32 --mem=200G --time=12:00:00 \
    -J merge46 --dependency=afterok:$xp:$xv:$dr -o $W/merge46.out run_py.sh merge_tiles.py $SRC)
s=$(sbatch --parsable $X -c 2 --mem=8G --time=00:30:00 -J snap46 --dependency=afterok:$m -o $W/snap46.out \
    --wrap "cd $W && mkdir final_m46 && ln tiles_m46/*.parquet final_m46/ && ls final_m46 | wc -l")
pl=$(sbatch --parsable $X -c 4 --mem=64G --time=02:00:00 -J lic46 --dependency=afterok:$s -o $W/lic46.out \
    run_py.sh patch_licence_open.py m46)
v=$(sbatch --parsable -J dissolve_m46 --dependency=afterok:$pl -o $W/dissolve_m46.out run_dissolve.sh m46)
ad=$(sbatch --parsable $X -c 32 --mem=200G --time=03:00:00 -J addv11 --dependency=afterok:$v -o $W/addv11.out \
    run_py.sh addendum_v02.py $W/final_m46 $W/dissolve_m46 $W/addendum_v11)
as=$(sbatch --parsable $X -c 8 --mem=160G --time=02:00:00 -J addstrat11 --dependency=afterok:$ad -o $W/addstrat11.out \
    run_py.sh addendum_strat.py $W/dissolve_m46 $W/addendum_v11)
st=$(sbatch --parsable --export=ALL,SURF_DOMAIN=domain,ESSD_TILES=$W/final_m46,ESSD_OUT=$W/essd_tables_m46 $XA \
    -c 32 --mem=200G --time=04:00:00 -J essdst46 --dependency=afterok:$pl -o $W/essdst46.out run_py.sh essd/essd_stats.py)
mp=$(sbatch --parsable $X -c 32 --mem=160G --time=04:00:00 -J essdmap46 --dependency=afterok:$pl -o $W/essdmap46.out \
    run_py.sh essd/essd_maps.py $W/final_m46 --export)
re=$(sbatch --parsable $X -c 16 --mem=120G --time=08:00:00 -J release46 --dependency=afterok:$v -o $W/release46.out \
    run_py.sh export_release.py m46 --full --name ArcSurf_v1.0)
ar=$(sbatch --parsable $X -c 4 --mem=96G --time=02:00:00 -J addrel46 --dependency=afterok:$as -o $W/addrel46.out \
    run_py.sh export_addendum_release.py $W/dissolve_m46 $W/addendum_v11 $W/release_m46)
nu=$(sbatch --parsable $X -c 4 --mem=96G --time=01:00:00 -J numrel46 --dependency=afterok:$as -o $W/numrel46.out \
    run_py.sh essd/numbers_release.py $W/dissolve_m46 $W/addendum_v11 $W/dissolve_m46.out $W/numbers_release_m46.json)
sr=$(sbatch --parsable $X -c 2 --mem=48G --time=00:40:00 -J srctab46 --dependency=afterok:$v -o $W/srctab46.out \
    run_py.sh essd/sources_table.py $W/dissolve_m46 $W/release_m46_sources.csv)
ll=$(sbatch --parsable $X -c 4 --mem=64G --time=01:00:00 -J leglang46 --dependency=afterok:$v -o $W/leglang46.out \
    run_py.sh essd/legend_language.py $W/dissolve_m46 $W/legend_language_m46.csv)
ri=$(sbatch --parsable $X -c 2 --mem=48G --time=00:40:00 -J ruidx46 --dependency=afterok:$v -o $W/ruidx46.out \
    run_py.sh essd/ru_index_check.py $W/dissolve_m46 $W/ru_index_check_m46.csv)
a0=$(sbatch --parsable $X -c 16 --mem=200G --time=04:00:00 -J a0pdf46 --dependency=afterok:$pl -o $W/a0pdf46.out \
    run_py.sh a0_map.py layout --dpi 300 --tiles ../work/final_m46 --pdf)
echo "a0dry $dry rerun $rr ing_pdf $ip xw_pdf $xp ing_pv $iv xw_pv $xv drop $dr merge $m snap $s licence $pl dissolve $v" \
     "addendum $ad strat $as stats $st maps $mp release $re addrel $ar numbers $nu sources $sr leglang $ll ruidx $ri a0 $a0"
