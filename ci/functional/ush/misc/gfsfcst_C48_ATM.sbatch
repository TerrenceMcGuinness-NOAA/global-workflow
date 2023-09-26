#! /bin/sh
#SBATCH --job-name=C48_ATM_gfsfcst_12
#SBATCH --account=nems
#SBATCH --qos=batch
#SBATCH --partition=orion
#SBATCH -t 03:00:00
#SBATCH --nodes=1-1
#SBATCH --tasks-per-node=40
#SBATCH --cpus-per-task=1
#SBATCH -o gfsfcst.log
#SBATCH --export=NONE
export RUN_ENVIR='emc'
export HOMEgfs='/work2/noaa/global/mterry/FUNCTESTS_DATA_ROOT/global-workflow'
export EXPDIR='/work2/noaa/global/mterry/FUNCTESTS_DATA_ROOT/RUNTESTS/EXPDIR/C48_ATM'
export NET='gfs'
export CDUMP='gfs'
export RUN='gfs'
export CDATE='2021032312'
export PDY='20210323'
export cyc='12'
export COMROOT='/work/noaa/global/glopara/com'
export DATAROOT='/work/noaa/stmp/mterry/RUNDIRS/C48_ATM'
echo "NO FAIL"
/work2/noaa/global/mterry/FUNCTESTS_DATA_ROOT/global-workflow/jobs/rocoto/fcst.sh
