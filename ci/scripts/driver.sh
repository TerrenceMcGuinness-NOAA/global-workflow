#!/bin/bash
set -eux

#####################################################################################
#
# Script description: Top level driver script for checking PR
#                     ready for CI regression testing
#
# Abstract:
#
# This script uses GitHub CLI to check for Pull Requests with CI-Ready-${machine} tags on the
# development branch for the global-workflow repo.  It then stages tests directories per
# PR number and calls clone-build_ci.sh to perform a clone and full build from the PR.
# It then is ready to run a suite of regression tests with various configurations
#######################################################################################

#################################################################
# TODO using static build for GitHub CLI until fixed in HPC-Stack
#################################################################
export GH=${HOME}/bin/gh
#export REPO_URL=${REPO_URL:-"https://github.com/NOAA-EMC/global-workflow.git"}
export REPO_URL=git@github.com:TerrenceMcGuinness-NOAA/global-workflow.git

################################################################
# Setup the reletive paths to scripts and PS4 for better logging
################################################################
ROOT_DIR="$(cd "$(dirname  "${BASH_SOURCE[0]}")/../.." >/dev/null 2>&1 && pwd )"
scriptname=$(basename "${BASH_SOURCE[0]}")
echo "Begin ${scriptname} at $(date -u)" || true
export PS4='+ $(basename ${BASH_SOURCE})[${LINENO}]'

#########################################################################
#  Set up runtime environment varibles for accounts on supproted machines
#########################################################################
source "${ROOT_DIR}/ci/scripts/utils/ci_utils.sh"
source "${ROOT_DIR}/ush/detect_machine.sh"
case ${MACHINE_ID} in
  hera | orion)
    echo "Running Automated Testing on ${MACHINE_ID}"
    source "${ROOT_DIR}/ci/platforms/config.${MACHINE_ID}"
    ;;
  *)
    echo "Unsupported platform. Exiting with error."
    exit 1
    ;;
esac

######################################################
# setup runtime env for correct python install and git
######################################################
set +x
source "${ROOT_DIR}/ush/module-setup.sh"
module use "${ROOT_DIR}/modulefiles"
module load "module_gwsetup.${MACHINE_ID}"
set -x

############################################################
# query repo and get list of open PRs with tags {machine}-CI
############################################################

pr_list_dbfile="${GFS_CI_ROOT}/open_pr_list.db"

if [[ ! -f "${pr_list_dbfile}" ]]; then
  "${ROOT_DIR}/ci/scripts/pr_list_database.py" --create --dbfile "${pr_list_dbfile}"
fi

pr_list=$(${GH} pr list --repo "${REPO_URL}" --label "CI-${MACHINE_ID^}-Ready" --state "open" | awk '{print $1}') || true

for pr in ${pr_list}; do
  pr_dir="${GFS_CI_ROOT}/PR/${pr}"
  output_ci="${pr_dir}/output_build_${id}"
  output_ci_single="${GFS_CI_ROOT}/PR/${pr}/output_driver_single.log"
  db_list=$("${ROOT_DIR}/ci/scripts/pr_list_database.py" --add_pr "${pr}" --dbfile "${pr_list_dbfile}")
  #############################################################
  # Check if a Ready labeled PR has changed back from once set
  # and in that case remove all previous jobs in scheduler and
  # and remove PR from filesystem to start clean
  #############################################################
  if [[ "${db_list}" == *"already is in list"* ]]; then
    job_id=$("${ROOT_DIR}/ci/scripts/pr_list_database.py" --dbfile "${pr_list_dbfile}" --display "${pr}" | awk '{print $4}') || true
    {
      echo "PR:${pr} Reset to ${MACHINE_ID^}-Ready by user and is now restarting CI tests on $(date +'%A %b %Y')" || true
    } >> "${output_ci_single}"
    if [[ -n "${job_id+x}" && "${job_id}" -ne 0 ]]; then
      scancel "${job_id}"
    fi
    "${ROOT_DIR}/ci/scripts/pr_list_database.py" --dbfile "${pr_list_dbfile}" --update_pr "${pr}" Open Ready "0"
    experiments=$(find "${pr_dir}/RUNTESTS" -mindepth 1 -maxdepth 1 -type d) || true
    if [[ -z "${experiments}" ]]; then
       echo "No current experiments to cancel in PR: ${pr} on ${MACHINE_ID^}" >> "${output_ci_single}"
    else
      for cases in ${experiments}; do
        cancel_slrum_jobs "${pr_dir}/RUNTESTS/${cases}"
        {
          echo "Canceled all jobs for experiment ${cases} in PR:${pr} on ${MACHINE_ID^}"
        } >> "${output_ci_single}"
      done
    fi
    sed -i "1 i\`\`\`" "${output_ci_single}"
    "${GH}" pr comment "${pr}" --repo "${REPO_URL}" --body-file "${output_ci_single}"
    rm -f "${output_ci_single}"
  fi
