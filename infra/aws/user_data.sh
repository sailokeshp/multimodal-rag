#!/usr/bin/env bash
# EC2 User Data — runs once on first boot as root.
# Installs Docker, Docker Compose, and sets up the app directory.
set -euo pipefail
exec > /var/log/user-data.log 2>&1

apt-get update -y
apt-get install -y docker.io docker-compose-plugin git curl wget unzip tesseract-ocr

# Enable Docker without sudo for ubuntu user
usermod -aG docker ubuntu
systemctl enable docker
systemctl start docker

# Create app directory
mkdir -p /opt/rag
chown ubuntu:ubuntu /opt/rag

# Placeholder service file — deploy.sh will populate the real .env and code
cat > /etc/systemd/system/rag.service << 'EOF'
[Unit]
Description=Multimodal RAG Stack
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/rag
ExecStartPre=/usr/bin/docker compose pull --quiet
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=always
RestartSec=10
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

systemctl enable rag.service
echo "User data complete"
