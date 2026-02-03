"""
Backend Orchestrator for Claude Agent SDK.
Manages multiple claude-code-docker instances based on user requests.
"""
import asyncio
import os
import json
import logging
from typing import List, Dict, Any
from dataclasses import dataclass, asdict
from flask import Flask, request, jsonify, Response
import threading
from queue import Queue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
WORKSPACE_PATH = os.getenv("WORKSPACE_PATH", "/workspace")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MCP_IMAGE = os.getenv("CLAUDE_MCP_IMAGE", "claude-mcp")
DOCKER_SOCKET = os.getenv("DOCKER_SOCKET", "/var/run/docker.sock")


@dataclass
class AgentResult:
    """Result from a single agent execution."""
    agent_id: int
    status: str  # "success", "error", "running"
    message: str
    details: Dict[str, Any] = None

    def to_dict(self):
        return asdict(self)


async def run_single_agent(agent_id: int, prompt: str, results_queue: Queue) -> AgentResult:
    """
    Run a single Claude agent with the given prompt.
    Uses claude-code-docker via MCP.
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, TextMessage

        logger.info(f"Agent {agent_id}: Starting execution")

        # Configure MCP server for this agent
        # In Kubernetes, we'll use a sidecar or separate pod for claude-code-docker
        options = ClaudeAgentOptions(
            mcp_servers={
                "claude-code-docker": {
                    "type": "stdio",
                    "command": "docker",
                    "args": [
                        "run", "-i", "--rm",
                        "-v", f"{WORKSPACE_PATH}:/workspace",
                        CLAUDE_MCP_IMAGE,
                        "claude", "mcp", "serve"
                    ],
                    "env": {
                        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY
                    }
                }
            },
            allowed_tools=["mcp__claude-code-docker__*"]
        )

        collected_messages = []

        async for message in query(
            prompt=prompt,
            options=options
        ):
            logger.info(f"Agent {agent_id}: Message type: {type(message).__name__}")

            if isinstance(message, ResultMessage):
                if message.subtype == "success":
                    result = AgentResult(
                        agent_id=agent_id,
                        status="success",
                        message=f"Task completed successfully",
                        details={"result": message.result}
                    )
                    logger.info(f"Agent {agent_id}: Success - {message.result}")
                elif message.subtype == "error":
                    result = AgentResult(
                        agent_id=agent_id,
                        status="error",
                        message=f"Task failed: {message.result}",
                        details={"error": message.result}
                    )
                    logger.error(f"Agent {agent_id}: Error - {message.result}")
                else:
                    result = AgentResult(
                        agent_id=agent_id,
                        status="unknown",
                        message=str(message.result),
                        details={"subtype": message.subtype}
                    )

                results_queue.put(result)
                return result
            elif isinstance(message, TextMessage):
                collected_messages.append(str(message))

        # If we get here without a ResultMessage
        result = AgentResult(
            agent_id=agent_id,
            status="success",
            message="Task completed",
            details={"messages": collected_messages}
        )
        results_queue.put(result)
        return result

    except ImportError as e:
        logger.error(f"Agent {agent_id}: SDK import error - {e}")
        result = AgentResult(
            agent_id=agent_id,
            status="error",
            message=f"Claude Agent SDK not available: {e}",
            details={"error_type": "import_error"}
        )
        results_queue.put(result)
        return result

    except Exception as e:
        logger.error(f"Agent {agent_id}: Unexpected error - {e}")
        result = AgentResult(
            agent_id=agent_id,
            status="error",
            message=f"Unexpected error: {str(e)}",
            details={"error_type": type(e).__name__}
        )
        results_queue.put(result)
        return result


async def orchestrate_agents(prompt: str, agent_count: int) -> List[AgentResult]:
    """
    Orchestrate multiple agents to work on the same prompt.
    Runs agents concurrently and collects results.
    """
    logger.info(f"Orchestrating {agent_count} agents for prompt: {prompt[:100]}...")

    results_queue = Queue()
    tasks = []

    for i in range(agent_count):
        task = asyncio.create_task(run_single_agent(i + 1, prompt, results_queue))
        tasks.append(task)

    # Wait for all agents to complete
    await asyncio.gather(*tasks, return_exceptions=True)

    # Collect results from queue
    results = []
    while not results_queue.empty():
        results.append(results_queue.get())

    # Sort by agent_id
    results.sort(key=lambda r: r.agent_id)

    return results


def run_async(coro):
    """Run async coroutine in a new event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.route("/api/orchestrate", methods=["POST"])
