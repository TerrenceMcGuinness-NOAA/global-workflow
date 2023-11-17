#!/bin/env bash

function cancel_slrum_jobs() {

    local substring=$1
    local job_ids
    job_ids=$(squeue -u "${USER}" -h -o "%i")

    for job_id in ${job_ids}; do
       batch_script=$(sacct -j "{$job_id}" --batch-script)
       if [[ "${$batch_script}" == *"${substring}"* ]]; then
        scancel "${job_id}"
      fi
    done
}
