#!/bin/bash
# ==========================================================================
# GitHub Integration Debugging Script for GitLab CI
# ==========================================================================
#
# This script provides comprehensive debugging for GitLab's GitHub integration
# features when running CI pipelines triggered from GitHub.
#
# Usage: ./debug_github_integration.sh
#
# This script will:
# 1. Check all GitLab CI variables related to GitHub integration
# 2. Test GitLab API endpoints for status updates
# 3. Verify GitHub integration configuration
# 4. Provide recommendations for fixing integration issues

set -euo pipefail

echo "======================================================================="
echo "GitLab GitHub Integration Debug Report - Triggered Pipeline Mode"
echo "Generated at: $(date)"
echo "GitLab Version: GitLab Enterprise Edition v18.2.6-ee"
echo "Setup: GitHub PR -> GitHub Action -> GitLab Trigger -> GitLab Pipeline"
echo "======================================================================="

# Function to safely print variable values
print_var() {
    local var_name="$1"
    local var_value="${!var_name:-'NOT SET'}"
    printf "%-40s: %s\n" "$var_name" "$var_value"
}

# Function to check if variable is set and not empty
is_set() {
    local var_name="$1"
    [[ -n "${!var_name:-}" ]]
}

echo ""
echo "=== Core CI Variables ==="
print_var "CI_COMMIT_SHA"
print_var "CI_COMMIT_SHORT_SHA"
print_var "CI_PIPELINE_ID"
print_var "CI_PIPELINE_SOURCE"
print_var "CI_PROJECT_ID"
print_var "CI_PROJECT_PATH"
print_var "CI_API_V4_URL"
print_var "CI_JOB_TOKEN"

echo ""
echo "=== Triggered Pipeline Variables ==="
print_var "GITHUB_COMMIT_SHA"
print_var "PR_NUMBER"
print_var "GW_REPO_URL"
print_var "PIPELINE_TYPE"
print_var "RUN_ON_MACHINES"

echo ""
echo "=== GitHub Integration Analysis (Triggered Pipeline Mode) ==="

# Check if this is a GitHub-triggered pipeline
if [[ "${CI_PIPELINE_SOURCE:-}" == "trigger" ]]; then
    echo "✓ Pipeline source is 'trigger' (correct for GitHub-triggered pipelines)"
else
    echo "❌ Pipeline source is '${CI_PIPELINE_SOURCE:-NOT SET}' (expected 'trigger')"
    echo "  This indicates the pipeline was not triggered via GitHub Action"
fi

# Check for GitHub commit SHA setup
if is_set "GITHUB_COMMIT_SHA" && is_set "CI_COMMIT_SHA"; then
    if [[ "${GITHUB_COMMIT_SHA}" == "${CI_COMMIT_SHA}" ]]; then
        echo "✓ Commit SHA properly configured for GitHub integration"
        echo "  Both GITHUB_COMMIT_SHA and CI_COMMIT_SHA match: ${CI_COMMIT_SHA}"
    else
        echo "❌ Commit SHA mismatch - this will prevent GitHub status updates:"
        echo "  GITHUB_COMMIT_SHA: ${GITHUB_COMMIT_SHA}"
        echo "  CI_COMMIT_SHA: ${CI_COMMIT_SHA}"
        echo "  Fix: Ensure CI_COMMIT_SHA is set to GITHUB_COMMIT_SHA in pipeline"
    fi
elif is_set "GITHUB_COMMIT_SHA"; then
    echo "⚠ GITHUB_COMMIT_SHA provided but CI_COMMIT_SHA not updated"
    echo "  GITHUB_COMMIT_SHA: ${GITHUB_COMMIT_SHA}"
    echo "  CI_COMMIT_SHA: ${CI_COMMIT_SHA:-NOT SET}"
    echo "  Fix: Add 'export CI_COMMIT_SHA=\"\${GITHUB_COMMIT_SHA}\"' to pipeline"
else
    echo "❌ GITHUB_COMMIT_SHA not provided by GitHub Action"
    echo "  This variable should be passed from the GitHub workflow"
fi

# Check PR context
if is_set "PR_NUMBER" && [[ "${PR_NUMBER}" != "0" ]]; then
    echo "✓ GitHub PR context detected: PR #${PR_NUMBER}"
else
    echo "⚠ No GitHub PR context (PR_NUMBER=${PR_NUMBER:-NOT SET})"
    echo "  Status updates will only work for actual PRs, not develop branch"
fi

# Check if GitLab project has GitHub integration configured
echo ""
echo "=== GitLab Project Integration Check ==="
echo "For triggered pipelines to update GitHub status, your GitLab project must:"
echo "1. Have GitHub repository connected in Project Settings > Integrations"
echo "2. Have 'Repository push' and 'Pipeline events' enabled"
echo "3. Have proper authentication token with 'repo:status' scope"

echo ""
echo "=== GitLab API Tests ==="

