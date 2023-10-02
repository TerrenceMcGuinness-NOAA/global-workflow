#!/bin/env bash
#set -eux
################################################################
# Setup the reletive paths to scripts and PS4 for better logging 
################################################################

export GH=${HOME}/bin/gh
#export REPO_URL=${REPO_URL:-"https://github.com/NOAA-EMC/global-workflow.git"}
export REPO_URL=https://github.com/TerrenceMcGuinness-NOAA/global-workflow.git

HOMEgfs="$(cd "$(dirname  "${BASH_SOURCE[0]}")/../.." >/dev/null 2>&1 && pwd )"
echo "HOMEgfs: ${HOMEgfs}"
scriptname=$(basename "${BASH_SOURCE[0]}")
echo "Begin ${scriptname} at $(date -u)" || true
export PS4='+ $(basename ${BASH_SOURCE})[${LINENO}]'

#########################################################################
#  Set up runtime environment varibles for accounts on supproted machines
#########################################################################

source "${HOMEgfs}/ush/detect_machine.sh"
case ${MACHINE_ID} in
  hera | orion)
    echo "Setting up environment for running Fuctional Based Automated Testing on ${MACHINE_ID}"
    source "${HOMEgfs}/workflow/gw_setup.sh"
    source "${HOMEgfs}/ci/platforms/config.${MACHINE_ID}"
    ;;
  *)
    echo "Unsupported platform. Exiting with error."
    exit 1
    ;;
esac

pr_list=$(${GH} pr list --repo "${REPO_URL}" --label "CI-${MACHINE_ID^}-Functiontest-Ready" --state "open" | awk '{print $1}') || true
for pr in ${pr_list}; do
 echo "PRs ready: ${pr}"
done

# TODO Hard code a specific PR number for now and 
# develop the rest of the functional test infrastructure
HOMEgfs_PR="${FUNCTESTS_DATA_ROOT}/global-workflow"
export HOMEgfs_PR
cd "${HOMEgfs_PR}"
pr_sha=$(git rev-parse --short HEAD)
DATE_STR=$(date +%m-%d-%y)

##########################################################################
# Clone and build global-workflow for the functional tests to work against
clone_branch="functional_tests"
"${HOMEgfs}"/ci/scripts/clone-build_ci.sh -b "${clone_branch}" -d "${FUNCTESTS_DATA_ROOT}" -o "${FUNCTESTS_DATA_ROOT}"/output_"${DATE_STR}".log
#echo "SKIPPING: ${HOMEgfs}/ci/scripts/clone-build_ci.sh -b ${clone_branch}  -d ${FUNCTESTS_DATA_ROOT} -o ${FUNCTESTS_DATA_ROOT}/output_${DATE_STR}.log"


############################################################################
# Create a expdirs for gfs and gdas cycling for drawing funtional tests from

functional_test_case_list="C48_ATM.yaml C48_S2SW.yaml C96_atm3DVar.yaml"

export RUNTESTS="${FUNCTESTS_DATA_ROOT}/RUNTESTS"
mkdir -p "${RUNTESTS}"

#for yaml_config in "${HOMEgfs_PR}/ci/cases/"*.yaml; do
for yaml_config in ${functional_test_case_list}; do
  case=$(basename "${yaml_config}" .yaml) || true
  pslot="${case}_${pr_sha}"
  export pslot
  set +e
  "${HOMEgfs_PR}/ci/scripts/create_experiment.py" --yaml "${HOMEgfs_PR}/ci/cases/pr/${case}.yaml" --dir foobar
  ci_status=$?
  set -e
  if [[ ${ci_status} -eq 0 ]]; then
    {
      echo "Created experiment:            *SUCCESS*"
      echo "Case setup: Completed at $(date) for experiment ${pslot}" || true
      "${HOMEgfs}/ci/functional/ush/test_configuration.py" "${RUNTESTS}"/EXPDIR/"${pslot}" -v
    } >> "${FUNCTESTS_DATA_ROOT}/output_${DATE_STR}.log"
    #"${GH}" pr edit --repo "${REPO_URL}" "${pr}" --remove-label "CI-${MACHINE_ID^}-Building" --add-label "CI-${MACHINE_ID^}-Running"
    #"${HOMEgfs}/ci/scripts/pr_list_database.py" --dbfile "${pr_list_dbfile}" --update_pr "${pr}" Open Running
  else 
    {
      echo "Failed to create experiment:  *FAIL* ${pslot}"
      echo "Experiment setup: failed at $(date) for experiment ${pslot}" || true
      echo ""
      cat "${HOMEgfs_PR}/ci/scripts/"setup_*.std*
    } >> "${FUNCTESTS_DATA_ROOT}/output_${DATE_STR}.log"
    #"${GH}" pr edit "${pr}" --repo "${REPO_URL}" --remove-label "CI-${MACHINE_ID^}-Building" --add-label "CI-${MACHINE_ID^}-Failed"
    #"${HOMEgfs}/ci/scripts/pr_list_database.py" --remove_pr "${pr}" --dbfile "${pr_list_dbfile}"
 fi
done

