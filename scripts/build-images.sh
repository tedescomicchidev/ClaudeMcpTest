#!/bin/bash
# Build Docker images for Minikube
# This script builds images directly in Minikube's Docker daemon

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Building Docker images for Minikube ==="

# Check if Minikube is running
if ! minikube status >/dev/null 2>&1; then
    echo "Error: Minikube is not running. Start it with: minikube start"
    exit 1
fi

# Configure Docker to use Minikube's daemon
echo "Configuring Docker to use Minikube's daemon..."
eval $(minikube docker-env)

# Build frontend image
echo ""
echo "Building frontend image..."
docker build -t claude-agent-frontend:latest "$PROJECT_DIR/frontend"

# Build backend orchestrator image
echo ""
echo "Building backend orchestrator image..."
docker build -t claude-agent-orchestrator:latest "$PROJECT_DIR/backend"

# Verify images
echo ""
echo "=== Built images ==="
docker images | grep -E "claude-agent-(frontend|orchestrator)"

echo ""
echo "Images built successfully!"
echo "You can now deploy with: ./scripts/deploy.sh"
