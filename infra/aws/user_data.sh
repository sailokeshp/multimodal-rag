#!/usr/bin/env bash
# EC2 User Data — runs once on first boot as root.
# Installs Docker (official repo), Docker Compose V2, and sets up the app directory.
set -euo pipefail
exec > /var/log/user-data.log 2>&1

apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release git wget unzip tesseract-ocr

# ── Install Docker from official Docker apt repo ──────────────────────────────
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Enable Docker without sudo for ubuntu user
usermod -aG docker ubuntu
systemctl enable docker
systemctl start docker

# Create app directory
mkdir -p /opt/rag
chown ubuntu:ubuntu /opt/rag

# Placeholder systemd service — deploy.sh will populate the real .env and code
cat > /etc/systemd/system/rag.service << 'EOF'
[Unit]
Description=Multimodal RAG Stack
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/rag
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down
Restart=always
RestartSec=10
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

systemctl enable rag.service
echo "User data complete"
