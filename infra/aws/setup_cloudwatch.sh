#!/usr/bin/env bash
# =============================================================================
# setup_cloudwatch.sh — Install CloudWatch agent + create alarms & dashboard.
#
# Free tier usage:
#   Logs    : awslogs Docker driver ships container logs → /rag/production
#   Metrics : CloudWatch agent sends memory + disk (2 of 10 free custom metrics)
#   Alarms  : 3 alarms (CPU, memory, API 5xx) — 3 of 10 free
#   Dashboard: 1 dashboard — 1 of 3 free
#
# Run from your LOCAL machine after provision.sh + deploy.sh.
# Requires: aws configure, .env.aws
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_AWS="${REPO_ROOT}/.env.aws"
KEY_PATH="${KEY_PATH:-${HOME}/Downloads/stockmind-key.pem}"
LOG_RETENTION_DAYS=7          # keep logs 7 days — well within 5 GB free tier
ALARM_EMAIL="${ALARM_EMAIL:-}" # optional: set to get email alerts

G="\033[0;32m"; Y="\033[0;33m"; NC="\033[0m"
info() { echo -e "${G}[INFO]${NC} $*"; }
warn() { echo -e "${Y}[WARN]${NC} $*"; }

[ -f "${ENV_AWS}" ] || { echo "Run provision.sh first"; exit 1; }
# shellcheck disable=SC2046
export $(grep -v '^#' "${ENV_AWS}" | xargs)

REGION="${AWS_REGION:-us-east-1}"
INSTANCE_ID="${EC2_INSTANCE_ID}"
PUBLIC_IP="${EC2_PUBLIC_IP}"
SSH="ssh -i ${KEY_PATH} -o StrictHostKeyChecking=no ubuntu@${PUBLIC_IP}"

info "Setting up CloudWatch for instance ${INSTANCE_ID} (${PUBLIC_IP})"

# ── 1. Set log retention on /rag/production ───────────────────────────────────
info "Setting log retention to ${LOG_RETENTION_DAYS} days…"
aws logs put-retention-policy \
    --log-group-name /rag/production \
    --retention-in-days "${LOG_RETENTION_DAYS}" \
    --region "${REGION}" 2>/dev/null || \
aws logs create-log-group --log-group-name /rag/production --region "${REGION}" && \
aws logs put-retention-policy \
    --log-group-name /rag/production \
    --retention-in-days "${LOG_RETENTION_DAYS}" \
    --region "${REGION}"
info "Log retention set"

# ── 2. Install CloudWatch agent on EC2 ───────────────────────────────────────
info "Installing CloudWatch agent on EC2…"
$SSH "bash -s" << 'REMOTE'
set -e
# Download and install CloudWatch agent
if ! command -v amazon-cloudwatch-agent-ctl &>/dev/null; then
    wget -q https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
    sudo dpkg -i amazon-cloudwatch-agent.deb
    rm amazon-cloudwatch-agent.deb
    echo "[REMOTE] CloudWatch agent installed"
else
    echo "[REMOTE] CloudWatch agent already installed"
fi
REMOTE

# ── 3. Push agent config (memory + disk metrics) ─────────────────────────────
info "Configuring CloudWatch agent (memory + disk metrics)…"

# Read creds from local .env for injection into agent config
AWS_KEY_ID=$(grep "^AWS_ACCESS_KEY_ID=" "${REPO_ROOT}/.env" | cut -d= -f2-)
AWS_SECRET=$(grep "^AWS_SECRET_ACCESS_KEY=" "${REPO_ROOT}/.env" | cut -d= -f2-)

$SSH "bash -s" << REMOTE
set -e
sudo mkdir -p /opt/aws/amazon-cloudwatch-agent/etc

# Write credentials for the agent (since no IAM role on this instance)
sudo mkdir -p /root/.aws
sudo tee /root/.aws/credentials > /dev/null << 'CREDS'
[AmazonCloudWatchAgent]
aws_access_key_id = ${AWS_KEY_ID}
aws_secret_access_key = ${AWS_SECRET}
CREDS

