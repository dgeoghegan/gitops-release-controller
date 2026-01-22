# gitops-release-controller

This repository demonstrates a minimal, legible GitOps deployment workflow using Argo CD and Helm to manage application releases on Kubernetes (EKS).

The intent is to show senior-level judgment around deploy mechanics, rollback safety, and separation of concerns, not to build a feature-complete platform.

## What this repo does

- Deploys a single application (versioned-app) to Kubernetes using Helm
- Uses Argo CD to continuously reconcile desired state from Git
- Treats Git as the source of truth for deployments
- Uses an immutable container image tag as the sole deploy / rollback knob
- Exposes the app via AWS ALB Ingress Controller

No autoscaling, observability stack, canaries, or external integrations are included by design.

## Repository structure

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
│
├── argocd/
│   └── applications/
│       ├── versioned-app-dev.yaml
│       ├── versioned-app-staging.yaml
│       └── versioned-app-prod.yaml

- charts/versioned-app
  The Helm chart defining Kubernetes resources.

- charts/versioned-app/environments/*
  Environment-specific values (replicas, resources, image tag, ingress behavior).

- argocd/applications/*
  Argo CD Application manifests, one per environment.

## Deployment model

1. A container image is built and pushed to ECR with an immutable tag (for example v0.1.1).
2. The image tag is updated in the appropriate environment values file.
3. Argo CD detects the Git change and reconciles the cluster.
4. Kubernetes rolls out the new version.

Rollback is performed by reverting the image tag in Git.

The application version reported at runtime comes from the image itself, not from Helm values.

## Environment differences

dev
- 1 replica
- smallest resource requests
- easiest exposure

staging
- 2 replicas
- moderate resources

prod
- 2 replicas
- tighter resource limits
- basic guardrails only

Differences are intentional and minimal.

## What this repo explicitly does NOT include

- Horizontal Pod Autoscaling
- Observability / metrics stack
- Canary or blue-green deployments
- Secrets management
- Multi-cluster or multi-region support

These are intentionally omitted to keep the demo focused.

## Destroy / recreate expectations

This repo assumes the underlying cluster and Argo CD installation may be destroyed and recreated.

No manual cleanup or hidden state should be required beyond the initial bootstrap.

## Why this exists

This project exists as a portfolio artifact to demonstrate:

- Clear GitOps boundaries
- Safe deploy and rollback mechanics
- Restraint in scope
- Systems that are easy to reason about and explain
