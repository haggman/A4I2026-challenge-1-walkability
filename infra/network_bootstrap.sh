#!/usr/bin/env bash
# infra/network_bootstrap.sh
# Idempotent VPC, subnet, Private Google Access, VPC peering, and VPC connector bootstrap
# for Stage 1 (M1) of the Atlanta Urban Heat Planning Assistant.
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:-qwiklabs-gcp-04-ec3596addc43}"
REGION="${COMPUTE_REGION:-us-central1}"
VPC_NAME="heat-planner-vpc"
SUBNET_NAME="heat-planner-subnet"
SUBNET_RANGE="10.10.0.0/24"
CONNECTOR_NAME="heat-vpc-connector"
CONNECTOR_RANGE="10.8.0.0/28"

echo "==> [1/4] Enabling required networking & serverless APIs on ${PROJECT}..."
gcloud services enable \
  compute.googleapis.com \
  vpcaccess.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  bigquery.googleapis.com \
  cloudtrace.googleapis.com \
  --project="${PROJECT}" --quiet

echo "==> [2/4] Ensuring custom VPC ${VPC_NAME} and subnet ${SUBNET_NAME} (${SUBNET_RANGE})..."
if ! gcloud compute networks describe "${VPC_NAME}" --project="${PROJECT}" >/dev/null 2>&1; then
  gcloud compute networks create "${VPC_NAME}" \
    --project="${PROJECT}" \
    --subnet-mode=custom \
    --bgp-routing-mode=regional \
    --quiet
fi

if ! gcloud compute networks subnets describe "${SUBNET_NAME}" --region="${REGION}" --project="${PROJECT}" >/dev/null 2>&1; then
  gcloud compute networks subnets create "${SUBNET_NAME}" \
    --project="${PROJECT}" \
    --network="${VPC_NAME}" \
    --region="${REGION}" \
    --range="${SUBNET_RANGE}" \
    --enable-private-ip-google-access \
    --quiet
else
  gcloud compute networks subnets update "${SUBNET_NAME}" \
    --project="${PROJECT}" \
    --region="${REGION}" \
    --enable-private-ip-google-access \
    --quiet
fi

echo "==> [3/4] Ensuring bidirectional VPC peering between ${VPC_NAME} and default VPC..."
if ! gcloud compute networks peerings list --network="${VPC_NAME}" --project="${PROJECT}" --format="value(peerings.name)" | grep -q "heat-vpc-to-default"; then
  gcloud compute networks peerings create heat-vpc-to-default \
    --network="${VPC_NAME}" \
    --peer-network=default \
    --project="${PROJECT}" \
    --quiet || true
fi

if ! gcloud compute networks peerings list --network=default --project="${PROJECT}" --format="value(peerings.name)" | grep -q "default-to-heat-vpc"; then
  gcloud compute networks peerings create default-to-heat-vpc \
    --network=default \
    --peer-network="${VPC_NAME}" \
    --project="${PROJECT}" \
    --quiet || true
fi

echo "==> [4/4] Checking VPC peering status..."
gcloud compute networks peerings list --project="${PROJECT}"
