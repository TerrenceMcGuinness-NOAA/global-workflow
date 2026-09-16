#!/usr/bin/env bash
# Starts a `pw sessions connect` tunnel from THIS host (an on-prem RDHPCS PW
# cluster) to the shared MCP gateway running on the oca-rocky9-mcp-v2 session
# in PW project 'ca-infa-mdc'. After this script exits successfully the local
# TCP endpoint http://localhost:${PORT}/mcp forwards to the MCP gateway on the
# session VM, so VS Code's eib-mcp-gateway-local MCP server can connect.
#
# Ownership model (READ THIS if you are NOT Terry.McGuinness):
#   * The MCP session VM (oca-rocky9-mcp-v2) is owned by Terry.McGuinness under
#     project 'ca-infa-mdc'. There is ONE MCP gateway; every user tunnels into
#     the same backend, which is fine (HTTP fan-in, no redundancy problem).
#   * PW tunnel sessions are per-user objects. `pw sessions ls` only lists
#     sessions YOU own, so as a collaborator you will not see
#     oca-rocky9-mcp-v2 in your list. You must pass the fully-qualified name:
#         SESSION=Terry.McGuinness/oca-rocky9-mcp-v2 bash start_mcp_tunnel.sh
#     If PW rejects the connect (not authorized), ask Terry to share the
#     session with your PW user, or create your own tunnel session against
#     the same MCP cluster and pass its bare name via SESSION=...
#
# Env overrides (all optional):
#   SESSION          bare or owner/session name (default: oca-rocky9-mcp-v2)
#   PORT             local TCP port to bind (default: 18888)
#   PW               path to the pw CLI (default: $HOME/pw/pw)
#   PW_API_KEY_FILE  file containing a PW API key. If your pw CLI is already
#                    authenticated (`pw auth whoami` works), leave this unset.
#   LOGFILE          pw connect log (default: /tmp/pw_session_connect_$USER_$PORT.log)
#
# References:
#   Ports / self-hosting:      https://parallelworks.com/docs/self-hosting/ports
#   pw CLI auth:               https://parallelworks.com/docs/cli#authentication
#   `pw sessions connect ...`  -> creates an SSH port-forward from THIS host to
#                                 the tunnel session's remote host:port on the
#                                 PW-managed session VM.
#   `pw endpoints http PORT`   -> alternative that dials OUT from the app host
#                                 (no inbound SSH needed). Use this on the PW
#                                 session host if this host cannot SSH to it.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PW=${PW:-$HOME/pw/pw}
PORT=${PORT:-18888}
# SESSION can be a bare name (only resolvable if YOU own it) or an owner-qualified
# name like 'Terry.McGuinness/oca-rocky9-mcp-v2' when connecting as a collaborator
# in project 'ca-infa-mdc'. Override via env:
#     SESSION=Terry.McGuinness/oca-rocky9-mcp-v2 ./start_mcp_tunnel.sh
SESSION=${SESSION:-oca-rocky9-mcp-v2}
# Per-user, per-port log so multiple users on a shared login node don't clobber each other.
LOGFILE=${LOGFILE:-/tmp/pw_session_connect_${USER}_${PORT}.log}
# API key file:
#   * Default keeps Terry's original layout (.vscode/pw_api_key.txt) working.
#   * Collaborators whose on-prem RDHPCS PW cluster is already authenticated
#     (`pw auth whoami` works) can leave PW_API_KEY_FILE unset and this file
#     absent; the script will just rely on the existing pw context.
API_KEY_FILE="${PW_API_KEY_FILE:-${SCRIPT_DIR}/pw_api_key.txt}"

# --- 1. Load PW API key (so `pw` works non-interactively / from cron etc.) ---
# The file lives under .vscode/ which is gitignored. Keep it chmod 600.
if [[ -f "${API_KEY_FILE}" ]]; then
  # Enforce restrictive perms; warn (don't fail) if we cannot.
  chmod 600 "${API_KEY_FILE}" 2>/dev/null || true
  key_contents=$(tr -d '[:space:]' < "${API_KEY_FILE}")
  if [[ -n "${key_contents}" ]]; then
    export PW_API_KEY="${key_contents}"
    echo "Loaded PW_API_KEY from ${API_KEY_FILE} (${#key_contents} chars)."
  else
    echo "NOTE: ${API_KEY_FILE} is empty; relying on existing pw context."
  fi
else
  echo "NOTE: no ${API_KEY_FILE}; relying on existing pw context."
fi

# --- 2. Sanity-check the PW CLI and auth ---
if [[ ! -x "${PW}" ]]; then
  echo "ERROR: pw CLI not found or not executable at ${PW}"
  exit 1
fi

if ! whoami_out=$("${PW}" auth whoami 2>&1); then
  echo "ERROR: 'pw auth whoami' failed. Auth is not valid."
  echo "${whoami_out}"
  echo "Fix: put a valid API key in ${API_KEY_FILE} or run 'pw auth' interactively."
  exit 1
fi
echo "Authenticated to PW as: ${whoami_out}"

# --- 3. Confirm the tunnel session exists and is running on the platform ---
# NOTE: `pw sessions ls` only lists sessions the CURRENT pw user owns. If you
# are a collaborator in project 'ca-infa-mdc' trying to connect to Terry's
# oca-rocky9-mcp-v2 session, the session will NOT appear here. In that case we
# warn and proceed; `pw sessions connect` will fail cleanly if you are not
# authorized to attach.
if ! sess_line=$("${PW}" sessions ls 2>/dev/null | awk -v s="${SESSION}" 'index($1, s) {print; exit}'); then
  sess_line=""
