#!/usr/bin/env bash
# =============================================================================
# provision.sh — Create all AWS free-tier resources for the Multimodal RAG app.
#
# Idempotent: safe to re-run.  Resources already existing are skipped.
#
# Prerequisites:
#   aws configure       (run first, enter Access Key / Secret / region)
#   chmod +x provision.sh && ./provision.sh
#
# Free-tier-friendly resources created:
#   EC2 t3.micro        (conservative default for small AWS trial deployments)
#   S3 bucket           (5 GB / 20k GET / 2k PUT free)
#   SQS queue           (1M requests/month free)
#   Security group      (port 22, 80, 8000)
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
KEY_NAME="${KEY_NAME:-stockmind-key}"
REGION="${REGION:-$(aws configure get region || echo us-east-1)}"
INSTANCE_TYPE="t3.micro"
AMI_ID=""                         # auto-detected below
SG_NAME="multimodal-rag-sg"
S3_BUCKET=""                      # auto-generated below
SQS_QUEUE_NAME="multimodal-rag-ingestion"
TAG="multimodal-rag"

# Colors
G="\033[0;32m"; Y="\033[0;33m"; R="\033[0;31m"; NC="\033[0m"
info()  { echo -e "${G}[INFO]${NC} $*"; }
warn()  { echo -e "${Y}[WARN]${NC} $*"; }
error() { echo -e "${R}[ERR] ${NC} $*"; exit 1; }

# ── Validate credentials ──────────────────────────────────────────────────────
info "Checking AWS credentials…"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text) || \
    error "AWS credentials not configured. Run: aws configure"
info "Account: ${ACCOUNT_ID}  Region: ${REGION}"

# ── S3 bucket ─────────────────────────────────────────────────────────────────
S3_BUCKET="multimodal-rag-${ACCOUNT_ID}-${REGION}"
info "S3 bucket: ${S3_BUCKET}"

if aws s3api head-bucket --bucket "${S3_BUCKET}" 2>/dev/null; then
    info "S3 bucket already exists — skipping"
else
    if [ "${REGION}" = "us-east-1" ]; then
        aws s3api create-bucket --bucket "${S3_BUCKET}" --region "${REGION}"
    else
        aws s3api create-bucket --bucket "${S3_BUCKET}" --region "${REGION}" \
            --create-bucket-configuration LocationConstraint="${REGION}"
    fi
    # Enable server-side encryption
    aws s3api put-bucket-encryption --bucket "${S3_BUCKET}" \
        --server-side-encryption-configuration \
        '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
    # Block all public access
    aws s3api put-public-access-block --bucket "${S3_BUCKET}" \
        --public-access-block-configuration \
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
    info "S3 bucket created: ${S3_BUCKET}"
fi

# ── SQS queue ─────────────────────────────────────────────────────────────────
info "SQS queue: ${SQS_QUEUE_NAME}"
SQS_URL=$(aws sqs get-queue-url --queue-name "${SQS_QUEUE_NAME}" \
              --query QueueUrl --output text 2>/dev/null || true)
if [ -z "${SQS_URL}" ]; then
    SQS_URL=$(aws sqs create-queue \
        --queue-name "${SQS_QUEUE_NAME}" \
        --attributes VisibilityTimeout=300,MessageRetentionPeriod=86400 \
        --query QueueUrl --output text)
    info "SQS queue created: ${SQS_URL}"
else
    info "SQS queue already exists — skipping"
fi

# ── Security group ────────────────────────────────────────────────────────────
info "Security group: ${SG_NAME}"
SG_ID=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=${SG_NAME}" \
    --query "SecurityGroups[0].GroupId" --output text 2>/dev/null || echo "None")

if [ "${SG_ID}" = "None" ] || [ -z "${SG_ID}" ]; then
    SG_ID=$(aws ec2 create-security-group \
        --group-name "${SG_NAME}" \
        --description "Multimodal RAG security group" \
        --query GroupId --output text)
    # SSH
    aws ec2 authorize-security-group-ingress --group-id "${SG_ID}" \
        --protocol tcp --port 22 --cidr 0.0.0.0/0
    # HTTP (Nginx frontend)
    aws ec2 authorize-security-group-ingress --group-id "${SG_ID}" \
        --protocol tcp --port 80 --cidr 0.0.0.0/0
    # API direct access (optional, can remove after Nginx is confirmed)
    aws ec2 authorize-security-group-ingress --group-id "${SG_ID}" \
        --protocol tcp --port 8000 --cidr 0.0.0.0/0
    info "Security group created: ${SG_ID}"
else
    info "Security group already exists: ${SG_ID}"
fi

# ── Latest Ubuntu 22.04 LTS AMI ───────────────────────────────────────────────
info "Looking up latest Ubuntu 22.04 AMI in ${REGION}…"
AMI_ID=$(aws ec2 describe-images \
    --owners 099720109477 \
    --filters \
        "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
        "Name=state,Values=available" \
    --query "sort_by(Images, &CreationDate)[-1].ImageId" \
    --output text)
