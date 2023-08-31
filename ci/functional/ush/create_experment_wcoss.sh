#!/usr/bin/env bash

YAML_CASE=$1

export HOMEgfs_PR=/lfs/h2/emc/eib/noscrub/terry.mcguinness/GLOBAL/global-workflow_forked
source ${HOMEgfs_PR}/ci/platforms/wcoss2.sh

filename=$(basename -- ${YAML_CASE})
export pslot="${filename%.*}"
export RUNTESTS=/lfs/h2/emc/eib/noscrub/terry.mcguinness/RUNTESTS

${HOMEgfs_PR}/ci/scripts/create_experiment.py --yaml $YAML_CASE --dir foobar
