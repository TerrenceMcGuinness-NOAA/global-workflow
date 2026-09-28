#!/usr/bin/env bash
#
# One-shot COTS graph import for the 20260926 Neptune export.
# Run on the PW COTS host where Neo4j runs in Docker.
#
# Usage:
#   cd ~/eib-mcp-rag-server   # or wherever the repo lives on PW
#   git pull origin develop
#   bash scripts/run_cots_import_20260926.sh
#
set -euo pipefail

export S3_BUCKET="mdc-mcp-rag-snapshots-903050880929"
export S3_EXPORT_ID="20260926-000101-dd89534f"
export EXPECTED_NODES=610758
export EXPECTED_RELATIONSHIPS=12674556
export EXPECTED_FILES=395

SCRIPT="scripts/cots_graph_import.sh"

if [[ ! -f "${SCRIPT}" ]]; then
  echo "[ERROR] ${SCRIPT} not found. Are you in the repo root?" >&2
  exit 1
fi

echo "============================================================"
echo "  COTS Graph Import: export ${S3_EXPORT_ID}"
echo "  Nodes: ${EXPECTED_NODES}  Edges: ${EXPECTED_RELATIONSHIPS}"
echo "  S3: s3://${S3_BUCKET}/portable-export/dev/${S3_EXPORT_ID}/graph"
echo "============================================================"
echo ""

for step in preflight backup fetch convert gen-flags "import --force" verify; do
  echo ""
  echo ">>> Step: ${step}"
  echo "------------------------------------------------------------"
  # shellcheck disable=SC2086
  bash "${SCRIPT}" ${step}
  echo "[OK] ${step} completed"
  echo ""
done

echo "============================================================"
echo "  ALL DONE — graph imported and verified"
echo "============================================================"
