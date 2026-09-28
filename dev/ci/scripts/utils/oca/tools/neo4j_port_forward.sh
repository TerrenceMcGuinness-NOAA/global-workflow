#!/usr/bin/env bash
# Forward the Neo4j Browser and Bolt ports from a remote host to localhost.

set -u

usage() {
  cat <<'EOF'
Usage: neo4j_port_forward.sh [options] HOST_IP

Options:
  -u, --user USER       SSH user (default: $USER)
  -i, --identity FILE   RSA private key (default: ~/.ssh/id_rsa)
  -a, --auto-key        Generate/provision the RSA key when needed
  -l, --local-ui PORT   Local Browser port (default: 7474)
  -b, --local-bolt PORT Local Bolt port (default: 7687)
  --transport MODE  auto, pw, or ssh (default: auto)
  --pw-ui-session N  PW session for Browser port (default: neo4j-web-ui)
  --pw-bolt-session N PW session for Bolt port (default: neo4j-bolt)
  --foreground          Keep the forwards attached to this shell
  --stop                Stop forwards started in the background
  -h, --help            Show this help

Examples:
  neo4j_port_forward.sh 203.0.113.10
  neo4j_port_forward.sh --user terry --auto-key 203.0.113.10
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

runtime_dir="${XDG_RUNTIME_DIR:-${HOME}/.cache}/neo4j-port-forward"
pid_file="${runtime_dir}/tunnel.pid"
log_file="${runtime_dir}/tunnel.log"
foreground=0
managed=0
stop=0

is_managed_process() {
  local pid="$1"
  [[ -r "/proc/${pid}/cmdline" ]] &&
    tr '\0' '\n' < "/proc/${pid}/cmdline" | grep -Fxq -- --managed
}

stop_forward() {
  [[ -f "${pid_file}" ]] || { echo "No background port forwards are recorded."; return 0; }
  local pid
  pid="$(<"${pid_file}")"
  if [[ ! "${pid}" =~ ^[0-9]+$ ]] || ! kill -0 "${pid}" 2>/dev/null || ! is_managed_process "${pid}"; then
    rm -f "${pid_file}"
    echo "Removed stale port-forward state."
    return 0
  fi

  kill -TERM "${pid}" 2>/dev/null || true
  for _ in {1..50}; do
    [[ -f "${pid_file}" && "$(<"${pid_file}")" == "${pid}" ]] || {
      echo "Stopped background port forwards."
      return 0
    }
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.1
  done
  die "port-forward process ${pid} did not stop; see ${log_file}"
}

write_managed_pid() {
  [[ "${managed}" -eq 1 ]] || return 0
  mkdir -p "${runtime_dir}"
  chmod 700 "${runtime_dir}"
  printf '%s\n' "$$" > "${pid_file}"
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  [[ -n "${ui_pid:-}" ]] && kill "${ui_pid}" 2>/dev/null || true
  [[ -n "${bolt_pid:-}" ]] && kill "${bolt_pid}" 2>/dev/null || true
  [[ -n "${ssh_pid:-}" ]] && kill "${ssh_pid}" 2>/dev/null || true
  [[ -n "${ui_pid:-}" ]] && wait "${ui_pid}" 2>/dev/null || true
  [[ -n "${bolt_pid:-}" ]] && wait "${bolt_pid}" 2>/dev/null || true
  [[ -n "${ssh_pid:-}" ]] && wait "${ssh_pid}" 2>/dev/null || true
  [[ -n "${public_key:-}" ]] && rm -f "${public_key}"
  if [[ "${managed}" -eq 1 && -f "${pid_file}" && "$(<"${pid_file}")" == "$$" ]]; then
    rm -f "${pid_file}"
  fi
  exit "${status}"
}

start_background() {
  mkdir -p "${runtime_dir}"
  chmod 700 "${runtime_dir}"
  if [[ -f "${pid_file}" ]]; then
    local existing_pid
    existing_pid="$(<"${pid_file}")"
    if [[ "${existing_pid}" =~ ^[0-9]+$ ]] && kill -0 "${existing_pid}" 2>/dev/null && is_managed_process "${existing_pid}"; then
      die "background port forwards already running as PID ${existing_pid}; use --stop first"
    fi
    rm -f "${pid_file}"
  fi

  local child_args=(--user "${user}" --identity "${identity_file}"
    --local-ui "${local_ui_port}" --local-bolt "${local_bolt_port}"
    --transport "${transport}" --pw-ui-session "${pw_ui_session}"
    --pw-bolt-session "${pw_bolt_session}" "${host_ip}" --foreground --managed)
  nohup env NEO4J_PORT_FORWARD_PREPARED=1 "$0" "${child_args[@]}" \
    > "${log_file}" 2>&1 < /dev/null &
  local pid=$!

  for _ in {1..50}; do
    if [[ -f "${pid_file}" && "$(<"${pid_file}")" == "${pid}" ]]; then
      echo "Started background port forwards (PID ${pid})."
      echo "Browser: http://localhost:${local_ui_port}/browser/"
      echo "Bolt:    neo4j://localhost:${local_bolt_port}"
      echo "Log:     ${log_file}"
      echo "Stop:    $0 --stop"
      return 0
    fi
    if ! kill -0 "${pid}" 2>/dev/null; then
      [[ -f "${pid_file}" && "$(<"${pid_file}")" == "${pid}" ]] && rm -f "${pid_file}"
      tail -n 20 "${log_file}" >&2 2>/dev/null || true
      die "background port forwards failed to start"
    fi
    sleep 0.1
  done
  kill -TERM "${pid}" 2>/dev/null || true
  die "timed out waiting for background port forwards to start; see ${log_file}"
}

user="${USER}"
identity_file="${HOME}/.ssh/id_rsa"
auto_key=0
local_ui_port=7474
local_bolt_port=7687
transport=auto
pw_ui_session=neo4j-web-ui
pw_bolt_session=neo4j-bolt

while [[ $# -gt 0 ]]; do
  case "$1" in
    -u|--user)
      [[ $# -ge 2 ]] || die "${1} requires a value"
      user="$2"
      shift 2
      ;;
    -i|--identity)
      [[ $# -ge 2 ]] || die "${1} requires a value"
      identity_file="$2"
      shift 2
      ;;
    -a|--auto-key)
      auto_key=1
      shift
      ;;
    -l|--local-ui)
      [[ $# -ge 2 ]] || die "${1} requires a value"
      local_ui_port="$2"
      shift 2
      ;;
    -b|--local-bolt)
      [[ $# -ge 2 ]] || die "${1} requires a value"
      local_bolt_port="$2"
      shift 2
      ;;
    --transport)
      [[ $# -ge 2 ]] || die "${1} requires a value"
      transport="$2"
      shift 2
      ;;
    --pw-ui-session)
      [[ $# -ge 2 ]] || die "${1} requires a value"
      pw_ui_session="$2"
      shift 2
      ;;
    --pw-bolt-session)
      [[ $# -ge 2 ]] || die "${1} requires a value"
      pw_bolt_session="$2"
      shift 2
      ;;
    --foreground)
      foreground=1
      shift
      ;;
    --managed)
      managed=1
      shift
      ;;
    --stop)
      stop=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      [[ -z "${host_ip:-}" ]] || die "only one host IP is allowed"
      host_ip="$1"
      shift
      ;;
  esac
done

if [[ "${stop}" -eq 1 ]]; then
  stop_forward
  exit 0
fi

[[ -n "${host_ip:-}" ]] || { usage >&2; exit 2; }

case "${transport}" in
  auto)
    if command -v pw >/dev/null 2>&1; then
      transport=pw
    else
      transport=ssh
    fi
    ;;
  pw|ssh)
    ;;
  *)
    die "invalid transport '${transport}'; expected auto, pw, or ssh"
    ;;
esac

for port in "${local_ui_port}" "${local_bolt_port}"; do
  [[ "${port}" =~ ^[0-9]+$ ]] || die "invalid local port: ${port}"
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq ":${port}$"; then
    die "local port ${port} is already in use"
  fi
done

if [[ "${transport}" == "pw" ]]; then
  command -v pw >/dev/null 2>&1 || die "pw CLI is required for --transport pw"
  [[ "${auto_key}" -eq 0 ]] || die "--auto-key applies only to SSH transport"

  if [[ "${foreground}" -eq 0 ]]; then
    start_background
    exit $?
  fi

  write_managed_pid
  trap cleanup EXIT INT TERM

  echo "Using PW CLI sessions on this machine:"
  echo "Forwarding Browser: http://localhost:${local_ui_port}/browser/"
  echo "Forwarding Bolt:    neo4j://localhost:${local_bolt_port}"
  echo "Press Ctrl-C to stop both forwards."

  pw sessions connect "${pw_ui_session}" --port "${local_ui_port}" &
  ui_pid=$!
  pw sessions connect "${pw_bolt_session}" --port "${local_bolt_port}" &
  bolt_pid=$!
  wait "${ui_pid}" "${bolt_pid}"
  exit $?
fi

command -v ssh >/dev/null 2>&1 || die "ssh is required"
command -v ssh-keygen >/dev/null 2>&1 || die "ssh-keygen is required"

if [[ ! -f "${identity_file}" ]]; then
  if [[ "${auto_key}" -ne 1 ]]; then
    die "RSA key not found: ${identity_file}; rerun with --auto-key"
  fi
  mkdir -p "$(dirname "${identity_file}")"
  chmod 700 "$(dirname "${identity_file}")"
  echo "Generating RSA key: ${identity_file}"
  ssh-keygen -q -t rsa -b 4096 -f "${identity_file}" -N "" \
    -C "${user}@neo4j-port-forward"
fi

[[ -r "${identity_file}" ]] || die "RSA private key is not readable: ${identity_file}"
chmod 600 "${identity_file}" 2>/dev/null || true

# Parsing the key and deriving its public half catches truncated or mismatched keys.
public_key="$(mktemp)"
trap 'rm -f "${public_key}"' EXIT
if ! ssh-keygen -y -f "${identity_file}" > "${public_key}" 2>/dev/null; then
  die "invalid RSA private key: ${identity_file}"
fi
if ! ssh-keygen -lf "${identity_file}" >/dev/null 2>&1; then
  die "could not read RSA key fingerprint: ${identity_file}"
fi

if [[ "${auto_key}" -eq 1 && "${NEO4J_PORT_FORWARD_PREPARED:-0}" != "1" ]]; then
  command -v ssh-copy-id >/dev/null 2>&1 || die "ssh-copy-id is required for --auto-key"
  echo "Ensuring the RSA public key is authorized on ${user}@${host_ip}..."
  ssh-copy-id -i "${public_key}" "${user}@${host_ip}"
fi

if [[ "${foreground}" -eq 0 ]]; then
  start_background
  exit $?
fi

write_managed_pid
trap cleanup EXIT INT TERM

echo "Forwarding Browser: http://localhost:${local_ui_port}/browser/"
echo "Forwarding Bolt:    neo4j://localhost:${local_bolt_port}"
if [[ "${managed}" -eq 0 ]]; then
  echo "Press Ctrl-C to stop both forwards."
fi

ssh \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -i "${identity_file}" \
  -L "${local_ui_port}:127.0.0.1:7474" \
  -L "${local_bolt_port}:127.0.0.1:7687" \
  -N "${user}@${host_ip}" &
ssh_pid=$!
wait "${ssh_pid}"