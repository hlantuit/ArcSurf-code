#!/bin/bash
# Merge 46, 22 Oct evening: N-44-XVI was read without a water entry in its legend, so 57 km2 of the Novosibirsk
# Reservoir inside the domain became lake-bog deposits (lhIV). The sheet is extracted again with the water row
# (sources/legend_N-44-XVI.csv, row 13, tint sampled on the map) by its own r200d command (work/r200d/runs.tsv), and
# ru_vsegei_pdf is ingested again after it; xw_pdf46 (48519547) is moved onto the new ingest BEFORE the running one
# (48519546) is cancelled, so nothing downstream is lost. Old outputs are MOVED, so a failed extraction fails its job.
# Run on a login node from scripts/:  bash fix_n44_m46.sh
set -e
R=/albedo/work/user/hlantuit/arctic_surficial
W=$R/work
XA="-A perm_ag_coas.perm_ag_coas -p smp --qos=12h"
X="--export=ALL,SURF_DOMAIN=domain $XA"
cd $R/scripts
C="76.5,117.5;1919.2,111.9;1936.8,2247.0;64.2,2242.1"
T="81.250000,54.166667,534.6,1712.4;81.250000,54.333333,534.5,1182.0;81.250000,54.500000,537.0,651.3"
T="$T;81.500000,54.166667,1001.3,1714.5;81.500000,54.333333,1001.4,1181.5;81.500000,54.500000,1000.3,648.5"
T="$T;81.750000,54.166667,1466.4,1715.3;81.750000,54.333333,1464.9,1181.5;81.750000,54.500000,1461.8,648.3"
mkdir -p $W/jpgvec/old_qa46
mv $W/jpgvec/N-44-XVI.gpkg $W/jpgvec/N-44-XVI.json $W/jpgvec/N-44-XVI.log $W/jpgvec/N-44-XVI_class.png $W/jpgvec/old_qa46/
rr=$(sbatch --parsable $X -c 4 --mem=32G --time=00:30:00 -J rr_n44 -o $W/rr_n44.out \
    --wrap "R200D_IMG=$W/r200d/N-44-XVI/prep.png bash $W/r200d/run_r200d.sh N-44-XVI \"$C\" --ties \"$T\"")
ip=$(sbatch --parsable $X -c 4 --mem=160G --time=10:00:00 -J ing_pdf46b --dependency=afterok:$rr \
    -o $W/ing_pdf46b.out run_py.sh ingest_russia.py ru_vsegei_pdf)
scontrol update jobid=48519547 dependency=afterok:$ip
echo "rr_n44 $rr ing_pdf46b $ip"
squeue -j 48519547 -h -o "%i %j %T %E"
