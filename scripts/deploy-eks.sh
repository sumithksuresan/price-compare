#!/usr/bin/env bash
# Apply all Kubernetes manifests to an EKS cluster.
# Usage: CLUSTER_NAME=pricehop-cluster AWS_REGION=ap-south-1 ./scripts/deploy-eks.sh
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:?Set CLUSTER_NAME}"
AWS_REGION="${AWS_REGION:-ap-south-1}"
MANIFEST_DIR="kubernetes/manifests"

echo "==> Updating kubeconfig for cluster: ${CLUSTER_NAME}"
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION"

echo "==> Applying namespace…"
kubectl apply -f "${MANIFEST_DIR}/namespace.yaml"

echo "==> Applying secrets template (edit secrets.yaml first or use kubectl create secret)…"
# Only apply if it doesn't already exist — avoids overwriting real secrets
kubectl get secret pricehop-secrets -n pricehop &>/dev/null \
  || kubectl apply -f "${MANIFEST_DIR}/secrets.yaml"

echo "==> Applying services…"
kubectl apply -f "${MANIFEST_DIR}/auth-service.yaml"
kubectl apply -f "${MANIFEST_DIR}/price-service.yaml"
kubectl apply -f "${MANIFEST_DIR}/frontend.yaml"
kubectl apply -f "${MANIFEST_DIR}/api-gateway.yaml"

echo ""
echo "==> Waiting for rollout…"
kubectl rollout status deployment/auth-service  -n pricehop --timeout=120s
kubectl rollout status deployment/price-service -n pricehop --timeout=120s
kubectl rollout status deployment/frontend      -n pricehop --timeout=120s
kubectl rollout status deployment/api-gateway   -n pricehop --timeout=120s

echo ""
echo "✅ Deployment complete."
echo ""
kubectl get pods -n pricehop
echo ""
echo "LoadBalancer address:"
kubectl get svc api-gateway -n pricehop -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
echo ""