# Test GitLab API availability
if is_set "CI_API_V4_URL" && is_set "CI_JOB_TOKEN"; then
    echo "Testing GitLab API access..."
    api_response=$(curl -s -w "%{http_code}" -o /tmp/api_test.json \
        -H "JOB-TOKEN: ${CI_JOB_TOKEN}" \
        "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}" || echo "000")
    
    if [[ "$api_response" == "200" ]]; then
        echo "✓ GitLab API accessible"
        
        # Test status update endpoint for triggered pipeline
        if is_set "CI_COMMIT_SHA" && is_set "PR_NUMBER" && [[ "${PR_NUMBER}" != "0" ]]; then
            echo "Testing status update endpoint for GitHub PR integration..."
            status_response=$(curl -s -w "%{http_code}" -o /tmp/status_test.json \
                -X POST \
                -H "JOB-TOKEN: ${CI_JOB_TOKEN}" \
                -H "Content-Type: application/json" \
                -d '{
                    "state": "pending",
                    "description": "Test status update from debug script",
                    "context": "debug/test",
                    "target_url": "'${CI_PIPELINE_URL:-}'"
                }' \
                "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/statuses/${CI_COMMIT_SHA}" || echo "000")
            
            if [[ "$status_response" == "201" ]] || [[ "$status_response" == "200" ]]; then
                echo "✓ Status update API working for GitHub integration (HTTP $status_response)"
                echo "  This should appear as a status check on GitHub PR #${PR_NUMBER}"
            else
                echo "❌ Status update failed for GitHub integration (HTTP $status_response)"
                echo "  This indicates GitLab cannot update GitHub status for this commit"
                echo "Response body:"
                cat /tmp/status_test.json 2>/dev/null || echo "No response body"
                echo ""
                echo "Common causes:"
                echo "  - GitLab project not connected to GitHub repository"
                echo "  - GitHub token lacks 'repo:status' permissions"
                echo "  - Commit SHA not found in connected GitHub repository"
            fi
        else
            echo "⚠ Cannot test status update - missing required variables:"
            echo "  CI_COMMIT_SHA: ${CI_COMMIT_SHA:-NOT SET}"
            echo "  PR_NUMBER: ${PR_NUMBER:-NOT SET} (need >0)"
        fi
    else
        echo "❌ GitLab API not accessible (HTTP $api_response)"
        echo "Response body:"
        cat /tmp/api_test.json 2>/dev/null || echo "No response body"
    fi
else
    echo "❌ Cannot test API - CI_API_V4_URL or CI_JOB_TOKEN not set"
fi

echo ""
echo "=== Recommendations ==="

# Provide specific recommendations based on findings
recommendations=()

if [[ "${CI_PIPELINE_SOURCE:-}" != "trigger" ]]; then
    recommendations+=("Ensure GitHub Action properly triggers GitLab pipeline with 'trigger' source")
fi

if ! is_set "GITHUB_COMMIT_SHA"; then
    recommendations+=("GitHub Action must pass GITHUB_COMMIT_SHA variable to GitLab")
fi

if is_set "GITHUB_COMMIT_SHA" && [[ "${GITHUB_COMMIT_SHA}" != "${CI_COMMIT_SHA:-}" ]]; then
    recommendations+=("GitLab pipeline must set CI_COMMIT_SHA=\${GITHUB_COMMIT_SHA}")
fi

if ! is_set "PR_NUMBER" || [[ "${PR_NUMBER}" == "0" ]]; then
    recommendations+=("GitHub Action must pass valid PR_NUMBER > 0 for status updates")
fi

if ! is_set "CI_JOB_TOKEN"; then
    recommendations+=("Ensure CI_JOB_TOKEN is available for GitLab API calls")
fi

if [[ ${#recommendations[@]} -eq 0 ]]; then
    echo "✓ Configuration appears correct for GitHub integration"
    echo "  If status updates still don't work, check GitLab project integration settings"
else
    echo "Configuration issues found:"
    for rec in "${recommendations[@]}"; do
        echo "• $rec"
    done
fi

echo ""
echo "=== GitLab Project Integration Settings ==="
echo "In your GitLab project, verify:"
echo "1. Settings > Integrations > GitHub"
echo "2. Repository URL: ${GW_REPO_URL:-'(not set)'}"
echo "3. Token permissions: 'repo:status' (at minimum)"
echo "4. Enable 'Push events' and 'Pipeline events'"
echo ""
echo "=== How Status Updates Work in Your Setup ==="
echo "1. GitHub PR triggers GitHub Action"
echo "2. GitHub Action calls GitLab pipeline trigger with PR HEAD SHA"
echo "3. GitLab sets CI_COMMIT_SHA to GitHub commit SHA"
echo "4. GitLab pipeline posts status to GitHub via GitLab's GitHub integration"
echo "5. Status appears on GitHub PR as external check"

echo ""
echo "======================================================================="
echo "Debug report complete. Save this output for troubleshooting."
echo "======================================================================="

# Cleanup temporary files
rm -f /tmp/api_test.json /tmp/status_test.json