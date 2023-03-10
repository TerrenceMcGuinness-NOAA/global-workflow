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
# PR number and calls run_ci.sh to perform a clone and full build from $(HOMEgfs)/sorc
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
pwd="$(cd "$(dirname  "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd )"
scriptname=$(basename "${BASH_SOURCE[0]}")
echo "Begin ${scriptname} at $(date -u)" || true
export PS4='+ $(basename ${BASH_SOURCE})[${LINENO}]'

usage() {
  set +x
  echo
  echo "Usage: $0 -t <target> -h"
  echo
  echo    "  -h  display this message and quit"
  echo -n "  -t  target/machine script is running"
  if [[ -n "${TARGET+x}" ]]; then
    echo "on DEFAULT: ${TARGET}"
  fi  
  echo
  exit 1
}



#########################################################################
#  Set up runtime environment varibles for accounts on supproted machines
#########################################################################

source "${pwd}/../ush/detect_machine.sh"
if [[ "${MACHINE_ID}" != "UNKNOWN" ]]; then
   TARGET="${MACHINE_ID}"
fi   

if [[ -z ${TARGET+x} || $1 == "-h" ]]; then
  export TARGET
  while getopts "t:h" opt; do
    case ${opt} in
      t)
        TARGET=${OPTARG}
        ;;
      h|\?|:)
        usage
        ;;
      *)
        echo "Unrecognized option" 
        usage
    esac
  done

  if [[ -z "${TARGET+x}" ]]; then
    usage
  fi  

fi

case ${TARGET} in
  hera | orion)
    echo "Running Automated Testing on ${TARGET}"
    source "${pwd}/${TARGET}.sh"
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
 exit
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
  # call run_ci to clone and build PR
  id=$("${GH}" pr view "${pr}" --repo "${repo_url}" --json id --jq '.id')
  "${pwd}/run_ci.sh" -p "${pr}" -d "${pr_dir}" -o "${pr_dir}/output_${id}"
  ci_status=$?
  if [[ ${ci_status} -eq 0 ]]; then
    export RUNTEST="${pr_dir}/RUNTEST"
    mkdir -p "${RUNTEST}"
    cd "${RUNTEST}"
    rm -Rf *
    export HOMEgfs="${pr_dir}/global-workflow"
    "${pwd}/create_experment.py" --yaml "${pwd}/cold_96_00z.yaml"
    ci_status=$?
    if [[ ${ci_status} -eq 0 ]]; then
      {
        echo "Created experment"
        echo "Experment setup: Completed at $(date)" || true
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

  ####################################
  # TODO setup_test.py -t testname.py
  ####################################

##########################################
# scrub working directory for older files
##########################################
#find "${GFS_CI_ROOT}/PR/*" -maxdepth 1 -mtime +3 -exec rm -rf {} \;

exit 0
