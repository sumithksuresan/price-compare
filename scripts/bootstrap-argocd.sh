#!/usr/bin/env bash
# One-time bootstrap: install ArgoCD + Image Updater on EKS, then register the app.
# Usage: CLUSTER_NAME=pricehop-cluster AWS_REGION=ap-south-1 GIT_REPO=https://github.com/ORG/price-compare.git ./scripts/bootstrap-argocd.sh
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:?Set CLUSTER_NAME}"
AWS_REGION="${AWS_REGION:-ap-south-1}"
GIT_REPO="${GIT_REPO:?Set GIT_REPO to your GitHub repo URL}"
ARGOCD_VERSION="${ARGOCD_VERSION:-v2.11.3}"
IMAGE_UPDATER_VERSION="${IMAGE_UPDATER_VERSION:-v0.12.3}"

echo "==> Connecting to EKS cluster: ${CLUSTER_NAME}"
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION"

# ── 1. Install ArgoCD ──────────────────────────────────────────────────────────
echo ""
echo "==> Installing ArgoCD ${ARGOCD_VERSION}…"
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd \
  -f "https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"

echo "==> Waiting for ArgoCD server to be ready…"
kubectl rollout status deployment/argocd-server -n argocd --timeout=180s

# ── 2. Install ArgoCD Image Updater ───────────────────────────────────────────
echo ""
echo "==> Installing ArgoCD Image Updater ${IMAGE_UPDATER_VERSION}…"
kubectl apply -n argocd \
  -f "https://raw.githubusercontent.com/argoproj-labs/argocd-image-updater/${IMAGE_UPDATER_VERSION}/manifests/install.yaml"

# Patch image updater with ECR credentials via IRSA (preferred) or access key
# If using IRSA, annotate the service account instead:
# kubectl annotate serviceaccount argocd-image-updater \
#   -n argocd eks.amazonaws.com/role-arn=arn:aws:iam::ACCOUNT:role/ArgoImageUpdaterRole

# ── 3. Register git repo (uses HTTPS + GitHub deploy token) ───────────────────
echo ""
echo "==> Configuring ArgoCD CLI…"
# Get initial admin password
ARGOCD_PASS=$(kubectl get secret argocd-initial-admin-secret -n argocd \
  -o jsonpath="{.data.password}" | base64 -d)

# Port-forward in background so we can use argocd CLI locally
kubectl port-forward svc/argocd-server -n argocd 8080:443 &
PF_PID=$!
sleep 3
trap "kill $PF_PID 2>/dev/null || true" EXIT

argocd login localhost:8080 \
  --username admin \
  --password "$ARGOCD_PASS" \
  --insecure

# Add the git repo (prompts for token if not set as env var)
argocd repo add "$GIT_REPO" \
  --username git \
  --password "${GITHUB_TOKEN:-$(read -rsp 'GitHub token: ' t; echo $t)}" \
  --insecure-skip-server-verification

# ── 4. Apply ArgoCD manifests ─────────────────────────────────────────────────
echo ""
echo "==> Applying AppProject and Application…"
# Patch repo URL into manifests before applying
sed "s|https://github.com/YOUR_ORG/price-compare.git|${GIT_REPO}|g" \
  kubernetes/argocd/appproject.yaml | kubectl apply -f -
sed "s|https://github.com/YOUR_ORG/price-compare.git|${GIT_REPO}|g" \
  kubernetes/argocd/application.yaml | kubectl apply -f -

# ── 5. Apply notification config ──────────────────────────────────────────────
echo ""
echo "==> Applying notification config…"
kubectl apply -f kubernetes/argocd/notifications-config.yaml

# ── 6. Create CI role token for GitHub Actions ────────────────────────────────
echo ""
echo "==> Creating CI deployer token (save this as ARGOCD_AUTH_TOKEN in GitHub Secrets)…"
argocd proj role create-token pricehop ci-deployer --valid-duration 8760h 2>/dev/null || true

echo ""
echo "✅ ArgoCD bootstrap complete."
echo ""
echo "ArgoCD admin password: ${ARGOCD_PASS}"
echo ""
echo "Next steps:"
echo "  1. Add GitHub Actions secrets (Settings → Secrets):"
echo "     AWS_ACCOUNT_ID, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
echo "     GH_DEPLOY_TOKEN  (PAT with repo write scope)"
echo "     ARGOCD_SERVER    (e.g. argocd.internal or your LB hostname)"
echo "     ARGOCD_AUTH_TOKEN (token printed above)"
echo "  2. Optionally expose ArgoCD UI: kubectl patch svc argocd-server -n argocd -p '{\"spec\":{\"type\":\"LoadBalancer\"}}'"
echo "  3. Push any change to main — the pipeline closes the loop automatically."
