"""Task pool mixin: pool, webhooks, subtask rules, auto-claim, worker pattern."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .models import CivitasError


class PoolMixin:
    """Task pool, webhooks, subtask rules, auto-claim, worker decorator pattern."""

    def pool_post(
        self,
        required_capability: str,
        input_data: Any = None,
        reward: int = 100,
        min_reputation: float = 0.0,
        deadline_secs: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Post a task to the shared pool for any capable agent to claim."""
        body: Dict[str, Any] = {
            "requester": self._agent_id or "anonymous",
            "required_capability": required_capability,
            "input": input_data or {},
            "reward": reward,
            "min_reputation": min_reputation,
        }
        if deadline_secs is not None:
            body["deadline_secs"] = deadline_secs
        return self._a2a_request("POST", "/pool/post", body)

    def pool_discover(
        self,
        capability: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        min_reputation: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Discover open pool tasks matching capabilities.

        Searches the task pool for claimable tasks. To discover *agents*
        by capability, use ``a2a_discover()`` instead.
        """
        caps: List[str] = capabilities or ([capability] if capability else [])
        aid = self._agent_id or "anonymous"
        return self._a2a_request("POST", "/pool/discover", {
            "agent_id": aid,
            "capabilities": caps,
        })

    def pool_claim(self, task_id: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Claim a pool task for execution."""
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified")
        return self._a2a_request("POST", "/pool/claim", {
            "task_id": task_id,
            "agent_id": aid,
        })

    def pool_complete(self, task_id: str) -> Dict[str, Any]:
        """Mark a pool task as completed."""
        return self._a2a_request("POST", f"/pool/complete/{task_id}")

    def pool_fail(self, task_id: str) -> Dict[str, Any]:
        """Mark a pool task as failed."""
        return self._a2a_request("POST", f"/pool/fail/{task_id}")

    def pool_list(self) -> List[Dict[str, Any]]:
        """List all tasks in the pool."""
        return self._a2a_request("GET", "/pool/tasks")

    # ─── Webhooks ────────────────────────────────────────────────────

    def webhook_register(
        self,
        callback_url: str,
        events: Optional[List[str]] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register a webhook subscription for A2A task events.

        Args:
            callback_url: URL to receive webhook POST notifications
            events: List of event types to subscribe to. Defaults to all events.
                Valid events: task.posted, task.claimed, task.completed,
                task.failed, task.settled, agent.registered
            agent_id: Agent registering the webhook (defaults to self)
        """
        return self._a2a_request("POST", "/webhooks/register", {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "callback_url": callback_url,
            "events": events or [
                "task.posted", "task.claimed", "task.completed",
                "task.failed", "task.settled",
            ],
        })

    def webhook_unregister(self, subscription_id: str) -> Dict[str, Any]:
        """Unregister a webhook subscription."""
        return self._a2a_request("POST", "/webhooks/unregister", {
            "subscription_id": subscription_id,
        })

    def webhook_list(self) -> Dict[str, Any]:
        """List all active webhook subscriptions."""
        return self._a2a_request("GET", "/webhooks/list")

    # ─── Subtask Rules ───────────────────────────────────────────────

    def subtask_rule_register(
        self,
        trigger_capability: str,
        subtask_capability: str,
        description: str,
        trigger_on: str = "success",
        reward: int = 100,
    ) -> Dict[str, Any]:
        """Register a dynamic subtask generation rule.

        When a task with trigger_capability is settled, a new subtask
        requiring subtask_capability is automatically created.

        Args:
            trigger_capability: Source capability that triggers generation
            subtask_capability: Capability required for the generated subtask
            description: Description of the subtask
            trigger_on: When to trigger — "success", "failure", or "always"
            reward: Reward for the generated subtask
        """
        return self._a2a_request("POST", "/subtask-rules", {
            "trigger_capability": trigger_capability,
            "subtask_capability": subtask_capability,
            "description": description,
            "trigger_on": trigger_on,
            "reward": reward,
        })

    def subtask_rule_list(self) -> Dict[str, Any]:
        """List all subtask generation rules."""
        return self._a2a_request("GET", "/subtask-rules")

    def subtask_rule_delete(self, rule_id: int) -> Dict[str, Any]:
        """Delete a subtask generation rule by index."""
        return self._a2a_request("DELETE", f"/subtask-rules/{rule_id}")

    # ─── Auto-Claim ──────────────────────────────────────────────────

    def auto_claim_register(
        self,
        capabilities: List[str],
        agent_id: Optional[str] = None,
        min_reward: Optional[int] = None,
        max_reward: Optional[int] = None,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """Register auto-claim preferences for an agent.

        When a new task is posted matching one of the listed capabilities,
        the agent will automatically claim it (if concurrency allows and
        reward is within range).

        Args:
            capabilities: Capabilities the agent wants to auto-claim
            agent_id: Agent ID (defaults to self)
            min_reward: Minimum reward threshold
            max_reward: Maximum reward threshold
            enabled: Whether auto-claim is active
        """
        body: Dict[str, Any] = {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "capabilities": capabilities,
            "enabled": enabled,
        }
        if min_reward is not None:
            body["min_reward"] = min_reward
        if max_reward is not None:
            body["max_reward"] = max_reward
        return self._a2a_request("POST", "/auto-claim/register", body)

    def auto_claim_list(self) -> Dict[str, Any]:
        """List all auto-claim preferences."""
        return self._a2a_request("GET", "/auto-claim/list")

    def auto_claim_delete(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Remove auto-claim preferences for an agent."""
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified")
        return self._a2a_request("DELETE", f"/auto-claim/{aid}")

    # ─── Worker Decorator Pattern ────────────────────────────────────

    def task_handler(self, capability: str):
        """Decorator to register a function as a handler for pool tasks.

        Usage::

            agent = CivitasAgent("http://localhost:8099")
            agent.generate_keys()
            agent.register("translator", "Translator", ["translation"])
            agent.authenticate()

            @agent.task_handler("translation")
            def handle_translation(task):
                text = task["input"].get("text", "")
                return {"translated": text.upper()}

            agent.start_worker()   # blocks, polling for tasks
        """
        def decorator(fn: Callable):
            self._task_handlers[capability] = fn
            return fn
        return decorator

    def start_worker(self, poll_interval: float = 5.0, daemon: bool = False):
        """Start polling for pool tasks and dispatching to registered handlers.

        Args:
            poll_interval: Seconds between discover polls
            daemon: If True, run in a background thread and return immediately.
        """
        if not self._task_handlers:
            raise CivitasError("No task handlers registered — use @agent.task_handler(capability)")
        if not self._agent_id:
            raise CivitasError("Agent not registered — call register() first")

        self._worker_running = True
        if daemon:
            t = threading.Thread(target=self._worker_loop, args=(poll_interval,), daemon=True)
            t.start()
            return t
        else:
            self._worker_loop(poll_interval)

    def stop_worker(self):
        """Signal the worker loop to stop after the current poll cycle."""
        self._worker_running = False

    def _worker_loop(self, poll_interval: float):
        """Internal: poll → discover → claim → dispatch → complete/fail."""
        caps = list(self._task_handlers.keys())
        while self._worker_running:
            try:
                result = self.pool_discover(capabilities=caps)
                if isinstance(result, dict):
                    tasks = result.get("tasks", [])
                else:
                    tasks = result if isinstance(result, list) else []
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    task_id = task.get("task_id") or task.get("id")
                    cap = task.get("required_capability", "")
                    handler = self._task_handlers.get(cap)
                    if not task_id or not handler:
                        continue
                    try:
                        self.pool_claim(task_id)
                        result = handler(task)
                        self.pool_complete(task_id)
                    except Exception:
                        try:
                            self.pool_fail(task_id)
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(poll_interval)
