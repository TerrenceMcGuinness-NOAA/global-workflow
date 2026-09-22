#!/usr/bin/env bash
#
# aws-mfa-session.sh
#
# Mint a 12-hour MFA-backed STS session and write it into the [mfa] profile
# of ~/.aws/credentials, replacing whatever was there before.
#
# Usage:
#   tools/aws-mfa-session.sh            # prompts for the 6-digit code
#   tools/aws-mfa-session.sh 123456     # non-interactive (lands in shell history)
#   tools/aws-mfa-session.sh --check    # verify the current session, mint nothing
#
# Overrides (env):
#   AWS_MFA_SERIAL     MFA device ARN
#   AWS_SOURCE_PROFILE long-lived credentials used to call STS (default: default)
#   AWS_MFA_PROFILE    profile section to write   (default: mfa)
#   AWS_MFA_DURATION   session lifetime seconds   (default: 43200 = 12h)
#   AWS_CREDENTIALS    credentials file path      (default: ~/.aws/credentials)
#   SKIP_MODEL_CHECK=1 skip the Bedrock model-access confirmation step

set -euo pipefail

MFA_SERIAL="${AWS_MFA_SERIAL:-arn:aws:iam::903050880929:mfa/awseibgoogleauth}"
SOURCE_PROFILE="${AWS_SOURCE_PROFILE:-default}"
TARGET_PROFILE="${AWS_MFA_PROFILE:-mfa}"
DURATION="${AWS_MFA_DURATION:-43200}"
CREDENTIALS_FILE="${AWS_CREDENTIALS:-${HOME}/.aws/credentials}"

# ── Bedrock model access table (SPOT) ──────────────────────────────────────
# The confirmation step at the end probes each row with
#   aws bedrock list-foundation-model-agreement-offers --model-id <MODEL ID>
# Edit this table to change what gets checked. Format: MODEL ID|DESCRIPTION
#
# | MODEL ID                     | DESCRIPTION                              |
# |------------------------------|------------------------------------------|
# | anthropic.claude-opus-4-7    | Claude Opus 4.7 — primary agent model    |
BEDROCK_MODELS=(
  "anthropic.claude-opus-4-7|Claude Opus 4.7 — primary agent model"
)

command -v aws >/dev/null 2>&1 || { echo "[ERROR] aws CLI not found on PATH"; exit 1; }

check_only=0
token_code=""
case "${1:-}" in
  --check|-c|check) check_only=1 ;;
  --help|-h)
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  *) token_code="${1:-}" ;;
esac

region_source_profile="${SOURCE_PROFILE}"
[[ "${check_only}" -eq 1 ]] && region_source_profile="${TARGET_PROFILE}"
region="$(aws configure get region --profile "${region_source_profile}" 2>/dev/null || true)"
region="${AWS_REGION:-${region:-us-east-1}}"

if [[ "${check_only}" -eq 1 ]]; then
  echo "[INFO] Check-only mode — no new MFA session will be minted"
  recorded_expiry="$(awk -v target="[${TARGET_PROFILE}]" '
    /^[[:space:]]*\[/ { in_target = ($0 == target) }
    in_target && /^# expires / { sub(/^# expires /, ""); print; exit }
  ' "${CREDENTIALS_FILE}" 2>/dev/null || true)"
  [[ -n "${recorded_expiry}" ]] && echo "[INFO] Recorded expiry: ${recorded_expiry}"
else
  if [[ -z "${token_code}" ]]; then
    # Prompted rather than argv by default so the code stays out of shell history.
    read -r -p "MFA code for ${MFA_SERIAL}: " token_code
  fi

  if [[ ! "${token_code}" =~ ^[0-9]{6}$ ]]; then
    echo "[ERROR] MFA code must be exactly 6 digits"
    exit 1
  fi

  echo "[INFO] Requesting session token (profile=${SOURCE_PROFILE}, duration=${DURATION}s)"
  sts_output="$(aws sts get-session-token \
    --profile "${SOURCE_PROFILE}" \
    --serial-number "${MFA_SERIAL}" \
    --token-code "${token_code}" \
    --duration-seconds "${DURATION}" \
    --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken,Expiration]' \
    --output text)" || {
    echo "[ERROR] aws sts get-session-token failed"
    exit 1
  }

  IFS=$'\t' read -r access_key secret_key session_token expiration <<<"${sts_output}"

  if [[ -z "${access_key}" || -z "${secret_key}" || -z "${session_token}" ]]; then
    echo "[ERROR] STS response missing credential fields"
    exit 1
  fi

  mkdir -p "$(dirname "${CREDENTIALS_FILE}")"
  touch "${CREDENTIALS_FILE}"
  cp -p "${CREDENTIALS_FILE}" "${CREDENTIALS_FILE}.bak"

  umask 077
  tmp_file="$(mktemp "${CREDENTIALS_FILE}.XXXXXX")"
  trap 'rm -f "${tmp_file}"' EXIT

  # Copy every section except the target profile, then append the fresh block.
  awk -v target="[${TARGET_PROFILE}]" '
    /^[[:space:]]*\[/ { skip = ($0 ~ "^[[:space:]]*\\[" substr(target, 2, length(target) - 2) "\\][[:space:]]*$") }
    !skip { print }
  ' "${CREDENTIALS_FILE}" >"${tmp_file}"

  # Collapse trailing blank lines so the appended block is not orphaned.
  printf '%s\n' "$(cat "${tmp_file}")" >"${tmp_file}.trimmed"
  mv "${tmp_file}.trimmed" "${tmp_file}"

  {
    echo ""
    echo "[${TARGET_PROFILE}]"
    echo "aws_access_key_id = ${access_key}"
    echo "aws_secret_access_key = ${secret_key}"
    echo "aws_session_token = ${session_token}"
    echo "region = ${region}"
    echo "# expires ${expiration}"
  } >>"${tmp_file}"

  chmod 600 "${tmp_file}"
  mv "${tmp_file}" "${CREDENTIALS_FILE}"
  trap - EXIT

  echo "[OK] Wrote [${TARGET_PROFILE}] to ${CREDENTIALS_FILE} (backup: ${CREDENTIALS_FILE}.bak)"
  echo "[OK] Session expires ${expiration}"
fi

echo "[INFO] Verifying caller identity..."
if ! aws sts get-caller-identity --profile "${TARGET_PROFILE}" --output text; then
  echo "[ERROR] [${TARGET_PROFILE}] session is invalid or expired — re-run without --check to refresh"
  exit 1
fi

if [[ "${SKIP_MODEL_CHECK:-0}" == "1" ]]; then
  exit 0
fi

echo "[INFO] Confirming Bedrock model access (region=${region})"
model_failures=0
for row in "${BEDROCK_MODELS[@]}"; do
  model_id="${row%%|*}"
  model_desc="${row#*|}"
  if offers="$(AWS_PROFILE="${TARGET_PROFILE}" aws bedrock list-foundation-model-agreement-offers \
      --model-id "${model_id}" \
      --region "${region}" \
      --query 'offers[].offerId' \
      --output text 2>&1)" && [[ -n "${offers}" && "${offers}" != "None" ]]; then
    echo "[OK]    ${model_id} — ${model_desc} (offers: ${offers})"
  else
    echo "[WARN]  ${model_id} — ${model_desc} (no offer returned)"
    model_failures=$((model_failures + 1))
  fi
done

if [[ "${model_failures}" -gt 0 ]]; then
  echo "[WARN] ${model_failures} of ${#BEDROCK_MODELS[@]} model(s) returned no offer — session is still valid"
fi
