#!/usr/bin/env bash
###############################################################################
# kiro-prompt.sh — Feed a prompt to kiro-cli with auto-selected model+effort
#
# Usage:
#   kiro-prompt.sh "Execute task 1 from .kiro/specs/foo/tasks.md"
#   kiro-prompt.sh --model claude-opus-4.6 --effort max "Do the thing"
#   kiro-prompt.sh --dry-run "Show me what would run"
#   echo "long prompt" | kiro-prompt.sh --stdin
#
# Model/effort selection (when not overridden):
#   The script classifies the prompt by complexity and picks a model+effort
#   tier that balances cost vs capability.  Override with --model / --effort.
#
# Yolo mode:
#   All runs use --trust-all-tools --no-interactive (yolo).  The script is
#   designed for batch/headless execution of well-defined SDD tasks where
#   human confirmation on every tool call would defeat the purpose.
###############################################################################
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
MODEL=""
EFFORT=""
DRY_RUN=false
USE_STDIN=false
V3=false
EXTRA_ARGS=()
PROMPT=""

# ── Parse flags ──────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)    MODEL="$2";  shift 2 ;;
    --effort)   EFFORT="$2"; shift 2 ;;
    --dry-run)  DRY_RUN=true; shift ;;
    --stdin)    USE_STDIN=true; shift ;;
    --v3)       V3=true; shift ;;
    --)         shift; break ;;
    --*)        EXTRA_ARGS+=("$1"); shift ;;
    *)          break ;;
  esac
done

# Remaining args are the prompt
if [[ "${USE_STDIN}" == true ]]; then
  PROMPT="$(cat)"
elif [[ $# -gt 0 ]]; then
  PROMPT="$*"
fi

if [[ -z "${PROMPT}" ]]; then
  echo "Usage: kiro-prompt.sh [--model MODEL] [--effort EFFORT] [--dry-run] [--stdin] PROMPT..." >&2
  echo "" >&2
  echo "Or pipe a prompt:  echo 'do the thing' | kiro-prompt.sh --stdin" >&2
  exit 1
fi

# ── Auto-select model + effort based on prompt complexity ────────────────────
#
# Tier 1 (quick): simple reads, checks, single-file edits
#   → sonnet-4.6 / medium effort — fast, cheap, good enough
#
# Tier 2 (standard): multi-step tasks, spec execution, code changes + tests
#   → opus-4.6 / high effort — the workhorse
#
# Tier 3 (heavy): multi-file refactors, architecture, complex debugging
#   → opus-4.6 / max effort — full power
#
# Heuristics: keyword density in the prompt.

auto_select_tier() {
  local prompt_lower
  prompt_lower="$(echo "${PROMPT}" | tr '[:upper:]' '[:lower:]')"
  local word_count
  word_count="$(echo "${PROMPT}" | wc -w | tr -d ' ')"

  # ── Tier 3 signals (heavy) ──
  # Multi-phase, architecture, refactor, deploy, multiple tasks in parallel
  local tier3_patterns=(
    "execute all tasks"
    "refactor"
    "architecture"
    "deploy.*image"
    "rebuild.*container"
    "multi.*file"
    "phase [0-9].*phase [0-9]"
    "tasks.*parallel"
    "autonomously"
    "end.to.end"
  )
  for pat in "${tier3_patterns[@]}"; do
    if echo "${prompt_lower}" | grep -qE "${pat}"; then
      echo "heavy"
      return
    fi
  done

  # Long prompts (>150 words) are likely complex
  if [[ "${word_count}" -gt 150 ]]; then
    echo "heavy"
    return
  fi

  # ── Tier 1 signals (quick) ──
  # Simple reads, checks, verifications, short queries
  local tier1_patterns=(
    "^read "
    "^show "
    "^list "
    "^check "
    "^verify "
    "^what is"
    "^how do"
    "^explain "
    "^search "
    "^find "
    "^grep "
    "^run.*test"
    "^run.*pytest"
    "mark.*complete"
  )
  for pat in "${tier1_patterns[@]}"; do
    if echo "${prompt_lower}" | grep -qE "${pat}"; then
      echo "quick"
      return
    fi
  done

  # Short prompts (<30 words) without heavy signals → quick
  if [[ "${word_count}" -lt 30 ]]; then
    echo "quick"
    return
  fi

  # ── Default: Tier 2 (standard) ──
  echo "standard"
}

if [[ -z "${MODEL}" || -z "${EFFORT}" ]]; then
  TIER="$(auto_select_tier)"

  case "${TIER}" in
    quick)
      [[ -z "${MODEL}" ]]  && MODEL="claude-sonnet-4.6"
      [[ -z "${EFFORT}" ]] && EFFORT="medium"
      ;;
    standard)
      [[ -z "${MODEL}" ]]  && MODEL="claude-opus-4.6"
      [[ -z "${EFFORT}" ]] && EFFORT="high"
      ;;
    heavy)
      [[ -z "${MODEL}" ]]  && MODEL="claude-opus-4.6"
      [[ -z "${EFFORT}" ]] && EFFORT="max"
      ;;
  esac
else
  TIER="manual"
fi

# ── Build the command ────────────────────────────────────────────────────────
CMD=(
  kiro-cli chat
  --model "${MODEL}"
  --effort "${EFFORT}"
  --trust-all-tools
  --no-interactive
)

if [[ "${V3}" == true ]]; then
  CMD+=(--v3)
fi

# Pass any extra flags through
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  CMD+=("${EXTRA_ARGS[@]}")
fi

# The prompt goes last as the positional argument
CMD+=("${PROMPT}")

# ── Execute or dry-run ───────────────────────────────────────────────────────
echo "┌─────────────────────────────────────────────────────────────" >&2
echo "│ kiro-prompt — ${TIER} tier" >&2
echo "│ Model:  ${MODEL}" >&2
echo "│ Effort: ${EFFORT}" >&2
echo "│ Yolo:   --trust-all-tools --no-interactive" >&2
if [[ ${#PROMPT} -gt 120 ]]; then
  echo "│ Prompt: ${PROMPT:0:120}..." >&2
else
  echo "│ Prompt: ${PROMPT}" >&2
fi
echo "└─────────────────────────────────────────────────────────────" >&2

if [[ "${DRY_RUN}" == true ]]; then
  echo "" >&2
  echo "[dry-run] Would execute:" >&2
  printf '  %s\n' "${CMD[@]}" >&2
  exit 0
fi

exec "${CMD[@]}"
