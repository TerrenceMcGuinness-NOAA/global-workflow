#!/bin/env bash

function cancel_slrum_jobs() {

  local substring=$1
  local job_ids
  job_ids=$(squeue -u "${USER}" -h -o "%i")

  for job_id in ${job_ids}; do
    job_name=$(sacct -j "${job_id}" --format=JobName%100 | head -3 | tail -1 | sed -r 's/\s+//g')
    if [[ "${job_name}" == *"${substring}"* ]]; then
      scancel "${job_id}"
    fi
  done
}
