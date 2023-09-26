#!/usr/bin/env bash

YAML_CASE=$1

source /work2/noaa/global/mterry/global-workflow_forked/ci/platforms/orion.sh

filename=$(basename -- ${YAML_CASE})
export pslot="${filename%.*}"
export RUNTESTS=/work2/noaa/global/mterry/RUNTESTS
export HOMEgfs_PR=/work2/noaa/global/mterry/global-workflow_forked

${HOMEgfs_PR}/ci/scripts/create_experiment.py --yaml $YAML_CASE --dir foobar
