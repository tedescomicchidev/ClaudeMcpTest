"""
Frontend Flask application for Claude Agent orchestration.
Provides a simple web interface to submit prompts and select agent count.
"""
import os
import requests
from flask import Flask, render_template, request, jsonify, Response
import json

app = Flask(__name__)

# Backend orchestrator URL (Kubernetes service)
BACKEND_URL = os.getenv("BACKEND_URL", "http://orchestrator-service.backend.svc.cluster.local:8080")


@app.route("/")
def index():
    """Render the main page with prompt input and agent selector."""
    return render_template("index.html")


@app.route("/api/submit", methods=["POST"])
def submit_prompt():
    """
    Submit a prompt to the backend orchestrator.
    Expects JSON with 'prompt' and 'agent_count' fields.
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    prompt = data.get("prompt", "").strip()
    agent_count = data.get("agent_count", 1)

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    try:
        agent_count = int(agent_count)
        if agent_count < 1 or agent_count > 10:
            return jsonify({"error": "Agent count must be between 1 and 10"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid agent count"}), 400

    # Forward request to backend orchestrator
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/orchestrate",
            json={"prompt": prompt, "agent_count": agent_count},
            timeout=300  # 5 minute timeout for long-running tasks
        )
        return jsonify(response.json()), response.status_code
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request timed out"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to backend orchestrator"}), 503
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


@app.route("/api/submit/stream", methods=["POST"])
def submit_prompt_stream():
    """
    Submit a prompt to the backend orchestrator with streaming response.
    Returns Server-Sent Events (SSE) for real-time updates.
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    prompt = data.get("prompt", "").strip()
    agent_count = data.get("agent_count", 1)

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    try:
        agent_count = int(agent_count)
        if agent_count < 1 or agent_count > 10:
            return jsonify({"error": "Agent count must be between 1 and 10"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid agent count"}), 400

    def generate():
        try:
            response = requests.post(
                f"{BACKEND_URL}/api/orchestrate/stream",
                json={"prompt": prompt, "agent_count": agent_count},
                stream=True,
                timeout=300
            )

            for line in response.iter_lines():
                if line:
                    yield f"data: {line.decode('utf-8')}\n\n"

        except requests.exceptions.Timeout:
            yield f"data: {json.dumps({'error': 'Request timed out'})}\n\n"
        except requests.exceptions.ConnectionError:
            yield f"data: {json.dumps({'error': 'Could not connect to backend'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/health")
def health():
    """Health check endpoint for Kubernetes probes."""
    return jsonify({"status": "healthy"}), 200


@app.route("/ready")
def ready():
    """Readiness check endpoint for Kubernetes probes."""
    # Optionally check backend connectivity
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=5)
        backend_healthy = response.status_code == 200
    except Exception:
        backend_healthy = False

    return jsonify({
        "status": "ready",
        "backend_connected": backend_healthy
    }), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