sudo tee /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json > /dev/null << 'CONF'
{
  "agent": {
    "metrics_collection_interval": 60,
    "run_as_user": "root"
  },
  "metrics": {
    "namespace": "RAG/EC2",
    "append_dimensions": {
      "InstanceId": "\${aws:InstanceId}"
    },
    "metrics_collected": {
      "mem": {
        "measurement": ["mem_used_percent"],
        "metrics_collection_interval": 60
      },
      "disk": {
        "measurement": ["disk_used_percent"],
        "resources": ["/"],
        "metrics_collection_interval": 60
      }
    }
  }
}
CONF

sudo amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
    -s

echo "[REMOTE] CloudWatch agent started"
sudo amazon-cloudwatch-agent-ctl -a status | grep status
REMOTE

info "CloudWatch agent configured"

# ── 4. Create SNS topic for alarms (email alerts) ────────────────────────────
SNS_ARN=""
if [ -n "${ALARM_EMAIL}" ]; then
    info "Creating SNS topic for alarm emails → ${ALARM_EMAIL}…"
    SNS_ARN=$(aws sns create-topic --name rag-alerts --region "${REGION}" \
        --query TopicArn --output text)
    aws sns subscribe \
        --topic-arn "${SNS_ARN}" \
        --protocol email \
        --notification-endpoint "${ALARM_EMAIL}" \
        --region "${REGION}" > /dev/null
    warn "Check your email to confirm the SNS subscription before alarms fire"
fi

ALARM_ACTIONS=""
[ -n "${SNS_ARN}" ] && ALARM_ACTIONS="--alarm-actions ${SNS_ARN}"

# ── 5. Create CloudWatch alarms ───────────────────────────────────────────────
info "Creating CloudWatch alarms…"

# Alarm 1 — High CPU (>80% for 10 min)
aws cloudwatch put-metric-alarm \
    --alarm-name "RAG-HighCPU" \
    --alarm-description "EC2 CPU > 80% for 10 minutes" \
    --namespace "AWS/EC2" \
    --metric-name "CPUUtilization" \
    --dimensions "Name=InstanceId,Value=${INSTANCE_ID}" \
    --statistic Average \
    --period 300 \
    --evaluation-periods 2 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --treat-missing-data notBreaching \
    --region "${REGION}" \
    ${ALARM_ACTIONS}
info "Alarm created: RAG-HighCPU"

# Alarm 2 — High Memory (>85%)
aws cloudwatch put-metric-alarm \
    --alarm-name "RAG-HighMemory" \
    --alarm-description "EC2 memory > 85%" \
    --namespace "RAG/EC2" \
    --metric-name "mem_used_percent" \
    --dimensions "Name=InstanceId,Value=${INSTANCE_ID}" \
    --statistic Average \
    --period 300 \
    --evaluation-periods 2 \
    --threshold 85 \
    --comparison-operator GreaterThanThreshold \
    --treat-missing-data notBreaching \
    --region "${REGION}" \
    ${ALARM_ACTIONS}
info "Alarm created: RAG-HighMemory"

# Alarm 3 — High Disk (>80%)
aws cloudwatch put-metric-alarm \
    --alarm-name "RAG-HighDisk" \
    --alarm-description "EC2 disk > 80% full" \
    --namespace "RAG/EC2" \
    --metric-name "disk_used_percent" \
    --dimensions "Name=InstanceId,Value=${INSTANCE_ID}" \
    --statistic Average \
    --period 300 \
    --evaluation-periods 1 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --treat-missing-data notBreaching \
    --region "${REGION}" \
    ${ALARM_ACTIONS}
info "Alarm created: RAG-HighDisk"

# ── 6. Create CloudWatch dashboard ───────────────────────────────────────────
info "Creating CloudWatch dashboard…"

