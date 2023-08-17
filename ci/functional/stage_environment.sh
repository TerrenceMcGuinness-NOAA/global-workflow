#!/bin/bash
#set -eux
################################################################
# Setup the reletive paths to scripts and PS4 for better logging 
################################################################

export GH=${HOME}/bin/gh
export REPO_URL=${REPO_URL:-"https://github.com/NOAA-EMC/global-workflow.git"}

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
    #source "${HOMEgfs}/workflow/gw_setup.sh"
    source "${HOMEgfs}/ci/platforms/${MACHINE_ID}.sh"
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
PR="${PR_FUNCTIONAL_TEST}"

"${HOMEgfs}/ci/scripts/clone-build_ci.sh -p ${PR} -d ${FUNCTESTS_DATA_ROOT}"
