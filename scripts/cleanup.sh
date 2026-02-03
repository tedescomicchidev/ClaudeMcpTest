#!/bin/bash
# Cleanup the Claude Agent Platform from Minikube

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
K8S_DIR="$PROJECT_DIR/k8s"

echo "=== Cleaning up Claude Agent Platform ==="

# Delete frontend resources
echo "Deleting frontend..."
kubectl delete -f "$K8S_DIR/frontend/" --ignore-not-found=true

# Delete backend resources
echo "Deleting backend..."
kubectl delete -f "$K8S_DIR/backend/pdb.yaml" --ignore-not-found=true
kubectl delete -f "$K8S_DIR/backend/service.yaml" --ignore-not-found=true
kubectl delete -f "$K8S_DIR/backend/deployment.yaml" --ignore-not-found=true
kubectl delete -f "$K8S_DIR/backend/secret.yaml" --ignore-not-found=true
kubectl delete -f "$K8S_DIR/backend/configmap.yaml" --ignore-not-found=true

# Optionally delete namespaces
read -p "Delete namespaces (frontend/backend)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    kubectl delete -f "$K8S_DIR/namespaces/" --ignore-not-found=true
fi

echo ""
echo "Cleanup complete!"
