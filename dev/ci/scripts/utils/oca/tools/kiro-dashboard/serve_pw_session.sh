#!/usr/bin/env bash
# Serve the Kiro dashboard through Parallel Works as a browser-accessible URL.
#
# Uses `pw endpoints serve`, which runs its own static file server and dials out
# to register a reverse tunnel -- no inbound access, no VNC desktop, and no
# separate web server. The dashboard opens in a normal browser tab.
#
# Usage:
#   ./serve_pw_session.sh [--sync] [--cloudtrail] [--since YYYY-MM-DD]
#                         [--name NAME] [--subdomain LABEL] [--public] [--open]
#                         [--no-keep] [--output interactive|text]
#
# The session is kept on exit by default, so the URL survives Ctrl-C and stays
# usable by anyone you shared it with. Pass --no-keep to delete it on exit.
#
# A new session is owner-only. Others get "You do not have access to this
# session" until you share it with a group -- see the command printed below.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

session_name="kiro-dashboard"
share_group="ca-infra-mdc"
share_group_id="69f3c5564f578d0776757f39"
keep_session=1
sync_args=()
pw_args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sync)       sync_args+=("--sync"); shift ;;
    --cloudtrail) sync_args+=("--cloudtrail"); shift ;;
    --since)      sync_args+=("--since" "$2"); shift 2 ;;
    --name)       session_name="$2"; shift 2 ;;
    --subdomain)  pw_args+=("--subdomain" "$2"); shift 2 ;;
    --output)     pw_args+=("--output" "$2"); shift 2 ;;
    --public)     pw_args+=("--public"); shift ;;
    --open)       pw_args+=("--open"); shift ;;
    --keep)       keep_session=1; shift ;;
    --no-keep)    keep_session=0; shift ;;
    -h|--help)
      sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *)
      echo "[ERROR] unknown argument: $1" >&2
      exit 2 ;;
  esac
done

command -v pw >/dev/null 2>&1 || { echo "[ERROR] pw CLI not found on PATH" >&2; exit 1; }

(( keep_session )) && pw_args+=("--keep")

# Serve from a dedicated directory: pw serves the whole DIR, so pointing it at
# output/ or the tool root would also expose cache/, which holds raw prompt text.
serve_dir="${script_dir}/output/pw_session"
mkdir -p "${serve_dir}"

echo "[INFO] Rendering dashboard..." >&2
# Interpreter selection is the launcher's job, not this script's: the AWS host
# needs python3.12 and the Parallel Works host needs python3, and neither name
# may be hard-coded here. A launcher failure (exit 3) must abort before pw runs.
launcher_status=0
"${script_dir}/kiro-dashboard.sh" "${sync_args[@]}" \
  --output "${serve_dir}/index.html" >/dev/null || launcher_status=$?
if [[ "${launcher_status}" -ne 0 ]]; then
  echo "[ERROR] dashboard render failed (exit ${launcher_status}); not serving" >&2
  exit "${launcher_status}"
fi

echo "[INFO] Serving '${serve_dir}' as endpoint '${session_name}'..." >&2
if (( keep_session )); then
  echo "[INFO] Session is kept on exit; the URL stays live after Ctrl-C." >&2
  echo "[INFO] Delete it later with: pw endpoints delete ${session_name}" >&2
else
  echo "[WARN] --no-keep: the endpoint is deleted on exit and the URL dies." >&2
fi

echo "[WARN] A new session is OWNER-ONLY. Others get 'You do not have access" >&2
echo "[WARN] to this session' until you share it, even after logging in." >&2
echo "[WARN] Sharing is per-session, so re-run this after every restart:" >&2
echo "[WARN]" >&2
echo "[WARN]   pw api -X POST -F access=true -F groupId=${share_group_id} \\" >&2
echo "[WARN]     organizations/noaademo/users/${USER}/sessions/${session_name}/access" >&2
echo "[WARN]" >&2
echo "[WARN]   (${share_group}; verify with: pw api -q '.[] | select(.name==\"${session_name}\") | .shared' sessions)" >&2
echo "[WARN] Sharing grants 'run the workflow as you', so share narrowly." >&2
echo "[WARN] This dashboard shows per-person emails and usage - do not share" >&2
echo "[WARN] organization-wide." >&2

exec pw endpoints serve --name "${session_name}" "${pw_args[@]}" "${serve_dir}"
