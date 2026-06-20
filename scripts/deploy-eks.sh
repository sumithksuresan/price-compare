#!/usr/bin/env bash
# Full cluster deployment: ArgoCD (as a pod) + PriceHop app manifests.
# Usage: bash ./scripts/deploy-eks.sh  (or chmod +x and ./scripts/deploy-eks.sh)
[ -z "$BASH_VERSION" ] && exec bash "$0" "$@"
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:?Set CLUSTER_NAME}"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo "==> Connecting to EKS cluster: ${CLUSTER_NAME}"
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION"

# ── 1. Install / upgrade ArgoCD inside the cluster ────────────────────────────
echo ""
echo "==> Applying ArgoCD core (argocd-install/)…"
kubectl apply -k kubernetes/argocd-install/

echo ""
echo "==> Installing ArgoCD Image Updater v1.2.1…"
kubectl apply -n argocd -f \
  https://raw.githubusercontent.com/argoproj-labs/argocd-image-updater/v1.2.1/config/install.yaml

echo ""
echo "==> Applying Image Updater config patch…"
kubectl apply -f kubernetes/argocd-install/image-updater-cm-patch.yaml

echo ""
echo "==> Waiting for ArgoCD deployments to be ready…"
for deploy in argocd-server argocd-application-controller argocd-repo-server argocd-redis; do
  echo "    → ${deploy}"
  kubectl rollout status deployment/"${deploy}" -n argocd --timeout=180s 2>/dev/null \
    || kubectl rollout status statefulset/"${deploy}" -n argocd --timeout=180s 2>/dev/null \
    || true
done

# ── 2. Print the ArgoCD LoadBalancer address ──────────────────────────────────
echo ""
echo "==> Waiting for NLB hostname to be assigned (may take ~60s)…"
for i in $(seq 1 24); do
  LB=$(kubectl get svc argocd-server -n argocd \
    -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
  if [ -n "$LB" ]; then
    echo ""
    echo "✅ ArgoCD is live at: https://${LB}"
    echo "   (Create a DNS CNAME → ${LB} if you have a custom domain)"
    break
  fi
  sleep 5
done

# ── 3. Fetch initial admin password ───────────────────────────────────────────
ARGOCD_PASS=$(kubectl get secret argocd-initial-admin-secret -n argocd \
  -o jsonpath="{.data.password}" 2>/dev/null | base64 -d || echo "<not yet available>")
echo ""
echo "   ArgoCD admin password: ${ARGOCD_PASS}"
echo "   (Change it after first login with: argocd account update-password)"

# ── 4. Register the app secrets & AppProject / Application CRDs ───────────────
echo ""
echo "==> Applying pricehop namespace and secrets…"
kubectl apply -f kubernetes/manifests/namespace.yaml

echo "==> Applying ArgoCD AppProject + Application…"
kubectl apply -f kubernetes/argocd/appproject.yaml
kubectl apply -f kubernetes/argocd/application.yaml

echo "==> Applying ArgoCD notification config…"
kubectl apply -f kubernetes/argocd/notifications-config.yaml

# ── 5. Deploy app manifests directly (first time, before ArgoCD takes over) ───
echo ""
echo "==> Applying pricehop app manifests (initial deploy)…"
echo "    (ArgoCD will manage subsequent deploys via GitOps)"

# Ensure secrets exist before applying other resources
if ! kubectl get secret pricehop-secrets -n pricehop &>/dev/null; then
  echo ""
  echo "⚠️  Secret 'pricehop-secrets' not found in namespace 'pricehop'."
  echo "   Create it now, then re-run this script:"
  echo ""
  echo "   kubectl create secret generic pricehop-secrets --namespace pricehop \\"
  echo "     --from-literal=SECRET_KEY='...' \\"
  echo "     --from-literal=JWT_SECRET='...' \\"
  echo "     --from-literal=GOOGLE_CLIENT_ID='...' \\"
  echo "     --from-literal=GOOGLE_CLIENT_SECRET='...'"
  echo ""
  exit 1
fi

# Apply PVCs first and wait for them to be Bound before starting pods
echo "==> Ensuring PVCs exist before deploying pods…"
kubectl apply -f kubernetes/manifests/namespace.yaml
kubectl apply -f kubernetes/manifests/pvcs.yaml
echo "    Waiting for PVCs to be Bound…"
for pvc in auth-data-pvc price-data-pvc; do
  for i in $(seq 1 24); do
    STATUS=$(kubectl get pvc "$pvc" -n pricehop -o jsonpath='{.status.phase}' 2>/dev/null || echo "Pending")
    [ "$STATUS" = "Bound" ] && echo "    ✅ ${pvc} Bound" && break
    [ "$i" -eq 24 ] && echo "    ⚠️  ${pvc} still ${STATUS} after 120s — continuing anyway"
    sleep 5
  done
done

kubectl apply -k kubernetes/ --server-side --force-conflicts

echo ""
echo "==> Waiting for pricehop rollout…"
ROLLOUT_OK=true
for deploy in auth-service price-service frontend api-gateway; do
  echo "    → ${deploy}"
  if ! kubectl rollout status deployment/"${deploy}" -n pricehop --timeout=180s; then
    ROLLOUT_OK=false
    echo ""
    echo "⚠️  Rollout timed out for ${deploy}. Pod status:"
    kubectl get pods -n pricehop -l "app=${deploy}" -o wide
    echo ""
    echo "   Recent events:"
    kubectl get events -n pricehop --field-selector involvedObject.name="${deploy}" \
      --sort-by='.lastTimestamp' 2>/dev/null | tail -10
    echo ""
    echo "   Pod describe (first pod):"
    POD=$(kubectl get pod -n pricehop -l "app=${deploy}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    [ -n "$POD" ] && kubectl describe pod "$POD" -n pricehop | tail -30
    echo ""
    echo "   ── Common causes ──────────────────────────────────────────"
    echo "   ImagePullBackOff → Node IAM role missing ECR pull policy."
    echo "   Fix: attach AmazonEC2ContainerRegistryReadOnly to the node"
    echo "        group IAM role, then: kubectl rollout restart deployment/${deploy} -n pricehop"
    echo "   ───────────────────────────────────────────────────────────"
  fi
done

[ "$ROLLOUT_OK" = false ] && echo "" && echo "❌ One or more deployments did not roll out. See diagnostics above." && exit 1

# ── 6. Summary ────────────────────────────────────────────────────────────────
echo ""
echo "✅ Full deployment complete."
echo ""
echo "── ArgoCD ──────────────────────────────────────────────"
[ -n "${LB:-}" ] && echo "   UI:       https://${LB}" || echo "   UI:       (NLB hostname pending)"
echo "   Username: admin"
echo "   Password: ${ARGOCD_PASS}"
echo ""
echo "── PriceHop App ────────────────────────────────────────"
APP_LB=$(kubectl get svc api-gateway -n pricehop \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "pending")
echo "   App URL:  http://${APP_LB}"
echo ""
kubectl get pods -n argocd
echo ""
kubectl get pods -n pricehop
