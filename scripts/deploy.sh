#!/bin/bash
# Deploy the Claude Agent Platform to Minikube

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
K8S_DIR="$PROJECT_DIR/k8s"

echo "=== Deploying Claude Agent Platform to Minikube ==="

# Check if Minikube is running
if ! minikube status >/dev/null 2>&1; then
    echo "Error: Minikube is not running. Start it with: minikube start"
    exit 1
fi

# Check if kubectl is available
if ! command -v kubectl >/dev/null 2>&1; then
    echo "Error: kubectl is not installed"
    exit 1
fi

# Create namespaces
echo ""
echo "Creating namespaces..."
kubectl apply -f "$K8S_DIR/namespaces/"

# Wait for namespaces
sleep 2

# Deploy backend first (frontend depends on it)
echo ""
echo "Deploying backend..."
kubectl apply -f "$K8S_DIR/backend/configmap.yaml"
kubectl apply -f "$K8S_DIR/backend/secret.yaml"
kubectl apply -f "$K8S_DIR/backend/deployment.yaml"
kubectl apply -f "$K8S_DIR/backend/service.yaml"
kubectl apply -f "$K8S_DIR/backend/pdb.yaml"

# Deploy frontend
echo ""
echo "Deploying frontend..."
kubectl apply -f "$K8S_DIR/frontend/"

# Wait for deployments
echo ""
echo "Waiting for deployments to be ready..."
kubectl rollout status deployment/orchestrator -n backend --timeout=120s
kubectl rollout status deployment/frontend -n frontend --timeout=120s

# Get status
echo ""
echo "=== Deployment Status ==="
echo ""
echo "Backend pods:"
kubectl get pods -n backend
echo ""
echo "Frontend pods:"
kubectl get pods -n frontend
echo ""

# Get the URL
FRONTEND_URL=$(minikube service frontend-service -n frontend --url 2>/dev/null || echo "")
if [ -n "$FRONTEND_URL" ]; then
    echo "=== Access the Application ==="
    echo "Frontend URL: $FRONTEND_URL"
else
    NODE_IP=$(minikube ip)
    echo "=== Access the Application ==="
    echo "Frontend URL: http://$NODE_IP:30080"
fi

echo ""
echo "Deployment complete!"
echo ""
echo "IMPORTANT: Make sure to set your Anthropic API key:"
echo "  kubectl create secret generic anthropic-secrets \\"
echo "    --from-literal=ANTHROPIC_API_KEY=your-key-here \\"
echo "    -n backend --dry-run=client -o yaml | kubectl apply -f -"
