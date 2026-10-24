#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export KUBECONFIG="$ROOT/.local/kubeconfig"

die() {
  printf '%s\n' "$*" >&2
  exit 1
}

require() {
  for tool in "$@"; do
    command -v "$tool" >/dev/null || die "Install $tool before running this command."
  done
}

up() {
  require aws terraform kubectl helm docker git
  [[ -f .env ]] || die "Copy .env.example to .env and fill in the passwords."
  [[ -f terraform/terraform.tfvars ]] || die "Create terraform/terraform.tfvars using README.md#run-on-aws."
  for key in DB_ADMIN_PASSWORD DB_PASS GRAFANA_DB_PASS GRAFANA_ADMIN_USER GRAFANA_ADMIN_PASSWORD; do
    grep -q "^${key}=." .env || die "Set $key in .env."
  done
  chmod 600 .env
  kubectl create secret generic uptime-secrets --from-env-file=.env --dry-run=client -o json >/dev/null

  printf 'Checking the published Git configuration...\n'
  git fetch --quiet origin master
  git diff --quiet FETCH_HEAD -- . || die "Publish the current changes to origin/master before running up."
  [[ -z "$(git ls-files --others --exclude-standard)" ]] || die "Commit and publish the new project files before running up."

  mkdir -p .local/helm/cache
  printf 'Creating or updating AWS infrastructure...\n'
  terraform -chdir=terraform init -input=false
  terraform -chdir=terraform plan -input=false -out="$ROOT/.local/lab.tfplan"
  terraform -chdir=terraform apply -input=false "$ROOT/.local/lab.tfplan"
  region="$(terraform -chdir=terraform output -raw aws_region)"
  cluster="$(terraform -chdir=terraform output -raw cluster_name)"
  repository="$(terraform -chdir=terraform output -raw ecr_repository_url)"
  aws eks update-kubeconfig --region "$region" --name "$cluster" --alias uptime-lab-cluster
  chmod 600 "$KUBECONFIG"
  kubectl wait --for=condition=Ready nodes --all --timeout=5m

  printf 'Preparing the namespace, storage, and application Secret...\n'
  kubectl apply -f k8s/app/namespace.yaml -f k8s/app/storageclass.yaml
  existing_secret="$(kubectl -n uptime get secret uptime-secrets --ignore-not-found -o name)"
  if [[ -z "$existing_secret" ]]; then
    existing_pvc="$(kubectl -n uptime get pvc postgres-pvc --ignore-not-found -o name)"
    [[ -z "$existing_pvc" ]] || die "Restore the original database Secret before reusing postgres-pvc. See README.md#secrets."
    kubectl -n uptime create secret generic uptime-secrets --from-env-file=.env
  else
    printf 'Keeping the existing Secret and database passwords.\n'
  fi

  image="$(kubectl kustomize k8s/app | awk '$1 == "image:" && $2 ~ /amazonaws.com/ {print $2}')"
  [[ "$image" == "$repository:"* ]] || die "Update the ECR image reference in k8s/app/kustomization.yaml."
  tag="${image##*:}"
  existing_tag="$(aws ecr batch-get-image --region "$region" --repository-name "${repository##*/}" --image-ids "imageTag=$tag" --query 'images[0].imageId.imageTag' --output text)"
  if [[ "$existing_tag" == None ]]; then
    printf 'Building and publishing the initial application image...\n'
    docker build --platform linux/amd64 --tag "$image" .
    aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "${repository%%/*}"
    docker push "$image"
  else
    printf 'Using the existing ECR image: %s\n' "$image"
  fi

  printf 'Installing Argo CD...\n'
  helm upgrade --install argocd argo-cd \
    --repo https://argoproj.github.io/argo-helm --version 10.10.5 \
    --namespace argocd --create-namespace \
    --repository-config .local/helm/repositories.yaml \
    --repository-cache .local/helm/cache \
    -f helm/argocd-values.yaml --wait --timeout 10m
  kubectl apply -f gitops/project.yaml
  kubectl apply -f gitops/applications.yaml
  printf 'Waiting for Argo CD to deploy the application and monitoring...\n'
  kubectl -n argocd wait --for=jsonpath='{.status.sync.status}'=Synced --timeout=10m -f gitops/applications.yaml
  kubectl -n argocd wait --for=jsonpath='{.status.health.status}'=Healthy --timeout=10m -f gitops/applications.yaml
  printf 'Lab ready. Run scripts/lab.sh grafana or scripts/lab.sh argocd.\n'
}

down() {
  require aws terraform kubectl
  cluster="$(terraform -chdir=terraform output -raw cluster_name)"
  region="$(terraform -chdir=terraform output -raw aws_region)"
  printf 'This deletes database history, monitoring data, and the AWS lab.\n'
  printf 'Type %s to continue: ' "$cluster"
  read -r confirmation
  [[ "$confirmation" == "$cluster" ]] || die "Cleanup cancelled."
  aws eks update-kubeconfig --region "$region" --name "$cluster" --alias uptime-lab-cluster
  volume_ids=""
  for pv in $(kubectl -n uptime get pvc -o jsonpath='{.items[*].spec.volumeName}'); do
    volume_ids+=" $(kubectl get pv "$pv" -o jsonpath='{.spec.csi.volumeHandle}')"
  done
  printf 'Stopping GitOps and removing workloads and PVCs...\n'
  kubectl delete -f gitops/applications.yaml --ignore-not-found
  kubectl delete namespace uptime --ignore-not-found --wait --timeout=10m
  for volume in $volume_ids; do
    printf 'Waiting for EBS volume deletion: %s\n' "$volume"
    aws ec2 wait volume-deleted --region "$region" --volume-ids "$volume"
  done
  terraform -chdir=terraform destroy -auto-approve
}

case "${1:-help}" in
  up)
    up
    ;;
  status)
    require kubectl
    kubectl get nodes
    kubectl -n argocd get pods,applications
    kubectl -n uptime get pods,pvc
    ;;
  grafana)
    require kubectl
    printf 'Open http://localhost:3000 and log in as admin. The password is in .env.\n'
    kubectl -n uptime port-forward --address 127.0.0.1 service/uptime-grafana 3000:80
    ;;
  argocd)
    require kubectl
    printf 'Open https://localhost:8443 and log in as admin. The lab certificate is self-signed.\n'
    printf 'Read the initial password using the command in README.md#open-grafana-and-argo-cd.\n'
    kubectl -n argocd port-forward --address 127.0.0.1 service/argocd-server 8443:443
    ;;
  down)
    down
    ;;
  help|--help|-h)
    printf 'Usage: scripts/lab.sh {up|status|grafana|argocd|down}\n'
    ;;
  *)
    die "Unknown command: $1. Run scripts/lab.sh help."
    ;;
esac
