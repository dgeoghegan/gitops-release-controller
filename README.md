# gitops-release-controller

This repository demonstrates a minimal, legible GitOps deployment workflow using Argo CD and Helm to manage application releases on Kubernetes (EKS).

The intent is to show senior-level judgment around deploy mechanics, rollback safety, and separation of concerns — not to build a feature-complete platform.

## What this repo does

- Deploys a single application (`versioned-app`) to Kubernetes using Helm
- Uses Argo CD to continuously reconcile desired state from Git
- Treats Git as the sole source of truth for deployments
- Uses an immutable container image tag as the only deploy / rollback knob
- Exposes the app via AWS ALB Ingress Controller

No autoscaling, observability stack, canaries, or external integrations are included by design.

## Where this fits

This repository is the GitOps source of truth:
- Argo CD Applications
- Environment-specific Helm values
- PR-based promotion and rollback workflows (“Cannon”)

It assumes an existing Kubernetes cluster with Argo CD installed.

**End-to-end demo start:**
To provision the cluster and bootstrap Argo CD from scratch, start with
[`gitops-infra`](https://github.com/dgeoghegan/gitops-infra).

If infrastructure already exists, follow the FAST PATH in `DEMO_WALKTHROUGH.md`
to validate deployment and rollback behavior.

## Repository structure

```
.
├── charts/
│   └── versioned-app/
│       ├── Chart.yaml
│       ├── values.yaml
│       ├── environments/
│       │   ├── dev/values.yaml
│       │   ├── staging/values.yaml
│       │   └── prod/values.yaml
│       └── templates/
│           ├── deployment.yaml
│           ├── service.yaml
│           └── ingress.yaml
├── scripts/
│   └── cannon_update_values.py
├── argocd/
│   └── applications/
│       ├── versioned-app-dev.yaml
│       ├── versioned-app-staging.yaml
│       └── versioned-app-prod.yaml
```

### charts/versioned-app

The Helm chart defining all Kubernetes resources for the application.

### charts/versioned-app/environments/*

Environment-specific values, including replica counts, resource requests/limits, image tag, and ingress behavior.

### argocd/applications/*

Argo CD `Application` manifests, one per environment, each pointing at the appropriate values file.

## Deployment model

1. A container image is built and pushed to ECR with an immutable tag (for example `v0.1.1` or `sha-<shortsha>`).
2. A deployment is initiated by updating the pinned image tag in the appropriate environment values file.
3. Argo CD detects the Git change and reconciles the cluster.
4. Kubernetes performs a rolling update.
5. Rollback is performed by reverting the Git change.

The application version reported at runtime comes from the container image and injected environment variables, not from Helm release metadata.  
For SHA-based deploys, the short Git SHA is injected. For semver deploys, the semantic version is injected and `GIT_SHA` is intentionally left empty.

### Deployment selection (“Cannon”)

Deployments are initiated via a GitHub Actions workflow (“Cannon”) that acts as an explicit deployment selector.

Cannon:
- Accepts a target environment and an image tag
- Validates tag format (dev allows SHA or semver; staging and prod require semver)
- Opens a pull request that updates only the pinned image tag (and related version fields) in the corresponding values file

Cannon does not interact with the Kubernetes cluster. Argo CD remains the sole reconciler of runtime state.

## Environment differences

These differences are intentional and minimal.

### dev

- 1 replica
- Smallest resource requests
- Easiest exposure
- Allows SHA-based or semver image tags

### staging

- 2 replicas
- Moderate resource requests
- Semver image tags only

### prod

- 2 replicas
- Tighter resource limits
- Basic guardrails only
- Semver image tags only

## What this repo explicitly does NOT include

- Horizontal Pod Autoscaling
- Observability or metrics stack
- Canary or blue-green deployments
- Secrets management
- Multi-cluster or multi-region support

These are intentionally omitted to keep the demo focused and legible.

## Destroy / recreate expectations

This repository assumes the underlying EKS cluster and Argo CD installation may be destroyed and recreated at any time.

The only required post-recreate step is re-applying the initial Argo CD bootstrap that points at this repository.  
All application state is derived from Git; no manual reconciliation or cleanup is expected.

## Why this exists

This project exists as a portfolio artifact to demonstrate:

- Clear GitOps boundaries
- Safe, auditable deploy and rollback mechanics
- Restraint in scope
- Systems that are easy to reason about and explain
