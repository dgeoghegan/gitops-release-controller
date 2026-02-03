# DEMO_WALKTHROUGH.md
Reviewer-grade validation of a minimal GitOps deployment workflow (10–15 minutes).

Repos:
- App: https://github.com/dgeoghegan/versioned-app
- Infra: https://github.com/dgeoghegan/gitops-infra
- GitOps controller: https://github.com/dgeoghegan/gitops-release-controller

Region: us-east-1  
GitOps rule: Git is source of truth. Argo CD reconciles. CI never applies manifests.

---

## Review models (how to validate this project)

This demo supports two review modes. Choose one:

### Mode 1: Author-run demo (recommended for interviews)
You do not need AWS credentials. I run the workflows and show:
- the PR that changes desired state in Git
- Argo CD reconciling to the new version
- a rollback by Git revert

### Mode 2: Fork-and-run (self-serve)
You run the full demo in your own AWS account. This requires AWS permissions and may incur cost.

Minimum setup assumptions:
- You can run `terraform apply` and `gitops-infra/scripts/bootstrap.sh` successfully.
- You can run GitHub Actions in your fork.
- You can create the required GitHub Actions secrets/vars in your forked repos.

Bounded repo-specific configuration you must supply:
- `gitops-infra`: Terraform backend config values (S3 bucket + DynamoDB lock table) via `backend.hcl` / `-backend-config` as documented.
- `versioned-app`: set `AWS_ROLE_TO_ASSUME` (repo variable) and `GITOPS_REPO_DISPATCH_TOKEN` (secret) so the workflow can dispatch into your `gitops-release-controller` repo.
- `versioned-app`: set `TARGET_REPO` in the workflow to point at your fork (OWNER/REPO) if it is not already.

---

## What is durable vs ephemeral
Durable: ECR images; Terraform state (typically S3 + DynamoDB lock table, provided by the reviewer).
Ephemeral: EKS cluster, Argo CD install, ALBs, Kubernetes resources (can be destroyed and recreated).

---

There are two distinct prerequisite layers depending on which walkthrough path you take.

---

## Fast Path Prerequisites (Infra Already Running)

The FAST PATH in `DEMO_WALKTHROUGH.md` assumes the environment has already been bootstrapped using `gitops-infra`.

Concretely, this means:

- An EKS cluster exists
- Argo CD is installed in the cluster
- Argo CD is configured to pull from `gitops-release-controller`
- Argo Applications for dev / staging / prod already exist
- ALB ingress controller is installed and functional
- Application endpoints (ALB DNS names) are reachable

Access and permissions:

- `kubectl` is configured to point at the cluster (correct kubeconfig / context)
- You can port-forward to Argo CD:
  ```bash
  kubectl -n argocd port-forward svc/argocd-server 8080:443
  ```
- You have GitHub access to:
  - Run `workflow_dispatch` workflows
  - Merge PRs in `gitops-release-controller`
- You can reach the application endpoints via curl

Shorthand:
> “The cluster has already been bootstrapped by gitops-infra, and kubectl is pointing at it.”

---

## Recreate Path Prerequisites (Running gitops-infra)

The RECREATE PATH requires the ability to provision and bootstrap everything from scratch using `gitops-infra`.

Required tools:

- terraform
- aws CLI
- kubectl
- git
- bash-compatible shell

Required access:

- AWS credentials with permission to create:
  - EKS
  - VPC and networking resources
  - ECR
  - S3 (Terraform state)
  - DynamoDB (Terraform locking)
- GitHub access to clone all three repositories
- Network access for Argo CD to pull from GitHub

Shorthand:
> “You can successfully run `terraform apply` and `scripts/bootstrap.sh` in gitops-infra.”

---

## Non-Prerequisites (Explicitly Out of Scope)

- No manual kubectl apply of application manifests
- No direct image promotion logic in CI
- No requirement to understand internal Helm templates to run the demo



---

### 1) Open Argo CD
```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
```

The port-forward maps local 8080 to Argo CD’s HTTPS port (443).