DASHBOARD_BODY=$(cat << DASH
{
  "widgets": [
    {
      "type": "metric",
      "width": 12, "height": 6,
      "properties": {
        "title": "CPU Utilization",
        "metrics": [["AWS/EC2","CPUUtilization","InstanceId","${INSTANCE_ID}"]],
        "period": 300, "stat": "Average", "region": "${REGION}",
        "annotations": {"horizontal": [{"value": 80, "label": "Alert threshold", "color": "#ff0000"}]}
      }
    },
    {
      "type": "metric",
      "width": 12, "height": 6,
      "properties": {
        "title": "Memory Used %",
        "metrics": [["RAG/EC2","mem_used_percent","InstanceId","${INSTANCE_ID}"]],
        "period": 300, "stat": "Average", "region": "${REGION}",
        "annotations": {"horizontal": [{"value": 85, "label": "Alert threshold", "color": "#ff0000"}]}
      }
    },
    {
      "type": "metric",
      "width": 12, "height": 6,
      "properties": {
        "title": "Disk Used %",
        "metrics": [["RAG/EC2","disk_used_percent","InstanceId","${INSTANCE_ID}"]],
        "period": 300, "stat": "Average", "region": "${REGION}",
        "annotations": {"horizontal": [{"value": 80, "label": "Alert threshold", "color": "#ff0000"}]}
      }
    },
    {
      "type": "metric",
      "width": 12, "height": 6,
      "properties": {
        "title": "Network In/Out",
        "metrics": [
          ["AWS/EC2","NetworkIn","InstanceId","${INSTANCE_ID}"],
          ["AWS/EC2","NetworkOut","InstanceId","${INSTANCE_ID}"]
        ],
        "period": 300, "stat": "Sum", "region": "${REGION}"
      }
    },
    {
      "type": "log",
      "width": 24, "height": 6,
      "properties": {
        "title": "API Logs (last 30 min)",
        "query": "SOURCE '/rag/production' | fields @timestamp, @message | filter @logStream = 'api' | sort @timestamp desc | limit 50",
        "region": "${REGION}",
        "view": "table"
      }
    },
    {
      "type": "log",
      "width": 24, "height": 6,
      "properties": {
        "title": "Worker Logs (last 30 min)",
        "query": "SOURCE '/rag/production' | fields @timestamp, @message | filter @logStream = 'worker' | sort @timestamp desc | limit 50",
        "region": "${REGION}",
        "view": "table"
      }
    },
    {
      "type": "alarm",
      "width": 24, "height": 4,
      "properties": {
        "title": "Alarm Status",
        "alarms": [
          "arn:aws:cloudwatch:${REGION}:$(aws sts get-caller-identity --query Account --output text):alarm:RAG-HighCPU",
          "arn:aws:cloudwatch:${REGION}:$(aws sts get-caller-identity --query Account --output text):alarm:RAG-HighMemory",
          "arn:aws:cloudwatch:${REGION}:$(aws sts get-caller-identity --query Account --output text):alarm:RAG-HighDisk"
        ]
      }
    }
  ]
}
DASH
)

aws cloudwatch put-dashboard \
    --dashboard-name "RAG-Production" \
    --dashboard-body "${DASHBOARD_BODY}" \
    --region "${REGION}" > /dev/null
info "Dashboard created: RAG-Production"

# ── Summary ───────────────────────────────────────────────────────────────────
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo ""
echo -e "${G}═══════════════════════════════════════════════════════${NC}"
echo -e "${G} CloudWatch setup complete!${NC}"
echo -e "${G}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "  Dashboard : https://console.aws.amazon.com/cloudwatch/home?region=${REGION}#dashboards:name=RAG-Production"
echo "  Logs      : https://console.aws.amazon.com/cloudwatch/home?region=${REGION}#logsV2:log-groups/log-group/\$252Frag\$252Fproduction"
echo "  Alarms    : https://console.aws.amazon.com/cloudwatch/home?region=${REGION}#alarmsV2:"
echo ""
[ -n "${ALARM_EMAIL}" ] && echo "  Confirm your alarm email subscription: ${ALARM_EMAIL}"
echo ""
