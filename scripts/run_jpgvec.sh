#!/bin/bash
# raster (JPG) sheets -> work/jpgvec/<sheet>.gpkg ; spec = folder|sheet|map_box
R=/albedo/work/user/hlantuit/arctic_surficial; G=/albedo/scratch/user/hlantuit/arctic_surficial/raw/russia_geokniga
PY="/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python -W ignore"
cd $R/scripts
for spec in \
  'T-47-XXXI,XXXII|T-47-XXXI,XXXII,XXXIII|2150,600,7200,5420' \
  'T-47-XXXIV,XXXV|T-47-XXXIV,XXXV,XXXVI|2250,600,7250,5300' \
  'R-53-IX,_X|R-53-IX,X|2120,650,6680,5400|ice:#0669b1:33' \
  'R-58-XXXV,XXXVI|R-58-XXXV,XXXVI|2150,650,7300,5360' \
  'S-47-XIX,XX|S-47-XIX,XX|180,650,4160,5370' \
  'S-46-XIX,XX|S-46-XIX,XX|2200,540,6110,5140' ; do
  IFS='|' read d s b ov <<< "$spec"
  [ -n "$ONLY" ] && [ "$ONLY" != "$s" ] && continue
  echo "#### $s"
  timeout 900 $PY jpg_to_polygons.py extract "$(ls $G/$d/*.jpg)" "$s" "../sources/legend_$s.csv" "../work/jpgvec/$s.gpkg" --map-box "$b" ${ov:+--overprint "$ov"} > "../work/jpgvec/$s.log" 2>&1
  python3 -c "import json; r=json.load(open('../work/jpgvec/$s.json')); print({k: (round(r[k],4) if isinstance(r[k],float) else r[k]) for k in ('rms_m','max_res_m','unassigned_before_fill','cover_frac','n_polygons')}, 'confusable:', r['confusable_pairs'])" 2>&1 | tail -1
done
