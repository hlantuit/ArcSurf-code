#!/bin/bash
# Dissolved release geometry + asid for a merge snapshot (dissolve_release.py), then its topology check.
# usage: sbatch -J dissolve_m44 -o /albedo/work/user/hlantuit/arctic_surficial/work/dissolve_m44.out run_dissolve.sh m44
#SBATCH -A perm_ag_coas.perm_ag_coas
#SBATCH -p smp
#SBATCH --qos=12h
#SBATCH -t 12:00:00
#SBATCH -c 32
#SBATCH --mem=200G
T=${1:?usage: run_dissolve.sh <snapshot tag, e.g. m44>}
W=/albedo/work/user/hlantuit/arctic_surficial/work
PY=/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python
cd /albedo/work/user/hlantuit/arctic_surficial/scripts
$PY dissolve_release.py --tiles $W/final_$T --out $W/dissolve_$T --workers 32 || { echo "EXIT 1 (dissolve)"; exit 1; }
$PY dissolve_check.py $W/dissolve_$T --workers 32
rc=$?
echo "EXIT $rc"
exit $rc
