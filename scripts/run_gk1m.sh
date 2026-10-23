#!/bin/bash
# usage: run_gk1m.sh <sheet_g> <pdf in work/gk1m_leg> [nomen override]   -> work/pdfvec1m/<sheet_g>.gpkg
R=/albedo/work/user/hlantuit/arctic_surficial; P=/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python
s=$1; pdf=$2; nom=${3:-${s%_g*}}
read lon0 lat0 lon1 lat1 < <(cd $R/scripts && $P -c "import nomen;print(*nomen.frame('$nom'))")
mkdir -p $R/work/pdfvec1m
cd $R/scripts && $P -W ignore pdf_to_polygons.py $R/work/gk1m_leg/$pdf $s $lon0 $lat0 $lon1 $lat1 $R/sources/legend_$s.csv $R/work/pdfvec1m/$s.gpkg --scale 1000000 ${ROT:+--rot $ROT} 2>&1 | grep -E 'neatline area|rms_m|area by index' | cut -c1-700
