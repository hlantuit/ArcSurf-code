#!/bin/bash
# usage: gk200_run.sh <sheet> [...]  -> upload legend(s)+sheet list, extract, print QA
R=/albedo/work/user/hlantuit/arctic_surficial
cd "$(dirname "$0")/.."
for s in "$@"; do scp -q "sources/legend_$s.csv" albedo0:$R/sources/ 2>&1 | grep -v -E "post-quantum|store now|upgraded"; done
scp -q sources/gk_pdf_sheets.csv albedo0:$R/sources/ 2>&1 | grep -v -E "post-quantum|store now|upgraded"
args=$(printf "'%s' " "$@")
ssh albedo0 "cd $R/scripts && timeout 2400 /albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python run_gk_pdf.py $args | cut -c1-110; for s in $args; do python3 -c \"import json,sys;q=json.load(open('../work/pdfvec/'+sys.argv[1]+'_qa.json'));print(sys.argv[1],'gap',round(q['gap_frac']*100,3),'%',q['non_legend_colours'][:4])\" \$s; done" 2>&1 | grep -v -E "post-quantum|store now|upgraded"
