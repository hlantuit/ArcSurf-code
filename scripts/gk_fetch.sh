#!/bin/bash
# usage: gk200_fetch.sh <file stem in work/${GKD:-gk200_leg} (no .pdf)> -> work_local/<stem-short>_L<k>.png + prints fills
D=/albedo/work/user/hlantuit/arctic_surficial/work/${GKD:-gk200_leg}
cd "$(dirname "$0")/.."
f=$1; s=${f%%__*}; t=$(echo $s | tr -d ',')
for k in 0 1 2 3 4; do scp -q "albedo0:$D/${f}_L$k.png" work_local/${t}_L$k.png 2>/dev/null && echo work_local/${t}_L$k.png; done
ssh albedo0 "cat '$D/${f}_fills.json'" 2>&1 | grep -v -E "post-quantum|store now|upgraded"; echo
