# PriceHop 🛒

Compare grocery prices across **Blinkit, Swiggy Instamart, Zepto, and BigBasket** in real time.

Built as a microservices application with Flask, SQLite, Google SSO, Docker, and GitOps-based continuous delivery to AWS EKS via ArgoCD.

---

## Table of Contents

- [Architecture](#architecture)
- [Features](#features)
- [Run Locally](#run-locally)
  - [Option A — Docker Compose](#option-a--docker-compose)
  - [Option B — Plain Python](#option-b--plain-python)
- [Google SSO Setup](#google-sso-setup-optional)
- [Deploy to AWS EKS](#deploy-to-aws-eks)
  - [Prerequisites](#prerequisites)
  - [Step 1 — Create EKS Cluster](#step-1--create-eks-cluster)
  - [Step 2 — Build & Push Images to ECR](#step-2--build--push-images-to-ecr)
  - [Step 3 — Create Kubernetes Secrets](#step-3--create-kubernetes-secrets)
  - [Step 4 — Deploy ArgoCD + App](#step-4--deploy-argocd--app)
  - [Step 5 — Bootstrap ArgoCD](#step-5--bootstrap-argocd)
  - [Step 6 — Verify](#step-6--verify)
- [GitOps with ArgoCD](#gitops-with-argocd)
- [CI/CD Pipeline](#cicd-pipeline)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)

---

## Architecture

```
                        ┌─────────────────────────────────────┐
                        │           AWS EKS Cluster           │
                        │                                     │
  Browser ──► NLB:80 ──►│  api-gateway (nginx)                │
                        │       │                             │
              NLB:80 ──►│  argocd-server          [argocd ns] │
                        │                                     │
                        │  frontend  ──► auth-service         │
                        │      │             │                │
                        │      └──► price-service             │
                        │               │                     │
                        │           SQLite PVC                │
                        └─────────────────────────────────────┘
                                        ▲
                              ArgoCD watches git
                                        │
                        GitHub repo (kubernetes/kustomization.yaml)
                                        ▲
                              CI pushes image tag updates
                                        │
                              GitHub Actions (on push to main)
```

| Service | Port | Responsibility |
|---|---|---|
| `api-gateway` | 80 | Nginx reverse proxy + rate limiting |
| `frontend` | 5000 | Flask UI — serves HTML, proxies API calls |
| `auth-service` | 5001 | JWT auth, user registration, Google SSO |
| `price-service` | 5002 | Price search, 5-min SQLite cache, watchlist |

---

## Features

- Search products and compare prices across 4 platforms side-by-side
- Best deal highlighted automatically
- Filter by platform, sort by price / discount / delivery speed
- User accounts with email + password or **Google SSO**
- Per-user watchlist persisted in SQLite
- Trending searches (last 7 days)
- GitOps CD: push to `main` → images built → EKS updated automatically

---

## Run Locally

### Option A — Docker Compose

**Prerequisites:** Docker Desktop running.

```bash
# 1. Clone the repo
git clone https://github.com/sumithksuresan/price-compare.git
cd price-compare

# 2. Create your env file
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY and JWT_SECRET to random strings.
# Leave GOOGLE_CLIENT_ID blank to skip SSO.

# 3. Start all services
docker compose up --build

# 4. Open the app
open http://localhost        # via nginx on port 80
# or directly:
open http://localhost:5000   # frontend only
```

To stop: `docker compose down`  
To wipe volumes (reset databases): `docker compose down -v`

---

### Option B — Plain Python

**Prerequisites:** Python 3.12+

```bash
git clone https://github.com/sumithksuresan/price-compare.git
cd price-compare

# Install dependencies for all three Python services
pip install flask PyJWT authlib requests

mkdir -p data

# Terminal 1 — auth service
DB_PATH=data/auth.db SECRET_KEY=dev JWT_SECRET=dev-jwt \
  python services/auth-service/app.py

# Terminal 2 — price service
DB_PATH=data/prices.db \
  python services/price-service/app.py

# Terminal 3 — frontend
AUTH_SERVICE_URL=http://localhost:5001 \
PRICE_SERVICE_URL=http://localhost:5002 \
  python services/frontend/app.py

# Open http://localhost:5000
```

---

## Google SSO Setup (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials**
2. Create an **OAuth 2.0 Client ID** (Web application)
3. Add authorised redirect URI:
   - Local: `http://localhost:5001/sso/google/callback`
   - Production: `https://<your-domain>/sso/google/callback`
4. Copy the Client ID and Client Secret into your `.env`:

```env
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
FRONTEND_URL=http://localhost
```

5. Restart the services — the **Continue with Google** button becomes active.

---

## Deploy to AWS EKS

### Prerequisites

Install these tools before starting:

```bash
# AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip && sudo ./aws/install

# eksctl
curl --silent --location \
  "https://github.com/eksctl-io/eksctl/releases/latest/download/eksctl_Linux_amd64.tar.gz" \
  | tar xz -C /tmp && sudo mv /tmp/eksctl /usr/local/bin

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# ArgoCD CLI
curl -sSL -o /usr/local/bin/argocd \
  https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
chmod +x /usr/local/bin/argocd

# kustomize
curl -sL "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash
sudo mv kustomize /usr/local/bin/

# Configure AWS credentials
aws configure
# Region: us-east-1
```

---

### Step 1 — Create EKS Cluster

```bash
eksctl create cluster \
  --name pricehop-cluster \
  --region us-east-1 \
  --nodegroup-name standard-workers \
  --node-type t3.medium \
  --nodes 2 \
  --nodes-min 2 \
  --nodes-max 4 \
  --managed

# Verify nodes are ready
kubectl get nodes
```

> **KodeKloud Playground:** if a cluster is already provisioned, skip this step and just update your kubeconfig:
> ```bash
> aws eks update-kubeconfig --name <cluster-name> --region us-east-1
> ```

---

### Step 2 — Build & Push Images to ECR

```bash
# Set your AWS account ID
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=us-east-1

# Build and push all 4 service images
AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID AWS_REGION=$AWS_REGION \
  ./scripts/push-to-ecr.sh v1.0.0
```

This script:
1. Logs in to ECR
2. Creates the 4 ECR repositories (idempotent)
3. Builds each Docker image
4. Pushes with the given tag + `latest`
5. Updates image references in `kubernetes/manifests/*.yaml`

---

### Step 3 — Create Kubernetes Secrets

The app needs a secret for JWT signing and (optionally) Google SSO credentials. Create it once — ArgoCD will never overwrite it.

```bash
kubectl create namespace pricehop

kubectl create secret generic pricehop-secrets \
  --namespace pricehop \
  --from-literal=SECRET_KEY="$(openssl rand -base64 32)" \
  --from-literal=JWT_SECRET="$(openssl rand -base64 32)" \
  --from-literal=GOOGLE_CLIENT_ID="" \
  --from-literal=GOOGLE_CLIENT_SECRET=""
```

To enable Google SSO, replace the empty strings with your actual credentials from [Step — Google SSO Setup](#google-sso-setup-optional).

---

### Step 4 — Deploy ArgoCD + App

A single command installs ArgoCD as pods in the cluster (exposed via NLB), then applies all the PriceHop manifests:

```bash
CLUSTER_NAME=pricehop-cluster AWS_REGION=us-east-1 \
  ./scripts/deploy-eks.sh
```

**What this does, in order:**

| Step | Action |
|---|---|
| 1 | `kubectl apply -k kubernetes/argocd-install/` — installs ArgoCD v2.11.3 + Image Updater |
| 2 | Patches `argocd-server` Service to `type: LoadBalancer` (AWS NLB) |
| 3 | Waits for all ArgoCD pods to become Ready |
| 4 | Prints the NLB hostname and initial admin password |
| 5 | Applies `AppProject` and `Application` CRDs |
| 6 | Runs `kubectl apply -k kubernetes/` for the first app deploy |
| 7 | Waits for all pricehop pods to roll out |
| 8 | Prints both NLB URLs (ArgoCD UI + app) |

> **Note:** NLB hostname provisioning takes ~60 seconds after the service is created.

---

### Step 5 — Bootstrap ArgoCD

This registers your git repo with ArgoCD, sets a new admin password, and creates the CI deploy token:

```bash
CLUSTER_NAME=pricehop-cluster \
AWS_REGION=us-east-1 \
GIT_REPO=https://github.com/sumithksuresan/price-compare.git \
GITHUB_TOKEN=ghp_YOUR_TOKEN \
  ./scripts/bootstrap-argocd.sh
```

The script prints a summary at the end:

```
╔══════════════════════════════════════════════════════╗
║              ArgoCD Bootstrap Complete               ║
╠══════════════════════════════════════════════════════╣
║ UI:       https://abc123.elb.us-east-1.amazonaws.com ║
║ Username: admin                                      ║
║ Password: <generated — save this>                    ║
╠══════════════════════════════════════════════════════╣
║ Add these to GitHub → Settings → Secrets:            ║
║  ARGOCD_SERVER=abc123.elb.us-east-1.amazonaws.com   ║
║  ARGOCD_AUTH_TOKEN=<token>                           ║
╚══════════════════════════════════════════════════════╝
```

Copy those two values into **GitHub → Settings → Secrets and variables → Actions**.

---

### Step 6 — Verify

```bash
# Check all pods are Running
kubectl get pods -n argocd
kubectl get pods -n pricehop

# Get app URL
kubectl get svc api-gateway -n pricehop
# Copy the EXTERNAL-IP hostname → open in browser

# Get ArgoCD UI URL
kubectl get svc argocd-server -n argocd
# Copy the EXTERNAL-IP hostname → open in browser (admin / password from bootstrap)
```

Expected pod list in `pricehop`:

```
NAME                             READY   STATUS    
api-gateway-xxx                  1/1     Running   
auth-service-xxx                 1/1     Running   
frontend-xxx                     1/1     Running   
price-service-xxx                1/1     Running   
```

---

## GitOps with ArgoCD

Once bootstrapped, **you never run `kubectl apply` again**. The workflow is:

```
git push → CI builds images → CI updates kustomization.yaml → ArgoCD syncs → EKS
```

| ArgoCD setting | Value |
|---|---|
| Sync | Automatic (polls every 3 min) |
| Self-heal | Yes — reverts manual `kubectl` changes |
| Prune | Yes — removes resources deleted from git |
| Namespace | `pricehop` |
| Source path | `kubernetes/` (reads `kustomization.yaml`) |

### Upgrading ArgoCD itself

ArgoCD is not managed by itself — it's applied by `deploy-eks.sh`. To upgrade:

```bash
# Edit kubernetes/argocd-install/kustomization.yaml
# Change: v2.11.3 → v2.12.0 (or whatever the new version is)
git add kubernetes/argocd-install/kustomization.yaml
git commit -m "chore: upgrade ArgoCD to v2.12.0"
git push

# Then re-run the deploy script
CLUSTER_NAME=pricehop-cluster AWS_REGION=us-east-1 ./scripts/deploy-eks.sh
```

---

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push to `main`:

```
push to main
    │
    ├── test (matrix: frontend / auth-service / price-service)
    │       pytest + ruff lint
    │
    └── build-push (matrix: all 4 services)  [only on main, after tests pass]
            docker build + push to ECR with git SHA tag
            ECR image scan (logs CRITICAL CVE count)
            │
            └── update-manifest
                    kustomize edit set image → new SHA tags
                    git commit + push [skip ci]
                    POST /api/v1/applications/pricehop/sync  (hard-sync ArgoCD)
```

### Required GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Where to get it |
|---|---|
| `AWS_ACCOUNT_ID` | `aws sts get-caller-identity --query Account --output text` |
| `AWS_ACCESS_KEY_ID` | IAM user with ECR push + EKS describe permissions |
| `AWS_SECRET_ACCESS_KEY` | Same IAM user |
| `GH_DEPLOY_TOKEN` | GitHub PAT with `repo` scope (for manifest commit-back) |
| `ARGOCD_SERVER` | NLB hostname printed by `bootstrap-argocd.sh` |
| `ARGOCD_AUTH_TOKEN` | CI role token printed by `bootstrap-argocd.sh` |

---

## Project Structure

```
price-compare/
├── .github/
│   └── workflows/
│       └── ci.yml                  # CI: test → build → push → update manifest
│
├── services/
│   ├── api-gateway/
│   │   ├── Dockerfile
│   │   └── nginx.conf              # Rate limiting, reverse proxy config
│   ├── auth-service/
│   │   ├── app.py                  # JWT auth, register/login, Google SSO
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── frontend/
│   │   ├── app.py                  # Flask app + API proxy routes
│   │   ├── templates/index.html    # Single-page UI
│   │   ├── static/css/style.css
│   │   ├── static/js/app.js
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── price-service/
│       ├── app.py                  # Search, cache, watchlist endpoints
│       ├── scrapers/
│       │   ├── base.py             # Shared mock catalog (20+ products)
│       │   ├── blinkit.py
│       │   ├── swiggy.py
│       │   ├── zepto.py
│       │   └── bigbasket.py
│       ├── requirements.txt
│       └── Dockerfile
│
├── kubernetes/
│   ├── kustomization.yaml          # ArgoCD sync target — image tags live here
│   ├── argocd-install/             # ArgoCD pods (applied by deploy-eks.sh)
│   │   ├── kustomization.yaml      # Pulls upstream ArgoCD + Image Updater
│   │   ├── namespace.yaml
│   │   ├── argocd-server-svc-patch.yaml     # LoadBalancer + NLB annotations
│   │   ├── argocd-server-deploy-patch.yaml  # --insecure flag
│   │   └── image-updater-cm-patch.yaml      # ECR registry config
│   ├── argocd/
│   │   ├── appproject.yaml         # ArgoCD AppProject (RBAC scoping)
│   │   ├── application.yaml        # ArgoCD Application (auto-sync config)
│   │   └── notifications-config.yaml # Slack alerts
│   └── manifests/
│       ├── namespace.yaml
│       ├── secrets.yaml            # Template only — create with kubectl
│       ├── frontend.yaml
│       ├── auth-service.yaml
│       ├── price-service.yaml
│       └── api-gateway.yaml        # NLB LoadBalancer + HPA
│
├── scripts/
│   ├── push-to-ecr.sh             # Build + push all images to ECR
│   ├── deploy-eks.sh              # Full cluster deploy (ArgoCD + app)
│   └── bootstrap-argocd.sh        # One-time: register repo, create tokens
│
├── docker-compose.yml
└── .env.example
```

---

## Environment Variables

| Variable | Service | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | auth | *(required)* | Flask session secret |
| `JWT_SECRET` | auth | *(required)* | JWT signing key |
| `GOOGLE_CLIENT_ID` | auth | `""` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | auth | `""` | Google OAuth client secret |
| `FRONTEND_URL` | auth | `http://localhost` | Redirect URL after SSO |
| `DB_PATH` | auth, price | `/data/*.db` | SQLite file path |
| `AUTH_SERVICE_URL` | frontend | `http://auth-service:5001` | Auth service base URL |
| `PRICE_SERVICE_URL` | frontend | `http://price-service:5002` | Price service base URL |
| `CACHE_TTL_SECONDS` | price | `300` | How long to cache prices |
