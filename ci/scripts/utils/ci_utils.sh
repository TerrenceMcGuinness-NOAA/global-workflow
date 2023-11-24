#!/bin/env bash

function cancel_slurm_jobs() {

  local substring=$1
  local job_ids
  job_ids=$(squeue -u "${USER}" -h -o "%i")

  for job_id in ${job_ids}; do
    job_name=$(sacct -j "${job_id}" --format=JobName%100 | head -3 | tail -1 | sed -r 's/\s+//g') || true
    if [[ "${job_name}" == *"${substring}"* ]]; then
      echo"Canceling Slurm Job ${job_name} with: scancel ${job_id}"
      scancel "${job_id}"
    fi
  done
}


function checkout () {

  PR = $1
  repodir = $2
  outfile = $3

  cd "${repodir}" || exit 1
  git clone "${REPO_URL}"
  cd global-workflow || exit 1

  # checkout pull request
  "${GH}" pr checkout "${PR}" --repo "${REPO_URL}"
  HOMEgfs="${PWD}"
  source "${HOMEgfs}/ush/detect_machine.sh"

  ####################################################################
  # start output file
  {
  echo "Automated global-workflow Testing Results:"
  echo '```'
  echo "Machine: ${MACHINE_ID^}"
  echo "Start: $(date) on $(hostname)" || true
  echo "---------------------------------------------------"
  }  >> "${outfile}"
  ######################################################################

  MACHINE=$(echo "${MACHINE_ID}" | tr '[:upper:]' '[:lower:]')
  export MACHINE

  # get commit hash
  commit=$(git log --pretty=format:'%h' -n 1)
  echo "${commit}" > "../commit"

  # run checkout script
  cd sorc || exit 1
  set +e
  ./checkout.sh -c -g -u >> log.checkout 2>&1
  checkout_status=$?
  if [[ ${checkout_status} != 0 ]]; then
    {
      echo "Checkout: *** FAILED ***"
      echo "Checkout: Failed at $(date)" || true
      echo "Checkout: see output at ${PWD}/log.checkout"
    } >> "${outfile}"
    echo "ERROR: ${checkout_status}"
    exit "${checkout_status}"
  else
    {
      echo "Checkout: Completed at $(date)" || true
    } >> "${outfile}"
  fi

}