fi
if [[ -z "${sess_line}" ]]; then
  echo "WARN: session '${SESSION}' is not visible in your 'pw sessions ls' output."
  echo "      This is expected if you do not own the session (e.g. you are a"
  echo "      collaborator in project 'ca-infa-mdc' connecting to Terry's MCP host)."
  echo "      Proceeding with 'pw sessions connect ${SESSION}'; if PW rejects the"
  echo "      connect, ask the session owner to share it or create your own tunnel"
  echo "      session against the same MCP cluster and re-run with SESSION=<name>."
else
  sess_status=$(awk '{print $2}' <<< "${sess_line}")
  echo "PW session status: ${sess_status}  (${sess_line})"
  if [[ "${sess_status}" != "running" ]]; then
    echo "ERROR: session '${SESSION}' is not 'running' (status=${sess_status})."
    echo "Start it in the PW UI, then re-run this script."
    exit 1
  fi
fi

# --- 4. Kill any prior local forward on this port ---
# Scope the pgrep to THIS user so we never signal another user's tunnel that
# happens to reference the same shared SESSION name on a multi-user login node.
existing=$(pgrep -u "${USER}" -f "pw.*sessions.*connect.*${SESSION}" 2>/dev/null || true)
if [[ -n "${existing}" ]]; then
  echo "Stopping existing pw tunnel(s) owned by ${USER}: ${existing}"
  kill ${existing} 2>/dev/null || true
  sleep 1
fi

echo "Connecting to PW session '${SESSION}' on local port ${PORT}..."
nohup "${PW}" sessions connect "${SESSION}" --port "${PORT}" \
  > "${LOGFILE}" 2>&1 &
TUNNEL_PID=$!
echo "Tunnel PID: ${TUNNEL_PID}   log: ${LOGFILE}"

# Wait for the local listener to appear AND for the backend to actually respond.
# The pw listener binds immediately, but if the underlying SSH tunnel to the
# remote host cannot be established, curl will hang -> VS Code sees
# "Failed to fetch" when starting the MCP server. So we probe end-to-end.
listener_ready=0
for i in $(seq 1 15); do
  if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
    listener_ready=1
    break
  fi
  sleep 1
done

if [[ "${listener_ready}" -ne 1 ]]; then
  echo "ERROR: Port ${PORT} not listening after 15s. Check ${LOGFILE}"
  exit 1
fi

echo "Local listener up. Probing MCP backend through the tunnel..."
for i in $(seq 1 20); do
  code=$(curl -sS -o /dev/null -m 3 -w '%{http_code}' \
    -H 'Authorization: Bearer eib-mcp-gateway-token-2025' \
    "http://localhost:${PORT}/mcp" 2>/dev/null)
  curl_rc=$?
  # A real HTTP response (2xx/3xx/4xx/5xx) means the SSH tunnel + gateway are alive.
  # curl_rc==0 AND code is a 3-digit non-000 value.
  if [[ ${curl_rc} -eq 0 && "${code}" =~ ^[1-9][0-9]{2}$ ]]; then
    echo "Tunnel + MCP backend OK (HTTP ${code}) -> http://localhost:${PORT}/mcp"
    exit 0
  fi
  # If pw itself is already reporting an SSH connect failure, don't wait the full loop.
  if grep -q "Failed to establish SSH connection" "${LOGFILE}" 2>/dev/null; then
    break
  fi
  sleep 2
done

echo
echo "ERROR: Listener on localhost:${PORT} is up, but the MCP backend is not reachable."
echo "----- last 20 lines of ${LOGFILE} -----"
tail -n 20 "${LOGFILE}"
echo "---------------------------------------"
echo
bad_ip=$(grep -oE 'dial tcp [0-9.]+:[0-9]+' "${LOGFILE}" 2>/dev/null | tail -1 | awk '{print $3}')
if [[ -n "${bad_ip}" ]]; then
  echo "Diagnosis: 'pw sessions connect' cannot SSH to the tunnel's remote host (${bad_ip})."
else
  echo "Diagnosis: pw's local listener is up but no backend responded within the probe window."
  echo "           (An SSH-connect timeout to the remote host takes ~2min to surface in the log."
  echo "            Re-run this script or tail ${LOGFILE} to see it.)"
fi
echo
echo "Most likely causes:"
echo "  1. The PW session host (the VM behind '${SESSION}') is stopped or has a"
echo "     new public IP. PW's control plane can still show 'running' while the"
echo "     underlying VM is dark."
echo "     -> Stop and re-create the session so its IP is re-resolved:"
echo "          ${PW} sessions stop ${SESSION}"
echo "          # then re-create it from the PW UI (or:"
echo "          #   ${PW} sessions create --type tunnel --remote-port ${PORT} \\"
echo "          #       --name ${SESSION} <cluster>)"
echo "        then re-run this script."
echo "  2. Outbound tcp/22 from this host is blocked to the session-host IP."
echo "     -> Quick test:  timeout 5 bash -c '</dev/tcp/github.com/22' && echo OK"
echo "        If even github.com:22 is blocked from here, this host cannot host the"
echo "        tunnel client at all."
echo
echo "Alternative (recommended when SSH from this host to the PW session host is blocked):"
echo "  Instead of a 'tunnel' session, run 'pw endpoints http ${PORT}' ON the PW"
echo "  session host, next to the MCP gateway. It dials OUT to the PW platform"
echo "  and gives you a URL like https://<name>.noaa.parallel.works. Point the"
echo "  eib-mcp-gateway-ms server in .vscode/mdp.json at that URL. No inbound SSH"
echo "  from this host is required in that mode."
echo "  Docs: https://parallelworks.com/docs/self-hosting/ports"
exit 2
