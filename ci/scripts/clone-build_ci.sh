#!/bin/bash
set -eux

#####################################################################
#  Usage and arguments for specfifying cloned directgory
#####################################################################
usage() {
  set +x
  echo
  echo "Usage: $0 [-p <PR#> | -b branch ] -d <directory> -o <output> -h"
  echo
  echo "  -p  PR nunber to clone and build"
  echo "  -b  new branch to clone and build"
  echo "  -d  Full path of <directory> of were to clone and build PR"
  echo "  -o  Full path to output message file detailing results of CI tests"
  echo "  -h  display this message and quit"
  echo
  exit 1
}

################################################################
while getopts "d:o:hb:p" opt; do
  case ${opt} in
    p)
      eval nextopt=\${$OPTIND}
      if [[ -n $nextopt && $nextopt != -* ]] ; then
        OPTIND=$((OPTIND + 1))
        offset=$nextopt
      else
        offset=0
      fi
      if [[ -n $offset && ! $offset =~ ^[0-9]+$ ]]; then
        echo "-p for PR nuber parameter must be an integer."
        exit
      fi
      PR=${offset}
      ;;
    d)
      repodir=${OPTARG}
      ;;
    o)
      outfile=${OPTARG}
      ;;
    b)  
      branch=${OPTARG}
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

if [ -z "${PR+x}" ] && [ -z "${branch+x}" ]; then
  echo "ERROR: either PR number had to be specified or a branch name (both can not be empty)"
  usage
fi
if [ -z "${repodir+x}" ] || [ -z "${outfile+x}" ]; then
  echo "ERROR: directory to clone and outfile need to be specified"
  usage
fi

if [[ ! -d "${repodir}" ]]; then
  echo "ERROR: directory ${repodir} does not exists"
  exit 1
fi
cd "${repodir}" || exit 1
if [[ -d global-workflow ]]; then
  rm -Rf global-workflow
fi

if [[ -z "${PR+x}" ]]; then
  git clone "${REPO_URL}" -b "${branch}"
  cd global-workflow || exit 1
else
  git clone "${REPO_URL}"
  cd global-workflow || exit 1

  pr_state=$("${GH}" pr view "${PR}" --json state --jq '.state')
  if [[ "${pr_state}" != "OPEN" ]]; then
    title=$("${GH}" pr view "${PR}" --json title --jq '.title')
    echo "PR ${title} is no longer open, state is ${pr_state} ... quitting"
    exit 1
  fi
  # checkout pull request
  "${GH}" pr checkout "${PR}" --repo "${REPO_URL}"
fi  

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

# get commit hash
commit=$(git log --pretty=format:'%h' -n 1)
echo "${commit}" > "../commit"

# run checkout script
cd sorc || exit 1
set +e
# TODO enable -u later when GDASApp tests are added
./checkout.sh -c -g -u >> log.checkout 2>&1
checkout_status=$?
if [[ ${checkout_status} != 0 ]]; then
  {
    echo "Checkout:                      *FAILED*"
    echo "Checkout: Failed at $(date)" || true
    echo "Checkout: see output at ${PWD}/log.checkout"
  } >> "${outfile}"
  exit "${checkout_status}"
else
  {
    echo "Checkout:                      *SUCCESS*"
    echo "Checkout: Completed at $(date)" || true
  } >> "${outfile}"
fi

# build full cycle
source "${HOMEgfs}/ush/module-setup.sh"
export BUILD_JOBS=8
rm -rf log.build
./build_all.sh  >> log.build 2>&1
build_status=$?

if [[ ${build_status} != 0 ]]; then
  {
    echo "Build:                         *FAILED*"
    echo "Build: Failed at $(date)" || true
    echo "Build: see output at ${PWD}/log.build"
  } >> "${outfile}"
  exit "${build_status}"
else
  {
    echo "Build:                         *SUCCESS*"
    echo "Build: Completed at $(date)" || true
  } >> "${outfile}"
fi

./link_workflow.sh

echo "check/build/link test completed"
exit "${build_status}"
