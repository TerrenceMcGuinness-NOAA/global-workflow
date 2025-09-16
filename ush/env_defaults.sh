#!/usr/bin/env bash

########################################################################
# Enhanced Environment Variable Defaults for EE2 Compliance
# 
# This script provides standardized default fallback values for
# environment variables used throughout the global workflow system
# to ensure 100% EE2 compliance with NOAA standards.
#
# Usage: source "${HOMEgfs}/ush/env_defaults.sh"
########################################################################

# Enhanced environment variable defaults - Core paths
export DATAROOT="${DATAROOT:-${STMP:-/tmp}/RUNDIRS}"
export GESIN="${GESIN:-${GESROOT:-}/${envir}}"
export GESOUT="${GESOUT:-${GESROOT:-}/${envir}}"
export COMIN="${COMIN:-${ROTDIR:-}/${RUN}.${PDY}/${cyc}}"
export COMOUT="${COMOUT:-${ROTDIR:-}/${RUN}.${PDY}/${cyc}}"

# Model-specific defaults
export USHmodel="${USHmodel:-${HOMEgfs}/ush}"
export EXECmodel="${EXECmodel:-${HOMEgfs}/exec}"
export PARMmodel="${PARMmodel:-${HOMEgfs}/parm}"
export FIXmodel="${FIXmodel:-${HOMEgfs}/fix}"

# Operational defaults
export envir="${envir:-prod}"
export NET="${NET:-gfs}"
export RUN="${RUN:-gfs}"

# Additional standard defaults for EE2 compliance
export SENDECF="${SENDECF:-NO}"
export SENDDBN="${SENDDBN:-NO}"
export SENDMAIL="${SENDMAIL:-NO}"
export VERBOSE="${VERBOSE:-YES}"
export KEEPDATA="${KEEPDATA:-NO}"

# Job control defaults
export TRACE="${TRACE:-YES}"
export STRICT="${STRICT:-YES}"

# Ensure critical directories exist if variables are set
if [[ -n "${DATAROOT:-}" && ! -d "${DATAROOT}" ]]; then
    mkdir -p "${DATAROOT}" 2>/dev/null || true
fi

if [[ -n "${GESROOT:-}" && ! -d "${GESROOT}" ]]; then
    mkdir -p "${GESROOT}" 2>/dev/null || true
fi