def orchestrate():
    """
    Main orchestration endpoint.
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

    # Check for API key
    if not ANTHROPIC_API_KEY:
        return jsonify({
            "error": "ANTHROPIC_API_KEY not configured",
            "hint": "Set the ANTHROPIC_API_KEY environment variable"
        }), 500

    try:
        # Run the orchestration
        results = run_async(orchestrate_agents(prompt, agent_count))

        return jsonify({
            "status": "completed",
            "prompt": prompt,
            "agent_count": agent_count,
            "results": [r.to_dict() for r in results]
        }), 200

    except Exception as e:
        logger.error(f"Orchestration failed: {e}")
        return jsonify({
            "error": f"Orchestration failed: {str(e)}",
            "status": "failed"
        }), 500


@app.route("/api/orchestrate/stream", methods=["POST"])
def orchestrate_stream():
    """
    Streaming orchestration endpoint.
    Returns Server-Sent Events for real-time updates.
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
        """Generator for SSE stream."""
        try:
            results_queue = Queue()

            # Start agents in a thread
            def run_agents():
                run_async(orchestrate_agents(prompt, agent_count))

            thread = threading.Thread(target=run_agents)
            thread.start()

            # Stream initial event
            yield json.dumps({
                "type": "start",
                "agent_count": agent_count,
                "prompt": prompt[:100]
            }) + "\n"

            # Wait for results and stream them
            completed = 0
            while completed < agent_count and thread.is_alive():
                try:
                    result = results_queue.get(timeout=1)
                    yield json.dumps({
                        "type": "agent_result",
                        "data": result.to_dict()
                    }) + "\n"
                    completed += 1
                except Exception:
                    pass

            # Wait for thread to complete
            thread.join(timeout=60)

            # Drain any remaining results
            while not results_queue.empty():
                result = results_queue.get()
                yield json.dumps({
                    "type": "agent_result",
                    "data": result.to_dict()
                }) + "\n"

            yield json.dumps({
                "type": "complete",
                "total_agents": agent_count
            }) + "\n"

        except Exception as e:
            yield json.dumps({
                "type": "error",
                "error": str(e)
            }) + "\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/health")
def health():
    """Health check endpoint for Kubernetes probes."""
    return jsonify({
        "status": "healthy",
        "api_key_configured": bool(ANTHROPIC_API_KEY)
    }), 200


@app.route("/ready")
def ready():
    """Readiness check endpoint for Kubernetes probes."""
    # Check if we can import the SDK
    try:
        from claude_agent_sdk import query
        sdk_available = True
    except ImportError:
        sdk_available = False

    return jsonify({
        "status": "ready",
        "sdk_available": sdk_available,
        "api_key_configured": bool(ANTHROPIC_API_KEY)
    }), 200


@app.route("/")
def index():
    """Root endpoint with API info."""
    return jsonify({
        "service": "Claude Agent Orchestrator",
        "version": "1.0.0",
        "endpoints": {
            "POST /api/orchestrate": "Run multiple agents on a prompt",
            "POST /api/orchestrate/stream": "Run agents with streaming results",
            "GET /health": "Health check",
            "GET /ready": "Readiness check"
        }
    }), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    logger.info(f"Starting orchestrator on port {port}")
    logger.info(f"API Key configured: {bool(ANTHROPIC_API_KEY)}")
    logger.info(f"Workspace path: {WORKSPACE_PATH}")
    logger.info(f"Claude MCP image: {CLAUDE_MCP_IMAGE}")

    app.run(host="0.0.0.0", port=port, debug=debug)
