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
HOMEgfs_PR="${FUNCTESTS_DATA_ROOT}/global-workflow"
export HOMEgfs_PR

cd "${HOMEgfs_PR}"
pr_sha=$(git rev-parse --short HEAD)

${HOMEgfs}/ci/scripts/clone-build_ci.sh -p "${PR}" -d "${FUNCTESTS_DATA_ROOT}" -o "${FUNCTESTS_DATA_ROOT}/output_${PR}.log"
#echo "SKIPPING: ${HOMEgfs}/ci/scripts/clone-build_ci.sh -p ${PR} -d ${FUNCTESTS_DATA_ROOT} -o ${FUNCTESTS_DATA_ROOT}/output_${PR}.log"
export RUNTESTS="${FUNCTESTS_DATA_ROOT}/RUNTESTS"
mkdir -p "${RUNTESTS}"


    for yaml_config in "${HOMEgfs_PR}/ci/cases/"*.yaml; do
      case=$(basename "${yaml_config}" .yaml) || true
      pslot="${case}_${pr_sha}"
      export pslot
      set +e
      "${HOMEgfs_PR}/ci/scripts/create_experiment.py" --yaml "${HOMEgfs_PR}/ci/cases/${case}.yaml" --dir foobar
      ci_status=$?
      set -e
      if [[ ${ci_status} -eq 0 ]]; then
        {
          echo "Created experiment:            *SUCCESS*"
          echo "Case setup: Completed at $(date) for experiment ${pslot}" || true
        } >> "${FUNCTESTS_DATA_ROOT}/output_${PR}.log"
        #"${GH}" pr edit --repo "${REPO_URL}" "${pr}" --remove-label "CI-${MACHINE_ID^}-Building" --add-label "CI-${MACHINE_ID^}-Running"
        #"${HOMEgfs}/ci/scripts/pr_list_database.py" --dbfile "${pr_list_dbfile}" --update_pr "${pr}" Open Running
       cd $RUNTESTS/EXPDIR/$pslot
       echo $PWD
       SDATE=$(${HOMEgfs}/ci/functional/test_configuration.py ${PWD} | grep SDATE | cut -d ":" -f 2 | tr -d " \t\n\r")
       ${HOMEgfs}/ci/functional/get_batchscripts.sh $PWD $SDATE
      else 
        {
          echo "Failed to create experiment:  *FAIL* ${pslot}"
          echo "Experiment setup: failed at $(date) for experiment ${pslot}" || true
          echo ""
          cat "${HOMEgfs_PR}/ci/scripts/"setup_*.std*
        } >> "${FUNCTESTS_DATA_ROOT}/output_${PR}.log"
        #"${GH}" pr edit "${pr}" --repo "${REPO_URL}" --remove-label "CI-${MACHINE_ID^}-Building" --add-label "CI-${MACHINE_ID^}-Failed"
        #"${HOMEgfs}/ci/scripts/pr_list_database.py" --remove_pr "${pr}" --dbfile "${pr_list_dbfile}"
      fi
    done
