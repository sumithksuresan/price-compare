#!/usr/bin/env bash
# One-time post-deploy setup: login to ArgoCD, register the git repo,
# create the CI role token, and change the admin password.
#
# Run AFTER deploy-eks.sh has applied argocd-install/ and the NLB is ready.
#
# Usage:
#   CLUSTER_NAME=pricehop-cluster \
#   AWS_REGION=ap-south-1 \
#   GIT_REPO=https://github.com/sumithksuresan/price-compare.git \
#   GITHUB_TOKEN=ghp_... \
#   ./scripts/bootstrap-argocd.sh
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:?Set CLUSTER_NAME}"
AWS_REGION="${AWS_REGION:-ap-south-1}"
GIT_REPO="${GIT_REPO:?Set GIT_REPO}"
GITHUB_TOKEN="${GITHUB_TOKEN:?Set GITHUB_TOKEN (GitHub PAT with repo scope)}"

echo "==> Connecting to EKS cluster: ${CLUSTER_NAME}"
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION"

# ── 1. Resolve ArgoCD LoadBalancer hostname ────────────────────────────────────
echo "==> Resolving ArgoCD LoadBalancer hostname…"
for i in $(seq 1 30); do
  ARGOCD_HOST=$(kubectl get svc argocd-server -n argocd \
    -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
  [ -n "$ARGOCD_HOST" ] && break
  echo "    Waiting… (${i}/30)"
  sleep 5
done

if [ -z "$ARGOCD_HOST" ]; then
  echo "❌ Could not get NLB hostname. Run deploy-eks.sh first." && exit 1
fi
echo "   ArgoCD host: ${ARGOCD_HOST}"

# ── 2. Get initial admin password ─────────────────────────────────────────────
ARGOCD_PASS=$(kubectl get secret argocd-initial-admin-secret -n argocd \
  -o jsonpath="{.data.password}" | base64 -d)

# ── 3. Log in with argocd CLI ─────────────────────────────────────────────────
echo ""
echo "==> Logging in to ArgoCD at ${ARGOCD_HOST}…"
argocd login "$ARGOCD_HOST" \
  --username admin \
  --password "$ARGOCD_PASS" \
  --insecure   # NLB may not have DNS propagated yet; remove after DNS is set

# ── 4. Register the git repo ──────────────────────────────────────────────────
echo ""
echo "==> Registering git repository…"
argocd repo add "$GIT_REPO" \
  --username git \
  --password "$GITHUB_TOKEN"

# ── 5. Patch repo URL in manifests and re-apply ───────────────────────────────
echo ""
echo "==> Patching YOUR_ORG placeholder in ArgoCD manifests…"
sed -i "s|https://github.com/YOUR_ORG/price-compare.git|${GIT_REPO}|g" \
  kubernetes/argocd/appproject.yaml \
  kubernetes/argocd/application.yaml

kubectl apply -f kubernetes/argocd/appproject.yaml
kubectl apply -f kubernetes/argocd/application.yaml

# ── 6. Create CI deployer role token (for GitHub Actions ARGOCD_AUTH_TOKEN) ──
echo ""
echo "==> Creating CI deployer token…"
CI_TOKEN=$(argocd proj role create-token pricehop ci-deployer \
  --valid-duration 8760h \
  --token-only 2>/dev/null || echo "")

# ── 7. Set a new admin password ───────────────────────────────────────────────
NEW_PASS="${ARGOCD_NEW_PASS:-$(openssl rand -base64 16)}"
argocd account update-password \
  --current-password "$ARGOCD_PASS" \
  --new-password "$NEW_PASS"

# ── 8. Summary ────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║              ArgoCD Bootstrap Complete               ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║ UI:       https://${ARGOCD_HOST}"
echo "║ Username: admin"
echo "║ Password: ${NEW_PASS}  ← save this"
echo "╠══════════════════════════════════════════════════════╣"
echo "║ Add these to GitHub → Settings → Secrets:           ║"
echo "║                                                      ║"
echo "║  ARGOCD_SERVER=${ARGOCD_HOST}"
if [ -n "$CI_TOKEN" ]; then
echo "║  ARGOCD_AUTH_TOKEN=${CI_TOKEN}"
else
echo "║  ARGOCD_AUTH_TOKEN=<run: argocd proj role create-token pricehop ci-deployer>"
fi
echo "╚══════════════════════════════════════════════════════╝"
