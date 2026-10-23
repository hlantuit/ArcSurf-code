#!/bin/bash
# usage: sbatch -J name run_py.sh script.py [args]   (logs to work/<jobname>.out)
#SBATCH -A perm_ag_coas.perm_ag_coas
#SBATCH -p smp
#SBATCH --qos=12h
#SBATCH -t 12:00:00
#SBATCH -c 32
#SBATCH --mem=200G
#SBATCH -o /albedo/work/user/hlantuit/arctic_surficial/work/%x.out
cd /albedo/work/user/hlantuit/arctic_surficial/scripts
/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python "$@"
rc=$?
echo "EXIT $rc"
exit $rc
