#!/bin/bash
set -eux

#####################################################################
#  Usage and arguments for specfifying cloned directgory
#####################################################################
usage() {
  set +x
  echo
  echo "Usage: $0 -p <PR#> -d <directory> -o <output> -h"
  echo
  echo "  -p  PR number to clone and build"
  echo "  -d  Full path of <directory> of where to clone and build PR"
  echo "  -o  Full path to output message file detailing results of CI tests"
  echo "  -h  display this message and quit"
  echo
  exit 1
}

################################################################
while getopts "p:d:o:h" opt; do
  case ${opt} in
    p)
      PR=${OPTARG}
      ;;
    d)
      repodir=${OPTARG}
      ;;
    o)
      outfile=${OPTARG}
      ;;
    h|\?|:)
      usage
      ;;
    *)
      echo "Unrecognized option"
      usage
     ;;
  esac
done

checkout=False

if [[ ${checkout} == True ]]; then

  rm -Rf "${repodir}"
  mkdir -p "${repodir}"

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

  export MACHINE
  export MACHINE_ID

  cd "${repodir}/gobal-workflow"
  HOMEgfs="${PWD}"

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

fi  # skipping checkout


cd "${repodir}/global-workflow"
HOMEgfs="${PWD}"

# Passing on MACINE and MACHINE_ID to build sripts
# because the detect machine scripts to not pickup
# hostnames on computre nodes
export MACHINE
export MACHINE_ID

export BUILD_JOBS=8
rm -rf log.build
./build_all.sh  >> log.build 2>&1
build_status=$?

if [[ ${build_status} != 0 ]]; then
  {
    echo "Build: *** FAILED *** ${MACHINE_ID^}"
    echo "Build: Failed at $(date)" || true
    echo "Build: see output at ${PWD}/log.build"
  } >> "${outfile}"
  echo "ERROR: ${build_status}"
  exit "${build_status}"
else
  {
    echo "Build: Completed at $(date)" || true
  } >> "${outfile}"
fi

LINK_LOGFILE_PATH=link_workflow.log
./link_workflow.sh > "${LINK_LOGFILE_PATH}" 2>&1
link_status=$?
if [[ ${link_status} != 0 ]]; then
  {
    echo "Link: *** FAILED *** on ${MACHINE_ID^}"
    echo "Link: Failed at $(date)" || true
    echo ""
    cat "${LINK_LOGFILE_PATH}"
  } >> "${outfile}"
  # a unique error code is needed to distinguish between
  # a true link failure and one cause by user restart
  echo "ERROR: ${link_status}"
  exit "${link_status}"
fi

echo "check/build/link test completed"
