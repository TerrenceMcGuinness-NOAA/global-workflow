#! /usr/bin/env bash

#######
# Preamble script to be SOURCED at the beginning of every script. Sets 
#   useful PS4 and optionally turns on set -x and set -eu. Also sets up 
#   crude script timing and provides a postamble that runs on exit.
#
# Syntax:
#   preamble.sh
#   
# Input environment variables:
#   TRACE (YES/NO): Whether to echo every command (set -x) [default: "YES"]
#   STRICT (YES/NO): Whether to exit immediately on error or undefined variable
#     (set -eu) [default: "YES"]
#   POSTAMBLE_CMD (empty/set): A command to run at the end of the job
#     [default: empty]
#   _calling_script: The name of the calling script (optional)
#
#######
set +x

# Record the start time so we can calculate the elapsed time later
start_time=$(date +%s)

# Get the base name of the calling script
_calling_script=${_calling_script:-$(basename "${BASH_SOURCE[1]}")}

# Announce the script has begun
start_time_human=$(date -d"@${start_time}" -u)
echo "Begin ${_calling_script} at ${start_time_human}"

declare -x PS4='+ $(basename ${BASH_SOURCE[0]:-${FUNCNAME[0]:-"Unknown"}})[${LINENO}]'

set_strict() {
    if [[ ${STRICT:-"YES"} == "YES" ]]; then
        # Exit on error and undefined variable
        set -eu
    fi
}

set_trace() {
    # Print the script name and line number of each command as it is 
    #   executed when using trace. 
    if [[ ${TRACE:-"YES"} == "YES" ]]; then
        set -x
    fi
}

postamble() {
    #
    # Commands to execute when a script ends. 
    #
    # Syntax:
    #   postamble script start_time rc
    #
    #   Arguments:
    #     script: name of the script ending
    #     start_time: start time of script (in seconds)
    #     rc: the exit code of the script
    #

    set +x
    script="${1}"
    start_time="${2}"
    rc="${3}"

    # Execute postamble command
    #
    # Commands can be added to the postamble by appending them to $POSTAMBLE_CMD:
    #    POSTAMBLE_CMD="new_thing; ${POSTAMBLE_CMD:-}" # (before existing commands)
    #    POSTAMBLE_CMD="${POSTAMBLE_CMD:-}; new_thing" # (after existing commands)
    #
    # Always use this form so previous POSTAMBLE_CMD are not overwritten. This should
    #   only be used for commands that execute conditionally (i.e. on certain machines
    #   or jobs). Global changes should just be added to this function.
    # These commands will be called when EACH SCRIPT terminates, so be mindful. Please
    #   consult with global-workflow CMs about permanent changes to $POSTAMBLE_CMD or
    #   this postamble function.
    #

    if [[ -v 'POSTAMBLE_CMD' ]]; then
      ${POSTAMBLE_CMD}
    fi

    # Calculate the elapsed time
    end_time=$(date +%s)
    end_time_human=$(date -d@"${end_time}" -u +%H:%M:%S)
    elapsed_sec=$((end_time - start_time))
    elapsed=$(date -d@"${elapsed_sec}" -u +%H:%M:%S)

    # Announce the script has ended, then pass the error code up
    echo "End ${script} at ${end_time_human} with error code ${rc:-0} (time elapsed: ${elapsed})"
    exit "${rc}"
}

# TODO: Remove this when moving to operations
function err_exit() {
    # Taken from NCO prod_util v2.1.0
    # SCRIPT NAME:  err_exit
    #
    # ABSTRACT:  This script is to be used when a fatal error or condition 
    # has been reached and you want to terminate the job.
    #
    # USAGE:  To use this script one must export the following variables to the
    # script: jobid, SENDECF, pgm, pgmout, DATA. One can provide
    # a message for the logfile by passing it to the script as an argument.

    # Do not fail in err_exit
    set +eux

    msg1=${*:-Job ${jobid} failed}
    if [[ -n "${pgm}" ]]; then
      msg1+=", ERROR IN ${pgm}"
    fi
    if [[ -n "${err}" ]]; then
      msg1+=" RETURN CODE ${err}"
    fi

    msg2="
    -------------------------------------------------------------
    -- FATAL ERROR: ${msg1}
    -- ABNORMAL EXIT at $(date) on ${HOSTNAME}
    -------------------------------------------------------------
    "

    >&2 echo "${msg2}"

    # list loaded modules
    module list
    >&2 echo ""

    >&2 echo "${msg1}"

    # list files in temporary working directory
    if [[ -n "${DATA}" ]]; then
      >&2 echo "${DATA}"
      >&2 ls -ltr "${DATA}"
    else
      >&2 echo "WARNING: DATA variable not defined"
    fi

    # save standard output
    if [[ -n "${pgmout}" ]]; then
      if [[ -s errfile ]]; then
        echo "----- contents of errfile -----" >> "${pgmout}"
        cat errfile >> "${pgmout}"
      fi
      >&2 cat "${pgmout}"
    elif [[ -s errfile ]]; then
      >&2 cat errfile
    fi

    # Write to ecflow log:
    if [[ "${SENDECF}" == "YES" ]]; then
      timeout 30 ecflow_client --msg "${ECF_NAME}: ${msg1}"
      timeout 30 ssh "${ECF_HOST}" "echo \"${msg}2\" >> ${ECF_JOBOUT:?}"
    fi

    # KILL THE JOB:
    if [[ "${SENDECF}" == "YES" ]]; then
      ecflow_client --kill="${ECF_NAME:?}"
    fi

    if [[ -n "${PBS_JOBID}" ]]; then
      qdel "${PBS_JOBID}"
    elif [[ -n "${SLURM_JOB_ID}" ]]; then
      scancel "${SLURM_JOB_ID}"
    fi
}