Open https://localhost:8080  
Login with the password printed by `gitops-infra/scripts/bootstrap.sh` or by executing this command:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 --decode; echo
```

Confirm Applications for dev/staging/prod are present and Healthy.

---

### 2) Build and tag an image (versioned-app)

Image build and Git tagging are intentionally separate concerns.

- CI builds and pushes images to ECR.
- Semantic version tags are created explicitly in Git.
- The Cannon workflow only selects an existing image tag; it does not create tags in Git or ECR.

#### 2A) Build and push an image (CI)
The image build runs automatically on Git events. You normally do not manually dispatch it.

Build triggers:
- Push to `main` → builds and pushes a dev image (referenced by SHA)
- Push of tag `v*` → builds and pushes a semver image (referenced by vX.Y.Z)

Workflow:
```
versioned-app/.github/workflows/build-push.yaml
```

Example:
- Push to main (or push a tag) in git CLI
- Observe the workflow run in GitHub UI (https://github.com/dgeoghegan/versioned-app/actions/workflows/build-push.yaml)
- Note the resulting image tag used for dev (e.g. `sha-<12>`)

Evidence to capture later: workflow run URL.

#### 2B) Create a semver tag (for staging/prod)
Create and push a Git tag pointing at the desired commit.

```bash
git clone https://github.com/dgeoghegan/versioned-app
cd versioned-app
git fetch origin --tags
git tag vX.Y.Z <COMMIT_SHA>
git push origin vX.Y.Z
```

Confirm the image exists before deploying to staging/prod:
- Verify the build workflow has run for tag `vX.Y.Z`, and
- Verify the image `vX.Y.Z` exists in ECR.

---

### 3) Deploy to dev (automatic bump)
Dev deployments are automatic.

Flow:
- A push to `main` in `versioned-app` triggers the build-push workflow.
- That workflow triggers `bump-dev-image` in `gitops-release-controller`.
- `bump-dev-image` opens a PR updating the dev environment values file with the new image tag (SHA-based).

Workflow:
```
gitops-release-controller/.github/workflows/bump-dev-image.yaml
```

Expected result:
- A PR is opened modifying only:
```
charts/versioned-app/environments/dev/values.yaml
```
Fields changed are limited to `image.tag` and related version fields.

Merge the PR. (https://github.com/dgeoghegan/gitops-release-controller/pulls)

---

### 4) Observe reconciliation (dev)
In Argo CD:
- Application `versioned-app-dev` transitions to Synced/Healthy.

Fetch the endpoint:
```bash
kubectl get ingress -n jb-dev
curl http://<JB_DEV_ALB_DNS>
```

Expected response:
```
app=versioned-app
env=dev
version=<GIT_SHA or tag>
```

#### Example: dev deploy and rollback (proof of life)

This is example output from one successful dev deploy and rollback. Hostnames and tags will differ in other environments. After a bump or rollback is performed (PR merged), Argo CD must reconcile before the correct version is deployed. 

Get the dev URL:

```bash
kubectl -n jb-dev get ingress versioned-app -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'; echo
```

Before deploy (existing version):

```bash
curl $(kubectl -n jb-dev get ingress versioned-app -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'; echo)
app=versioned-app
env=dev
version=sha-2b2316c5c0a4
```

After deploy (after merging the bump PR):

```bash
curl $(kubectl -n jb-dev get ingress versioned-app -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'; echo)
app=versioned-app
env=dev
version=sha-6c3f114715f
```

After rollback (after reverting the bump commit/PR and Argo reconciliation):

```bash
curl $(kubectl -n jb-dev get ingress versioned-app -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'; echo)
app=versioned-app
env=dev
version=sha-2b2316c5c0a4
```

---

### 5) Deploy to staging by semver
(Note: See 2B above for instructions on creating a semver tag)
Run Cannon with:
- env: `staging`
- image: `<SEMVER_TAG>`

Merge the PR.

Verify:
```bash
kubectl get ingress -n jb-staging
curl http://<JB_STAGING_ALB_DNS>
```

app=versioned-app
env=staging
version=<SEMVER_TAG>`.

---

### 6) Deploy to prod by semver
Repeat Cannon with:
- env: `prod`
- image: `<SEMVER_TAG>`

Merge the PR.

Verify:
```bash
kubectl get ingress -n jb-prod
curl http://<JB_PROD_ALB_DNS>
```

app=versioned-app
env=prod
version=<SEMVER_TAG>`.

---

### 7) Rollback by Git revert
In `gitops-release-controller`, revert the prod PR commit:
```bash
git revert <PROD_DEPLOY_COMMIT_SHA>
git push origin main
```

Observe in Argo CD:
- prod app reconciles back to the previous version.

Verify endpoint reflects the rollback:
```bash
curl http://<JB_PROD_ALB_DNS>
```

---

## RECREATE PATH (optional, brief)

### 1) Destroy runtime resources
From `gitops-infra`:
```bash
scripts/teardown.sh
```

Note: teardown is bounded best-effort and may time out waiting for AWS load balancer dependencies. If destroy fails due to dependencies, wait briefly and re-run teardown.

### 2) Recreate artifacts + infra
```bash
cd terraform/artifacts
terraform init \
  -backend-config=../../backend.hcl \
  -backend-config="key=gitops-infra/artifacts/terraform.tfstate"
terraform apply

cd ../infrastructure
terraform init \
  -backend-config=../../backend.hcl \
  -backend-config="key=gitops-infra/infrastructure/terraform.tfstate"
terraform apply
```

### 3) Bootstrap Argo CD
```bash
scripts/bootstrap.sh
```
Note the printed Argo admin password.

Return to FAST PATH step 1.

---

## Notes for reviewers
- CI builds images only; it never applies Kubernetes manifests.
- All environment changes occur via Git PRs.
- Argo CD is the sole reconciler.
- Rollback is a Git operation.
