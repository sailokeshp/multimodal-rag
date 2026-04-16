#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Build and deploy the Multimodal RAG app to EC2.
#
# Usage:
#   ./deploy.sh [--skip-build]
#
# Prerequisites:
#   1. Run provision.sh first (generates .env.aws)
#   2. .env file must exist in repo root with all secrets
#   3. stockmind-key.pem in ~/Downloads/ (or set KEY_PATH env var)
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_AWS="${REPO_ROOT}/.env.aws"
ENV_FILE="${REPO_ROOT}/.env"
KEY_PATH="${KEY_PATH:-${HOME}/Downloads/stockmind-key.pem}"
REMOTE_DIR="/opt/rag"
SKIP_BUILD="${1:-}"

# Colors
G="\033[0;32m"; Y="\033[0;33m"; R="\033[0;31m"; NC="\033[0m"
info()  { echo -e "${G}[INFO]${NC} $*"; }
warn()  { echo -e "${Y}[WARN]${NC} $*"; }
error() { echo -e "${R}[ERR] ${NC} $*"; exit 1; }

# ── Validate prerequisites ────────────────────────────────────────────────────
[ -f "${ENV_AWS}" ]  || error ".env.aws not found — run provision.sh first"
[ -f "${ENV_FILE}" ] || error ".env not found — copy .env.example to .env and fill in secrets"
[ -f "${KEY_PATH}" ] || error "PEM key not found at ${KEY_PATH} — set KEY_PATH env var"

chmod 600 "${KEY_PATH}"

# Load .env.aws
# shellcheck disable=SC2046
export $(grep -v '^#' "${ENV_AWS}" | xargs)

PUBLIC_IP="${EC2_PUBLIC_IP}"
[ -n "${PUBLIC_IP}" ] || error "EC2_PUBLIC_IP not set in .env.aws"

SSH_OPTS="-i ${KEY_PATH} -o StrictHostKeyChecking=no -o ConnectTimeout=30"
SSH="ssh ${SSH_OPTS} ubuntu@${PUBLIC_IP}"

info "Deploying to EC2 ${PUBLIC_IP}…"

# ── Wait for SSH ──────────────────────────────────────────────────────────────
info "Waiting for SSH to be ready…"
for i in $(seq 1 30); do
    if ${SSH} "echo ok" >/dev/null 2>&1; then
        info "SSH ready"
        break
    fi
    if [ "${i}" -eq 30 ]; then
        error "SSH timed out after 5 minutes. Check security group port 22."
    fi
    echo -n "."
    sleep 10
done

# ── Build frontend ────────────────────────────────────────────────────────────
if [ "${SKIP_BUILD}" != "--skip-build" ]; then
    WEB_DIR="${REPO_ROOT}/apps/web"
    if [ ! -d "${WEB_DIR}/node_modules" ]; then
        info "Installing frontend dependencies…"
        (cd "${WEB_DIR}" && npm install --silent)
    fi

    info "Building frontend for production (API at http://${PUBLIC_IP})…"
    (cd "${WEB_DIR}" && VITE_API_URL="http://${PUBLIC_IP}/api" npm run build)
    info "Frontend built: $(du -sh "${WEB_DIR}/dist" | cut -f1)"
else
    info "Skipping frontend build (--skip-build)"
fi

# ── Sync code to EC2 ──────────────────────────────────────────────────────────
info "Syncing code to ${REMOTE_DIR}…"

# Create remote dir if needed
${SSH} "sudo mkdir -p ${REMOTE_DIR} && sudo chown ubuntu:ubuntu ${REMOTE_DIR}"

# Rsync — exclude large dev artifacts
rsync -az --delete \
    -e "ssh ${SSH_OPTS}" \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='apps/web/node_modules' \
    --exclude='.env.local' \
    --exclude='*.pem' \
    --exclude='.env.aws' \
    "${REPO_ROOT}/" \
    "ubuntu@${PUBLIC_IP}:${REMOTE_DIR}/"

info "Code synced"

# ── Copy .env ─────────────────────────────────────────────────────────────────
info "Uploading .env…"
scp ${SSH_OPTS} "${ENV_FILE}" "ubuntu@${PUBLIC_IP}:${REMOTE_DIR}/.env"

# ── Wait for user_data (Docker install) to finish ────────────────────────────
info "Waiting for Docker to be ready on EC2 (user_data may still be running)…"
for i in $(seq 1 30); do
    if ${SSH} "docker version &>/dev/null 2>&1 || sudo docker version &>/dev/null 2>&1"; then
        info "Docker is ready"
        break
    fi
    if [ "${i}" -eq 30 ]; then
        error "Docker never became ready after 5 minutes. Check /var/log/user-data.log on the instance."
    fi
    echo -n "."
    sleep 10
done

# ── Pull latest images & start stack ─────────────────────────────────────────
info "Starting production stack on EC2…"
${SSH} "bash -s" << REMOTE
set -e
cd ${REMOTE_DIR}

# Ensure docker is running
sudo systemctl start docker 2>/dev/null || true

# Add ubuntu to docker group (idempotent)
sudo usermod -aG docker ubuntu 2>/dev/null || true

# Pull base images
sudo docker compose -f docker-compose.prod.yml pull --quiet 2>/dev/null || true

# Build app images (api + worker) from source
sudo docker compose -f docker-compose.prod.yml build --quiet

# Restart stack
sudo docker compose -f docker-compose.prod.yml down --remove-orphans 2>/dev/null || true
sudo docker compose -f docker-compose.prod.yml up -d

echo "[REMOTE] Stack started"
REMOTE

# ── Health check ──────────────────────────────────────────────────────────────
info "Waiting for API health check…"
for i in $(seq 1 24); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time 10 "http://${PUBLIC_IP}/health" 2>/dev/null || echo "000")
    if [ "${HTTP_CODE}" = "200" ]; then
        info "Health check passed (HTTP ${HTTP_CODE})"
        break
    fi
    if [ "${i}" -eq 24 ]; then
        warn "Health check did not return 200 after 2 minutes (last: HTTP ${HTTP_CODE})"
        warn "Check logs: ssh -i ${KEY_PATH} ubuntu@${PUBLIC_IP} 'sudo docker compose -f /opt/rag/docker-compose.prod.yml logs --tail=50'"
    fi
    echo -n "."
    sleep 5
done

# ── Print summary ─────────────────────────────────────────────────────────────
echo ""
echo -e "${G}═══════════════════════════════════════════════════════${NC}"
echo -e "${G} Deployment complete!${NC}"
echo -e "${G}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "  Frontend:  http://${PUBLIC_IP}/"
echo "  API docs:  http://${PUBLIC_IP}/api/docs"
echo "  Health:    http://${PUBLIC_IP}/health"
echo ""
echo "  SSH:       ssh -i ${KEY_PATH} ubuntu@${PUBLIC_IP}"
echo "  Logs:      ssh -i ${KEY_PATH} ubuntu@${PUBLIC_IP} \\"
echo "               'sudo docker compose -f /opt/rag/docker-compose.prod.yml logs -f'"
echo ""