# Place the postamble in a trap so it is always called no matter how the script exits
# Shellcheck: Turn off warning about substitions at runtime instead of signal time
# shellcheck disable=SC2064
trap "postamble ${_calling_script} ${start_time} \$?" EXIT
# shellcheck disable=

# Load environment defaults for EE2 compliance
if [[ -f "${HOMEgfs}/ush/env_defaults.sh" ]]; then
    source "${HOMEgfs}/ush/env_defaults.sh"
fi

# Load environment validation functions for EE2 compliance
if [[ -f "${HOMEgfs}/ush/validate_environment.sh" ]]; then
    source "${HOMEgfs}/ush/validate_environment.sh"
fi

source "${HOMEgfs}/ush/bash_utils.sh"

# Standardized error handling functions for EE2 compliance
error_exit() {
    local msg="$1"
    local code="${2:-1}"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "FATAL ERROR [${timestamp}]: ${msg}" >&2
    export err=${code}
    err_exit "${msg}"
}

warning_msg() {
    local msg="$1"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "WARNING [${timestamp}]: ${msg}" >&2
}

info_msg() {
    local msg="$1"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "INFO [${timestamp}]: ${msg}"
}

# Enhanced error checking with context
err_chk_with_context() {
    local context="$1"
    if [[ ${err} -ne 0 ]]; then
        error_exit "${context}: Command failed with exit code ${err}"
    fi
}

# Enhanced compath.py integration function
setup_data_paths() {
    local component="${1:-atmos}"
    
    # Use compath.py for standardized path construction if available
    if [[ -x "${HOMEgfs}/ush/compath.py" ]]; then
        local comin_result
        local comout_result
        comin_result=$(python3 "${HOMEgfs}/ush/compath.py" "${NET}" "${RUN}" "${PDY}" "${cyc}" --component="${component}")
        comout_result=$(python3 "${HOMEgfs}/ush/compath.py" "${NET}" "${RUN}" "${PDY}" "${cyc}" --component="${component}" --output)
        export COMIN="${comin_result}"
        export COMOUT="${comout_result}"
    else
        # Fallback to manual construction
        export COMIN="${ROTDIR}/${RUN}.${PDY}/${cyc}/${component}"
        export COMOUT="${ROTDIR}/${RUN}.${PDY}/${cyc}/${component}"
    fi
    
    # Create output directories
    mkdir -p "${COMOUT}"
}

# Standardized module loading function
load_required_modules() {
    local machine_id="${MACHINE_ID:-$(detect_machine.sh)}"
    
    # Clear existing modules
    module purge
    
    # Load standard environment
    module use "${HOMEgfs}/modulefiles"
    
    if [[ -f "${HOMEgfs}/modulefiles/module_gwsetup.${machine_id}" ]]; then
        module load "module_gwsetup.${machine_id}"
    else
        warning_msg "Module file not found for machine: ${machine_id}"
        return 1
    fi
    
    # Log loaded modules for debugging
    info_msg "Loaded modules:"
    { module list 2>&1 | head -10; } || true
}

# Turn on our settings
export SHELLOPTS
declare -xf set_strict
declare -xf set_trace
declare -xf postamble
declare -xf err_exit
declare -xf error_exit
declare -xf warning_msg
declare -xf info_msg
declare -xf err_chk_with_context
declare -xf setup_data_paths
declare -xf load_required_modules
set_strict
set_trace
