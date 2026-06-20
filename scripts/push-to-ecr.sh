#!/usr/bin/env bash
# Push all service images to AWS ECR and update K8s manifests.
# Usage: AWS_ACCOUNT_ID=123456789 AWS_REGION=ap-south-1 ./scripts/push-to-ecr.sh [tag]
set -euo pipefail

AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:?Set AWS_ACCOUNT_ID}"
AWS_REGION="${AWS_REGION:-ap-south-1}"
TAG="${1:-latest}"
ECR_BASE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/pricehop"

SERVICES=(frontend auth-service price-service api-gateway)

echo "==> Logging in to ECR…"
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

for SVC in "${SERVICES[@]}"; do
  REPO="${ECR_BASE}/${SVC}"
  LOCAL_DIR="services/${SVC}"

  echo ""
  echo "==> [${SVC}] Creating ECR repository (idempotent)…"
  aws ecr describe-repositories --repository-names "pricehop/${SVC}" --region "$AWS_REGION" 2>/dev/null \
    || aws ecr create-repository --repository-name "pricehop/${SVC}" --region "$AWS_REGION" \
         --image-scanning-configuration scanOnPush=true

  echo "==> [${SVC}] Building image…"
  docker build -t "${REPO}:${TAG}" "${LOCAL_DIR}"

  echo "==> [${SVC}] Pushing ${REPO}:${TAG}…"
  docker push "${REPO}:${TAG}"

  echo "==> [${SVC}] Updating K8s manifest image reference…"
  sed -i "s|123456789.dkr.ecr.ap-south-1.amazonaws.com/pricehop/${SVC}:.*|${REPO}:${TAG}|g" \
    "kubernetes/manifests/${SVC}.yaml" 2>/dev/null || true
done

echo ""
echo "✅ All images pushed to ECR."
echo ""
echo "Next steps:"
echo "  1. Update FRONTEND_URL in kubernetes/manifests/*.yaml to your domain."
echo "  2. Create secrets:  kubectl create secret generic pricehop-secrets --namespace pricehop \\"
echo "       --from-literal=SECRET_KEY='...' --from-literal=JWT_SECRET='...' \\"
echo "       --from-literal=GOOGLE_CLIENT_ID='...' --from-literal=GOOGLE_CLIENT_SECRET='...'"
echo "  3. Apply manifests: kubectl apply -f kubernetes/manifests/"
echo "  4. Check pods:      kubectl get pods -n pricehop"
echo "  5. Get LB address:  kubectl get svc api-gateway -n pricehop"