info "AMI: ${AMI_ID}"

# ── EC2 instance ──────────────────────────────────────────────────────────────
INSTANCE_ID=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=${TAG}" "Name=instance-state-name,Values=running,stopped,pending" \
    --query "Reservations[0].Instances[0].InstanceId" \
    --output text 2>/dev/null || echo "None")

if [ "${INSTANCE_ID}" = "None" ] || [ -z "${INSTANCE_ID}" ]; then
    info "Launching EC2 ${INSTANCE_TYPE}…"
    INSTANCE_ID=$(aws ec2 run-instances \
        --image-id "${AMI_ID}" \
        --instance-type "${INSTANCE_TYPE}" \
        --key-name "${KEY_NAME}" \
        --security-group-ids "${SG_ID}" \
        --user-data file://user_data.sh \
        --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":20,"VolumeType":"gp2"}}]' \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${TAG}}]" \
        --query "Instances[0].InstanceId" \
        --output text)
    info "Instance launched: ${INSTANCE_ID}"
    info "Waiting for instance to be running…"
    aws ec2 wait instance-running --instance-ids "${INSTANCE_ID}"
else
    info "EC2 instance already exists: ${INSTANCE_ID}"
    # Make sure it's running
    aws ec2 start-instances --instance-ids "${INSTANCE_ID}" 2>/dev/null || true
    aws ec2 wait instance-running --instance-ids "${INSTANCE_ID}"
fi

# ── Get public IP ─────────────────────────────────────────────────────────────
PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids "${INSTANCE_ID}" \
    --query "Reservations[0].Instances[0].PublicIpAddress" \
    --output text)

info "Public IP: ${PUBLIC_IP}"

# ── Save outputs to .env.aws ──────────────────────────────────────────────────
cat > ../../.env.aws <<EOF
# Auto-generated by provision.sh — $(date)
AWS_REGION=${REGION}
AWS_ACCOUNT_ID=${ACCOUNT_ID}
EC2_INSTANCE_ID=${INSTANCE_ID}
EC2_PUBLIC_IP=${PUBLIC_IP}
S3_BUCKET=${S3_BUCKET}
SQS_QUEUE_URL=${SQS_URL}
KEY_NAME=${KEY_NAME}
EOF

# ── Patch .env with real S3/SQS values ───────────────────────────────────────
ENV_FILE="../../.env"
if [ -f "${ENV_FILE}" ]; then
    # Update S3_BUCKET
    if grep -q "^S3_BUCKET=" "${ENV_FILE}"; then
        sed -i.bak "s|^S3_BUCKET=.*|S3_BUCKET=${S3_BUCKET}|" "${ENV_FILE}"
    else
        echo "S3_BUCKET=${S3_BUCKET}" >> "${ENV_FILE}"
    fi
    # Update SQS_QUEUE_URL
    if grep -q "^SQS_QUEUE_URL=" "${ENV_FILE}"; then
        sed -i.bak "s|^SQS_QUEUE_URL=.*|SQS_QUEUE_URL=${SQS_URL}|" "${ENV_FILE}"
    else
        echo "SQS_QUEUE_URL=${SQS_URL}" >> "${ENV_FILE}"
    fi
    # Update AWS_REGION
    if grep -q "^AWS_REGION=" "${ENV_FILE}"; then
        sed -i.bak "s|^AWS_REGION=.*|AWS_REGION=${REGION}|" "${ENV_FILE}"
    else
        echo "AWS_REGION=${REGION}" >> "${ENV_FILE}"
    fi
    rm -f "${ENV_FILE}.bak"
    info ".env updated with S3_BUCKET, SQS_QUEUE_URL, AWS_REGION"
fi

echo ""
echo -e "${G}═══════════════════════════════════════════${NC}"
echo -e "${G} Provisioning complete!${NC}"
echo -e "${G}═══════════════════════════════════════════${NC}"
echo ""
echo "  EC2 Instance:  ${INSTANCE_ID}"
echo "  Public IP:     ${PUBLIC_IP}"
echo "  S3 Bucket:     ${S3_BUCKET}"
echo "  SQS Queue:     ${SQS_URL}"
echo ""
echo "Next step:"
echo "  ./deploy.sh"
echo ""

# ── Update GitHub Actions secrets with live values ────────────────────────────
if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
    REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)
    if [ -n "${REPO}" ]; then
        info "Updating GitHub Actions secrets for ${REPO}…"
        gh secret set EC2_HOST      --body "${PUBLIC_IP}"  -R "${REPO}"
        gh secret set S3_BUCKET     --body "${S3_BUCKET}"  -R "${REPO}"
        gh secret set SQS_QUEUE_URL --body "${SQS_URL}"    -R "${REPO}"
        info "GitHub secrets updated — future pushes will deploy automatically"
    fi
fi
