#!/usr/bin/env bash
# =============================================================================
# sync_github_secrets.sh — Push deployment secrets from local env files to
# GitHub Actions repository secrets.
#
# Sources:
#   - .env      : app/runtime secrets
#   - .env.aws  : provisioned AWS host/resource outputs
#   - PEM file  : EC2_SSH_KEY
#
# Usage:
#   ./sync_github_secrets.sh
#   REPO=owner/name ./sync_github_secrets.sh
#   KEY_PATH=/path/to/key.pem ./sync_github_secrets.sh
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
ENV_AWS_FILE="${REPO_ROOT}/.env.aws"
KEY_PATH="${KEY_PATH:-${REPO_ROOT}/stockmind-key.pem}"
REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)}"

G="\033[0;32m"; Y="\033[0;33m"; R="\033[0;31m"; NC="\033[0m"
info()  { echo -e "${G}[INFO]${NC} $*"; }
warn()  { echo -e "${Y}[WARN]${NC} $*"; }
error() { echo -e "${R}[ERR] ${NC} $*"; exit 1; }

require_file() {
    local path="$1"
    [ -f "${path}" ] || error "Required file not found: ${path}"
}

env_get() {
    local key="$1"
    local file="$2"
    [ -f "${file}" ] || return 0
    grep -m1 "^${key}=" "${file}" | cut -d= -f2- || true
}

set_secret_body() {
    local name="$1"
    local value="$2"
    if [ -z "${value}" ]; then
        warn "Skipping ${name} — value is empty"
        return 0
    fi
    gh secret set "${name}" --body "${value}" -R "${REPO}"
    info "Updated GitHub secret: ${name}"
}

set_secret_file() {
    local name="$1"
    local path="$2"
    require_file "${path}"
    gh secret set "${name}" -R "${REPO}" < "${path}"
    info "Updated GitHub secret: ${name}"
}

gh auth status >/dev/null 2>&1 || error "GitHub CLI is not authenticated. Run: gh auth login"
[ -n "${REPO}" ] || error "Could not determine repo. Set REPO=owner/name"

require_file "${ENV_FILE}"
require_file "${ENV_AWS_FILE}"
require_file "${KEY_PATH}"

info "Syncing GitHub Actions secrets for ${REPO}…"

set_secret_body "POSTGRES_PASSWORD"   "$(env_get POSTGRES_PASSWORD "${ENV_FILE}")"
set_secret_body "AWS_REGION"          "$(env_get AWS_REGION "${ENV_FILE}")"
set_secret_body "AWS_ACCESS_KEY_ID"   "$(env_get AWS_ACCESS_KEY_ID "${ENV_FILE}")"
set_secret_body "AWS_SECRET_ACCESS_KEY" "$(env_get AWS_SECRET_ACCESS_KEY "${ENV_FILE}")"
set_secret_body "S3_BUCKET"           "$(env_get S3_BUCKET "${ENV_FILE}")"
set_secret_body "SQS_QUEUE_URL"       "$(env_get SQS_QUEUE_URL "${ENV_FILE}")"
set_secret_body "GROQ_API_KEY"        "$(env_get GROQ_API_KEY "${ENV_FILE}")"
set_secret_body "GOOGLE_AI_API_KEY"   "$(env_get GOOGLE_AI_API_KEY "${ENV_FILE}")"
set_secret_body "EC2_HOST"            "$(env_get EC2_PUBLIC_IP "${ENV_AWS_FILE}")"
set_secret_file "EC2_SSH_KEY"         "${KEY_PATH}"

echo ""
info "GitHub secret sync complete."
echo "  Repo: ${REPO}"
echo "  EC2 Host: $(env_get EC2_PUBLIC_IP "${ENV_AWS_FILE}")"
