#!/bin/bash
# usage: rast_prep.sh <sheet> "<legend box1> [box2 ...]" (space-separated) "<approx corners TL;TR;BR;BL>"
# -> work_local/<t>_leg<k>_<n>.png (legend crops), <t>_corners.png, prints swatch fills per box
S="$1"; BOXES="$2"; C="$3"; t=$(echo "$S" | tr -d ',')
R=/albedo/work/user/hlantuit/arctic_surficial
ssh albedo0 "cd $R/scripts; P=/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python; I=\$(ls -S \"/albedo/scratch/user/hlantuit/arctic_surficial/raw/russia_geokniga/$S\"/*.jpg | head -1); k=0; for b in $BOXES; do \$P -W ignore jpg_to_polygons.py legend \"\$I\" \$b ../work/rast/${t}_leg\$k 2>&1 | grep -v -E 'PROJ|saved|swatches'; echo ---; k=\$((k+1)); done; \$P -W ignore scan_corners.py \"\$I\" ../work/rast/${t}_corners.png $(echo $C | tr ';' ' ') 300 2>&1 | grep -v PROJ | grep -v saved" 2>&1 | grep -v -E "post-quantum|store now|upgraded"
cd "$(dirname "$0")/.."
scp -q "albedo0:$R/work/rast/${t}_leg*_legend_*.png" "albedo0:$R/work/rast/${t}_corners.png" work_local/ 2>&1 | grep -v -E "post-quantum|store now|upgraded"
ls work_local/${t}_leg*_legend_*.png work_local/${t}_corners.png