done

pr_list=""
if [[ -f "${pr_list_dbfile}" ]]; then
  pr_list=$("${ROOT_DIR}/ci/scripts/pr_list_database.py" --display --dbfile "${pr_list_dbfile}" | grep -v Failed | grep Open | grep Ready | awk '{print $1}') || true
fi
if [[ -z "${pr_list+x}" ]]; then
  echo "no PRs open and ready for checkout/build .. exiting"
  exit 0
fi


#############################################################
# Loop throu all open PRs
# Clone, checkout, build, creat set of cases, for each
#############################################################

for pr in ${pr_list}; do
  # Skip pr's that are currently Building for when overlapping driver scripts are being called from within cron
  pr_building=$("${ROOT_DIR}/ci/scripts/pr_list_database.py" --display "${pr}" --dbfile "${pr_list_dbfile}" | grep Building) || true
  if [[ -z "${pr_building+x}" ]]; then
      continue
  fi
  echo "Processing Pull Request #${pr}"
  pr_dir="${GFS_CI_ROOT}/PR/${pr}"
  # call clone-build_ci to clone and build PR
  id=$("${GH}" pr view "${pr}" --repo "${REPO_URL}" --json id --jq '.id')
  set +e
  output_ci="${pr_dir}/output_build_${id}"
  output_ci_single="${GFS_CI_ROOT}/PR/${pr}/output_driver_single.log"
  log_build="${GFS_CI_ROOT}/build_logs/log.build_PR-${pr}"
  log_build_err="${GFS_CI_ROOT}/build_logs/log.err.build_PR-${pr}"
  mkdir -p "${GFS_CI_ROOT}/build_logs"
  rm -f "${output_ci}" "${outout_ci_single}"
  BUILD_TIME_LIMIT="04:00:00"
  # shellcheck disable=SC2016
  build_job_id=$(sbatch --export=ALL,MACHINE="${MACHINE_ID}" -A "${SLURM_ACCOUNT}" -p service -t "${BUILD_TIME_LIMIT}" --nodes=1 --cpus-per-task=25 -o "${log_build}-%A" -e "${log_build_err}-%A" --job-name "${pr}_building_PR" "${ROOT_DIR}/ci/scripts/clone-build_ci.sh" -p "${pr##}" -d "${pr_dir##}" -o "${output_ci}" | awk '{print $4}') || true
  "${GH}" pr edit --repo "${REPO_URL}" "${pr}" --remove-label "CI-${MACHINE_ID^}-Ready" --add-label "CI-${MACHINE_ID^}-Building"
  "${ROOT_DIR}/ci/scripts/pr_list_database.py" --dbfile "${pr_list_dbfile}" --update_pr "${pr}" Open Building "${build_job_id}"
  # shellcheck disable=SC2312
  while squeue -j "${build_job_id}" | grep -q "${build_job_id}"
  do
    sleep 10
  done
  ci_status=0
  check=$(tail -1 "${log_build_err}-${build_job_id}")
  if [[ "${check}" == *"CANCELLED"* ]]; then
    # User canceled the build job so exit and let the next driver script take over
    output_build_single="${GFS_CI_ROOT}/build_logs/single.log-${build_job_id}"
    rm -f "${output_build_single}"
    if [[ "${check}" == *"DUE TO TIME LIMIT"* ]]; then
      CAUSE="because of time limit over ${BUILD_TIME_LIMIT}"
      ci_status=-1
    else # TODO find a more conclusive check for cancel by user
      CAUSE="by user"
    fi
    job_id=$("${ROOT_DIR}/ci/scripts/pr_list_database.py" --dbfile "${pr_list_dbfile}" --display "${pr}" | awk '{print $4}') || true
    {
      echo "Job ${build_job_id} for building PR:${pr} on ${MACHINE_ID^} was *** CANCELED *** on $(date +'%A %b %Y') ${CAUSE}" || true
      echo "Rebuilding PR:${pr} with new job_id:${job_id} in ${pr_dir}/global-workflow"
      cat "${check}"
    } >> "${output_build_single}"
    sed -i "1 i\`\`\`" "${output_build_single}"
    "${GH}" pr comment "${pr}" --repo "${REPO_URL}" --body-file "${output_build_single}"
    rm -f "${output_build_single}"
    if [[ "${ci_status}" -eq 0 ]]; then
      exit "${ci_status}"
    fi
  fi
  # Checking for ERROR in log file from build-clone and assiging ci_status
  if [[ "${check}" == *"ERROR"* ]]; then
     ci_status=$(echo check | awk '{print $2}')
  fi
  set -e
  if [[ ${ci_status} -eq 0 ]]; then
    "${ROOT_DIR}/ci/scripts/pr_list_database.py" --dbfile "${pr_list_dbfile}" --update_pr "${pr}" Open Built
    #setup space to put an experiment
    # export RUNTESTS for yaml case files to pickup
    export RUNTESTS="${pr_dir}/RUNTESTS"
    rm -Rf "${pr_dir:?}/RUNTESTS/"*

    #############################################################
    # loop over every yaml file in the PR's ci/cases
    # and create an run directory for each one for this PR loop
    #############################################################
    HOMEgfs="${pr_dir}/global-workflow"
    cd "${HOMEgfs}"
    pr_sha=$(git rev-parse --short HEAD)

    for yaml_config in "${HOMEgfs}/ci/cases/pr/"*.yaml; do
      case=$(basename "${yaml_config}" .yaml) || true
      # export pslot for yaml case files to pickup
      export pslot="${case}_${pr_sha}"
      rm -Rf "${STMP}/RUNDIRS/${pslot}"
      set +e
      export LOGFILE_PATH="${HOMEgfs}/ci/scripts/create_experiment.log"
      rm -f "${LOGFILE_PATH}"
      "${HOMEgfs}/workflow/create_experiment.py" --yaml "${HOMEgfs}/ci/cases/pr/${case}.yaml" > "${LOGFILE_PATH}" 2>&1
      ci_status=$?
      set -e
      if [[ ${ci_status} -eq 0 ]]; then
        last_line=$(tail -1 "${LOGFILE_PATH}")
        if [[ "${last_line}" == *"Skipping creation"* ]]; then
          action="Skipped"
        else
          action="Completed"
        fi
        {
          echo "Case setup: ${action} for experiment ${pslot}" || true
        } >> "${output_ci}"
      else
        {
          echo "*** Failed *** to create experiment: ${pslot}"
          echo ""
          cat "${LOGFILE_PATH}"
        } >> "${output_ci}"
        "${GH}" pr edit "${pr}" --repo "${REPO_URL}" --remove-label "CI-${MACHINE_ID^}-Building" --add-label "CI-${MACHINE_ID^}-Failed"
        "${ROOT_DIR}/ci/scripts/pr_list_database.py" --remove_pr "${pr}" --dbfile "${pr_list_dbfile}"
        "${GH}" pr comment "${pr}" --repo "${REPO_URL}" --body-file "${output_ci}"
        exit 1
      fi
    done

    "${GH}" pr edit --repo "${REPO_URL}" "${pr}" --remove-label "CI-${MACHINE_ID^}-Building" --add-label "CI-${MACHINE_ID^}-Running"
    "${ROOT_DIR}/ci/scripts/pr_list_database.py" --dbfile "${pr_list_dbfile}" --update_pr "${pr}" Open Running
    "${GH}" pr comment "${pr}" --repo "${REPO_URL}" --body-file "${output_ci}"

  else # if build failed without CANCELLED
    {
      echo "Cloning and building *** FAILED *** on ${MACHINE_ID^} for PR: ${pr}"
      echo "on $(date +'%A %b %Y') for repo ${REPO_URL}" || true
      echo ""
      cat "${log_build_err}-${build_job_id}"
    } >> "${output_ci}"
    sed -i "1 i\`\`\`" "${output_ci}"
    "${GH}" pr edit "${pr}" --repo "${REPO_URL}" --remove-label "CI-${MACHINE_ID^}-Building" --add-label "CI-${MACHINE_ID^}-Failed"
    "${ROOT_DIR}/ci/scripts/pr_list_database.py" --remove_pr "${pr}" --dbfile "${pr_list_dbfile}"
    "${GH}" pr comment "${pr}" --repo "${REPO_URL}" --body-file "${output_ci}"
  fi

done # looping over each open and labeled PR

##########################################
# scrub working directory for older files
##########################################
#
#find "${GFS_CI_ROOT}/PR/*" -maxdepth 1 -mtime +3 -exec rm -rf {} \;
