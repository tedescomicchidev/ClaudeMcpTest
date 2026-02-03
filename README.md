# Claude Agent Platform

A Kubernetes-based platform for orchestrating multiple Claude AI agents using the Claude Agent SDK. Run on Minikube on macOS.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Minikube Cluster                         │
│                                                                   │
│  ┌─────────────────────────┐    ┌────────────────────────────┐  │
│  │   Frontend Namespace    │    │    Backend Namespace        │  │
│  │                         │    │                             │  │
│  │  ┌───────────────────┐  │    │  ┌───────────────────────┐  │  │
│  │  │  Frontend App     │  │───▶│  │  Orchestrator (x2)    │  │  │
│  │  │  (Flask/Python)   │  │    │  │  Load Balanced        │  │  │
│  │  │  Port: 30080      │  │    │  │  (Claude Agent SDK)   │  │  │
│  │  └───────────────────┘  │    │  └───────────┬───────────┘  │  │
│  │                         │    │              │               │  │
│  └─────────────────────────┘    │              ▼               │  │
│                                 │  ┌───────────────────────┐  │  │
│                                 │  │  claude-code-docker   │  │  │
│                                 │  │  (MCP instances)      │  │  │
│                                 │  └───────────────────────┘  │  │
│                                 │                             │  │
│                                 └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### Frontend (frontend namespace)
- Python Flask web application
- Simple UI for entering prompts and selecting agent count (1-10)
- Calls backend orchestrator API on "Go" button click
- Exposed via NodePort on port 30080

### Backend (backend namespace)
- **Orchestrator**: Python application using Claude Agent SDK
  - Load balanced with 2 replicas always running
  - Receives requests from frontend
  - Spawns multiple claude-code-docker instances based on user selection
  - PodDisruptionBudget ensures minimum availability

- **claude-code-docker**: MCP instances
  - Spawned on-demand by the orchestrator
  - Run as containers via Docker socket

## Prerequisites

- macOS with Homebrew installed
- Docker Desktop (or Docker)
- Minikube
- kubectl
- Anthropic API Key

### Install Prerequisites

```bash
# Install Minikube
brew install minikube

# Install kubectl
brew install kubectl

# Start Minikube with Docker driver
minikube start --driver=docker
```

## Quick Start

### 1. Clone and Setup

```bash
cd ClaudeMcpTest
```

### 2. Build Docker Images

Build the images directly in Minikube's Docker daemon:

```bash
./scripts/build-images.sh
```

### 3. Configure Anthropic API Key

Before deploying, set your Anthropic API key:

```bash
# Option 1: Edit the secret file directly
# Edit k8s/backend/secret.yaml and replace "your-anthropic-api-key-here"

# Option 2: Create secret manually after deploying
kubectl create secret generic anthropic-secrets \
  --from-literal=ANTHROPIC_API_KEY=your-actual-key \
  -n backend --dry-run=client -o yaml | kubectl apply -f -
```

### 4. Deploy to Minikube

```bash
./scripts/deploy.sh
```

### 5. Access the Application

Get the frontend URL:

```bash
minikube service frontend-service -n frontend --url
```

Or access directly at:
```
http://$(minikube ip):30080
```

## Usage

1. Open the frontend URL in your browser
2. Enter a prompt describing the task for the AI agents
3. Select the number of agents (1-10) to work on the prompt
4. Click "Go - Start Agents"
5. View results as they come in from each agent

## Project Structure

```
ClaudeMcpTest/
├── frontend/                    # Frontend Flask application
│   ├── app.py                   # Main Flask app
│   ├── templates/
│   │   └── index.html          # Web UI
│   ├── requirements.txt
│   └── Dockerfile
├── backend/                     # Backend orchestrator
│   ├── orchestrator.py         # Claude Agent SDK orchestrator
│   ├── requirements.txt
│   └── Dockerfile
├── k8s/                        # Kubernetes manifests
│   ├── namespaces/
│   │   ├── frontend-namespace.yaml
│   │   └── backend-namespace.yaml
│   ├── frontend/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   └── backend/
│       ├── configmap.yaml
│       ├── secret.yaml
│       ├── deployment.yaml
│       ├── service.yaml
│       └── pdb.yaml
├── scripts/                    # Helper scripts
│   ├── build-images.sh
│   ├── deploy.sh
│   └── cleanup.sh
└── README.md
```

## Configuration

### Environment Variables

#### Frontend
| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_URL` | `http://orchestrator-service.backend.svc.cluster.local:8080` | Backend orchestrator URL |
| `PORT` | `5000` | Flask server port |
| `FLASK_DEBUG` | `false` | Enable debug mode |

#### Backend Orchestrator
| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | (required) | Your Anthropic API key |
| `WORKSPACE_PATH` | `/workspace` | Workspace directory for agents |
| `CLAUDE_MCP_IMAGE` | `claude-mcp:latest` | Docker image for claude-code-docker |
| `PORT` | `8080` | Flask server port |

## API Endpoints

### Frontend
- `GET /` - Web UI
- `POST /api/submit` - Submit prompt to orchestrator
- `POST /api/submit/stream` - Submit with streaming response
- `GET /health` - Health check
- `GET /ready` - Readiness check

### Backend Orchestrator
- `GET /` - API info
- `POST /api/orchestrate` - Execute prompt with multiple agents
- `POST /api/orchestrate/stream` - Execute with streaming
- `GET /health` - Health check
- `GET /ready` - Readiness check

## Troubleshooting

### Check Pod Status

```bash
# Frontend pods
kubectl get pods -n frontend

# Backend pods
kubectl get pods -n backend

# Pod logs
kubectl logs -n backend deployment/orchestrator
kubectl logs -n frontend deployment/frontend
```

### Common Issues

**Images not found:**
```bash
# Ensure you're using Minikube's Docker daemon
eval $(minikube docker-env)
docker images | grep claude-agent
```

**API key not configured:**
```bash
# Check if secret exists
kubectl get secret anthropic-secrets -n backend

# Update the secret
kubectl create secret generic anthropic-secrets \
  --from-literal=ANTHROPIC_API_KEY=your-key \
  -n backend --dry-run=client -o yaml | kubectl apply -f -

# Restart orchestrator to pick up new secret
kubectl rollout restart deployment/orchestrator -n backend
```

**Cannot access frontend:**
```bash
# Check service status
kubectl get svc -n frontend

# Use minikube tunnel for LoadBalancer services
minikube tunnel
```

## Cleanup

Remove all resources from the cluster:

```bash
./scripts/cleanup.sh
```

## Development

### Local Testing (without Kubernetes)

**Frontend:**
```bash
cd frontend
pip install -r requirements.txt
BACKEND_URL=http://localhost:8080 python app.py
```

**Backend:**
```bash
cd backend
pip install -r requirements.txt
ANTHROPIC_API_KEY=your-key python orchestrator.py
```

### Rebuild and Redeploy

```bash
./scripts/build-images.sh
kubectl rollout restart deployment/frontend -n frontend
kubectl rollout restart deployment/orchestrator -n backend
```

## License

MIT License
