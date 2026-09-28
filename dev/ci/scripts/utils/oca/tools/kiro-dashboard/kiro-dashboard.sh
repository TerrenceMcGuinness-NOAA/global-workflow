#!/usr/bin/env bash
# Kiro dashboard launcher. Resolves a Python 3.10+ interpreter that can import
# the five runtime libraries, then execs cli.py with every argument passed
# through unchanged.
#
# Usage:
#   ./kiro-dashboard.sh [--sync] [--cloudtrail] [--since YYYY-MM-DD]
#                       [--output PATH] [--open]
#   ./kiro-dashboard.sh --print-python      # print resolved path, exit 0
#
#   KIRO_DASHBOARD_PYTHON=/path/to/python   # override: sole candidate
#
# Interpreter resolution is PATH-only: the candidate names python3.12,
# python3.11, python3 are probed in that order via `command -v`. Nothing here
# activates an environment module system, a Spack tree, or any other platform's
# toolchain, and no absolute interpreter path is hard-coded. Exit 3 when no
# eligible interpreter is found; stdout stays empty in that case.
#
# Deliberately uses only bash builtins (cd, pwd, printf, command) so the
# launcher still produces its diagnostic when PATH holds no external binaries.

set -euo pipefail

script_path="${BASH_SOURCE[0]}"
script_dir="${script_path%/*}"
if [[ "${script_dir}" == "${script_path}" ]]; then
  script_dir="."
fi
script_dir="$(cd "${script_dir}" && pwd)"

candidates=(python3.12 python3.11 python3)
requirements_path="tools/kiro-dashboard/requirements.txt"

# Probe program: prints "<major.minor.micro>|<comma-separated missing modules>".
# A version below 3.10 reports the sentinel module name "python<3.10" so the
# caller can treat "too old" and "libraries absent" through one code path.
probe_source='
import importlib.util
import sys

version = "%d.%d.%d" % sys.version_info[:3]
modules = ("pandas", "numpy", "plotly", "jinja2", "boto3")
if sys.version_info < (3, 10):
  missing = ["python<3.10"]
else:
  missing = [name for name in modules if importlib.util.find_spec(name) is None]
sys.stdout.write("%s|%s" % (version, ",".join(missing)))
'

probe_version=""
probe_missing=""

# _probe <python-path> -> rc 0 when eligible; sets probe_version/probe_missing.
_probe() {
  local python_path="$1"
  local output=""
  probe_version="unknown"
  probe_missing="interpreter did not run"
  if ! output="$("${python_path}" -c "${probe_source}" 2>/dev/null)"; then
    return 1
  fi
  if [[ "${output}" != *"|"* ]]; then
    return 1
  fi
  probe_version="${output%%|*}"
  probe_missing="${output#*|}"
  [[ -z "${probe_missing}" ]]
}

# _minor_of <version> -> the minor component, or -1 when unparseable.
_minor_of() {
  local version="$1"
  local major="${version%%.*}"
  local rest="${version#*.}"
  local minor="${rest%%.*}"
  if [[ "${major}" =~ ^[0-9]+$ ]] && [[ "${minor}" =~ ^[0-9]+$ ]]; then
    if [[ "${major}" -lt 3 ]]; then
      printf '%s\n' "-1"
    else
      printf '%s\n' "${minor}"
    fi
  else
    printf '%s\n' "-1"
  fi
}

override_used=0
if [[ -n "${KIRO_DASHBOARD_PYTHON:-}" ]]; then
  # An explicit override has no fallback probe: a wrong value must be reported,
  # not silently replaced by a working interpreter (cron misconfiguration).
  candidates=("${KIRO_DASHBOARD_PYTHON}")
  override_used=1
fi

resolved=""
report=()
found_any=0
best_name=""
best_minor=-1

for name in "${candidates[@]}"; do
  if [[ "${override_used}" -eq 1 && -x "${name}" ]]; then
    path="${name}"
  else
    path="$(command -v "${name}" 2>/dev/null || true)"
  fi
  if [[ -z "${path}" ]]; then
    report+=("[ERROR] candidate ${name}: not found on PATH")
    continue
  fi
  found_any=1
  if _probe "${path}"; then
    resolved="${path}"
    break
  fi
  report+=("[ERROR] candidate ${name}: found at ${path}, version ${probe_version}, unusable modules: ${probe_missing}")
  minor="$(_minor_of "${probe_version}")"
  if [[ "${minor}" -ge 10 && "${minor}" -gt "${best_minor}" ]]; then
    best_minor="${minor}"
    best_name="${path}"
  fi
done

if [[ -z "${resolved}" ]]; then
  printf '%s\n' "${report[@]}" >&2
  if [[ "${found_any}" -eq 1 && -n "${best_name}" ]]; then
    printf '%s\n' "[ERROR] install the dashboard libraries with: ${best_name} -m pip install --user -r ${requirements_path}" >&2
  else
    printf '%s\n' "[ERROR] install a Python 3.10 or newer interpreter with the dashboard libraries, or set KIRO_DASHBOARD_PYTHON to the path of one" >&2
  fi
  exit 3
fi

if [[ $# -eq 1 && "$1" == "--print-python" ]]; then
  printf '%s\n' "${resolved}"
  exit 0
fi

exec "${resolved}" "${script_dir}/cli.py" "$@"
