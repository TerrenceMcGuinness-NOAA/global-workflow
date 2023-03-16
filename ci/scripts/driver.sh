#!/bin/bash --login
#
#####################################################################################
#
# Script description: Top level driver script for checking PR
#                     ready for CI regression testing
#
# Abstract:
#
# This script uses GitHub CLI to check for Pull Requests with {machine}-CI tags on the
# development branch for the global-workflow repo.  It then stages tests directories per
# PR number and calls clone-build_ci.sh to perform a clone and full build from $(HOMEgfs)/sorc
# of the PR. It then is ready to run a suite of regression tests with various
# configurations with run_tests.py.
#######################################################################################

#################################################################
# TODO using static build for GitHub CLI until fixed in HPC-Stack
#################################################################
GH=/home/Terry.McGuinness/bin/gh
repo_url=${repo_url:-"https://github.com/NOAA-EMC/global-workflow.git"}

################################################################
# Setup the reletive paths to scripts and PS4 for better logging 
################################################################
WF_ROOT_DIR="$(cd "$(dirname  "${BASH_SOURCE[0]}")/../.." >/dev/null 2>&1 && pwd )"
scriptname=$(basename "${BASH_SOURCE[0]}")
echo "Begin ${scriptname} at $(date -u)" || true
export PS4='+ $(basename ${BASH_SOURCE})[${LINENO}]'


usage() {
  set +x
  echo
  echo "Usage: $0 -h"
  echo
  echo    "  -h  display this message and quit"
  echo
  echo "This is top level script to run CI tests on the global-workflow repo"
  if [[ -n "${TARGET+x}" ]]; then
     echo "on the DEFAULTED: ${TARGET} machine"
  fi  
  echo
  exit 1
}


#########################################################################
#  Set up runtime environment varibles for accounts on supproted machines
#########################################################################

source "${WF_ROOT_DIR}/ush/detect_machine.sh"
if [[ "${MACHINE_ID}" != "UNKNOWN" ]]; then
  TARGET="${MACHINE_ID}"
else
  echo "Unsupported platform. Exiting with error."
  exit 1
fi

case ${TARGET} in
  hera | orion)
    echo "Running Automated Testing on ${TARGET}"
    source "${WF_ROOT_DIR}/ci/environments/${TARGET}.sh"
    ;;
  *)
    echo "Unsupported platform. Exiting with error."
    exit 1
    ;;
esac

############################################################
# query repo and get list of open PRs with tags {machine}-CI
############################################################
set -eux
export CI_HOST="${TARGET^}"
pr_list_file="open_pr_list"
rm -f "${pr_list_file}"
list=$(${GH} pr list --repo "${repo_url}" --label "${CI_HOST}-CI" --state "open")
list=$(echo "${list}" | awk '{print $1;}' > "${GFS_CI_ROOT}/${pr_list_file}")

if [[ -s "${GFS_CI_ROOT}/${pr_list_file}" ]]; then
 pr_list=$(cat "${GFS_CI_ROOT}/${pr_list_file}")
else
 echo "no PRs to process .. exit"
 exit 1
fi 

#######################################
# clone, checkout, build, test, each PR
# loop throu all open PRs
#######################################

cd "${GFS_CI_ROOT}"
for pr in ${pr_list}; do
  "${GH}" pr edit --repo "${repo_url}" "${pr}" --remove-label "${CI_HOST}-CI" --add-label "${CI_HOST}-Running"
  echo "Processing Pull Request #${pr}"
  pr_dir="${GFS_CI_ROOT}/PR/${pr}"
  mkdir -p "${pr_dir}"
  # call clone-build_ci to clone and build PR
  id=$("${GH}" pr view "${pr}" --repo "${repo_url}" --json id --jq '.id')
  #"${WF_ROOT_DIR}/ci/scripts/clone-build_ci.sh" -p "${pr}" -d "${pr_dir}" -o "${pr_dir}/output_${id}"
  echo "SKIPPING CONE-BUILD"
  ci_status=$?
  if [[ ${ci_status} -eq 0 ]]; then
    #setup runtime env for correct python install
    export HOMEGFS="${pr_dir}/global-workflow"
    module use "${HOMEGFS}/modulefiles"
    module load "module_setup.${TARGET}"
    module list
    #setup space to put an experiment
    export RUNTEST="${pr_dir}/RUNTEST"
    rm -Rf "${RUNTEST}"
    mkdir -p "${RUNTEST}"
    # TODO adding pip install for YAML until is in HPC minicanda3
    cd "${HOMEGFS}/ush/python/pygw"
    python3 -m pip install .
    #make links to the python packages used in the PR'ed repo
    cd "${WF_ROOT_DIR}/ci/scripts"
    if [[ ! -L workflow ]]; then
      ln -s "${HOMEGFS}/workflow" workflow
    fi
    if [[ ! -L pygw ]]; then
      ln -s "${HOMEGFS}/ush/python/pygw/src/pygw" pygw
    fi
    PSLOT=C96C48_hybatmDA # TODO loop over experments for each yaml file in the experiments dir
    "${WF_ROOT_DIR}/ci/scripts/create_experiment.py" --yaml "${WF_ROOT_DIR}/ci/experiments/${PSLOT}.yaml"
    ci_status=$?
    if [[ ${ci_status} -eq 0 ]]; then
      {
        echo "Created experiment"
        echo "Experiment setup: Completed at $(date)" || true
      } >> "${GFS_CI_ROOT}/PR/${pr}/output_${id}"
      "${GH}" pr comment "${pr}" --repo "${repo_url}" --body-file "${GFS_CI_ROOT}/PR/${pr}/output_${id}"
      "${GH}" pr edit --repo "${repo_url}" "${pr}" --remove-label "${CI_HOST}-Running" --add-label "${CI_HOST}-Passed"
    else
      "${GH}" pr edit "${pr}" --repo "${repo_url}" --remove-label "${CI_HOST}-Running" --add-label "${CI_HOST}-Failed"
    fi
  else
    "${GH}" pr edit "${pr}" --repo "${repo_url}" --remove-label "${CI_HOST}-Running" --add-label "${CI_HOST}-Failed"
  fi
done

##########################################
# scrub working directory for older files
##########################################
#find "${GFS_CI_ROOT}/PR/*" -maxdepth 1 -mtime +3 -exec rm -rf {} \;

exit 0
