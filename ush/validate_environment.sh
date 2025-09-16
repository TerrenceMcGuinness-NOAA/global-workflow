#!/usr/bin/env bash

########################################################################
# Environment Validation for EE2 Compliance
#
# This script provides comprehensive validation of required environment
# variables and system state to ensure EE2 compliance with NOAA standards.
#
# Usage: source "${HOMEgfs}/ush/validate_environment.sh"
#        validate_ee2_environment
########################################################################

# Environment validation function
validate_ee2_environment() {
    local missing_vars=()
    local required_vars=(
        "HOMEgfs"
        "DATAROOT" 
        "DATA"
        "PDY"
        "cyc"
        "NET"
        "RUN"
        "envir"
        "job"
        "jobid"
    )
    
    info_msg "Starting EE2 environment validation"
    
    # Check required variables
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var}" ]]; then
            missing_vars+=("${var}")
        fi
    done
    
    # Report missing variables
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        error_exit "Missing required EE2 environment variables: ${missing_vars[*]}"
    fi
    
    # Validate directory paths
    if [[ ! -d "${HOMEgfs}" ]]; then
        error_exit "HOMEgfs directory does not exist: ${HOMEgfs}"
    fi
    
    if [[ ! -d "${DATAROOT}" ]]; then
        info_msg "Creating DATAROOT directory: ${DATAROOT}"
        mkdir -p "${DATAROOT}" || error_exit "Cannot create DATAROOT: ${DATAROOT}"
    fi
    
    # Validate critical workflow directories
    local critical_dirs=(
        "${HOMEgfs}/ush"
        "${HOMEgfs}/jobs"
        "${HOMEgfs}/scripts"
    )
    
    for dir in "${critical_dirs[@]}"; do
        if [[ ! -d "${dir}" ]]; then
            warning_msg "Critical directory missing: ${dir}"
        fi
    done
    
    # Validate date format (PDY should be YYYYMMDD)
    if [[ ! "${PDY}" =~ ^[0-9]{8}$ ]]; then
        error_exit "PDY format invalid. Expected YYYYMMDD, got: ${PDY}"
    fi
    
    # Validate cycle format (cyc should be HH)
    if [[ ! "${cyc}" =~ ^[0-9]{2}$ ]]; then
        error_exit "cyc format invalid. Expected HH, got: ${cyc}"
    fi
    
    # Validate environment type
    local valid_envirs=("prod" "para" "test" "dev")
    local envir_found=false
    for valid_envir in "${valid_envirs[@]}"; do
        if [[ "${envir}" == "${valid_envir}" ]]; then
            envir_found=true
            break
        fi
    done
    if [[ "${envir_found}" == "false" ]]; then
        warning_msg "Unusual envir value: ${envir}. Expected one of: ${valid_envirs[*]}"
    fi
    
    # Check for common required executables
    local required_commands=("python3" "module")
    local missing_commands=()
    
    for cmd in "${required_commands[@]}"; do
        if ! command -v "${cmd}" &> /dev/null; then
            missing_commands+=("${cmd}")
        fi
    done
    
    if [[ ${#missing_commands[@]} -gt 0 ]]; then
        warning_msg "Required commands not found in PATH: ${missing_commands[*]}"
    fi
    
    info_msg "EE2 environment validation passed successfully"
    
    # Log key environment information for debugging
    info_msg "Environment summary:"
    info_msg "  HOMEgfs: ${HOMEgfs}"
    info_msg "  DATAROOT: ${DATAROOT}"
    info_msg "  PDY: ${PDY}, cyc: ${cyc}"
    info_msg "  NET: ${NET}, RUN: ${RUN}"
    info_msg "  envir: ${envir}"
    info_msg "  job: ${job}, jobid: ${jobid}"
}

# Quick validation function for minimal checks
validate_ee2_minimal() {
    local critical_vars=("HOMEgfs" "PDY" "cyc" "RUN")
    
    for var in "${critical_vars[@]}"; do
        if [[ -z "${!var}" ]]; then
            error_exit "Critical EE2 variable not set: ${var}"
        fi
    done
    
    info_msg "EE2 minimal validation passed"
}

# Export functions for use in other scripts
declare -xf validate_ee2_environment
declare -xf validate_ee2_minimal