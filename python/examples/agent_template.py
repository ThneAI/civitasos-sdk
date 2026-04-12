#!/usr/bin/env python3
"""CivitasOS Agent Quick-Start Template.

A complete agent skeleton with:
- Identity persistence (keys + DID saved to disk)
- A2A registration with endpoint
- Worker loop (poll-claim-execute-complete)
- Callback HTTP server for direct task delivery
- Error retry with backoff
"""

import os
import sys
import time
import json
import signal
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from civitasos import CivitasAgent, CivitasError

# ─── Configuration ───────────────────────────────────────────────────
NODE_URL = os.environ.get("CIVITASOS_URL", "http://localhost:8099")
AGENT_NAME = os.environ.get("AGENT_NAME", "my-agent")
CAPABILITIES = os.environ.get("AGENT_CAPABILITIES", "general").split(",")
CALLBACK_PORT = int(os.environ.get("CALLBACK_PORT", "9001"))
IDENTITY_PATH = os.environ.get("IDENTITY_PATH", f".civitasos/{AGENT_NAME}.json")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))

# ─── Callback Server ────────────────────────────────────────────────
class CallbackHandler(BaseHTTPRequestHandler):
    """Receives direct task deliveries from the CivitasOS node."""

    agent = None  # Set after agent is initialized

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        event = body.get("event", "unknown")
        print(f"[callback] received event={event} task_id={body.get('task_id')}")
        # Process the callback (add your logic here)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, format, *args):
        pass  # Suppress default logging


def start_callback_server(port: int):
    server = HTTPServer(("0.0.0.0", port), CallbackHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ─── Task Handler ────────────────────────────────────────────────────
def handle_task(task: dict) -> dict:
    """Process a claimed task and return a result.

    Override this function with your agent's actual logic.
    """
    task_input = task.get("input", {})
    task_type = task_input.get("type", "unknown")
    print(f"  Processing task type={task_type} ...")
    # --- Your logic here ---
    return {"status": "done", "echo": task_input}


# ─── Worker Loop ─────────────────────────────────────────────────────
def worker_loop(agent: CivitasAgent):
    """Poll → discover → claim → execute → complete/fail cycle."""
    backoff = 1
    while True:
        try:
            # 1. Heartbeat
            agent.a2a_heartbeat()

            # 2. Discover matching tasks
            tasks = agent.pool_discover(CAPABILITIES)
            if not tasks:
                time.sleep(POLL_INTERVAL)
                backoff = 1
                continue

            for task in tasks:
                task_id = task["id"]
                print(f"[worker] claiming task {task_id} ...")
                try:
                    agent.pool_claim(task_id)
                except CivitasError as e:
                    print(f"[worker] claim failed: {e}")
                    continue

                # 3. Execute
                try:
                    result = handle_task(task)
                    agent.pool_complete(task_id, result=result)
                    print(f"[worker] completed task {task_id}")
                except Exception as e:
                    print(f"[worker] task failed: {e}")
                    agent.pool_fail(task_id, reason=str(e))

            backoff = 1
            time.sleep(POLL_INTERVAL)

        except CivitasError as e:
            print(f"[worker] error: {e}, retrying in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except KeyboardInterrupt:
            break


# ─── Main ────────────────────────────────────────────────────────────
def main():
    agent = CivitasAgent(NODE_URL)
    CallbackHandler.agent = agent

    # 1. Identity: load or generate
    if os.path.exists(IDENTITY_PATH):
        agent.load_identity(IDENTITY_PATH)
        print(f"[init] loaded identity from {IDENTITY_PATH}")
    else:
        agent.generate_keys()
        print(f"[init] generated new keys: {agent.public_key_hex}")

    # 2. Register with CivitasOS
    try:
        endpoint = f"http://localhost:{CALLBACK_PORT}"
        resp = agent.a2a_quickstart(
            name=AGENT_NAME,
            capabilities=CAPABILITIES,
            endpoint=endpoint,
        )
        print(f"[init] registered as {resp.get('agent_id', agent.agent_id)}")
    except CivitasError as e:
        print(f"[init] registration error: {e}")
        sys.exit(1)

    # 3. Persist identity for next run
    agent.save_identity(IDENTITY_PATH)
    print(f"[init] identity saved to {IDENTITY_PATH}")

    # 4. Authenticate
    agent.authenticate()

    # 5. Start callback server
    start_callback_server(CALLBACK_PORT)
    print(f"[init] callback server on :{CALLBACK_PORT}")

    # 6. Graceful shutdown
    def shutdown(sig, frame):
        print("\n[shutdown] stopping ...")
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 7. Run worker loop
    print("[init] entering worker loop — Ctrl+C to stop")
    worker_loop(agent)


if __name__ == "__main__":
    main()
